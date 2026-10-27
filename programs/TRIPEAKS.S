; TRIPEAKS SOLITAIRE - HI-RES
        .org $6000
PTR     = $06
GP      = $08
TMP     = $EB
TMP2    = $EC
CNT     = $ED
CNT2    = $EE
KBD     = $C000
KSTRB   = $C010
SPKR    = $C030

.macro SETGP base
        clc
        adc #<base
        sta GP
        lda #>base
        adc #0
        sta GP+1
.endmacro
.macro PRINTAT row,col,str
        lda #row
        ldx #col
        jsr setpos
        lda #<str
        sta GP
        lda #>str
        sta GP+1
        jsr putsn
.endmacro
.macro PRINTINV row,col,str
        lda #row
        ldx #col
        jsr setpos
        lda #<str
        sta GP
        lda #>str
        sta GP+1
        jsr putsi
.endmacro

start:
        jsr buildrows
        lda #0
        sta hisc
        sta hisc+1
title:
        jsr hgron
        jsr clrtext
        lda #0
        sta TMP
        lda #192
        sta TMP2
        jsr fillrows
        ldx #0
@d:     stx DI
        lda demov,x
        sta CV
        lda democ,x
        sta CC
        lda demoy,x
        sta CY
        lda demof,x
        sta CF
        jsr drawcard
        ldx DI
        inx
        cpx #8
        bne @d
        PRINTINV 20,10,t1
        PRINTAT 21,0,t2
        PRINTAT 22,0,t3
        PRINTAT 23,3,t4
        lda KSTRB
@w:     inc seed
        bne @w2
        inc seed+1
@w2:    lda KBD
        bpl @w
        sta KSTRB
        cmp #$9B
        bne @go
        jmp quit
@go:    lda seed
        ora seed+1
        bne newdeal
        inc seed

newdeal:
        jsr shuffle
        ldx #27
@t:     lda deck,x
        sta tab,x
        lda #1
        sta st,x
        dex
        bpl @t
        lda deck+28
        sta waste
        lda #29
        sta sp
        lda #0
        sta score
        sta score+1
        sta run
        sta cleared
        sta over
        sta pend
        jsr hgron
        jsr clrtext
        lda #0
        sta TMP
        lda #192
        sta TMP2
        jsr fillrows
        jsr buildavail
        lda navail
        lsr
        sta cp
        tax
        lda avail,x
        sta sel
        jsr drawtab
        jsr drawpiles
        jsr checkstate
        jsr drawstatus
        PRINTAT 22,2,h1
        PRINTAT 23,2,h2
        lda KSTRB

mainloop:
        lda KBD
        bpl mainloop
        sta KSTRB
        cmp #$9B
        bne @k1
        jmp quit
@k1:    cmp #$88
        bne @k2
        jmp kleft
@k2:    cmp #$95
        bne @k3
        jmp kright
@k3:    cmp #$8D
        beq @kp
        cmp #$8B
        bne @k4
@kp:    jmp kplay
@k4:    cmp #$A0
        beq @kd
        cmp #$8A
        bne @k5
@kd:    jmp kdraw
@k5:    and #$DF
        cmp #$CE
        bne mainloop
        jmp newdeal

quit:
        sta $C051
        sta $C054
        jsr $FC58
        rts

kleft:
        lda over
        bne @x
        lda cp
        beq @x
        jsr invsel
        dec cp
        ldx cp
        lda avail,x
        sta sel
        jsr invsel
        jsr sndtick
@x:     jmp mainloop

kright:
        lda over
        bne @x
        lda cp
        clc
        adc #1
        cmp navail
        bcs @x
        jsr invsel
        inc cp
        ldx cp
        lda avail,x
        sta sel
        jsr invsel
        jsr sndtick
@x:     jmp mainloop

kplay:
        lda over
        bne @x
        lda sel
        bmi @x
        tax
        lda tab,x
        jsr adjw
        bcs @ok
        jsr snderr
@x:     jmp mainloop
@ok:    ldx sel
        lda tab,x
        sta waste
        lda #0
        sta st,x
        inc cleared
        inc run
        lda score
        clc
        adc run
        sta score
        bcc @s1
        inc score+1
