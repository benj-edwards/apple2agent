;===============================================================================
; APPLE II AGENT - Deploy, Launch & Return
;
; Included from agent.s. Lets the proxy stream any program (Applesoft BASIC
; or machine code) into memory, shows a READY prompt, runs it, and gets back
; to the AGENT> prompt afterwards.
;
; Two launch modes, chosen by the proxy (RUN packet):
;
;   RESIDENT  - program lives in $0800-$5FFF, the agent stays in main RAM
;               at $6000+. LOAD packets write straight into main memory.
;
;   EXCHANGE  - (128K //e) program may use $0800-$BEFF. LOAD packets are
;               staged into AUX memory at their final addresses. At launch
;               the program's pages below $6000 are copied aux->main and
;               $6000-$BEFF is swapped main<->aux, so the program lands in
;               main and the agent's image waits in aux. Returning swaps
;               $6000-$BEFF back. Aux below $6000 still holds the pristine
;               staged copy, so /RUN starts the program fresh.
;
; Ways back to the agent (all end up at $03D0):
;   - program executes & (BASIC) or RTS/JMP $03D0 (machine code)
;   - ESC at the ] prompt (KSW hook) after a BASIC program ends
;   - Ctrl-Y from the monitor, Ctrl-Reset (reset vector), BRK (crash)
;
; Page 3 contract ($03C7-$03EB reserved, $0300-$03C6 is the program's):
;   $03C7  crash marker ($C5 = program crashed into BRK)
;   $03C8  BRK entry: sets crash marker, then JMP $03D0
;   $03D0  return entry: JMP agent_reentry (resident)
;                        STA RAMRDON (exchange - next fetch is AUX $03D3,
;                        which holds JMP agent_xreturn)
;   $03D3  KSW hook (main): ESC at the ] prompt returns to the agent
;===============================================================================

;-------------------------------------------------------------------------------
; Constants
;-------------------------------------------------------------------------------
RAMRDOFF        = $C002         ; CPU reads main $0200-$BFFF
RAMRDON         = $C003         ; CPU reads aux $0200-$BFFF
RAMWRTOFF       = $C004         ; CPU writes main $0200-$BFFF
RAMWRTON        = $C005         ; CPU writes aux $0200-$BFFF
SETSTDZP        = $C008         ; Main zero page/stack/LC
SETSLOTCXROM    = $C006         ; Slot ROMs at $C100-$CFFF (normal)
SETINTC3ROM     = $C00A         ; Internal 80-column firmware at $C300
TXTCLR          = $C050         ; Graphics
TXTSET          = $C051         ; Text
MIXCLR          = $C052         ; Full screen
MIXSET          = $C053         ; Mixed text/graphics
LORES           = $C056
HIRES           = $C057
SETAN3          = $C05F         ; AN3 on = no double hi-res

MACHID          = $BF98         ; ProDOS machine ID (bits 5-4: 11 = 128K)

CRASH_MARK      = $03C7         ; $C5 after a BRK crash
BRK_ENTRY       = $03C8         ; BRK vector target (crash)
RETURN_ENTRY    = $03D0         ; Every way back to the agent lands here
KSW_HOOK        = $03D3         ; keyboard hook: ESC typed into GETLN (] or INPUT)
PROMPT          = $33           ; GETLN prompt character
CRASH_MAGIC     = $C5
BRKVEC          = $03F0         ; Monitor BRK vector
RESETVEC        = $03F2         ; Reset vector + power-up byte at $03F4

KEYIN           = $FD1B         ; ROM keyboard input (standard KSW)
APPLESOFT_RUN   = $D566         ; JSR SETPTRS / JMP NEWSTT
MEMSIZ          = $73           ; Applesoft HIMEM
ERRFLG_ZP       = $D8           ; ONERR flag
TRCFLG          = $F2           ; TRACE flag
WNDLFT          = $20
WNDWDTH         = $21
WNDTOP          = $22
WNDBTM          = $23
INVFLG          = $32
PCL             = $3A           ; Monitor saves BRK address here
PCH             = $3B

