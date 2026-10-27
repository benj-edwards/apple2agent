; BREAKOUT - hi-res, mixed mode
        .org $0800

ptr     = $06
ptr2    = $08
tmp     = $FA
tmpy    = $FB
cnt     = $FC

PADY    = 150
AUTO    = 0
HOME    = $FC58

.macro PRINT dest, src
        lda #<dest
        sta ptr
        lda #>dest
        sta ptr+1
        lda #<src
        sta ptr2
        lda #>src
        sta ptr2+1
        jsr prints
.endmacro

start:
        cld
        sta $C010
        jsr maketables
        jsr HOME
        sta $C050
        sta $C053
        sta $C054
        sta $C057

newgame:
        jsr clearhgr
        jsr HOME
        lda #3
        sta lives
        lda #0
        sta score
        sta score+1
        sta ballon
        lda #1
        sta level
        lda #2
        sta speed
        ; top wall
        ldx #0
        jsr fillrow
        ldx #1
        jsr fillrow
        PRINT $0750, helptxt
        jsr initbricks
        jsr drawstatus
        jsr serve

mainloop:
        jsr waitvbl
        inc frame
        jsr eraseball
        jsr input
        lda launched
        bne @moving
        lda px
        clc
        adc #7
        sta bx
        lda #PADY-3
        sta by
        jmp @draw
@moving:
.if AUTO
        lda bx
        sec
        sbc #7
        bcs @a1
        lda #0
@a1:    cmp #125
        bcc @a2
        lda #124
@a2:    sta px
        jsr drawpaddle
.endif
        jsr moveball
        bcc @chklvl
        ; ball lost
        jsr losesnd
        dec lives
        jsr drawstatus
        lda lives
        bne @again
        jmp gameover
@again: jsr serve
        jmp mainloop
@chklvl:
        lda left
        bne @draw
        ; level cleared
        jsr levelsnd
        sed
        lda level
        clc
        adc #1
        sta level
        cld
        cmp #3
        bcc @nl
        lda #3
        sta speed
@nl:    jsr initbricks
        jsr drawstatus
        jsr serve
        jmp mainloop
@draw:  jsr drawball
        jmp mainloop

gameover:
        PRINT $07D0, overtxt
@w:     lda $C000
        bpl @w
        sta $C010
        and #$7F
        cmp #$1B
        beq quit
        cmp #$20
        bne @w
        jmp newgame

quit:
        sta $C051
        sta $C052
        sta $C054
        jsr HOME
        jmp $03D0

; ---------------- input
input:
        lda #0
        sta newkey
        lda $C000
        bpl @held
        and #$7F
        sta $C010
        cmp #$1B
        bne @ns
        pla
        pla
        jmp quit
@ns:    cmp #$20
        bne @nk
        lda launched
        bne @nk
        lda #1
        sta launched
        lda frame
        and #1
        beq @dl
        lda #1
        bne @sd
@dl:    lda #$FF
@sd:    sta dx
        lda #0
        sec
        sbc speed
        sta dy
        jsr clearl23
@nk:    lda #$80
        sta newkey
@held:  lda $C010
        ora newkey
        bpl @done
        lda $C000
        and #$7F
        cmp #$08
        beq @left
        cmp #$15
        beq @right
@done:  rts
@left:  lda px
        sec
        sbc #3
        bcs @l1
        lda #0
@l1:    sta px
        jmp drawpaddle
@right: lda px
        clc
        adc #3
        cmp #125
        bcc @r1
        lda #124
@r1:    sta px
        jmp drawpaddle

; ---------------- serve
serve:
        lda #0
        sta launched
        sta ballon
        lda #62
        sta px
        jsr drawpaddle
        PRINT $07D7, launchtxt
        rts

; ---------------- ball movement, carry set = lost
moveball:
        lda bx
        clc
        adc dx
        sta bx
        cmp #200
        bcc @nl
        lda #0
        sec
        sbc bx
        sta bx
        jsr negdx
        jsr click
        jmp @ydo
@nl:    cmp #139
        bcc @ydo
        sec
        sbc #138
        sta tmp
        lda #138
        sec
        sbc tmp
        sta bx
        jsr negdx
        jsr click
@ydo:   lda by
        clc
        adc dy
        sta by
        cmp #2
        bcc @top
        cmp #200
        bcc @nt
@top:   lda #2
        sta by
        jsr negdy
        jsr click