@s1:    cpx #3
        bcs @np
        lda score
        clc
        adc #15
        sta score
        bcc @s2
        inc score+1
@s2:    lda #1
        sta pend
@np:    lda cxt,x
        sta OX
        jsr sndplay
        jsr buildavail
        lda #$FF
        sta sel
        lda navail
        beq @draw
        ldx #0
@f:     ldy avail,x
        lda cxt,y
        cmp OX
        bcs @got
        inx
        cpx navail
        bne @f
        dex
@got:   stx cp
        lda avail,x
        sta sel
@draw:  jsr drawtab
        jsr drawpiles
        jsr checkstate
        jsr drawstatus
        lda over
        beq @end
        jsr sndend
@end:   jmp mainloop

kdraw:
        lda over
        bne @x
        lda sp
        cmp #52
        bcc @ok
        jsr snderr
@x:     jmp mainloop
@ok:    tax
        lda deck,x
        sta waste
        inc sp
        lda #0
        sta run
        jsr snddraw
        jsr drawpiles
        jsr checkstate
        jsr drawstatus
        lda over
        beq @end
        jsr sndend
@end:   jmp mainloop

; ---------- game logic ----------
rand:   ldy #8
        lda seed
@l:     asl
        rol seed+1
        bcc @n
        eor #$39
@n:     dey
        bne @l
        sta seed
        rts

shuffle:
        ldx #51
@i:     txa
        sta deck,x
        dex
        bpl @i
        ldx #51
@s:     inx
        stx TMP
        dex
        jsr rand
@m:     cmp TMP
        bcc @ok
        sbc TMP
        jmp @m
@ok:    tay
        lda deck,x
        pha
        lda deck,y
        sta deck,x
        pla
        sta deck,y
        dex
        bne @s
        rts

; X=index -> carry set if face up and playable
isopen: lda st,x
        beq @no
        cpx #18
        bcs @yes
        ldy c1t,x
        lda st,y
        bne @no
        ldy c2t,x
        lda st,y
        bne @no
@yes:   sec
        rts
@no:    clc
        rts

; A=card -> carry set if one rank from waste
adjw:   tay
        lda rkt,y
        sta TMP
        ldy waste
        lda rkt,y
        sec
        sbc TMP
        cmp #1
        beq @y
        cmp #$FF
        beq @y
        cmp #12
        beq @y
        cmp #$F4
        beq @y
        clc
        rts
@y:     sec
        rts

buildavail:
        lda #0
        sta navail
        sta COL
@c:     ldx #0
@i:     lda cxt,x
        cmp COL
        bne @n
        jsr isopen
        bcc @n
        txa
        ldy navail
        sta avail,y
        inc navail
@n:     inx
        cpx #28
        bne @i
        inc COL
        inc COL
        lda COL
        cmp #40
        bcc @c
        rts

checkstate:
        lda pend
        sta msg
        lda #0
        sta pend
        lda cleared
        cmp #28
        bne @notwin
        lda #52
        sec
        sbc sp
        sta TMP
        asl
        asl
        clc
        adc TMP
        adc #50
        sta bonus
        clc
        adc score
        sta score
        lda score+1
        adc #0
        sta score+1
        lda #1
        sta over
        lda #2
        sta msg
        jmp @hi
@notwin:
        ldx #0
@a:     cpx navail
        beq @none
        ldy avail,x
        lda tab,y
        jsr adjw
        bcs @some
        inx
        bne @a
@none:  lda sp
        cmp #52
        bcc @np
        lda #1
        sta over
        lda #3
        sta msg
        jmp @hi
@np:    lda #4
        sta msg
        rts
@some:  lda msg
        bne @r
        lda run
        cmp #3
        bcc @r
        lda #5
        sta msg
@r:     rts
@hi:    lda score+1
        cmp hisc+1
        bcc @r
        bne @set
        lda score
        cmp hisc
        bcc @r
        beq @r
@set:   lda score
        sta hisc
        lda score+1
        sta hisc+1
        rts

; ---------- drawing ----------
hgron:  sta $C050
        sta $C053
        sta $C054
        sta $C057
        rts

