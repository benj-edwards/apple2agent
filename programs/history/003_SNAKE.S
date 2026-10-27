; LO-RES SNAKE with sound
        .org $0800
ptr   = $06
sp    = $08
px    = $FA
py    = $FB
pc    = $FC
tmp   = $FD
seed  = $EB   ; 2 bytes
pitch = $ED

WALLC  = 5
BODYC  = 12
HEADC  = 13
FOODC  = 1
SROW   = $06D0  ; text row 21

start:
        lda #$A5
        sta seed
        lda #$3C
        sta seed+1
        sta $C050
        sta $C053
        sta $C054
        sta $C056
newgame:
        jsr clrscr
        jsr border
        lda #0
        sta tail
        sta grow
        sta ate
        sta score
        sta score+1
        lda #3
        sta head
        lda #10
        sta speed
        lda #1
        sta dx
        sta ndx
        lda #0
        sta dy
        sta ndy
        ldx #0
@ini:   txa
        clc
        adc #17
        sta bx,x
        sta px
        lda #20
        sta by,x
        sta py
        lda #BODYC
        cpx #3
        bne @c
        lda #HEADC
@c:     sta pc
        txa
        pha
        jsr plot
        pla
        tax
        inx
        cpx #4
        bne @ini
        lda #<m_score
        ldy #>m_score
        jsr print
        jsr drawscore
        lda #<m_help
        ldy #>m_help
        jsr print
        lda #<m_go
        ldy #>m_go
        jsr print
        ; wait for a key, stirring random
@wk:    jsr prng
        lda $C000
        bpl @wk
        jsr handlekey
        jsr placefood
        lda #<m_blank
        ldy #>m_blank
        jsr print

loop:
        ldx speed
@w:     lda $C000
        bpl @nk
        jsr handlekey
@nk:    lda #$40
        jsr $FCA8
        dex
        bne @w
        ; commit direction
        lda ndx
        sta dx
        lda ndy
        sta dy
        ; old head -> body color
        ldx head
        lda bx,x
        sta px
        lda by,x
        sta py
        lda #BODYC
        sta pc
        jsr plot
        ldx head
        lda bx,x
        clc
        adc dx
        sta px
        lda by,x
        clc
        adc dy
        sta py
        jsr readpix
        beq @ok
        cmp #FOODC
        beq @eat
        jmp die
@eat:   lda grow
        clc
        adc #3
        sta grow
        sed
        lda score
        clc
        adc #1
        sta score
        lda score+1
        adc #0
        sta score+1
        cld
        lda #1
        sta ate
        inc eaten
        lda eaten
        and #3
        bne @ok
        lda speed
        cmp #4
        bcc @ok
        dec speed
@ok:    inc head
        ldx head
        lda px
        sta bx,x
        lda py
        sta by,x
        lda #HEADC
        sta pc
        jsr plot
        lda grow
        beq @erase
        dec grow
        lda head
        sec
        sbc tail
        cmp #250
        bcc @after
        lda #0
        sta grow
        beq @erase
@after: jmp @aft2
@erase: ldx tail
        lda bx,x
        sta px
        lda by,x
        sta py
        lda #0
        sta pc
        jsr plot
        inc tail
@aft2:  lda ate
        beq @nl
        lda #0
        sta ate
        jsr drawscore
        jsr placefood
        lda #30
        sta pitch
        ldx #40
        jsr tone
        lda #20
        sta pitch
        ldx #60
        jsr tone
@nl:    jmp loop

die:
        ldx head
        lda bx,x
        sta px
        lda by,x
        sta py
        lda #HEADC
        sta pc
        jsr plot
        ; descending death sound
        lda #40
        sta tmp
@ds:    lda tmp
        sta pitch
        ldx #12
        jsr tone
        inc tmp
        inc tmp
        lda tmp
        cmp #200
        bcc @ds
        ; hi score
        lda score+1
        cmp hi+1
        bcc @nohi
        bne @sethi
        lda score
        cmp hi
        bcc @nohi
@sethi: lda score
        sta hi
        lda score+1
        sta hi+1
@nohi:  jsr drawscore
        lda #<m_over
        ldy #>m_over
        jsr print
        bit $C010
@wk:    jsr prng
        lda $C000
        bpl @wk
        sta $C010
        cmp #$9B
        beq quit
        cmp #$A0
        bne @wk
        jmp newgame

quit:
        sta $C010
        sta $C051
        sta $C054
        jsr $FC58
        jmp $03D0

; ---- key handling: sets ndx/ndy ----
handlekey:
        lda $C000
        sta $C010
        cmp #$9B
        beq quit
        cmp #$88
        beq @left
        cmp #$95
        beq @right
        cmp #$8B
        beq @up
        cmp #$8A
        beq @down
        rts
