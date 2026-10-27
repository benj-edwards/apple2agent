;===============================================================================
; DIAG.SYSTEM - agent boot disk diagnostic for real hardware
;
; One boot answers "does this machine get the right bytes off this disk?":
;   1. machine: MACHID, ROM ID, IIgs, ProDOS version, boot unit, slot ROM
;      IDs, memory soft switches
;   2. every block of the disk read with READ_BLOCK and checked against a
;      table of checksums made when the disk was built ('.' good, 'X' wrong
;      data, 'E' read error, 'D' this program's own blocks)
;   3. AGENT.SYSTEM loaded to $2000 exactly like ProDOS's boot launcher
;      (OPEN, GET_EOF, READ, CLOSE) and its checksum verified in memory
; then RETURN starts the agent, ESC goes to the monitor.
;
; ProDOS loads this at $2000; the loader copies the rest to $1000 so the
; agent can be read into $2000 like a normal boot.
; tools/make_diag_disk.py fills in the checksum table (after "DIAGTBL!").
;===============================================================================

        .setcpu "6502"

        .import __MAIN_LOAD__, __MAIN_RUN__, __MAIN_SIZE__

MLI             = $BF00
DEVNUM          = $BF30
MACHID          = $BF98
KVERSION        = $BFFF

HOME            = $FC58
COUT            = $FDED
CROUT           = $FD8E
PRBYTE          = $FDDA
RDKEY           = $FD0C
IDROUTINE       = $FE1F         ; IIgs: clears carry
MONZ            = $FF69

BLKBUF          = $0C00         ; 512-byte READ_BLOCK buffer
IOBUF           = $1C00         ; 1K OPEN buffer
AGENT_ADDR      = $2000
NUM_BLOCKS      = 280

ptr             = $06           ; 2 bytes
cnt             = $08           ; 2 bytes
s1              = $FA           ; checksum bytes
s2              = $FB
msgp            = $FC           ; 2 bytes
tmp             = $FE

;-------------------------------------------------------------------------------
        .segment "SYSLOAD"      ; runs where ProDOS put it ($2000)

        cld
        ldx #>(__MAIN_SIZE__ + 255)
        ldy #0
@page:  lda __MAIN_LOAD__,y
@dst:   sta __MAIN_RUN__,y
        iny
        bne @page
        inc @page+2
        inc @dst+2
        dex
        bne @page
        jmp main

;-------------------------------------------------------------------------------
        .segment "MAIN"

main:
        jsr HOME
        jsr print
        .byte "AGENT DISK DIAGNOSTIC", 13, 13, 0

        ; --- machine ---------------------------------------------------------
        jsr print
        .byte "MACHID ", 0
        lda MACHID
        jsr PRBYTE
        jsr print
        .byte " ROM ", 0
        lda $FBB3
        jsr PRBYTE
        lda $FBC0
        jsr PRBYTE
        sec
        jsr IDROUTINE
        bcs @not_gs
        jsr print
        .byte " IIGS", 0
@not_gs:
        jsr print
        .byte " PRODOS ", 0
        lda KVERSION
        jsr PRBYTE
        jsr print
        .byte " UNIT ", 0
        lda DEVNUM
        jsr PRBYTE
        jsr CROUT

        ; slot ROM bytes $Cn05 $Cn07 (ProDOS/Pascal/SmartPort IDs), 4 per line
        ldx #1
@slot:  txa
        ora #$B0                ; "1".."7"
        jsr COUT
        lda #':' | $80
        jsr COUT
        txa
        ora #$C0
        sta ptr+1
        lda #$05
        sta ptr
        ldy #0
        lda (ptr),y
        jsr PRBYTE
        ldy #2
        lda (ptr),y
        jsr PRBYTE
        lda #' ' | $80
        jsr COUT
        cpx #4
        bne :+
        jsr CROUT
:       inx
        cpx #8
        bne @slot
        lda $CFFF               ; release any slot's $C800 ROM
        jsr CROUT
        jsr show_switches

        ; --- every block ----------------------------------------------------
        jsr print
        .byte "BLOCKS ('.' OK  X BAD  E ERR  D DIAG)", 13, 0
        lda #0
        sta blk
        sta blk+1
        sta nbad
        sta nerr
        lda #$FF                ; hi $FF = no bad block yet
        sta first_bad+1
@block: lda DEVNUM
        sta rb_unit
        lda blk
        sta rb_blk
        lda blk+1
        sta rb_blk+1
        jsr MLI
        .byte $80               ; READ_BLOCK
        .word rb_parms
        bcc @read_ok
        sta last_err
        inc nerr
        lda #'E' | $80
        jmp @mark
@read_ok:
        lda #<BLKBUF
        sta ptr
        lda #>BLKBUF
        sta ptr+1
        lda #<512
        sta cnt
        lda #>512
        sta cnt+1
        jsr checksum
        ; this program's own blocks change when the table is filled in
        lda blk+1
        cmp skip_lo+1
        bcc @check
        bne :+
        lda blk
        cmp skip_lo
        bcc @check
:       lda skip_hi+1
        cmp blk+1
        bcc @check
        bne @diag
        lda skip_hi
        cmp blk
        bcc @check
@diag:  lda #'D' | $80
        bne @mark
@check: lda blk                 ; ptr = table + blk*2
        asl
        sta ptr
        lda blk+1
        rol
        sta ptr+1
        lda ptr
        clc
        adc #<table
        sta ptr
        lda ptr+1
        adc #>table
        sta ptr+1
        ldy #0
        lda (ptr),y
        cmp s1
        bne @bad
        iny
        lda (ptr),y
        cmp s2
        bne @bad
        lda #'.' | $80
        bne @mark
@bad:   inc nbad
        lda first_bad+1
        cmp #$FF
        bne @not_first
        lda blk                 ; remember the first bad block: number,
        sta first_bad           ; what it read as, what it should be
        lda blk+1
        sta first_bad+1
        lda s1
        sta fb_got
        lda s2
        sta fb_got+1
        ldy #0
        lda (ptr),y
        sta fb_want
        iny
        lda (ptr),y
        sta fb_want+1
        ldx #7
:       lda BLKBUF,x
        sta fb_bytes,x
        dex
        bpl :-
@not_first:
        lda #'X' | $80
@mark:  jsr COUT
        inc blk
        bne :+
        inc blk+1
:       lda blk
        cmp #<NUM_BLOCKS
        bne @more
        lda blk+1
        cmp #>NUM_BLOCKS
        beq @blocks_done
@more:  jmp @block

@blocks_done:
        jsr print
        .byte "BAD ", 0
        lda nbad
        jsr PRBYTE
        jsr print
        .byte " ERRORS ", 0
        lda nerr
        jsr PRBYTE
        lda nerr
        beq :+
        jsr print
        .byte " LAST $", 0
        lda last_err
        jsr PRBYTE
:       jsr CROUT
        lda first_bad+1
        cmp #$FF
        beq @load
        jsr print
        .byte "FIRST BAD BLOCK ", 0
        lda first_bad+1
        jsr PRBYTE
        lda first_bad
        jsr PRBYTE
        jsr print
        .byte " GOT ", 0
        lda fb_got
        jsr PRBYTE
        lda fb_got+1
        jsr PRBYTE
        jsr print
        .byte " WANT ", 0
        lda fb_want
        jsr PRBYTE
        lda fb_want+1
        jsr PRBYTE
        jsr CROUT
        jsr print
        .byte " READ AS:", 0
        ldx #0
:       lda #' ' | $80
        jsr COUT
        lda fb_bytes,x
        jsr PRBYTE
        inx
        cpx #8
        bne :-
        jsr CROUT

        ; --- AGENT.SYSTEM, the way ProDOS's launcher loads it ------------------
@load:  jsr print
        .byte "LOAD AGENT.SYSTEM: ", 0
        jsr MLI
        .byte $C8               ; OPEN
        .word open_parms
        bcc :+
        jsr print
        .byte "OPEN", 0
        jmp @mli_err
:       lda open_ref
        sta eof_ref
        sta read_ref
        sta close_ref
        jsr MLI
        .byte $D1               ; GET_EOF
        .word eof_parms
        bcc :+
        jsr print
        .byte "GET_EOF", 0
        jmp @mli_err
:       lda eof_len
        sta read_len
        lda eof_len+1
        sta read_len+1
        jsr MLI
        .byte $CA               ; READ
        .word read_parms
        bcc :+
        jsr print
        .byte "READ", 0
        jmp @mli_err
:       jsr MLI
        .byte $CC               ; CLOSE
        .word close_parms
        lda read_got+1
        jsr PRBYTE
        lda read_got
        jsr PRBYTE
        jsr print
        .byte " BYTES ", 0
        lda #<AGENT_ADDR
        sta ptr
        lda #>AGENT_ADDR
        sta ptr+1
        lda read_got
        sta cnt
        lda read_got+1
        sta cnt+1
        jsr checksum
        lda s1
        cmp agent_sum
        bne @sum_bad
        lda s2
        cmp agent_sum+1
        bne @sum_bad
        lda read_got
        cmp agent_len
        bne @sum_bad
        lda read_got+1
        cmp agent_len+1
        bne @sum_bad
        jsr print
        .byte "OK", 13, 0
        jmp @loaded
@sum_bad:
        jsr print
        .byte "WRONG", 13, " GOT ", 0
        lda s1
        jsr PRBYTE
        lda s2
        jsr PRBYTE
        jsr print
        .byte " WANT ", 0
        lda agent_sum
        jsr PRBYTE
        lda agent_sum+1
        jsr PRBYTE
        jsr print
        .byte " LEN ", 0
        lda agent_len+1
        jsr PRBYTE
        lda agent_len
        jsr PRBYTE
        jsr CROUT
        jmp @loaded

@mli_err:
        jsr print
        .byte " ERROR $", 0
        jsr PRBYTE
        jsr CROUT

@loaded:
        lda #>AGENT_ADDR
        jsr dump8
        lda #$40
        jsr dump8
        jsr show_switches

@ask:   jsr print
        .byte "RETURN=START AGENT  ESC=MONITOR", 0
@key:   jsr RDKEY
        cmp #$8D
        beq @go
        cmp #$9B
        bne @key
        jsr CROUT
        jmp MONZ
@go:    lda $C082               ; what ProDOS's launcher does
        ldx #$FF
        ldy #12
        jmp AGENT_ADDR

;-------------------------------------------------------------------------------
; Print the zero-terminated string after the JSR (13 = return)
print:  pla
        sta msgp
        pla
        sta msgp+1
@next:  inc msgp
        bne :+
        inc msgp+1
:       ldy #0
        lda (msgp),y
        beq @done
        cmp #13
        bne :+
        jsr CROUT
        jmp @next
:       ora #$80
        jsr COUT
        jmp @next
@done:  lda msgp+1
        pha
        lda msgp
        pha
        rts

; Fletcher-style sum of cnt bytes at ptr -> s1, s2 (mod 256 each)
checksum:
        lda #0
        sta s1
        sta s2
        ldy #0
@loop:  lda cnt
        ora cnt+1
        beq @done
        lda (ptr),y
        clc
        adc s1
        sta s1
        clc
        adc s2
        sta s2
        inc ptr
        bne :+
        inc ptr+1
:       lda cnt
        bne :+
        dec cnt+1
:       dec cnt
        jmp @loop
@done:  rts

; "HH00: " + 8 bytes from page A
dump8:  sta ptr+1
        lda #0
        sta ptr
        lda ptr+1
        jsr PRBYTE
        jsr print
        .byte "00:", 0
        ldy #0
:       lda #' ' | $80
        jsr COUT
        lda (ptr),y
        jsr PRBYTE
        iny
        cpy #8
        bne :-
        jmp CROUT

; Memory switches $C011-$C01F as 0/1 (bit 7 of each)
show_switches:
        jsr print
        .byte "SW 11-1F ", 0
        ldx #$11
:       lda $C000,x
        asl
        lda #'0' | $80
        adc #0
        jsr COUT
        inx
        cpx #$20
        bne :-
        jmp CROUT

;-------------------------------------------------------------------------------
rb_parms:       .byte 3
rb_unit:        .byte 0
                .word BLKBUF
rb_blk:         .word 0

open_parms:     .byte 3
                .word agent_name
                .word IOBUF
open_ref:       .byte 0

eof_parms:      .byte 2
eof_ref:        .byte 0
eof_len:        .byte 0, 0, 0

read_parms:     .byte 4
read_ref:       .byte 0
                .word AGENT_ADDR
read_len:       .word 0
read_got:       .word 0

close_parms:    .byte 1
close_ref:      .byte 0

agent_name:     .byte 12, "AGENT.SYSTEM"

blk:            .word 0
nbad:           .byte 0
nerr:           .byte 0
last_err:       .byte 0
first_bad:      .word 0
fb_got:         .word 0
fb_want:        .word 0
fb_bytes:       .res 8

; Filled in by tools/make_diag_disk.py
                .byte "DIAGTBL!"
skip_lo:        .word 0         ; DIAG.SYSTEM's own blocks: not checked
skip_hi:        .word 0
agent_len:      .word 0         ; AGENT.SYSTEM: length and checksum
agent_sum:      .word 0
table:          .res NUM_BLOCKS * 2     ; s1, s2 per block