buildrows:
        ldx #0
@l:     txa
        and #7
        asl
        asl
        ora #$20
        sta rowhi,x
        txa
        lsr
        lsr
        lsr
        and #7
        lsr
        pha
        lda #0
        ror
        sta rowlo,x
        pla
        clc
        adc rowhi,x
        sta rowhi,x
        txa
        and #$C0
        beq @s
        cmp #$40
        bne @two
        lda #$28
        bne @add
@two:   lda #$50
@add:   clc
        adc rowlo,x
        sta rowlo,x
@s:     inx
        cpx #192
        bne @l
        rts

; fill hires rows TMP..TMP2-1 with green felt
fillrows:
        ldx TMP
@r:     lda rowlo,x
        sta PTR
        lda rowhi,x
        sta PTR+1
        ldy #39
@c:     lda #$2A
        sta (PTR),y
        dey
        lda #$55
        sta (PTR),y
        dey
        bpl @c
        inx
        cpx TMP2
        bne @r
        rts

; set PTR to hires row (X = card row) for card at CC,CY
cardrow:
        txa
        clc
        adc CY
        tax
        lda rowlo,x
        clc
        adc CC
        sta PTR
        lda rowhi,x
        adc #0
        sta PTR+1
        rts

; draw card CV at byte col CC, top CY; CF=1 face down
drawcard:
        ldx #0
@row:   stx CNT
        jsr cardrow
        ldx CNT
        beq @blk
        cpx #31
        beq @blk
        lda CF
        beq @wht
        cpx #3
        bcc @wht
        cpx #29
        bcs @wht
        ldy #0
        lda #$AA
        sta (PTR),y
        iny
        lda #$D5
        sta (PTR),y
        iny
        lda #$AA
        sta (PTR),y
        jmp @nx
@blk:   lda #0
        ldy #0
        sta (PTR),y
        iny
        sta (PTR),y
        iny
        sta (PTR),y
        jmp @nx
@wht:   ldy #0
        lda #$7E
        sta (PTR),y
        iny
        lda #$7F
        sta (PTR),y
        iny
        lda #$3F
        sta (PTR),y
@nx:    ldx CNT
        inx
        cpx #32
        bne @row
        lda CF
        beq @face
        rts
@face:  ldx CV
        lda rkt,x
        sta RK
        lda sut,x
        sta SU
        lda #0
        sta GC
        sta GB
        lda RK
        asl
        asl
        asl
        SETGP rankn
        lda #3
        sta GR
        lda #7
        sta GN
        jsr drawgl
        lda SU
        asl
        asl
        asl
        SETGP suitn
        lda #11
        sta GR
        lda #5
        sta GN
        jsr drawgl
        lda #2
        sta GB
        lda SU
        asl
        asl
        asl
        SETGP suitr
        lda #16
        sta GR
        jsr drawgl
        lda RK
        asl
        asl
        asl
        SETGP rankr
        lda #22
        sta GR
        lda #7
        sta GN
        jsr drawgl
        lda #1
        sta GB
        ldx SU
        lda redt,x
        sta GC
        lda SU
        asl
        asl
        asl
        asl
        SETGP suitb
        lda #11
        sta GR
        lda #9
        sta GN
        jsr drawgl
        rts

; glyph GP, byte GB, start row GR, GN rows, GC=1 orange
drawgl: ldx #0
@l:     stx CNT2
        txa
        clc
        adc GR
        tax
        jsr cardrow
        ldy CNT2
        lda (GP),y
        sta TMP
        ldy GB
        eor #$7F
        and (PTR),y
        ldx GC
        beq @st
        sta TMP2
        lda TMP
        and #$2A
        ora TMP2
        ora #$80
@st:    sta (PTR),y
        ldx CNT2
        inx
        cpx GN
        bne @l
        rts

invsel: ldx sel
        lda cxt,x
        sta CC
        lda cyt,x
        sta CY
        ldx #0
@r:     stx CNT
        jsr cardrow
        ldy #2
@b:     lda (PTR),y
        eor #$7F
        sta (PTR),y
        dey
        bpl @b
        ldx CNT
        inx
        cpx #32
        bne @r
        rts