; Scratch zero page for the launch/return blob (Applesoft's free $06-$07)
XC_PTR          = $06           ; 2 bytes: page pointer (lo always 0)
SWAP_LO_PAGE    = $60           ; EXCHANGE swaps $6000-$BEFF (the agent)
W5100_MODE      = $C084 + $30   ; Uthernet II (slot 3, eth_init_default) mode register
W5100_IND_AI    = $03           ; indirect bus + address auto-increment
SWAP_HI_PAGE    = $BF

; Packet types (proxy -> Apple II)
PKT_LOAD        = $07           ; addr(2) + bytes
PKT_DEPLOY      = $08           ; mode(1) + purpose(1)
PKT_RUN         = $09           ; launch descriptor (see handle_run)
PKT_SHOW        = $0A           ; 0 = text, 1 = HGR preview

; Capability flags added to the INIT packet
CAP_AUX_RAM     = $08           ; 128K //e (aux memory usable for EXCHANGE)
CAP_DEPLOY      = $10           ; Understands DEPLOY/LOAD/RUN/SHOW
A2P_VERSION     = 2

DEPLOY_MAIN     = 0             ; LOAD writes main memory
DEPLOY_AUX      = 1             ; LOAD writes aux memory (EXCHANGE staging)
PURPOSE_PROGRAM = 0
PURPOSE_PREVIEW = 1

RUN_BASIC       = 0
RUN_BINARY      = 1

; RUN descriptor layout (copied from the RUN packet into run_desc)
RD_KIND         = 0             ; RUN_BASIC / RUN_BINARY
RD_START        = 1             ; BASIC: TXTTAB  / binary: entry address
RD_PRGEND       = 3             ; BASIC: end of program text
RD_LOMEM        = 5             ; BASIC: start of variables (VARTAB)
RD_HIMEM        = 7             ; BASIC: HIMEM
RD_MODE         = 9             ; MODE_RESIDENT / MODE_EXCHANGE
RD_LO_PAGE      = 10            ; first page holding program bytes
RD_HI_PAGE      = 11            ; exclusive end page of program bytes
RD_NAME         = 12            ; program name, zero terminated
RUN_DESC_SIZE   = 48

MODE_RESIDENT   = 0
MODE_EXCHANGE   = 1

        .segment "STARTUP"

;===============================================================================
; Startup helpers
;===============================================================================

;-------------------------------------------------------------------------------
; Detect usable aux memory (ProDOS MACHID says 128K)
;-------------------------------------------------------------------------------
detect_aux_ram:
        lda #0
        sta has_aux_ram
        lda MACHID
        and #$30
        cmp #$30
        bne @done
        lda #1
        sta has_aux_ram
@done:
        rts

;-------------------------------------------------------------------------------
; Point $03D0 and the reset/BRK vectors at the resident agent.
; Called at startup and every time the agent comes back.
;-------------------------------------------------------------------------------
install_resident_hooks:
        jsr install_page3_common
        lda #$4C                ; JMP agent_reentry
        sta RETURN_ENTRY
        lda #<agent_reentry
        sta RETURN_ENTRY+1
        lda #>agent_reentry
        sta RETURN_ENTRY+2
        rts

;-------------------------------------------------------------------------------
; KSW hook, BRK stub and vectors - shared by both launch modes.
; Caller writes RETURN_ENTRY afterwards (the copy leaves a hole there).
;-------------------------------------------------------------------------------
install_page3_common:
        ldx #page3_code_end - page3_code - 1
@copy:
        lda page3_code,x
        sta BRK_ENTRY,x
        dex
        bpl @copy

        lda #<BRK_ENTRY
        sta BRKVEC
        lda #>BRK_ENTRY
        sta BRKVEC+1

        lda #<RETURN_ENTRY
        sta RESETVEC
        lda #>RETURN_ENTRY
        sta RESETVEC+1
        eor #$A5                ; power-up byte makes reset warm
        sta RESETVEC+2
        rts

;-------------------------------------------------------------------------------
; Give Applesoft the zero page its cold start ($F128) would have set up.
; AGENT.SYSTEM boots without BASIC.SYSTEM, so nobody ran it - and a machine
; code program may have used page zero since. Without this, CHRGET at $B1
; is garbage and the first RUN crashes.
;-------------------------------------------------------------------------------
init_applesoft:
        lda LCRAM_ROM           ; template lives in ROM
        lda #$4C                ; JMP opcodes for GOWARM, GOSTROUT, USR, $90
        sta $00
        sta $03
        sta $90
        sta $0A
        lda #<$D43C             ; GOWARM -> RESTART, GOSTROUT -> STROUT:
        ldy #>$D43C             ; what the end of a cold start leaves
        sta $01                 ; ($F1C4; its first $F128 is a placeholder)
        sty $02
        lda #<$DB3A
        ldy #>$DB3A
        sta $04
        sty $05
        lda #<$E199             ; USR -> ILLEGAL QUANTITY until set
        ldy #>$E199
        sta $0B
        sty $0C
        ldx #$1C                ; CHRGET + RND seed -> $B1-$CC
@copy:
        lda $F10A,x
        sta $B0,x
        dex
        bne @copy
        lda #1
        sta $F1                 ; SPEED=255
        lda #0
        sta TRCFLG
        sta $A4
        sta $54
        sta ERRFLG_ZP
        sta $D6                 ; not run-only
        lda #3
        sta $8F
        lda #$FF
        sta CURLIN_H
        jsr $F273               ; NORMAL
        rts

;-------------------------------------------------------------------------------
; Empty Applesoft program with HIMEM just below the agent (what NEW would
; leave), for the /EXIT path to the ] prompt.
;-------------------------------------------------------------------------------
init_basic_program:
        lda #0
        sta BASIC_START-1
        sta BASIC_START
        sta BASIC_START+1
        lda #<BASIC_START
        sta TXTTAB
        lda #>BASIC_START
        sta TXTTAB+1
        lda #<(BASIC_START+2)
        sta VARTAB
        sta ARYTAB
        sta STREND
        sta PRGEND
        lda #>(BASIC_START+2)
        sta VARTAB+1
        sta ARYTAB+1
        sta STREND+1
        sta PRGEND+1
        lda #<$6000
        sta MEMSIZ
        sta $6F                 ; FRETOP
        lda #>$6000
        sta MEMSIZ+1
        sta $70
        rts