@nt:    jsr brickcheck
        ; paddle
        lda dy
        bmi @nopad
        lda by
        cmp #PADY-3
        bcc @nopad
        cmp #PADY+2
        bcs @nopad
        lda bx
        clc
        adc #2
        cmp px
        bcc @nopad
        beq @nopad
        lda px
        clc
        adc #16
        sta tmp
        lda bx
        cmp tmp
        bcs @nopad
        ; hit paddle
        lda #PADY-3
        sta by
        jsr negdy
        lda bx
        clc
        adc #1
        sec
        sbc px
        cmp #4
        bcc @m2
        cmp #8
        bcc @m1
        cmp #13
        bcc @p1
        lda #2
        bne @sdx
@m2:    lda #$FE
        bne @sdx
@m1:    lda #$FF
        bne @sdx
@p1:    lda #1
@sdx:   sta dx
        jsr padsnd
@nopad: lda by
        cmp #157
        bcc @ok
        lda #0
        sta ballon
        sec
        rts
@ok:    clc
        rts

negdx:  lda #0
        sec
        sbc dx
        sta dx
        rts
negdy:  lda #0
        sec
        sbc dy
        sta dy
        rts

; ---------------- bricks
brickcheck:
        lda by
        clc
        adc #1
        sec
        sbc #16
        bcc @none
        cmp #48
        bcs @none
        tax
        and #7
        cmp #6
        bcs @none
        txa
        lsr
        lsr
        lsr
        sta brow
        ldx bx
        inx
        lda hdiv,x
        lsr
        sta bcol
        lda brow
        asl
        asl
        sta tmp
        asl
        asl
        clc
        adc tmp
        clc
        adc bcol
        tax
        lda bricks,x
        beq @none
        lda #0
        sta bricks,x
        sta bmode
        jsr drawbrick
        jsr negdy
        ldx brow
        sed
        lda pts,x
        clc
        adc score
        sta score
        lda score+1
        adc #0
        sta score+1
        cld
        dec left
        jsr drawstatus
        jsr bricksnd
@none:  rts

initbricks:
        ldx #119
        lda #1
@f:     sta bricks,x
        dex
        bpl @f
        lda #120
        sta left
        lda #1
        sta bmode
        lda #0
        sta brow
@r:     lda #0
        sta bcol
@c:     jsr drawbrick
        inc bcol
        lda bcol
        cmp #20
        bne @c
        inc brow
        lda brow
        cmp #6
        bne @r
        rts

drawbrick:
        ldx brow
        lda bevn,x
        sta ce
        lda bodd,x
        sta co
        lda bmode
        bne @d
        sta ce
        sta co
@d:     lda brow
        asl
        asl
        asl
        clc
        adc #16
        sta tmpy
        lda #6
        sta cnt
@l:     ldx tmpy
        lda rowlo,x
        sta ptr
        lda rowhi,x
        sta ptr+1
        lda bcol
        asl
        tay
        lda ce
        sta (ptr),y
        iny
        lda co
        sta (ptr),y
        inc tmpy
        dec cnt
        bne @l
        rts

; ---------------- paddle
drawpaddle:
        ldx #40
        lda #0
@z:     sta pbuf,x
        dex
        bpl @z
        lda #16
        sta cnt
        lda px
        sta tmp
@b:     ldx tmp
        ldy hmod,x
        lda hdiv,x
        tax
        lda pbuf,x
        ora p2m0,y
        sta pbuf,x
        lda pbuf+1,x
        ora p2m1,y
        sta pbuf+1,x
        inc tmp
        dec cnt
        bne @b
        ldx #PADY
@row:   lda rowlo,x
        sta ptr
        lda rowhi,x
        sta ptr+1
        ldy #39
@cp:    lda pbuf,y
        sta (ptr),y
        dey
        bpl @cp
        inx
        cpx #PADY+4
        bne @row
        rts

; ---------------- ball (EOR)
eraseball:
        lda ballon
        beq xr
        lda #0
        sta ballon
        jmp xorball
drawball:
        lda #1
        sta ballon
xorball:
        ldx bx
        lda hmod,x
        sta tmp
        lda hdiv,x
        sta cnt
        ldx by
        lda #3
        sta tmpy
@l:     lda rowlo,x
        sta ptr
        lda rowhi,x
        sta ptr+1
        ldy cnt
        stx ptr2
        ldx tmp
        lda (ptr),y
        eor bm0,x
        sta (ptr),y
        iny
        lda (ptr),y
        eor bm1,x
        sta (ptr),y
        ldx ptr2
        inx
        dec tmpy
        bne @l
xr:     rts