drawtab:
        lda #0
        sta TMP
        lda #88
        sta TMP2
        jsr fillrows
        ldx #0
@l:     stx DI
        lda st,x
        beq @n
        lda cxt,x
        sta CC
        lda cyt,x
        sta CY
        lda tab,x
        sta CV
        jsr isopen
        lda #0
        bcs @u
        lda #1
@u:     sta CF
        jsr drawcard
@n:     ldx DI
        inx
        cpx #28
        bne @l
        lda sel
        bmi @x
        jsr invsel
@x:     rts

drawpiles:
        lda #96
        sta TMP
        lda #140
        sta TMP2
        jsr fillrows
        lda sp
        cmp #52
        bcs @no
        lda #14
        sta CC
        lda #102
        sta CY
        lda #1
        sta CF
        jsr drawcard
        lda sp
        cmp #48
        bcs @no
        lda #14
        sta CC
        lda #100
        sta CY
        jsr drawcard
        lda #98
        sta CY
        jsr drawcard
@no:    lda #22
        sta CC
        lda #100
        sta CY
        lda waste
        sta CV
        lda #0
        sta CF
        jsr drawcard
        rts

; ---------- text ----------
setpos: tay
        txa
        clc
        adc txlo,y
        sta PTR
        lda txhi,y
        adc #0
        sta PTR+1
        rts
putsn:  lda #$FF
        sta ANDM
        lda #$80
        sta ORAM
        jmp puts
putsi:  lda #$3F
        sta ANDM
        lda #0
        sta ORAM
puts:   ldy #0
@l:     lda (GP),y
        beq @d
        and ANDM
        ora ORAM
        sta (PTR),y
        iny
        bne @l
@d:     tya
        clc
        adc PTR
        sta PTR
        bcc @x
        inc PTR+1
@x:     rts
putc:   ldy #0
        sta (PTR),y
        inc PTR
        bne @x
        inc PTR+1
@x:     rts

clrrow: ldx #0
        jsr setpos
        ldy #39
        lda #$A0
@l:     sta (PTR),y
        dey
        bpl @l
        rts
clrtext:
        lda #23
        sta CNT
@l:     lda CNT
        jsr clrrow
        dec CNT
        bpl @l
        rts

printnum:
        lda #0
        sta STARTED
        ldx #0
@pow:   lda #0
        sta DIG
@sub:   lda NUM
        sec
        sbc plo,x
        sta TMP
        lda NUM+1
        sbc phi,x
        bcc @done
        sta NUM+1
        lda TMP
        sta NUM
        inc DIG
        bne @sub
@done:  lda DIG
        bne @out
        lda STARTED
        beq @skip
@out:   lda #1
        sta STARTED
        lda DIG
        ora #$B0
        jsr putc
@skip:  inx
        cpx #4
        bne @pow
        lda NUM
        ora #$B0
        jsr putc
        rts
plo:    .byte <10000,<1000,<100,<10
phi:    .byte >10000,>1000,>100,>10

drawstatus:
        lda #20
        jsr clrrow
        lda #21
        jsr clrrow
        PRINTAT 20,0,s_score
        lda score
        sta NUM
        lda score+1
        sta NUM+1
        jsr printnum
        PRINTAT 20,12,s_run
        lda run
        sta NUM
        lda #0
        sta NUM+1
        jsr printnum
        PRINTAT 20,19,s_stock
        lda #52
        sec
        sbc sp
        sta NUM
        lda #0
        sta NUM+1
        jsr printnum
        PRINTAT 20,29,s_hi
        lda hisc
        sta NUM
        lda hisc+1
        sta NUM+1
        jsr printnum
        lda msg
        cmp #1
        bne @m2
        PRINTAT 21,1,m_peak
        rts
@m2:    cmp #2
        bne @m3
        PRINTINV 21,0,m_win
        lda #$A0
        jsr putc
        lda #$AB
        jsr putc
        lda bonus
        sta NUM
        lda #0
        sta NUM+1
        jsr printnum
        rts
@m3:    cmp #3
        bne @m4
        PRINTINV 21,1,m_over
        rts
