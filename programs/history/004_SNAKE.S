; SNAKE - lo-res snake game with sound
        .org $0800
KBD     = $C000
STROBE  = $C010
SPKR    = $C030
VBL     = $C019
ptr     = $06
sptr    = $08

WALL    = $06
BODY    = $0C
HEAD    = $0D
FOOD    = $01

bodyX   = $1000
bodyY   = $1100

start:
        lda #0
        sta hiscore
        sta hiscore+1
        lda #$A5
        sta seed
        lda #$3C
        sta seed+1
newgame:
        lda $C056
        lda $C053
        lda $C054
        lda $C050
        lda #20
        sta gfxlines
        jsr clearscr
        jsr drawwalls
        lda #0
        sta score
        sta score+1
        sta grow
        sta dir
        sta ndir
        sta eaten
        sta needfood
        lda #$FF
        sta qdir
        lda #6
        sta delay
        ldx #0
@init:  txa
        clc
        adc #10
        sta bodyX,x
        lda #20
        sta bodyY,x
        inx
        cpx #4
        bne @init
        lda #0
        sta tl
        lda #3
        sta hd
        ldx #0
@db:    stx tmpi
        lda bodyY,x
        tay
        lda bodyX,x
        tax
        lda #BODY
        jsr plot
        ldx tmpi
        inx
        cpx #3
        bne @db
        ldx #13
        ldy #20
        lda #HEAD
        jsr plot
        jsr showstatus
        lda #<msgStart
        ldy #>msgStart
        jsr puts
        lda #<msgEsc
        ldy #>msgEsc
        jsr puts
        bit STROBE
@wk:    inc seed
        bne @nw
        inc seed+1
@nw:    lda KBD
        bpl @wk
        sta STROBE
        cmp #$9B
        bne @nq
        jmp quit
@nq:    jsr arrowdir
        bmi @go
        cmp #1
        beq @go
        sta dir
        sta ndir
@go:    lda seed
        ora seed+1
        bne @sok
        inc seed
@sok:   jsr clear22
        jsr placefood
mainloop:
        jsr waitmove
        jsr step
        bcc mainloop
        jmp gameover

; ---------------------------------------------
gameover:
        jsr deathsound
        jsr clear22
        lda #<msgOver
        ldy #>msgOver
        jsr puts
        bit STROBE
@w:     lda KBD
        bpl @w
        sta STROBE
        cmp #$9B
        beq quit
        cmp #$A0
        bne @w
        jmp newgame

quit:
        lda $C051
        lda $C054
        lda #0
        sta gfxlines
        jsr clearscr
        jmp $03D0

; ---------------------------------------------
; A = key -> A = dir (0 R,1 L,2 U,3 D) or $FF
arrowdir:
        cmp #$95
        beq @r
        cmp #$88
        beq @l
        cmp #$8B
        beq @u
        cmp #$8A
        beq @d
        cmp #$8D
        beq @d
        and #$DF
        cmp #$C4
        beq @r
        cmp #$C1
        beq @l
        cmp #$D7
        beq @u
        cmp #$D3
        beq @d
        lda #$FF
        rts
@r:     lda #0
        rts
@l:     lda #1
        rts
@u:     lda #2
        rts
@d:     lda #3
        rts

waitvbl:
@a:     lda VBL
        bpl @a
@b:     lda VBL
        bmi @b
        rts

waitmove:
        lda delay
        sta cnt
@l:     jsr waitvbl
        jsr readkey
        dec cnt
        bne @l
        rts

readkey:
        lda KBD
        bpl @x
        sta STROBE
        cmp #$9B
        bne @n
        jmp quit
@n:     jsr arrowdir
        bmi @x
        sta tmpd
        lda ndir
        cmp dir
        bne @second
        eor #1
        cmp tmpd
        beq @x
        lda tmpd
        sta ndir
        rts
@second:
        eor #1
        cmp tmpd
        beq @x
        lda tmpd
        cmp ndir
        beq @x
        sta qdir