; ---------------- status
drawstatus:
        PRINT $0651, scoretxt
        lda score+1
        ldy #6
        jsr hex2
        lda score
        jsr hex2
        PRINT $0661, ballstxt
        lda lives
        ora #$B0
        sta $0667
        PRINT $066D, leveltxt
        lda level
        ldy #6
        jsr hex2
        rts

; print A as 2 BCD digits at (ptr),y
hex2:   pha
        lsr
        lsr
        lsr
        lsr
        ora #$B0
        sta (ptr),y
        iny
        pla
        and #$0F
        ora #$B0
        sta (ptr),y
        iny
        rts

prints: ldy #0
@l:     lda (ptr2),y
        beq @d
        ora #$80
        sta (ptr),y
        iny
        bne @l
@d:     rts

clearl23:
        ldy #39
        lda #$A0
@l:     sta $07D0,y
        dey
        bpl @l
        rts

; ---------------- sound
tone:   ; tmp = period, cnt = count
@o:     lda $C030
        ldx tmp
@i:     dex
        bne @i
        dec cnt
        bne @o
        rts
click:  lda #20
        sta tmp
        lda #6
        sta cnt
        jmp tone
padsnd: lda #60
        sta tmp
        lda #16
        sta cnt
        jmp tone
bricksnd:
        lda #28
        sta tmp
        lda #24
        sta cnt
        jmp tone
losesnd:
        lda #250
        sta tmp
        lda #80
        sta cnt
        jmp tone
levelsnd:
        lda #40
        sta tmp
        lda #200
        sta cnt
        jsr tone
        lda #30
        sta tmp
        lda #250
        sta cnt
        jmp tone

; ---------------- misc
waitvbl:
        lda #72         ; ~14000 cycles -> ~60 frames/s
        jmp $FCA8

fillrow:                ; X = row, fill white
        lda rowlo,x
        sta ptr
        lda rowhi,x
        sta ptr+1
        ldy #39
        lda #$7F
@l:     sta (ptr),y
        dey
        bpl @l
        rts

clearhgr:
        lda #$20
        sta ptr+1
        lda #0
        sta ptr
        ldx #32
        tay
@l:     sta (ptr),y
        iny
        bne @l
        inc ptr+1
        dex
        bne @l
        rts

maketables:
        ldy #0
@r:     tya
        and #7
        asl
        asl
        sta tmp
        tya
        lsr
        lsr
        lsr
        and #7
        lsr
        clc
        adc tmp
        adc #$20
        sta rowhi,y
        tya
        and #8
        beq @z
        lda #$80
@z:     sta tmp
        tya
        asl
        rol
        rol
        and #3
        tax
        lda mul40,x
        clc
        adc tmp
        sta rowlo,y
        iny
        cpy #192
        bne @r
        ldx #0
        stx tmp
        stx cnt
@h:     lda tmp
        sta hdiv,x
        lda cnt
        sta hmod,x
        lda cnt
        clc
        adc #2
        cmp #7
        bcc @s
        sbc #7
        inc tmp
@s:     sta cnt
        inx
        cpx #144
        bne @h
        rts

; ---------------- data
mul40:  .byte 0,40,80
bm0:    .byte $0F,$1E,$3C,$78,$70,$60,$40
bm1:    .byte $00,$00,$00,$00,$01,$03,$07
p2m0:   .byte $03,$06,$0C,$18,$30,$60,$40
p2m1:   .byte $00,$00,$00,$00,$00,$00,$01
;        orange violet white green blue orange
bevn:   .byte $AA,$54,$7E,$2A,$D4,$AA
bodd:   .byte $95,$2A,$3F,$15,$AA,$95
pts:    .byte $07,$05,$04,$03,$02,$01

scoretxt:  .byte "SCORE ",0
ballstxt:  .byte "BALLS ",0
leveltxt:  .byte "LEVEL ",0
helptxt:   .byte "  ARROWS MOVE  SPACE LAUNCH  ESC QUIT",0
launchtxt: .byte "PRESS SPACE TO LAUNCH",0
overtxt:   .byte " GAME OVER - SPACE TO PLAY, ESC TO QUIT",0

lives:  .byte 0
score:  .word 0
level:  .byte 0
speed:  .byte 0
frame:  .byte 0
launched: .byte 0
ballon: .byte 0
newkey: .byte 0
px:     .byte 0
bx:     .byte 0
by:     .byte 0
dx:     .byte 0
dy:     .byte 0
brow:   .byte 0
bcol:   .byte 0
bmode:  .byte 0
left:   .byte 0
ce:     .byte 0
co:     .byte 0

rowlo:  .res 192
rowhi:  .res 192
hdiv:   .res 144
hmod:   .res 144
pbuf:   .res 41
bricks: .res 120