@m4:    cmp #4
        bne @m5
        PRINTAT 21,1,m_noplay
        rts
@m5:    cmp #5
        bne @m6
        PRINTAT 21,1,m_run
        lda run
        sta NUM
        lda #0
        sta NUM+1
        jsr printnum
        lda #$A1
        jsr putc
@m6:    rts

; ---------- sound ----------
tone:   sty TMP
@c:     lda SPKR
        ldy TMP
@d:     dey
        bne @d
        dex
        bne @c
        rts
sndtick: ldx #3
        ldy #30
        jmp tone
sndplay: ldx #40
        ldy #50
        jsr tone
        ldx #50
        ldy #38
        jmp tone
snddraw: ldx #20
        ldy #120
        jmp tone
snderr: ldx #40
        ldy #250
        jmp tone
sndend: lda msg
        cmp #2
        bne @lose
        ldx #60
        ldy #80
        jsr tone
        ldx #75
        ldy #64
        jsr tone
        ldx #90
        ldy #53
        jsr tone
        ldx #160
        ldy #40
        jmp tone
@lose:  ldx #60
        ldy #120
        jsr tone
        ldx #80
        ldy #180
        jmp tone

; ---------- strings ----------
t1:     .byte " TRIPEAKS SOLITAIRE ",0
t2:     .byte "PLAY CARDS ONE HIGHER OR LOWER THAN THE",0
t3:     .byte "WASTE CARD. CLEAR ALL 3 PEAKS TO WIN!",0
t4:     .byte "PRESS ANY KEY TO DEAL (ESC QUITS)",0
h1:     .byte "ARROWS:PICK  RETURN:PLAY  SPACE:DRAW",0
h2:     .byte "N:NEW DEAL   ESC:QUIT",0
s_score: .byte "SCORE ",0
s_run:  .byte "RUN ",0
s_stock: .byte "STOCK ",0
s_hi:   .byte "HIGH ",0
m_peak: .byte "PEAK CLEARED! +15",0
m_win:  .byte " YOU CLEARED ALL THE PEAKS! ",0
m_over: .byte " NO MORE MOVES - GAME OVER ",0
m_noplay: .byte "NO PLAY - PRESS SPACE TO DRAW",0
m_run:  .byte "GREAT RUN OF ",0
redt:   .byte 0,1,1,0
demov:  .byte 0,0,0,9,23,50,38,0
democ:  .byte 6,18,30,10,14,18,22,26
demoy:  .byte 12,12,12,60,60,60,60,60
demof:  .byte 1,1,1,0,0,0,0,0

rankn:
  .byte $1C,$22,$22,$3E,$22,$22,$22,$00
  .byte $1C,$22,$20,$18,$04,$02,$3E,$00
  .byte $1E,$20,$20,$1C,$20,$20,$1E,$00
  .byte $10,$18,$14,$12,$3E,$10,$10,$00
  .byte $3E,$02,$1E,$20,$20,$22,$1C,$00
  .byte $18,$04,$02,$1E,$22,$22,$1C,$00
  .byte $3E,$20,$10,$08,$04,$04,$04,$00
  .byte $1C,$22,$22,$1C,$22,$22,$1C,$00
  .byte $1C,$22,$22,$3C,$20,$10,$0C,$00
  .byte $3A,$2A,$2A,$2A,$2A,$2A,$3A,$00
  .byte $38,$10,$10,$10,$10,$12,$0C,$00
  .byte $1C,$22,$22,$22,$2A,$12,$2C,$00
  .byte $22,$12,$0A,$06,$0A,$12,$22,$00
rankr:
  .byte $22,$22,$22,$3E,$22,$22,$1C,$00
  .byte $3E,$20,$10,$0C,$02,$22,$1C,$00
  .byte $3C,$02,$02,$1C,$02,$02,$3C,$00
  .byte $04,$04,$3E,$24,$14,$0C,$04,$00
  .byte $1C,$22,$02,$02,$3C,$20,$3E,$00
  .byte $1C,$22,$22,$3C,$20,$10,$0C,$00
  .byte $10,$10,$10,$08,$04,$02,$3E,$00
  .byte $1C,$22,$22,$1C,$22,$22,$1C,$00
  .byte $18,$04,$02,$1E,$22,$22,$1C,$00
  .byte $2E,$2A,$2A,$2A,$2A,$2A,$2E,$00
  .byte $18,$24,$04,$04,$04,$04,$0E,$00
  .byte $1A,$24,$2A,$22,$22,$22,$1C,$00
  .byte $22,$24,$28,$30,$28,$24,$22,$00
