;===============================================================================
; agent_screen.s - the agent's screen primitives, so 80 columns work without
; the //e's 80-column firmware (included from agent.s)
;
; In 80 columns even columns live in aux memory and odd columns in main, at
; the same addresses in the $0400 text page. With 80STORE on, TXTPAGE2
; points $0400-$07FF at aux (the display still shows page 1) and TXTPAGE1
; points it back at main. In 40 columns every routine hands over to the ROM.
;
;   vid80_out    - COUT handler (CSW) for 80 columns
;   clear_eol    - CLREOL: clear row CV from CH to the end
;   clear_screen - HOME: clear the screen, cursor top left
;   read_key     - RDKEY: wait for a key with a blinking cursor at CV,CH
;   text40       - plain 40-column text for programs and the ] prompt
;===============================================================================

        .segment "STARTUP"

BASL            = $28           ; base address of row CV (VTAB sets it)
; NB: agent.s's VTAB is the ROM's TABV ($FB5B): it sets CV from A first, so
; always LDA CV before JSR VTAB here
BAS2L           = $2A           ; second row pointer (scrolling)
COLS80          = 80
CURSOR80        = $20           ; inverse space (alternate character set)

;-------------------------------------------------------------------------------
; COUT for 80 columns: A = character (bit 7 set). Keeps A, X and Y.
;-------------------------------------------------------------------------------
vid80_out:
        pha
        stx v80_x
        sty v80_y
        cmp #$A0
        bcs @printable
        cmp #$8D                ; RETURN: new line
        beq @cr
        cmp #$8A                ; line feed: down a line
        beq @lf
        cmp #$88                ; backspace: left one
        beq @bs
        bne @done               ; other control characters: ignore
@printable:
        and INVFLG
        jsr put80
        inc CH
        lda CH
        cmp #COLS80
        bcc @done
@cr:
        lda #0
        sta CH
@lf:
        inc CV
        lda CV
        cmp WNDBTM
        bcc @vtab
        dec CV                  ; past the bottom: scroll the window up
        jsr scroll80
@vtab:
        lda CV
        jsr VTAB
        jmp @done
@bs:
        lda CH
        beq @done
        dec CH
@done:
        ldy v80_y
        ldx v80_x
        pla
        rts

;-------------------------------------------------------------------------------
; Store A at column CH of the row at BASL (80 columns). Changes Y.
;-------------------------------------------------------------------------------
put80:
        pha
        lda CH
        lsr                     ; column / 2; carry = odd column
        tay
        pla
        bcs @main
        sta TXTPAGE2            ; even column: aux
        sta (BASL),y
        sta TXTPAGE1
        rts
@main:
        sta (BASL),y
        rts

;-------------------------------------------------------------------------------
; A = the character at column CH of the row at BASL (80 columns). Changes Y.
;-------------------------------------------------------------------------------
get80:
        lda CH
        lsr
        tay
        bcs @main
        sta TXTPAGE2
        lda (BASL),y
        sta TXTPAGE1            ; (a store, so A keeps the character)
        rts
@main:
        lda (BASL),y
        rts

;-------------------------------------------------------------------------------
; Scroll rows WNDTOP..WNDBTM-1 up one (both halves of each row), clear the last
;-------------------------------------------------------------------------------
scroll80:
        lda WNDTOP
        sta v80_row
@row:
        ldx v80_row
        inx
        cpx WNDBTM
        bcs @last
        lda screen_addr_lo,x    ; from the row below...
        sta BAS2L
        lda screen_addr_hi,x
        sta BAS2L+1
        ldx v80_row             ; ...to this one
        lda screen_addr_lo,x
        sta BASL
        lda screen_addr_hi,x
        sta BASL+1
        ldy #39
@copy:
        lda (BAS2L),y           ; main half
        sta (BASL),y
        sta TXTPAGE2
        lda (BAS2L),y           ; aux half
        sta (BASL),y
        sta TXTPAGE1
        dey
        bpl @copy
        inc v80_row
        bne @row
@last:
        ldx v80_row
        lda screen_addr_lo,x
        sta BASL
        lda screen_addr_hi,x
        sta BASL+1
        lda CH
        pha
        lda #0
        sta CH
        jsr clear_eol80
        pla
        sta CH
        rts

;-------------------------------------------------------------------------------
; CLREOL: clear the row at BASL from CH to the right edge. Keeps CH.
;-------------------------------------------------------------------------------
clear_eol:
        lda col_mode
        cmp #CAP_80_COL
        beq clear_eol80
        jmp CLREOL
clear_eol80:
        lda CH
        pha
@loop:
        lda CH
        cmp #COLS80
        bcs @end
        lda #$A0
        jsr put80
        inc CH
        bne @loop
@end:
        pla
        sta CH
        rts

;-------------------------------------------------------------------------------
; HOME: clear the whole screen, cursor at the top left
;-------------------------------------------------------------------------------
clear_screen:
        lda col_mode
        cmp #CAP_80_COL
        beq :+
        jmp HOME
:       lda #0
        sta CH
        lda #23
        sta CV
@row:
        lda CV
        jsr VTAB
        jsr clear_eol80
        dec CV
        bpl @row
        lda #0
        sta CV
        jmp VTAB

;-------------------------------------------------------------------------------
; RDKEY: wait for a key; in 80 columns with our own blinking cursor (the
; ROM's would be drawn at the wrong address past column 39)
;-------------------------------------------------------------------------------
read_key:
        lda col_mode
        cmp #CAP_80_COL
        beq :+
        jmp RDKEY
:       lda CV
        jsr VTAB
        jsr get80
        sta rk_under
@blink:
        lda #CURSOR80
        jsr put80
        jsr @wait
        bcs @key
        lda rk_under
        jsr put80
        jsr @wait
        bcc @blink
@key:
        lda rk_under            ; put back what was under the cursor
        jsr put80
        lda KBD
        bit KBDSTRB
        rts
@wait:                          ; ~0.3 s, or until a key: C=1 if a key
        lda #12
        sta rk_ticks
:       lda KBD
        bmi @pressed
        lda #$60                ; ~24 ms
        jsr WAIT
        dec rk_ticks
        bne :-
        clc
        rts
@pressed:
        sec
        rts

;-------------------------------------------------------------------------------
; Plain 40-column text with the ROM's output - what programs and the ]
; prompt expect (col_mode keeps the user's choice for when we're back)
;-------------------------------------------------------------------------------
text40:
        sta CLR80VID
        sta STORE80OFF
        sta CLRALTCHAR
        sta TXTPAGE1
        lda #<COUT1
        sta $36
        lda #>COUT1
        sta $37
        rts

        .segment "BSS"
v80_x:          .res 1
v80_y:          .res 1
v80_row:        .res 1
rk_under:       .res 1          ; character under the 80-column cursor
rk_ticks:       .res 1