@x:     rts

; ---------------------------------------------
; move one step; carry set = dead
step:
        lda ndir
        sta dir
        tay
        ldx hd
        lda bodyX,x
        clc
        adc dxt,y
        sta nx
        lda bodyY,x
        clc
        adc dyt,y
        sta ny
        lda qdir
        bmi @nq
        sta ndir
        lda #$FF
        sta qdir
@nq:    ldx nx
        ldy ny
        jsr getpix
        beq @move
        cmp #FOOD
        beq @eat
        sec
        rts
@eat:   lda grow
        clc
        adc #3
        sta grow
        jsr addscore
        jsr eatsound
        inc eaten
        lda eaten
        and #3
        bne @m2
        lda delay
        cmp #3
        bcc @m2
        dec delay
@m2:    lda #1
        sta needfood
@move:  lda SPKR
        ldx hd
        lda bodyY,x
        tay
        lda bodyX,x
        tax
        lda #BODY
        jsr plot
        inc hd
        ldx hd
        lda nx
        sta bodyX,x
        lda ny
        sta bodyY,x
        ldx nx
        ldy ny
        lda #HEAD
        jsr plot
        lda grow
        beq @tail
        dec grow
        lda hd
        sec
        sbc tl
        cmp #250
        bcc @done
        lda #0
        sta grow
        beq @done
@tail:  ldx tl
        lda bodyY,x
        tay
        lda bodyX,x
        tax
        lda #0
        jsr plot
        inc tl
@done:  lda needfood
        beq @r
        lda #0
        sta needfood
        jsr placefood
@r:     clc
        rts

addscore:
        sed
        lda score
        clc
        adc #1
        sta score
        lda score+1
        adc #0
        sta score+1
        cld
        lda score+1
        cmp hiscore+1
        bcc @s
        bne @set
        lda score
        cmp hiscore
        bcc @s
@set:   lda score
        sta hiscore
        lda score+1
        sta hiscore+1
@s:     jmp showstatus

; ---------------------------------------------
rand:   ldx #8
@l:     lsr seed+1
        ror seed
        bcc @n
        lda seed+1
        eor #$B4
        sta seed+1
@n:     dex
        bne @l
        lda seed
        rts

placefood:
@try:   jsr rand
        and #$3F
        cmp #38
        bcs @try
        adc #1
        sta fx
@ty:    jsr rand
        and #$3F
        cmp #38
        bcs @ty
        adc #1
        sta fy
        ldx fx
        ldy fy
        jsr getpix
        bne @try
        ldx fx
        ldy fy
        lda #FOOD
        jmp plot

; ---------------------------------------------
; plot X=col Y=row A=color (X preserved)
plot:
        and #$0F
        sta pcol
        tya
        lsr a
        php
        tay
        lda lineLo,y
        sta ptr
        lda lineHi,y
        sta ptr+1
        txa
        tay
        plp
        bcs @odd
        lda (ptr),y
        and #$F0
        ora pcol
        sta (ptr),y
        rts
@odd:   lda pcol
        asl a
        asl a
        asl a
        asl a
        sta pcol
        lda (ptr),y
        and #$0F
        ora pcol
        sta (ptr),y
        rts

; getpix X=col Y=row -> A=color, Z flag
getpix:
        tya
        lsr a
        php
        tay
        lda lineLo,y
        sta ptr
        lda lineHi,y
        sta ptr+1
        txa
        tay
        lda (ptr),y
        plp
        bcc @even
        lsr a
        lsr a
        lsr a
        lsr a
        rts
@even:  and #$0F
        rts

drawwalls:
        ldx #0
@h:     ldy #0
        lda #WALL
        jsr plot
        ldy #39
        lda #WALL
        jsr plot
        inx
        cpx #40
        bne @h
        lda #0
        sta tmpi