;-------------------------------------------------------------------------------
; Keep a copy of the config page so a program that scribbles on page 3
; can't lose the proxy IP/port.
;-------------------------------------------------------------------------------
save_config_shadow:
        ldx #CONFIG_SIZE-1
@loop:
        lda CONFIG_BASE,x
        sta config_shadow,x
        dex
        bpl @loop
        rts

restore_config_shadow:
        lda config_shadow+CONFIG_MAGIC-CONFIG_BASE
        cmp #CONFIG_MAGIC_VAL
        bne @done               ; never saved - leave page 3 alone
        ldx #CONFIG_SIZE-1
@loop:
        lda config_shadow,x
        sta CONFIG_BASE,x
        dex
        bpl @loop
@done:
        rts

;===============================================================================
; Packet handlers (called from process_packet inside the TCP callback)
; Nothing here may call tcp_send.
;===============================================================================

;-------------------------------------------------------------------------------
; DEPLOY: start receiving a program or a preview image
; data: mode (DEPLOY_MAIN/DEPLOY_AUX), purpose (PROGRAM/PREVIEW)
;-------------------------------------------------------------------------------
handle_deploy:
        jsr preview_off         ; HIRES must be off or 80STORE reroutes $2000
        lda #0
        sta load_bad
        sta packet_lost
        lda pkt_buffer+1
        sta load_purpose
        cmp #PURPOSE_PROGRAM
        beq @forget_program     ; old program is being replaced
        ; A preview writes main $2000-$3FFF: a RESIDENT program living
        ; there is about to be overwritten (EXCHANGE ones sit safe in aux)
        lda run_desc+RD_MODE
        bne @keep_program
        lda run_desc+RD_LO_PAGE
        cmp #$40
        bcs @keep_program
        lda run_desc+RD_HI_PAGE
        cmp #$21
        bcc @keep_program
@forget_program:
        lda #0
        sta program_ready
@keep_program:
        lda pkt_buffer
        cmp #DEPLOY_AUX
        bne @main
        lda has_aux_ram
        beq @main               ; no aux memory - can't stage there
        lda #DEPLOY_AUX
        sta load_mode
        lda #$BF                ; aux staging may fill $0800-$BEFF
        sta load_limit
        rts
@main:
        lda #DEPLOY_MAIN
        sta load_mode
        lda #$60                ; main writes must stay below the agent
        sta load_limit
        rts

;-------------------------------------------------------------------------------
; LOAD: addr(2) + up to 126 bytes. Writes to main or aux per load_mode.
;-------------------------------------------------------------------------------
handle_load:
        lda pkt_data_pos
        cmp #3
        bcc @done               ; no data

        lda pkt_buffer
        sta dst_ptr
        lda pkt_buffer+1
        sta dst_ptr+1
        cmp #$08                ; never below $0800 (screen, page 3, stack)
        bcc @bad

        ; last byte = addr + (len - 2) - 1 must be below load_limit page
        lda pkt_data_pos
        sec
        sbc #3                  ; len - 2 - 1
        clc
        adc dst_ptr
        lda dst_ptr+1
        adc #0
        cmp load_limit
        bcs @bad

        ldx #2
        ldy #0
        lda load_mode
        beq @main_loop

        ; AUX staging: only (dst_ptr),y may be written while RAMWRT is on
        sta RAMWRTON
@aux_loop:
        lda pkt_buffer,x
        sta (dst_ptr),y
        iny
        inx
        cpx pkt_data_pos
        bcc @aux_loop
        sta RAMWRTOFF
        rts

@main_loop:
        lda pkt_buffer,x
        sta (dst_ptr),y
        iny
        inx
        cpx pkt_data_pos
        bcc @main_loop
@done:
        rts

@bad:
        lda #1
        sta load_bad
        rts