suitn:
  .byte $08,$1C,$3E,$08,$1C,$00,$00,$00
  .byte $14,$3E,$3E,$1C,$08,$00,$00,$00
  .byte $08,$1C,$3E,$1C,$08,$00,$00,$00
  .byte $08,$1C,$2A,$3E,$08,$00,$00,$00
suitr:
  .byte $1C,$08,$3E,$1C,$08,$00,$00,$00
  .byte $08,$1C,$3E,$3E,$14,$00,$00,$00
  .byte $08,$1C,$3E,$1C,$08,$00,$00,$00
  .byte $08,$3E,$2A,$1C,$08,$00,$00,$00
suitb:
  .byte $08,$1C,$3E,$7F,$7F,$7F,$2A,$08
  .byte $1C,$00,$00,$00,$00,$00,$00,$00
  .byte $36,$7F,$7F,$7F,$3E,$3E,$1C,$1C
  .byte $08,$00,$00,$00,$00,$00,$00,$00
  .byte $08,$1C,$1C,$3E,$7F,$3E,$1C,$1C
  .byte $08,$00,$00,$00,$00,$00,$00,$00
  .byte $1C,$1C,$1C,$6B,$7F,$6B,$08,$08
  .byte $1C,$00,$00,$00,$00,$00,$00,$00
cxt: .byte 6,18,30,4,8,16,20,28,32,2,6,10,14,18,22,26,30,34,0,4,8,12,16,20,24,28,32,36
cyt: .byte 4,4,4,20,20,20,20,20,20,36,36,36,36,36,36,36,36,36,52,52,52,52,52,52,52,52,52,52
c1t: .byte 3,5,7,9,10,12,13,15,16,18,19,20,21,22,23,24,25,26,255,255,255,255,255,255,255,255,255,255
c2t: .byte 4,6,8,10,11,13,14,16,17,19,20,21,22,23,24,25,26,27,255,255,255,255,255,255,255,255,255,255
rkt: .byte 0,1,2,3,4,5,6,7,8,9,10,11,12,0,1,2,3,4,5,6,7,8,9,10,11,12,0,1,2,3,4,5,6,7,8,9,10,11,12,0,1,2,3,4,5,6,7,8,9,10,11,12
sut: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,2,2,2,2,2,2,2,2,2,2,2,2,2,3,3,3,3,3,3,3,3,3,3,3,3,3
txlo: .byte $00,$80,$00,$80,$00,$80,$00,$80,$28,$A8,$28,$A8,$28,$A8,$28,$A8,$50,$D0,$50,$D0,$50,$D0,$50,$D0
txhi: .byte $04,$04,$05,$05,$06,$06,$07,$07,$04,$04,$05,$05,$06,$06,$07,$07,$04,$04,$05,$05,$06,$06,$07,$07

; ---------- variables ----------
seed:   .res 2
hisc:   .res 2
score:  .res 2
NUM:    .res 2
sp:     .res 1
waste:  .res 1
run:    .res 1
cleared: .res 1
over:   .res 1
pend:   .res 1
msg:    .res 1
bonus:  .res 1
navail: .res 1
cp:     .res 1
sel:    .res 1
OX:     .res 1
COL:    .res 1
DI:     .res 1
CC:     .res 1
CY:     .res 1
CV:     .res 1
CF:     .res 1
RK:     .res 1
SU:     .res 1
GB:     .res 1
GR:     .res 1
GN:     .res 1
GC:     .res 1
ANDM:   .res 1
ORAM:   .res 1
STARTED: .res 1
DIG:    .res 1
deck:   .res 52
tab:    .res 28
st:     .res 28
avail:  .res 28
rowlo:  .res 192
rowhi:  .res 192