@v:     ldy tmpi
        ldx #0
        lda #WALL
        jsr plot
        ldy tmpi
        ldx #39
        lda #WALL
        jsr plot
        inc tmpi
        lda tmpi
        cmp #40
        bne @v
        rts

; lines < gfxlines get 0, others get spaces
clearscr:
        ldx #0
@ln:    lda lineLo,x
        sta ptr
        lda lineHi,x
        sta ptr+1
        lda #0
        cpx gfxlines
        bcc @f
        lda #$A0
@f:     ldy #39
@c:     sta (ptr),y
        dey
        bpl @c
        inx
        cpx #24
        bne @ln
        rts

clear22:
        lda #$50
        sta ptr
        lda #$07
        sta ptr+1
        lda #$A0
        ldy #39
@c:     sta (ptr),y
        dey
        bpl @c
        rts

; A/Y = string: .word dest, chars..., 0
puts:   sta sptr
        sty sptr+1
        ldy #0
        lda (sptr),y
        sta ptr
        iny
        lda (sptr),y
        sta ptr+1
        lda sptr
        clc
        adc #2
        sta sptr
        bcc @z
        inc sptr+1
@z:     ldy #0
@l:     lda (sptr),y
        beq @x
        ora #$80
        sta (ptr),y
        iny
        bne @l
@x:     rts

putbcd: pha
        lsr a
        lsr a
        lsr a
        lsr a
        ora #$B0
        sta (ptr),y
        iny
        pla
        and #$0F
        ora #$B0
        sta (ptr),y
        iny
        rts

showstatus:
        lda #<msgScore
        ldy #>msgScore
        jsr puts
        lda #$50
        sta ptr
        lda #$06
        sta ptr+1
        ldy #7
        lda score+1
        jsr putbcd
        lda score
        jsr putbcd
        ldy #35
        lda hiscore+1
        jsr putbcd
        lda hiscore
        jsr putbcd
        rts

; ---------------------------------------------
tone:   stx tper
@lp:    lda SPKR
        ldx tper
@d:     dex
        bne @d
        dey
        bne @lp
        rts

eatsound:
        ldx #40
        ldy #60
        jsr tone
        ldx #25
        ldy #100
        jmp tone

deathsound:
        lda #60
        sta tmpi
@l:     ldx tmpi
        ldy #30
        jsr tone
        lda tmpi
        clc
        adc #10
        sta tmpi
        cmp #250
        bcc @l
        rts

; ---------------------------------------------
dxt:    .byte 1,$FF,0,0
dyt:    .byte 0,0,$FF,1

lineLo: .byte $00,$80,$00,$80,$00,$80,$00,$80
        .byte $28,$A8,$28,$A8,$28,$A8,$28,$A8
        .byte $50,$D0,$50,$D0,$50,$D0,$50,$D0
lineHi: .byte $04,$04,$05,$05,$06,$06,$07,$07
        .byte $04,$04,$05,$05,$06,$06,$07,$07
        .byte $04,$04,$05,$05,$06,$06,$07,$07

msgScore: .word $0650
        .byte "SCORE:      ***  SNAKE  ***  HIGH:",0
msgStart: .word $0750
        .byte "     PRESS AN ARROW KEY TO START",0
msgEsc: .word $07D0
        .byte "  ARROWS OR WASD STEER - ESC QUITS",0
msgOver: .word $0750
        .byte "  GAME OVER!  SPACE TO PLAY AGAIN",0

; variables
seed:    .res 2
score:   .res 2
hiscore: .res 2
grow:    .res 1
dir:     .res 1
ndir:    .res 1
qdir:    .res 1
tmpd:    .res 1
eaten:   .res 1
needfood: .res 1
delay:   .res 1
cnt:     .res 1
hd:      .res 1
tl:      .res 1
nx:      .res 1
ny:      .res 1
fx:      .res 1
fy:      .res 1
tmpi:    .res 1
pcol:    .res 1
tper:    .res 1
gfxlines: .res 1