;-------------------------------------------------------------------------------
; RUN: the program is complete - remember how to launch it.
; Shown as READY once the whole response has arrived.
;-------------------------------------------------------------------------------
handle_run:
        lda packet_lost         ; part of it never arrived: don't run it
        bne @damaged
        lda load_bad
        bne @rejected
        ldx #0
@copy:
        cpx pkt_data_pos
        bcs @copied
        lda pkt_buffer,x
        sta run_desc,x
        inx
        cpx #RUN_DESC_SIZE-1
        bcc @copy
@copied:
        lda #0
        sta run_desc,x          ; terminate name
        sta run_desc+RUN_DESC_SIZE-1

        ; EXCHANGE needs aux memory; RESIDENT must stay below the agent
        lda run_desc+RD_MODE
        beq @resident
        lda has_aux_ram
        beq @rejected
        bne @ok
@resident:
        lda run_desc+RD_HI_PAGE
        cmp #SWAP_LO_PAGE+1
        bcs @rejected
@ok:
        lda #1
        sta program_ready
        sta run_pending
        lda #0
        sta refetch_tries
        rts
@damaged:
        lda #0
        sta program_ready
        lda #1
        sta run_damaged
        rts
@rejected:
        lda #0
        sta program_ready
        lda #1
        sta run_rejected
        rts

;-------------------------------------------------------------------------------
; SHOW: 0 = text, 1 = HGR page 1 mixed (live preview of what Claude sees)
;-------------------------------------------------------------------------------
handle_show:
        lda pkt_buffer
        beq preview_off
        lda HIRES
        lda MIXSET
        lda TXTPAGE1
        lda SETAN3
        lda TXTCLR
        lda #1
        sta preview_on
        rts

preview_off:
        lda TXTSET
        lda LORES
        lda MIXCLR
        lda #0
        sta preview_on
        rts

;===============================================================================
; READY prompt and launch
;===============================================================================

;-------------------------------------------------------------------------------
; After a response: if a program arrived, offer to run it
;-------------------------------------------------------------------------------
offer_program:
        ; Damaged on the way (handle_run): get a fresh copy, at most twice
        lda run_damaged
        beq @not_damaged
        lda #0
        sta run_damaged
        inc refetch_tries
        lda refetch_tries
        cmp #3
        bcs @give_up
        ldax #msg_refetch
        jsr print_status
        ldx #RERUN_CMD_LEN-1
:       lda rerun_cmd,x
        sta input_buffer,x
        dex
        bpl :-
        lda #RERUN_CMD_LEN
        sta input_len
        lda #0
        sta autorun             ; offer it as READY, as the first copy would have been
        jmp send_chat
@give_up:
        lda #0
        sta refetch_tries
        ldax #msg_damaged
        jmp print_status
@not_damaged:
        lda run_rejected
        beq @no_reject
        lda #0
        sta run_rejected
        ldax #msg_run_rejected
        jsr print_status
@no_reject:
        ldx autorun             ; /RUN fetched a fresh copy: run it on arrival
        lda #0
        sta autorun
        lda run_pending
        bne @offer
        rts
@offer:
        lda #0
        sta run_pending
        txa
        beq @prompt
        jmp launch_program
@prompt:
        ; The four lines below stay together: near the bottom of the log a
        ; page turn would leave only "RETURN = RUN IT" with no name
        lda output_row
        cmp #OUTPUT_END-3
        bcc :+
        jsr clear_output_area
:       jsr scroll_output
        jsr scroll_output
        ldax #msg_ready_stars
        jsr print
        ldax #run_desc+RD_NAME
        jsr print
        ldax #msg_ready_is_ready
        jsr print
        jsr scroll_output
        ldax #msg_ready_keys
        jsr print
        ldax #msg_ready_status
        jsr print_status

@wait:
        jsr read_key
        and #$7F
        cmp #$0D
        beq @run
        cmp #$1B
        beq @later
        cmp #' '
        bcc @wait               ; other control keys: ignore
        ; Typing something else = "not now", and it starts the next message
        sta input_buffer
        lda #1
        sta input_len
        sta prefill_input
@later:
        ldax #msg_run_later
        jsr print_status
        rts
@run:
        jmp launch_program

;-------------------------------------------------------------------------------
; /RUN - run the last program again
;-------------------------------------------------------------------------------
cmd_run:
        lda program_ready
        bne @have_program
        ldax #msg_no_program
        jsr print_status
        rts
@have_program:
        ; Run it from what's here - unless that's no longer the program as
        ; sent: machine code that reached $6000+ came back from its last run
        ; with that part as the run left it (EXCHANGE swaps it out as is),
        ; and a RESIDENT program has no pristine copy at all. Then ask the
        ; proxy for a fresh copy; offer_program runs it when it arrives.
        lda run_desc+RD_KIND
        cmp #RUN_BINARY
        bne launch_program
        lda run_desc+RD_MODE
        cmp #MODE_RESIDENT
        beq @fresh
        lda run_desc+RD_HI_PAGE
        cmp #SWAP_LO_PAGE+1
        bcc launch_program