@left:  lda #$FF
        bne @horiz
@right: lda #1
@horiz: ldy dx
        bne @r
        sta ndx
        lda #0
        sta ndy
@r:     rts
@up:    lda #$FF
        bne @vert
@down:  lda #1
@vert:  ldy dy
        bne @r
        sta ndy
        lda #0
        sta ndx
        rts

; ---- tone: pitch in zp, X = cycles ----
tone:
@c:     lda $C030
        ldy pitch
@d:     dey
        bne @d
        dex
        bne @c
        rts

; ---- 16-bit galois LFSR ----
prng:   ldy #8
        lda seed
@1:     asl
        rol seed+1
        bcc @2
        eor #$39
@2:     dey
        bne @1
        sta seed
        rts

; A = random 1..38
rnd38:  jsr prng
@m:     cmp #38
        bcc @ok
        sec
        sbc #38
        jmp @m
@ok:    clc
        adc #1
        rts

placefood:
@again: jsr rnd38
        sta px
        jsr rnd38
        sta py
        jsr readpix
        bne @again
        lda #FOODC
        sta pc
        jmp plot

; ---- lo-res pixel routines ----
setaddr:
        lda py
        lsr
        tay
        lda rowlo,y
        clc
        adc px
        sta ptr
        lda rowhi,y
        sta ptr+1
        ldy #0
        rts

plot:   jsr setaddr
        lda py
        lsr
        bcs @odd
        lda (ptr),y
        and #$F0
        ora pc
        sta (ptr),y
        rts
@odd:   lda pc
        asl
        asl
        asl
        asl
        sta tmp
        lda (ptr),y
        and #$0F
        ora tmp
        sta (ptr),y
        rts

readpix:
        jsr setaddr
        lda py
        lsr
        lda (ptr),y
        bcs @odd
        and #$0F
        rts
@odd:   lsr
        lsr
        lsr
        lsr
        rts

clrscr:
        ldx #0
@r:     lda rowlo,x
        sta ptr
        lda rowhi,x
        sta ptr+1
        lda #0
        cpx #20
        bcc @g
        lda #$A0
@g:     ldy #39
@c:     sta (ptr),y
        dey
        bpl @c
        inx
        cpx #24
        bne @r
        rts

border:
        lda #WALLC
        sta pc
        ldx #39
@h:     stx px
        lda #0
        sta py
        jsr plot
        lda #39
        sta py
        jsr plot
        ldx px
        dex
        bpl @h
        ldx #39
@v:     stx py
        lda #0
        sta px
        jsr plot
        lda #39
        sta px
        jsr plot
        ldx py
        dex
        bpl @v
        rts

; print: A/Y -> string: row, col, chars..., 0
print:  sta sp
        sty sp+1
        ldy #0
        lda (sp),y
        tax
        iny
        lda (sp),y
        clc
        adc rowlo,x
        sec
        sbc #2
        sta ptr
        lda rowhi,x
        sbc #0
        sta ptr+1
        ldy #2
@l:     lda (sp),y
        beq @d
        ora #$80
        sta (ptr),y
        iny
        bne @l
@d:     rts

drawscore:
        lda score+1
        ldx #7
        jsr bcd
        lda score
        ldx #9
        jsr bcd
        lda hi+1
        ldx #34
        jsr bcd
        lda hi
        ldx #36
        jsr bcd
        rts
bcd:    pha
        lsr
        lsr
        lsr
        lsr
        ora #$B0
        sta SROW,x
        pla
        and #$0F
        ora #$B0
        sta SROW+1,x
        rts

m_score: .byte 21,1,"SCORE",0
         .byte 0
m_help:  .byte 21,15,"SNAKE    HIGH",0
m_hi:
m_go:    .byte 22,2,"ARROWS STEER - PRESS ONE TO START",0
m_blank: .byte 22,2,"                                 ",0
m_over:  .byte 22,2,"GAME OVER! SPACE=PLAY  ESC=QUIT  ",0

rowlo:  .byte $00,$80,$00,$80,$00,$80,$00,$80
        .byte $28,$A8,$28,$A8,$28,$A8,$28,$A8
        .byte $50,$D0,$50,$D0,$50,$D0,$50,$D0
rowhi:  .byte $04,$04,$05,$05,$06,$06,$07,$07
        .byte $04,$04,$05,$05,$06,$06,$07,$07
        .byte $04,$04,$05,$05,$06,$06,$07,$07

head:   .byte 0
tail:   .byte 0
grow:   .byte 0
ate:    .byte 0
eaten:  .byte 0
speed:  .byte 0
dx:     .byte 0
dy:     .byte 0
ndx:    .byte 0
ndy:    .byte 0
score:  .byte 0,0
hi:     .byte 0,0
        .align 256
bx:     .res 256
by:     .res 256