@fresh:
        ldx #RERUN_CMD_LEN-1
:       lda rerun_cmd,x
        sta input_buffer,x
        dex
        bpl :-
        lda #RERUN_CMD_LEN
        sta input_len
        lda #1
        sta autorun
        jmp send_chat

rerun_cmd:
        .byte "/RERUN"
RERUN_CMD_LEN = * - rerun_cmd

;-------------------------------------------------------------------------------
; Launch the program described by run_desc. Does not return - the program
; comes back through RETURN_ENTRY.
;-------------------------------------------------------------------------------
launch_program:
        lda program_ready
        bne @go
        rts
@go:
        jsr save_config_shadow
        lda #1
        sta program_launched

        ; Plain 40-column text screen, ROM I/O, full window
        jsr preview_off
        sta SETSLOTCXROM
        sta SETINTC3ROM
        sta CLR80VID
        sta STORE80OFF
        sta CLRALTCHAR
        lda TXTPAGE1
        lda LCRAM_ROM
        lda #0
        sta WNDLFT
        sta WNDTOP
        lda #40
        sta WNDWDTH
        lda #24
        sta WNDBTM
        lda #$FF
        sta INVFLG
        lda #<COUT1
        sta $36
        lda #>COUT1
        sta $37
        jsr HOME

        ; Page 3 hooks for this launch
        jsr install_page3_common
        lda #0
        sta CRASH_MARK
        lda #$4C                ; & and Ctrl-Y come straight back
        sta AMPER_VECTOR
        sta CTRLY_VECTOR
        lda #<RETURN_ENTRY
        sta AMPER_VECTOR+1
        sta CTRLY_VECTOR+1
        lda #>RETURN_ENTRY
        sta AMPER_VECTOR+2
        sta CTRLY_VECTOR+2

        lda run_desc+RD_MODE
        beq @resident
        ; EXCHANGE: main $03D0 switches reads to aux; aux $03D3 continues
        lda #$8D                ; STA RAMRDON
        sta RETURN_ENTRY
        lda #<RAMRDON
        sta RETURN_ENTRY+1
        lda #>RAMRDON
        sta RETURN_ENTRY+2
        sta RAMWRTON
        lda #$4C                ; aux $03D3: JMP agent_xreturn
        sta RETURN_ENTRY+3
        lda #<agent_xreturn
        sta RETURN_ENTRY+4
        lda #>agent_xreturn
        sta RETURN_ENTRY+5
        sta RAMWRTOFF
        jmp @hooks_done
@resident:
        lda #$4C
        sta RETURN_ENTRY
        lda #<agent_reentry
        sta RETURN_ENTRY+1
        lda #>agent_reentry
        sta RETURN_ENTRY+2
@hooks_done:

        lda run_desc+RD_KIND
        cmp #RUN_BINARY
        beq @binary

        ; BASIC: ESC at ] or in an INPUT line comes home, pointers describe the program
        jsr init_applesoft
        lda #<KSW_HOOK
        sta KSWL
        lda #>KSW_HOOK
        sta KSWH
        lda run_desc+RD_START
        sta TXTTAB
        lda run_desc+RD_START+1
        sta TXTTAB+1
        lda run_desc+RD_PRGEND
        sta PRGEND
        lda run_desc+RD_PRGEND+1
        sta PRGEND+1
        lda run_desc+RD_LOMEM
        sta VARTAB
        sta ARYTAB
        sta STREND
        lda run_desc+RD_LOMEM+1
        sta VARTAB+1
        sta ARYTAB+1
        sta STREND+1
        lda run_desc+RD_HIMEM
        sta MEMSIZ
        lda run_desc+RD_HIMEM+1
        sta MEMSIZ+1
        lda #0
        sta ERRFLG_ZP
        sta TRCFLG
        lda #<APPLESOFT_RUN
        ldx #>APPLESOFT_RUN
        ldy #RUN_BASIC
        jmp @blob

@binary:
        lda #<KEYIN
        sta KSWL
        lda #>KEYIN
        sta KSWH
        lda run_desc+RD_START
        ldx run_desc+RD_START+1
        ldy #RUN_BINARY

@blob:
        ; Copy the blob to the stack page and patch its final jump
        pha
        txa
        pha
        tya
        pha
        jsr copy_blob
        pla
        sta blob_kind_imm+1     ; (in the copy at $01xx)
        pla
        sta blob_entry+2
        pla
        sta blob_entry+1
        lda #<blob_launch
        sta blob_after+1
        lda #>blob_launch
        sta blob_after+2

        lda run_desc+RD_MODE
        beq @go_blob            ; RESIDENT: nothing to move
        ; Program pages below the agent come from the aux staging copy
        lda run_desc+RD_LO_PAGE
        cmp #SWAP_LO_PAGE
        bcs @swap_only
        sta blob_cp_lo+1
        lda run_desc+RD_HI_PAGE
        cmp #SWAP_LO_PAGE
        bcc @cp_hi
        lda #SWAP_LO_PAGE
@cp_hi:
        sta blob_cp_hi+1
@swap_only:
        lda #SWAP_LO_PAGE       ; ...and $6000-$BEFF trades places
        sta blob_xc_lo+1
@go_blob:
        bit KBDSTRB             ; don't let RETURN leak into the program
        jmp blob_go

;-------------------------------------------------------------------------------
; Copy the stack-page blob into place ($0100)
;-------------------------------------------------------------------------------
copy_blob:
        ldx #0
@loop:
        lda blob_image,x
        sta blob_go,x
        inx
        cpx #blob_image_end - blob_image
        bne @loop
        rts

;-------------------------------------------------------------------------------
; EXCHANGE-mode return. Entered from aux $03D3 with RAMRD=aux, so this runs
; from the agent image waiting in aux memory while main still holds the
; program. RAMWRT is main: do NOT write agent variables here.
;-------------------------------------------------------------------------------
agent_xreturn:
        cld
        ldx #$FF
        txs
        sta STORE80OFF          ; $0400/$2000 must follow RAMRD/RAMWRT
        sta RAMWRTOFF
        lda TXTSET
        ldx #0
@copy:                          ; blob -> $0100 (stack page ignores RAMWRT)
        lda blob_image,x
        sta blob_go,x
        inx
        cpx #blob_image_end - blob_image
        bne @copy
        lda #<agent_reentry
        sta blob_after+1
        lda #>agent_reentry
        sta blob_after+2
        lda #SWAP_LO_PAGE       ; swap $6000-$BEFF back, no copy
        sta blob_xc_lo+1
        jmp blob_go

;-------------------------------------------------------------------------------
; Back from a program (every route). Rebuild the agent's world and go back
; to the AGENT> prompt.
;-------------------------------------------------------------------------------
agent_reentry:
        cld
        ldx #$FF
        txs
        sta RAMRDOFF
        sta RAMWRTOFF
        sta SETSTDZP
        sta SETSLOTCXROM        ; the BRK path leaves internal $Cxxx ROM in
        sta SETINTC3ROM
        lda LCRAM_ROM
        lda TXTSET
        lda TXTPAGE1
        lda MIXCLR
        lda LORES
        lda #0
        sta WNDLFT
        sta WNDTOP
        lda #40
        sta WNDWDTH
        lda #24
        sta WNDBTM
        lda #$FF
        sta INVFLG
        lda #<COUT1
        sta $36
        lda #>COUT1
        sta $37
        lda #<KEYIN
        sta KSWL
        lda #>KEYIN
        sta KSWH

        jsr restore_config_shadow
        jsr install_resident_hooks
        jsr install_hook        ; & -> RETURN_ENTRY (also from /EXIT's ] prompt)

        ; If Ctrl-Reset also reset the Uthernet's W5100, it has forgotten the
        ; bus mode IP65 set (indirect, auto-increment) and the next send
        ; would wait on it forever: start the network over before then
        lda W5100_MODE
        and #W5100_IND_AI
        cmp #W5100_IND_AI
        beq :+
        lda #1
        sta net_needs_init
:

        ; What happened to the program? (screen is still the program's)
        lda #0
        sta input_len
        sta prefill_input
        lda program_launched
        beq @no_program
        lda #0
        sta program_launched
        jsr find_program_problem
@no_program:

        ; Reset agent state
        lda #0
        sta in_ui
        sta in_callback
        sta recv_state
        sta preview_on

        lda display_mode
        jsr apply_display_mode
        jsr draw_ui

        lda prefill_input
        beq @welcome
        ldax #msg_program_error
        jsr print
        jsr scroll_output
        ldax #msg_fix_hint
        jsr print
        ldax #msg_back_error
        jsr print_status
        jmp @loop
@welcome:
        ldax #msg_back
        jsr print
        jsr scroll_output
        ldax #msg_back_hint
        jsr print
        ldax #msg_back_status
        jsr print_status
@loop:
        jsr main_ui_loop
        jmp BASIC_WARM          ; /QUIT

;-------------------------------------------------------------------------------
; Look at how the program ended: BRK crash, or an Applesoft error on screen.
; Builds "FIX: ..." in input_buffer and sets prefill_input.
;-------------------------------------------------------------------------------
find_program_problem:
        lda CRASH_MARK
        cmp #CRASH_MAGIC
        bne @check_screen
        lda #0
        sta CRASH_MARK
        ; "FIX: PROGRAM CRASHED (BRK AT $xxxx)" - PC is 2 past the BRK
        ldy #0
@crash_copy:
        lda msg_crash_fix,y
        beq @crash_addr
        sta input_buffer,y
        iny
        bne @crash_copy
@crash_addr:
        sty input_len
        lda PCL
        sec
        sbc #2
        sta temp1
        lda PCH
        sbc #0
        jsr append_hex_byte
        lda temp1
        jsr append_hex_byte
        ldy input_len
        lda #')'
        sta input_buffer,y
        iny
        lda #0
        sta input_buffer,y
        sty input_len
        lda #1
        sta prefill_input
        rts

@check_screen:
        ; Applesoft error: a line starting with "?" that contains "ERR"
        ldx #23
@scan:
        jsr get_screen_line_addr
        ldy #0
        lda (src_ptr),y
        and #$7F
        cmp #'?'
        bne @next
        ldy #1
@find_err:
        lda (src_ptr),y
        and #$7F
        cmp #'E'
        bne @next_char
        iny
        lda (src_ptr),y
        and #$7F
        cmp #'R'
        bne @find_err
        iny
        lda (src_ptr),y
        and #$7F
        cmp #'R'
        beq @found
        bne @find_err
@next_char:
        iny
        cpy #39
        bcc @find_err
@next:
        dex
        bpl @scan
        rts
@found:
        jsr check_basic_error   ; same line search, builds "FIX: ..."
        lda input_len
        beq @none
        lda #1
        sta prefill_input
@none:
        rts

;-------------------------------------------------------------------------------
; Append A as two hex digits to input_buffer at input_len
;-------------------------------------------------------------------------------
append_hex_byte:
        pha
        lsr
        lsr
        lsr
        lsr
        jsr @digit
        pla
        and #$0F
@digit:
        cmp #10
        bcc @num
        adc #'A'-10-1           ; carry is set
        bne @store
@num:
        ora #'0'
@store:
        ldy input_len
        sta input_buffer,y
        inc input_len
        rts

;===============================================================================
; The stack-page blob. Assembled to run at $0100, stored here, copied into
; place before use. It must live outside $0200-$BFFF so that flipping
; RAMRD/RAMWRT doesn't pull the code out from under the CPU.
;===============================================================================
        .segment "RODATA"
blob_image:
        .org $0100
;-------------------------------------------------------------------------------
; 1. Copy pages [cp_lo, cp_hi) aux -> main  (cp_lo = 0: skip)
; 2. Swap pages [xc_lo, SWAP_HI_PAGE) main <-> aux  (xc_lo = 0: skip)
; 3. Jump on (blob_launch or agent_reentry)
; The page numbers live in the immediate operands and get patched after
; the blob is copied into place.
;-------------------------------------------------------------------------------
blob_go:
        ldy #0
        sty XC_PTR
blob_cp_lo:
        lda #$00                ; patched: first page to copy
        beq blob_xc_lo
        sta XC_PTR+1
        sta RAMRDON             ; read aux, write main
blob_cp_loop:
        lda (XC_PTR),y
        sta (XC_PTR),y
        iny
        bne blob_cp_loop
        inc XC_PTR+1
        lda XC_PTR+1
blob_cp_hi:
        cmp #$00                ; patched: copy end page
        bcc blob_cp_loop
        sta RAMRDOFF
blob_xc_lo:
        lda #$00                ; patched: first page to swap
        beq blob_done
        sta XC_PTR+1
blob_xc_loop:
        sta RAMRDOFF
        lda (XC_PTR),y
        tax
        sta RAMRDON
        lda (XC_PTR),y
        sta RAMWRTOFF
        sta (XC_PTR),y
        txa
        sta RAMWRTON
        sta (XC_PTR),y
        iny
        bne blob_xc_loop
        inc XC_PTR+1
        lda XC_PTR+1
        cmp #SWAP_HI_PAGE
        bcc blob_xc_loop
blob_done:
        sta RAMRDOFF
        sta RAMWRTOFF
blob_after:
        jmp $FFFF               ; patched: blob_launch or agent_reentry

;-------------------------------------------------------------------------------
; Start the program: BASIC via Applesoft RUN, machine code with a return
; address of RETURN_ENTRY so a plain RTS comes home.
;-------------------------------------------------------------------------------
blob_launch:
        ldx #$FF
        txs
blob_kind_imm:
        lda #$00                ; patched: RUN_BASIC / RUN_BINARY
        beq blob_entry
        lda #>(RETURN_ENTRY-1)
        pha
        lda #<(RETURN_ENTRY-1)
        pha
blob_entry:
        jmp $FFFF               ; patched: $D566 or program entry
        .reloc
blob_image_end:

;-------------------------------------------------------------------------------
; Page 3 code copied to $03C8: BRK stub, a hole for RETURN_ENTRY, KSW hook.
;
; The hook can't use CURLIN to spot the ] prompt (Applesoft only sets it to
; $FF after a line is typed), so it checks that GETLN is reading a line with
; the ] prompt: PROMPT = ']' and RDKEY was called from the monitor ($FDxx).
; Applesoft's GET calls RDKEY from $D5xx, so programs keep their ESC key.
;-------------------------------------------------------------------------------
page3_code:
        .org BRK_ENTRY
p3_brk:
        lda #CRASH_MAGIC
        sta CRASH_MARK
        jmp RETURN_ENTRY
p3_hole:
        .res 3                  ; RETURN_ENTRY, written by the caller
p3_ksw:
        jsr KEYIN               ; A = the character under the cursor, which
        cmp #$9B                ; KEYIN puts back; X (GETLN's place in the
        bne @done               ; line) must come through untouched
        pla                     ; ESC typed into the monitor's GETLN - the ]
        tay                     ; prompt or an INPUT line, which never see ESC
        pla                     ; themselves (RDKEY's caller, high byte; GET
        pha                     ; calls RDKEY from Applesoft and gets its ESC)
        cmp #$FD
        beq p3_hole             ; -> back to the agent (it resets the stack)
        tya
        pha
        lda #$9B
        ldy CH                  ; as KEYIN leaves it
@done:
        rts
        .reloc
page3_code_end:

        .assert p3_hole = RETURN_ENTRY, error, "RETURN_ENTRY hole moved"
        .assert p3_ksw = KSW_HOOK, error, "KSW hook moved"
        .assert page3_code_end - page3_code <= BRKVEC - BRK_ENTRY, error, "page 3 code too big"

;-------------------------------------------------------------------------------
; Strings
;-------------------------------------------------------------------------------
msg_ready_stars:
        .byte "*** ", 0
msg_ready_is_ready:
        .byte " IS READY! ***", 0
msg_ready_keys:
        .byte "RETURN = RUN IT   (OR TYPE TO CHAT)", 0
msg_ready_status:
        .byte "PRESS RETURN TO RUN", 0
msg_run_later:
        .byte "OK - TYPE /RUN WHEN YOU WANT IT", 0
msg_no_program:
        .byte "NO PROGRAM YET - ASK FOR ONE!", 0
msg_refetch:
        .byte "PROGRAM ARRIVED DAMAGED - GETTING IT AGAIN", 0
msg_damaged:
        .byte "PROGRAM ARRIVED DAMAGED - TRY /RUN", 0
msg_run_rejected:
        .byte "PROGRAM DIDN'T FIT - ASK AGAIN", 0
msg_back:
        .byte "WELCOME BACK!", 0
msg_back_hint:
        .byte "/RUN PLAYS IT AGAIN. OR ASK FOR CHANGES.", 0
msg_back_status:
        .byte "READY", 0
msg_program_error:
        .byte "YOUR PROGRAM HIT A PROBLEM.", 0
msg_fix_hint:
        .byte "PRESS RETURN TO HAVE CLAUDE FIX IT.", 0
msg_back_error:
        .byte "RETURN = ASK CLAUDE TO FIX IT", 0
msg_crash_fix:
        .byte "FIX: PROGRAM CRASHED (BRK AT $", 0

;-------------------------------------------------------------------------------
; Variables
;-------------------------------------------------------------------------------
        .segment "BSS"
has_aux_ram:       .res 1       ; 1 = 128K, EXCHANGE launches possible
load_mode:         .res 1       ; DEPLOY_MAIN / DEPLOY_AUX
load_limit:        .res 1       ; LOAD writes must end below this page
load_purpose:      .res 1       ; PURPOSE_PROGRAM / PURPOSE_PREVIEW
load_bad:          .res 1       ; a LOAD was out of bounds
program_ready:     .res 1       ; run_desc describes a loaded program
run_pending:       .res 1       ; RUN arrived during this response
autorun:           .res 1       ; /RUN asked for a fresh copy: launch it on arrival
net_needs_init:    .res 1       ; the W5100 was reset: ip65_init before the next send
run_rejected:      .res 1       ; RUN refused (bad load / no aux)
run_damaged:       .res 1       ; RUN refused: a packet of it was lost
refetch_tries:     .res 1
program_launched:  .res 1       ; set at launch, cleared on return
preview_on:        .res 1       ; HGR preview showing
prefill_input:     .res 1       ; input_buffer holds text for AGENT>
config_shadow:     .res CONFIG_SIZE
run_desc:          .res RUN_DESC_SIZE
