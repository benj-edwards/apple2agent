; =========================================
;  GALAXIA - hi-res space shooter, Apple //e
; =========================================
        .setcpu "65C02"
        .org $6000

SRC   = $06
DST   = $08
TP    = $FA
TP2   = $FC
T0    = $EB
T1    = $EC
T2    = $ED
T3    = $EE
T4    = $EF
T5    = $19
T6    = $1A
T7    = $1B
T8    = $1C
DROW  = $1D
DIDX  = $1E
DCOL  = $1F

KBD   = $C000
KSTRB = $C010
SPKR  = $C030
RDVBL = $C019
OAPL  = $C061
CAPL  = $C062

SHPBUF = $4000
YLO    = $5000
YHI    = $5100
DIV7   = $5200
MOD7   = $5300
SHLO   = $5400
SHHI   = $5420
DBLL   = $5500
DBLR   = $5580

NSHP  = 12
NEN   = 32
NOBJ  = 39
OEXP  = 32
NEXP  = 6
OPLR  = 38
NSTAR = 20
NEB   = 6
PYPOS = 200
MSGROW = 96
PDIVE = 10
TEST  = 0

start:
        cld
        sta $C000
        sta $C00C
        jsr inittab
        jsr prepshp
        lda #0
        sta HI0
        sta HI1
        sta SNDT
        sta VCNT
        sta VST
        lda #$02
        sta HI2
        lda #$A7
        sta RNG
        lda #$3C
        sta RNG+1
@tl:    jsr title
        jsr game
        jmp @tl

quit:
        lda #0
        sta SNDT
        sta $C051
        sta $C054
        jmp $03D0

; ---------------- tables at init ----------------
inittab:
        ldx #0
@yl:    txa
        and #7
        asl
        asl
        ora #$20
        sta T0
        txa
        lsr
        lsr
        lsr
        and #7
        lsr
        ora T0
        sta T0
        lda #0
        ror
        sta T1
        txa
        rol
        rol
        rol
        and #3
        tay
        lda T1
        clc
        adc MUL28,y
        sta YLO,x
        lda T0
        sta YHI,x
        inx
        cpx #192
        bne @yl
        ldx #0
        lda #0
        sta T0
        sta T1
@dl:    lda T0
        sta DIV7,x
        lda T1
        sta MOD7,x
        clc
        adc #2
        cmp #7
        bcc @dn
        sbc #7
        inc T0
@dn:    sta T1
        inx
        cpx #140
        bne @dl
        ldx #0
@db:    stx T2
        lda #0
        sta T0
        sta T1
        ldy #7
@dbb:   asl T0
        rol T1
        asl T0
        rol T1
        lda T2
        and #$40
        beq @dz
        lda T0
        ora #3
        sta T0
@dz:    asl T2
        dey
        bne @dbb
        lda T0
        and #$7F
        sta DBLL,x
        lda T0
        asl
        lda T1
        rol
        and #$7F
        sta DBLR,x
        inx
        bpl @db
        rts

; ---------------- pre-shift sprites ----------------
prepshp:
        lda #<SHPBUF
        sta DST
        lda #>SHPBUF
        sta DST+1
        ldx #0
@shp:   stx PSHP
        lda DST
        sta SHLO,x
        lda DST+1
        sta SHHI,x
        txa
        asl
        tay
        lda ARTTAB,y
        sta SRC
        lda ARTTAB+1,y
        sta SRC+1
        lda ARTPAL,x
        sta PPAL
        lda #0
        sta PSH
@sh:    lda #0
        sta PROW
        sta PAI
@row:   lda #0
        sta PB0
        sta PB1
        sta PB2
        lda PSH
        sta PPX
        lda #7
        sta PCNT
@ch:    ldy PAI
        lda (SRC),y
        inc PAI
        cmp #'W'
        beq @both
        cmp #'B'
        beq @even
        cmp #'V'
        beq @even
        cmp #'O'
        beq @odd
        cmp #'G'
        beq @odd
        bra @next
@both:  jsr setpx
@odd:   inc PPX
        jsr setpx
        dec PPX
        bra @next
@even:  jsr setpx
@next:  inc PPX
        inc PPX
        dec PCNT
        bne @ch
        ldy #0
        lda PB0
        jsr palfix
        sta (DST),y
        iny
        lda PB1
        jsr palfix
        sta (DST),y
        iny
        lda PB2
        jsr palfix
        sta (DST),y
        lda DST
        clc
        adc #3
        sta DST
        bcc :+
        inc DST+1
:       inc PROW
        lda PROW
        cmp #8
        beq :+
        jmp @row
:       inc PSH
        lda PSH
        cmp #7
        beq :+
        jmp @sh
:       ldx PSHP
        inx
        cpx #NSHP
        beq :+
        jmp @shp
:       rts
palfix: beq :+
        ora PPAL
:       rts
setpx:  lda PPX
        ldx #0
@d:     cmp #7
        bcc @ok
        sbc #7
        inx
        bra @d
@ok:    tay
        lda BITS,y
        ora PB0,x
        sta PB0,x
        rts

; ---------------- low level gfx ----------------
gfxon:
        sta $C050
        sta $C052
        sta $C054
        sta $C057
        rts

clrhgr:
        lda #$20
        sta DST+1
        lda #0
        sta DST
        tay
@l:     sta (DST),y
        iny
        bne @l
        inc DST+1
        ldx DST+1
        cpx #$40
        bne @l
        rts

; XOR sprite SS at SX (0-132), SY (screen row+32)
drawspr:
        jsr vblpoll
        ldx SS
        ldy SX
        lda MOD7,y
        tay
        lda SHLO,x
        clc
        adc SHOFF,y
        sta SRC
        lda SHHI,x
        adc #0
        sta SRC+1
        ldy SX
        lda DIV7,y
        sta DCOL
        lda SY
        sec
        sbc #32
        sta DROW
        lda #0
        sta DIDX
@row:   ldx DROW
        cpx #10
        bcc @skip
        cpx #184
        bcs @skip
        lda YLO,x
        adc DCOL
        sec
        sbc DIDX
        sta DST
        lda YHI,x
        sbc #0
        sta DST+1
        ldy DIDX
        lda (SRC),y
        beq :+
        eor (DST),y
        sta (DST),y
:       iny
        lda (SRC),y
        beq :+
        eor (DST),y
        sta (DST),y
:       iny
        lda (SRC),y
        beq @skip
        eor (DST),y
        sta (DST),y
@skip:  inc DROW
        lda DIDX
        clc
        adc #3
        sta DIDX
        cmp #24
        bne @row
        rts

; bring object X on screen up to date. C=1 if redrawn
syncobj:
        lda O_S,x
        cmp D_S,x
        bne @chg
        cmp #$FF
        beq @no
        lda O_X,x
        cmp D_X,x
        bne @chg
        lda O_Y,x
        cmp D_Y,x
        beq @no
@chg:   stx SYNX
        lda D_S,x
        cmp #$FF
        beq @nod
        sta SS
        lda D_X,x
        sta SX
        lda D_Y,x
        sta SY
        jsr drawspr
        ldx SYNX
@nod:   lda O_S,x
        sta D_S,x
        cmp #$FF
        beq @yes
        sta SS
        lda O_X,x
        sta SX
        sta D_X,x
        lda O_Y,x
        sta SY
        sta D_Y,x
        jsr drawspr
        ldx SYNX
@yes:   sec
        rts
@no:    clc
        rts

; bullet bar: BX, BY, BT (0 player, 8 enemy)
bar:
        ldy BX
        lda DIV7,y
        sta DCOL
        lda MOD7,y
        clc
        adc BT
        tay
        lda BARL,y
        sta BML
        lda BARR,y
        sta BMR
        lda BY
        sec
        sbc #32
        sta DROW
        lda #6
        ldy BT
        beq :+
        lda #4
:       sta DIDX
@r:     ldx DROW
        cpx #10
        bcc @s
        cpx #184
        bcs @s
        lda YLO,x
        adc DCOL
        sta DST
        lda YHI,x
        sta DST+1
        ldy #0
        lda (DST),y
        eor BML
        sta (DST),y
        lda BMR
        beq @s
        iny
        eor (DST),y
        sta (DST),y
@s:     inc DROW
        dec DIDX
        bne @r
        rts

; ---------------- text ----------------
fontptr:
        sta TP2
        lda #0
        sta TP2+1
        asl TP2
        rol TP2+1
        asl TP2
        rol TP2+1
        asl TP2
        rol TP2+1
        lda TP2
        clc
        adc #<FONT
        sta TP2
        lda TP2+1
        adc #>FONT
        sta TP2+1
        rts

putch:
        sec
        sbc #32
        jsr fontptr
        ldx TROW
        lda #0
        sta TI2
@r:     lda YLO,x
        clc
        adc TCOL
        sta DST
        lda YHI,x
        sta DST+1
        ldy TI2
        lda (TP2),y
        ldy #0
        bit TMODE
        bpl :+
        eor (DST),y
:       sta (DST),y
        inx
        inc TI2
        lda TI2
        cmp #8
        bne @r
        rts

putstr:
        lda #0
        sta TIDX
@l:     ldy TIDX
        lda (TP),y
        beq @r
        jsr putch
        inc TCOL
        inc TIDX
        bra @l
@r:     rts

putbcd:
        pha
        lsr
        lsr
        lsr
        lsr
        ora #'0'
        jsr putch
        inc TCOL
        pla
        and #$0F
        ora #'0'
        jsr putch
        inc TCOL
        rts

; SRC -> list of col,row,ptr ; $FF ends
textlist:
        ldy #0
@l:     lda (SRC),y
        cmp #$FF
        beq @r
        sta TCOL
        iny
        lda (SRC),y
        sta TROW
        iny
        lda (SRC),y
        sta TP
        iny
        lda (SRC),y
        sta TP+1
        iny
        sty LIX
        jsr putstr
        ldy LIX
        bra @l
@r:     rts

bigstr:
        lda #0
        sta TIDX
@l:     ldy TIDX
        lda (TP),y
        beq @r
        jsr bigch
        inc TCOL
        inc TCOL
        inc TIDX
        bra @l
@r:     rts

bigch:
        sec
        sbc #32
        jsr fontptr
        ldx TROW
        lda #0
        sta TI2
@r:     lda TCS
        asl
        asl
        asl
        clc
        adc TI2
        tay
        lda SCHEMES,y
        tay
        lda CMEVEN,y
        sta MK0
        lda CMODD,y
        sta MK1
        ldy TI2
        lda (TP2),y
        tay
        lda MK0
        and #$80
        sta BB0
        lda DBLL,y
        and MK0
        ora BB0
        sta BB0
        lda MK1
        and #$80
        sta BB1
        lda DBLR,y
        and MK1
        ora BB1
        sta BB1
        lda THGT
        sta T4
@h:     jsr bigrow
        inx
        dec T4
        bne @h
        inc TI2
        lda TI2
        cmp #7
        bne @r
        jmp vblpoll

bigrow:
        lda YLO,x
        clc
        adc TCOL
        sta DST
        lda YHI,x
        sta DST+1
        ldy #0
        lda BB0
        bit TMODE
        bpl :+
        eor (DST),y
:       sta (DST),y
        iny
        lda BB1
        bit TMODE
        bpl :+
        eor (DST),y
:       sta (DST),y
        rts

; ---------------- timing / sound ----------------
vblpoll:
        lda RDVBL
        bmi @out
        lda VST
        bne @r
        lda #1
        sta VST
        inc VCNT
@r:     rts
@out:   lda #0
        sta VST
        rts

waitframe:
@w:     jsr vblpoll
        lda VCNT
        cmp #2
        bcs @go
        jsr sndtick
        bra @w
@go:    sec
        sbc #2
        cmp #2
        bcc :+
        lda #0
:       sta VCNT
        lda SNDT
        beq @r
        dec SNDT
        lda SNDP
        clc
        adc SNDD
        sta SNDP
@r:     rts

sndtick:
        lda SNDT
        beq @q
        ldy SNDP
@d:     dey
        bne @d
        lda SNDN
        beq @t
        jsr rnd
        and #1
        beq @x
@t:     bit SPKR
@x:     rts
@q:     ldy #30
@d2:    dey
        bne @d2
        rts

; A = sound id (higher = more important)
sound:
        sty SSAVE
        ldy SNDT
        beq @ok
        cmp SNDID
        bcc @x
@ok:    sta SNDID
        asl
        asl
        tay
        lda SNDTAB,y
        sta SNDP
        lda SNDTAB+1,y
        sta SNDD
        lda SNDTAB+2,y
        sta SNDT
        lda SNDTAB+3,y
        sta SNDN
@x:     ldy SSAVE
        rts

rnd:
        lda RNG
        asl
        rol RNG+1
        bcc :+
        eor #$39
:       sta RNG
        eor RNG+1
        rts

playtune:
        ldx #0
@n:     lda TUNE,x
        beq @e
        sta TPER
        lda TUNE+1,x
        sta TCNT
        lda TUNE+2,x
        sta TCNT+1
        lda TUNE+3,x
        sta TREST
@c:     ldy TPER
@d:     dey
        bne @d
        lda TREST
        bne :+
        bit SPKR
:       lda TCNT
        bne :+
        dec TCNT+1
:       dec TCNT
        lda TCNT
        ora TCNT+1
        bne @c
        txa
        clc
        adc #4
        tax
        bra @n
@e:     rts

; ---------------- stars ----------------
starplot:
        ldy ST_R,x
        lda YLO,y
        clc
        adc ST_C,x
        sta DST
        lda YHI,y
        sta DST+1
        ldy #0
        lda (DST),y
        eor ST_B,x
        sta (DST),y
        rts

rndcol:
        jsr rnd
        and #31
        sta T5
        jsr rnd
        and #7
        clc
        adc T5
        rts

initstars:
        ldx #NSTAR-1
@l:     jsr rndcol
        sta ST_C,x
        jsr rnd
        and #127
        sta T5
        jsr rnd
        and #31
        clc
        adc T5
        adc #10
        sta ST_R,x
        jsr rnd
        and #7
        cmp #7
        bne :+
        lda #3
:       tay
        lda BITS,y
        sta ST_B,x
        jsr rnd
        and #1
        clc
        adc #1
        sta ST_V,x
        jsr starplot
        dex
        bpl @l
        rts

dostars:
        ldx #NSTAR-1
@l:     jsr starplot
        lda ST_R,x
        clc
        adc ST_V,x
        cmp #184
        bcc @ok
        jsr rndcol
        sta ST_C,x
        lda #10
@ok:    sta ST_R,x
        jsr starplot
        dex
        bpl @l
        jmp vblpoll

; ---------------- title screen ----------------
title:
        jsr clrhgr
        jsr gfxon
        lda #0
        sta SNDT
        sta TMODE
        sta TCS
        lda #<STITLE
        sta TP
        lda #>STITLE
        sta TP+1
        lda #12
        sta TCOL
        lda #14
        sta TROW
        lda #3
        sta THGT
        jsr bigstr
        lda #0
        sta TMODE
        lda #<TLIST
        sta SRC
        lda #>TLIST
        sta SRC+1
        jsr textlist
        lda #23
        sta TCOL
        lda #124
        sta TROW
        lda HI2
        jsr putbcd
        lda HI1
        jsr putbcd
        lda HI0
        jsr putbcd
        jsr initstars
        lda #0
        sta FRAME
        sta TFL
        jsr tsprites
        jsr blinktxt
        sta KSTRB
@lp:    jsr waitframe
        jsr dostars
        jsr rnd
        inc FRAME
        lda FRAME
        and #15
        bne :+
        jsr blinktxt
:       lda FRAME
        and #15
        cmp #8
        bne :+
        jsr tflap
:       lda KBD
        bpl @lp
        sta KSTRB
        cmp #$9B
        bne :+
        jmp quit
:       cmp #$A0
        bne @lp
        rts

blinktxt:
        lda #$80
        sta TMODE
        lda #<SPRESS
        sta TP
        lda #>SPRESS
        sta TP+1
        lda #10
        sta TCOL
        lda #158
        sta TROW
        jmp putstr

tflap:
        lda TFL
        jsr tsprites
        lda TFL
        eor #1
        sta TFL
tsprites:
        sta T6
        lda #36
        sta SX
        lda #103
        sta SY
        lda #5
        clc
        adc T6
        sta SS
        jsr drawspr
        lda #119
        sta SY
        lda #3
        clc
        adc T6
        sta SS
        jsr drawspr
        lda #135
        sta SY
        lda #1
        clc
        adc T6
        sta SS
        jmp drawspr

; ---------------- game ----------------
game:
        jsr clrhgr
        jsr gfxon
        lda #0
        sta SC0
        sta SC1
        sta SC2
        sta WAVE
        sta WAVEB
        sta GSTATE
        sta GDONE
        sta FRAME
        sta FLAP
        sta SNDT
        sta MTIM
        sta FIREQ
        sta FCOOL
        sta SCDIRTY
        sta LVDIRTY
        lda #2
        sta LIVES
        sta NEXTL
        lda #35
        sta FORMX
        lda #1
        sta FDIR
        lda #10
        sta SWAYT
        jsr resetobjs
        jsr drawhud
        jsr initstars
        jsr nextwave
        jsr playtune
        jsr spawnplr
        lda #0
        sta VCNT
        sta KSTRB
@lp:    jsr waitframe
        inc FRAME
        jsr dostars
        jsr input
        jsr moveplr
        jsr dopb
        jsr doenemies
        jsr doeb
        jsr doexp
        jsr control
        jsr dohud
        lda GDONE
        beq @lp
        rts

resetobjs:
        ldx #NOBJ-1
        lda #$FF
@l:     sta O_S,x
        sta D_S,x
        dex
        bpl @l
        lda #0
        ldx #NEN-1
@e:     sta E_ST,x
        dex
        bpl @e
        ldx #NEXP-1
@x:     sta EX_A,x
        dex
        bpl @x
        ldx #NEB-1
@b:     sta EB_ON,x
        sta EB_D,x
        dex
        bpl @b
        sta PB_ON
        sta PB_ON+1
        sta PB_D
        sta PB_D+1
        sta MSGON
        sta MSGT
        sta P_ALIVE
        rts

spawnplr:
        lda #63
        sta P_X
        lda #1
        sta P_ALIVE
        lda #0
        sta MTIM
        sta FIREQ
        sta FCOOL
        rts

; ---------------- HUD ----------------
drawhud:
        lda #0
        sta TMODE
        lda #<HUDL
        sta SRC
        lda #>HUDL
        sta SRC+1
        jsr textlist
        jsr drawscore
        jsr drawhi
        jsr drawlives
        jmp drawstg

drawscore:
        lda #0
        sta TMODE
        sta TROW
        lda #5
        sta TCOL
        lda SC2
        jsr putbcd
        lda SC1
        jsr putbcd
        lda SC0
        jmp putbcd

drawhi:
        lda #0
        sta TMODE
        sta TROW
        lda #30
        sta TCOL
        lda HI2
        jsr putbcd
        lda HI1
        jsr putbcd
        lda HI0
        jmp putbcd

drawlives:
        lda #0
        sta TMODE
        sta TCOL
        sta T6
        lda #184
        sta TROW
@l:     lda T6
        cmp LIVES
        lda #'['
        bcc :+
        lda #' '
:       jsr putch
        inc TCOL
        inc T6
        lda T6
        cmp #8
        bne @l
        rts

drawstg:
        lda #0
        sta TMODE
        lda #184
        sta TROW
        lda #32
        sta TCOL
        lda #<SSTG
        sta TP
        lda #>SSTG
        sta TP+1
        jsr putstr
        lda #38
        sta TCOL
        lda WAVEB
        jmp putbcd

dohud:
        lda SCDIRTY
        beq :+
        lda #0
        sta SCDIRTY
        jsr drawscore
:       lda LVDIRTY
        beq :+
        lda #0
        sta LVDIRTY
        jsr drawlives
:       rts

; ---------------- messages ----------------
; TP = string, A = color scheme, MSGDUR = frames
showmsg:
        pha
        lda TP
        pha
        lda TP+1
        pha
        jsr clrmsg
        pla
        sta MSGPH
        pla
        sta MSGPL
        pla
        sta MSGCS
        lda MSGPL
        sta TP
        lda MSGPH
        sta TP+1
        ldy #0
@ln:    lda (TP),y
        beq @le
        iny
        bne @ln
@le:    sty T5
        lda #20
        sec
        sbc T5
        and #$FE
        sta MSGCOL
        lda MSGDUR
        sta MSGT
        lda #1
        sta MSGON
drawmsg:
        lda MSGPL
        sta TP
        lda MSGPH
        sta TP+1
        lda MSGCOL
        sta TCOL
        lda #MSGROW
        sta TROW
        lda MSGCS
        sta TCS
        lda #2
        sta THGT
        lda #$80
        sta TMODE
        jmp bigstr

clrmsg:
        lda MSGON
        beq :+
        lda #0
        sta MSGON
        sta MSGT
        jmp drawmsg
:       rts

mkstage:
        ldx #0
@c:     lda SSTAGE,x
        beq @d
        sta MSGBUF,x
        inx
        bra @c
@d:     lda WAVEB
        lsr
        lsr
        lsr
        lsr
        beq @u
        ora #'0'
        sta MSGBUF,x
        inx
@u:     lda WAVEB
        and #$0F
        ora #'0'
        sta MSGBUF,x
        inx
        lda #0
        sta MSGBUF,x
        rts

; ---------------- waves ----------------
nextwave:
        inc WAVE
        sed
        lda WAVEB
        clc
        adc #1
        sta WAVEB
        cld
        jsr setdiff
        jsr initwave
        jsr drawstg
        jsr mkstage
        lda #<MSGBUF
        sta TP
        lda #>MSGBUF
        sta TP+1
        lda #60
        sta MSGDUR
        lda #2
        jmp showmsg

setdiff:
        lda WAVE
        sec
        sbc #1
        lsr
        clc
        adc #5
        cmp #9
        bcc :+
        lda #8
:       sta DIVK
        lda #7
        sta ENTK
        lda WAVE
        cmp #7
        bcs @dmin
        asl
        asl
        asl
        sta T5
        lda #70
        sec
        sbc T5
        cmp #16
        bcs @dset
@dmin:  lda #16
@dset:  sta DIVINT
        lda WAVE
        clc
        adc #1
        cmp #7
        bcc :+
        lda #6
:       sta MAXDIV
        lda WAVE
        cmp #13
        bcs @fmax
        sta T5
        asl
        adc T5
        adc #3
        bra @fset
@fmax:  lda #40
@fset:  sta FIRECH
        rts

initwave:
        ldx #NEN-1
@l:     lda #6
        sta E_ST,x
        lda #$FF
        sta O_S,x
        ldy #1
        lda SLTYPE,x
        cmp #2
        bne :+
        ldy #2
:       tya
        sta E_HP,x
        dex
        bpl @l
        lda #NEN
        sta ENLEFT
        lda #0
        sta GIDX
        lda #30
        sta LTIM
        lda DIVINT
        sta DIVET
        lda WAVE
        sec
        sbc #1
        and #1
        asl
        asl
        sta GSET
        rts

; ---------------- player ----------------
input:
        lda KBD
        bpl @nok
        sta KSTRB
        and #$7F
        cmp #27
        bne :+
        jmp quit
:
.if TEST
        cmp #'N'
        bne :+
        jmp cheatn
:       cmp #'D'
        bne :+
        lda P_ALIVE
        beq @nok
        jmp killplayer
:
.endif
        cmp #8
        bne :+
        lda #$FF
        sta MDIR
        lda #5
        sta MTIM
        bra @nok
:       cmp #21
        bne :+
        lda #1
        sta MDIR
        lda #5
        sta MTIM
        bra @nok
:       cmp #' '
        bne @nok
        lda #1
        sta FIREQ
        lda #0
        sta MTIM
@nok:   lda OAPL
        ora CAPL
        bpl :+
        lda #1
        sta FIREQ
:       lda KSTRB
        bmi @held
        lda MTIM
        beq @r
        dec MTIM
@r:     rts
@held:  lda MTIM
        cmp #3
        bcc @r
        dec MTIM
        rts

.if TEST
cheatn:
        ldx #NEN-1
@l:     lda E_ST,x
        beq @n
        lda #0
        sta E_ST,x
        lda #$FF
        sta O_S,x
        stx KIX
        jsr syncobj
        ldx KIX
@n:     dex
        bpl @l
        lda #0
        sta ENLEFT
        lda #NEN
        sta GIDX
        rts
.endif

moveplr:
        lda P_ALIVE
        bne :+
        lda #0
        sta FIREQ
        rts
:       lda MTIM
        beq @nm
        lda MDIR
        bmi @lf
        lda P_X
        clc
        adc #2
        cmp #133
        bcc @st
        lda #132
        bra @st
@lf:    lda P_X
        sec
        sbc #2
        bcs @st
        lda #0
@st:    sta P_X
@nm:    lda P_X
        sta O_X+OPLR
        lda #PYPOS
        sta O_Y+OPLR
        lda #0
        sta O_S+OPLR
        ldx #OPLR
        jsr syncobj
        lda FCOOL
        beq :+
        dec FCOOL
:       lda FIREQ
        beq @r
        lda #0
        sta FIREQ
        lda FCOOL
        bne @r
        ldy #0
        lda PB_ON
        beq @fs
        iny
        lda PB_ON+1
        bne @r
@fs:    lda #1
        sta PB_ON,y
        lda P_X
        clc
        adc #3
        sta PB_X,y
        lda #PYPOS-4
        sta PB_Y,y
        lda #4
        sta FCOOL
        lda #0
        jsr sound
@r:     rts

; ---------------- player bullets ----------------
dopb:
        ldx #0
@lp:    stx PIX
        lda PB_D,x
        beq @nd
        lda PB_DX,x
        sta BX
        lda PB_DY,x
        sta BY
        lda #0
        sta BT
        jsr bar
        ldx PIX
        lda #0
        sta PB_D,x
@nd:    lda PB_ON,x
        beq @nx
        lda PB_Y,x
        sec
        sbc #8
        sta PB_Y,x
        cmp #40
        bcs @al
        lda #0
        sta PB_ON,x
        bra @nx
@al:    jsr pbhit
        ldx PIX
        lda PB_ON,x
        beq @nx
        lda PB_X,x
        sta BX
        sta PB_DX,x
        lda PB_Y,x
        sta BY
        sta PB_DY,x
        lda #0
        sta BT
        jsr bar
        ldx PIX
        lda #1
        sta PB_D,x
@nx:    inx
        cpx #2
        bne @lp
        rts

pbhit:
        ldy #0
@l:     lda E_ST,y
        beq @n
        cmp #6
        beq @n
        lda PB_X,x
        sec
        sbc O_X,y
        cmp #7
        bcs @n
        lda PB_Y,x
        clc
        adc #6
        sec
        sbc O_Y,y
        cmp #14
        bcs @n
        lda #0
        sta PB_ON,x
        tya
        tax
        jmp hitenemy
@n:     iny
        cpy #NEN
        bne @l
        rts

; X = enemy
hitenemy:
        stx KIX
        lda SLTYPE,x
        cmp #2
        bne @kill
        lda E_HP,x
        cmp #2
        bne @kill
        dec E_HP,x
        lda #1
        jsr sound
        rts
@kill:  lda SLTYPE,x
        asl
        sta T5
        lda E_ST,x
        cmp #4
        bcc @nb
        cmp #6
        bcs @nb
        inc T5
@nb:    ldx T5
        jsr addscore
        ldx KIX
        lda #0
        sta E_ST,x
        lda #$FF
        sta O_S,x
        jsr syncobj
        ldx KIX
        lda O_X,x
        sta T6
        lda O_Y,x
        sta T7
        lda #0
        sta T8
        jsr spawnexp
        dec ENLEFT
        lda #2
        jsr sound
        ldx KIX
        rts

addscore:
        sed
        clc
        lda SC0
        adc SCLO,x
        sta SC0
        lda SC1
        adc SCHI,x
        sta SC1
        lda SC2
        adc #0
        sta SC2
        cld
        lda #1
        sta SCDIRTY
        lda SC2
        cmp NEXTL
        bcc @r
        sed
        lda NEXTL
        clc
        adc #$05
        sta NEXTL
        cld
        inc LIVES
        lda #1
        sta LVDIRTY
        lda #3
        jsr sound
@r:     rts

; A = kind, T6 = x, T7 = y, T8 = start time
spawnexp:
        sta T5
        ldy #0
@f:     lda EX_A,y
        beq @g
        iny
        cpy #NEXP
        bne @f
        rts
@g:     lda #1
        sta EX_A,y
        lda T5
        sta EX_K,y
        lda T8
        sta EX_T,y
        lda T6
        sta O_X+OEXP,y
        lda T7
        sta O_Y+OEXP,y
        rts

killplayer:
        lda #0
        sta P_ALIVE
        sta MTIM
        lda #$FF
        sta O_S+OPLR
        ldx #OPLR
        jsr syncobj
        lda P_X
        sta T6
        lda #PYPOS
        sta T7
        lda #0
        sta T8
        lda #1
        jsr spawnexp
        lda P_X
        sec
        sbc #4
        bcs :+
        lda #0
:       sta T6
        lda #PYPOS-5
        sta T7
        lda #$FA
        sta T8
        lda #0
        jsr spawnexp
        lda P_X
        clc
        adc #4
        cmp #133
        bcc :+
        lda #132
:       sta T6
        lda #PYPOS+2
        sta T7
        lda #$F4
        sta T8
        lda #0
        jsr spawnexp
        lda #4
        jsr sound
        lda #2
        sta GSTATE
        lda #75
        sta STT
        rts

; ---------------- explosions ----------------
doexp:
        ldx #0
@l:     stx XIX
        lda EX_A,x
        beq @sy
        inc EX_T,x
        lda EX_T,x
        bmi @hd
        cmp #12
        bcc @vs
        lda #0
        sta EX_A,x
@hd:    lda #$FF
        bra @set
@vs:    lsr
        lsr
        sta T5
        lda EX_K,x
        asl
        asl
        clc
        adc T5
        tay
        lda EXSEQ,y
@set:   sta O_S+OEXP,x
@sy:    txa
        clc
        adc #OEXP
        tax
        jsr syncobj
        ldx XIX
        inx
        cpx #NEXP
        bne @l
        rts

; ---------------- enemy bullets ----------------
doeb:
        ldx #0
@l:     stx BIX
        lda EB_D,x
        beq @nd
        lda EB_DX,x
        sta BX
        lda EB_DY,x
        sta BY
        lda #8
        sta BT
        jsr bar
        ldx BIX
        lda #0
        sta EB_D,x
@nd:    lda EB_ON,x
        beq @nx
        lda EB_Y,x
        clc
        adc #4
        sta EB_Y,x
        cmp #216
        bcc @mv
@kl:    lda #0
        sta EB_ON,x
        bra @nx
@mv:    lda EB_XF,x
        clc
        adc EB_VX,x
        sta EB_XF,x
        lda EB_VX,x
        bmi @ng
        lda EB_X,x
        adc #0
        bra @sx
@ng:    lda EB_X,x
        adc #$FF
@sx:    cmp #139
        bcs @kl
        sta EB_X,x
        jsr ebhit
        ldx BIX
        lda EB_ON,x
        beq @nx
        lda EB_X,x
        sta BX
        sta EB_DX,x
        lda EB_Y,x
        sta BY
        sta EB_DY,x
        lda #8
        sta BT
        jsr bar
        ldx BIX
        lda #1
        sta EB_D,x
@nx:    inx
        cpx #NEB
        beq :+
        jmp @l
:       rts

ebhit:
        lda P_ALIVE
        beq @r
        lda EB_X,x
        sec
        sbc P_X
        sec
        sbc #1
        cmp #5
        bcs @r
        lda EB_Y,x
        clc
        adc #2
        sec
        sbc #PYPOS
        cmp #9
        bcs @r
        lda #0
        sta EB_ON,x
        jsr killplayer
@r:     rts

; X = enemy
efire:
        ldy #0
@f:     lda EB_ON,y
        beq @g
        iny
        cpy #NEB
        bne @f
        rts
@g:     lda #1
        sta EB_ON,y
        lda O_X,x
        clc
        adc #2
        sta EB_X,y
        lda #$80
        sta EB_XF,y
        lda O_Y,x
        clc
        adc #8
        sta EB_Y,y
        lda P_X
        sec
        sbc O_X,x
        bcc @neg
        cmp #32
        bcc @v
        lda #31
        bra @v
@neg:   cmp #$E1
        bcs @v
        lda #$E1
@v:     asl
        asl
        sta EB_VX,y
        rts

; ---------------- enemies ----------------
doenemies:
        lda #4
        sta FBUD
        ldx #0
@lp:    stx EIX
        jsr vblpoll
        lda E_ST,x
        beq @nx
        cmp #6
        beq @nx
        cmp #3
        bne @mv
        jsr eform
        jsr eshape
        lda FBUD
        beq @nx
        jsr syncobj
        bcc @nx
        dec FBUD
        bra @nx
@mv:    cmp #2
        bne @m1
        jsr ehome
        bra @act
@m1:    cmp #5
        bne @m2
        jsr eseek
        bra @act
@m2:    jsr escript
@act:   ldx EIX
        jsr eshape
        jsr pcoll
        bcs @nx
        ldx EIX
        jsr syncobj
@nx:    ldx EIX
        inx
        cpx #NEN
        bne @lp
        rts

eshape:
        ldy SLTYPE,x
        lda TYSH,y
        cpy #2
        bne @fl
        ldy E_HP,x
        cpy #2
        beq @fl
        lda #7
        bra @st
@fl:    clc
        adc FLAP
@st:    sta O_S,x
        rts

pcoll:
        lda P_ALIVE
        beq @no
        lda O_X,x
        sec
        sbc P_X
        clc
        adc #5
        cmp #11
        bcs @no
        lda O_Y,x
        sec
        sbc #PYPOS
        clc
        adc #7
        cmp #14
        bcs @no
        lda #1
        sta E_HP,x
        jsr hitenemy
        jsr killplayer
        sec
        rts
@no:    clc
        rts

eform:
        lda SLXO,x
        clc
        adc FORMX
        sta O_X,x
        lda SLY,x
        sta O_Y,x
        rts

ehome:
        lda #0
        sta T6
        lda SLXO,x
        clc
        adc FORMX
        sta T5
        lda O_X,x
        sec
        sbc T5
        beq @xa
        bcc @xl
        cmp #3
        bcc @xs
        lda O_X,x
        sbc #2
        sta O_X,x
        bra @yy
@xl:    cmp #$FE
        bcs @xs
        lda O_X,x
        clc
        adc #2
        sta O_X,x
        bra @yy
@xs:    lda T5
        sta O_X,x
@xa:    inc T6
@yy:    lda SLY,x
        sta T5
        lda O_Y,x
        sec
        sbc T5
        beq @ya
        bcc @yl
        cmp #4
        bcc @ys
        lda O_Y,x
        sbc #3
        sta O_Y,x
        bra @dn
@yl:    cmp #$FD
        bcs @ys
        lda O_Y,x
        clc
        adc #3
        sta O_Y,x
        bra @dn
@ys:    lda T5
        sta O_Y,x
@ya:    inc T6
@dn:    lda T6
        cmp #2
        bne @r
        lda #3
        sta E_ST,x
@r:     rts

escript:
        lda E_PC,x
        bne @run
        ldy E_PP,x
        lda PATHD,y
        bne @seg
        lda E_ST,x
        cmp #4
        beq @sk
        lda #2
        sta E_ST,x
        jmp ehome
@sk:    lda #5
        sta E_ST,x
        jmp eseek
@seg:   sta E_PC,x
        lda PATHD+1,y
        ldy E_MIR,x
        beq @nm
        eor #$FF
        clc
        adc #1
@nm:    sta E_TR,x
        lda E_PP,x
        clc
        adc #2
        sta E_PP,x
@run:   dec E_PC,x
        lda E_HD,x
        clc
        adc E_TR,x
        sta E_HD,x
        jmp emove

eseek:
        lda FRAME
        and #1
        bne @f
        lda O_X,x
        clc
        adc #2
        cmp P_X
        bcs @nr
        lda E_HD,x
        cmp #36
        bcc @f
        dec E_HD,x
        bra @f
@nr:    lda P_X
        clc
        adc #2
        cmp O_X,x
        bcs @f
        lda E_HD,x
        cmp #92
        bcs @f
        inc E_HD,x
@f:     lda P_ALIVE
        beq @m
        jsr rnd
        cmp FIRECH
        bcs @m
        lda O_Y,x
        cmp #160
        bcs @m
        jsr efire
@m:     jmp emove

; signed A * KS -> T1:T0
mulk:
        sta T2
        lda #0
        sta T0
        sta T1
        sta T3
        lda T2
        bpl :+
        dec T3
:       lda KS
        sta T4
@l:     lda T0
        clc
        adc T2
        sta T0
        lda T1
        adc T3
        sta T1
        dec T4
        bne @l
        rts

emove:
        lda E_ST,x
        cmp #1
        bne @dk
        lda ENTK
        bra @k
@dk:    lda DIVK
@k:     sta KS
        lda E_HD,x
        lsr
        lsr
        tay
        lda SIN64,y
        jsr mulk
        lda E_YF,x
        clc
        adc T0
        sta E_YF,x
        lda O_Y,x
        adc T1
        sta O_Y,x
        tya
        clc
        adc #16
        and #63
        tay
        lda SIN64,y
        jsr mulk
        lda T1
        cmp #$80
        ror
        sta T1
        ror T0
        lda E_XF,x
        clc
        adc T0
        sta E_XF,x
        lda O_X,x
        adc T1
        cmp #133
        bcc @xok
        cmp #200
        bcs @x0
        lda #132
        bra @xok
@x0:    lda #0
@xok:   sta O_X,x
        lda O_Y,x
        cmp #224
        bcc @r
        cmp #240
        bcs @top
        lda #8
        sta O_Y,x
        lda #2
        sta E_ST,x
        rts
@top:   lda #0
        sta O_Y,x
@r:     rts

; ---------------- control ----------------
control:
        dec SWAYT
        bne @nosw
        lda #10
        sta SWAYT
        lda FORMX
        clc
        adc FDIR
        sta FORMX
        cmp #25
        beq @flip
        cmp #45
        bne @fl
@flip:  lda FDIR
        eor #$FE
        sta FDIR
@fl:    lda FLAP
        eor #1
        sta FLAP
@nosw:  lda GIDX
        cmp #NEN
        bcs @nol
        dec LTIM
        bne @nol
        jsr launch
@nol:   lda GIDX
        cmp #NEN
        bcc @nod
        lda GSTATE
        bne @nod
        dec DIVET
        bne @nod
        lda DIVINT
        sta DIVET
        jsr trydive
@nod:   lda MSGT
        beq @nm
        dec MSGT
        bne @nm
        jsr clrmsg
@nm:    jmp gstep

launch:
        ldy GIDX
        lda ENTORD,y
        tax
        tya
        lsr
        lsr
        lsr
        clc
        adc GSET
        tay
        lda #1
        sta E_ST,x
        lda GPP,y
        sta E_PP,x
        lda GHD,y
        sta E_HD,x
        lda GMIR,y
        sta E_MIR,x
        lda GSX,y
        sta O_X,x
        lda GSY,y
        sta O_Y,x
        lda #0
        sta E_PC,x
        sta E_XF,x
        sta E_YF,x
        inc GIDX
        lda GIDX
        and #7
        bne :+
        lda #26
        bra :++
:       lda #6
:       sta LTIM
        rts

trydive:
        lda P_ALIVE
        beq @r
        jsr countdiv
        cmp MAXDIV
        bcs @r
        lda #12
        sta T7
@t:     jsr rnd
        and #31
        tax
        lda E_ST,x
        cmp #3
        beq @go
        dec T7
        bne @t
@r:     rts
@go:    jsr startdive
        lda SLTYPE,x
        cmp #2
        bne @r
        stx T6
        lda E_MIR,x
        sta T8
        txa
        clc
        adc #4
        tax
        jsr escort
        lda T6
        clc
        adc #6
        tax
        jmp escort

escort:
        lda E_ST,x
        cmp #3
        bne :+
        jsr startdive
        lda T8
        sta E_MIR,x
:       rts

startdive:
        lda #4
        sta E_ST,x
        lda #PDIVE
        sta E_PP,x
        lda #0
        sta E_PC,x
        sta E_XF,x
        sta E_YF,x
        lda #192
        sta E_HD,x
        lda SLCOL,x
        cmp #4
        lda #0
        rol
        sta E_MIR,x
        rts

countdiv:
        lda #0
        sta T5
        ldx #NEN-1
@l:     lda E_ST,x
        cmp #4
        bcc :+
        cmp #6
        bcs :+
        inc T5
:       dex
        bpl @l
        lda T5
        rts

gstep:
        lda GSTATE
        bne @g1
        lda ENLEFT
        bne @r
        lda #1
        sta GSTATE
        lda #70
        sta STT
@r:     rts
@g1:    cmp #1
        bne @g2
        dec STT
        bne @r
        lda #0
        sta GSTATE
        jmp nextwave
@g2:    cmp #2
        bne @g3
        lda STT
        beq :+
        dec STT
        rts
:       jsr countdiv
        bne @r
        lda LIVES
        beq @over
        dec LIVES
        lda #1
        sta LVDIRTY
        jsr spawnplr
        lda #0
        sta GSTATE
        lda #<SREADY
        sta TP
        lda #>SREADY
        sta TP+1
        lda #40
        sta MSGDUR
        lda #1
        jmp showmsg
@over:  lda #3
        sta GSTATE
        lda #150
        sta STT
        lda #<SGOVER
        sta TP
        lda #>SGOVER
        sta TP+1
        lda #255
        sta MSGDUR
        lda #3
        jsr showmsg
        jmp chkhi
@g3:    dec STT
        bne @r
        lda #1
        sta GDONE
        rts

chkhi:
        lda SC2
        cmp HI2
        bcc @r
        bne @new
        lda SC1
        cmp HI1
        bcc @r
        bne @new
        lda SC0
        cmp HI0
        bcc @r
        beq @r
@new:   lda SC0
        sta HI0
        lda SC1
        sta HI1
        lda SC2
        sta HI2
        jsr drawhi
        lda #$80
        sta TMODE
        lda #<SNEWHI
        sta TP
        lda #>SNEWHI
        sta TP+1
        lda #12
        sta TCOL
        lda #124
        sta TROW
        jsr putstr
        lda #3
        jsr sound
@r:     rts

; =============== DATA ===============
SHOFF:  .byte 0,24,48,72,96,120,144
MUL28:  .byte 0,$28,$50
BITS:   .byte 1,2,4,8,16,32,64
BARL:   .byte $03,$06,$0C,$18,$30,$60,$40,0
        .byte $8A,$94,$A8,$D0,$A0,$C0,$00,0
BARR:   .byte 0,0,0,0,0,0,$01,0
        .byte 0,0,0,0,$81,$82,$85,0
CMEVEN: .byte $7F,$55,$2A,$D5,$AA
CMODD:  .byte $7F,$2A,$55,$AA,$D5
SCHEMES:
        .byte 4,4,4,0,0,3,3,3
        .byte 0,0,0,0,0,0,0,0
        .byte 2,2,2,2,2,2,2,2
        .byte 4,4,4,4,4,4,4,4
        .byte 1,1,1,1,1,1,1,1
TYSH:   .byte 1,3,5
SCLO:   .byte $50,$00,$80,$60,$50,$00
SCHI:   .byte $00,$01,$00,$01,$01,$04
EXSEQ:  .byte 8,9,10,10,11,9,11,10
SNDTAB: .byte 16,14,6,0
        .byte 30,$FC,6,0
        .byte 40,12,10,1
        .byte 60,$F8,7,0
        .byte 50,6,35,1

PATHD:  .byte 14,0,40,$FC,0
        .byte 16,0,40,$FC,0
        .byte 2,0,26,$FB,0
        .byte 8,0,30,$FD,28,5,0
GPP:    .byte 0,0,5,5,15,15,5,0
GHD:    .byte 64,64,240,144,64,64,144,64
GMIR:   .byte 0,1,0,1,0,1,1,0
GSX:    .byte 40,92,0,132,56,76,132,40
GSY:    .byte 16,16,150,150,16,16,150,16

SLCOL:  .byte 2,3,4,5, 1,2,3,4,5,6, 1,2,3,4,5,6
        .byte 0,1,2,3,4,5,6,7, 0,1,2,3,4,5,6,7
SLXO:   .byte 18,27,36,45, 9,18,27,36,45,54, 9,18,27,36,45,54
        .byte 0,9,18,27,36,45,54,63, 0,9,18,27,36,45,54,63
SLY:    .byte 50,50,50,50, 62,62,62,62,62,62, 74,74,74,74,74,74
        .byte 86,86,86,86,86,86,86,86, 98,98,98,98,98,98,98,98
SLTYPE: .byte 2,2,2,2, 1,1,1,1,1,1, 1,1,1,1,1,1
        .byte 0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0
ENTORD: .byte 16,17,18,19,20,21,22,23
        .byte 4,5,6,7,8,9,0,1
        .byte 10,11,12,13,14,15,2,3
        .byte 24,25,26,27,28,29,30,31

SIN64:  .byte $00,$0C,$19,$25,$31,$3C,$47,$51,$5A,$62,$6A,$70,$75,$7A,$7D,$7E
        .byte $7F,$7E,$7D,$7A,$75,$70,$6A,$62,$5A,$51,$47,$3C,$31,$25,$19,$0C
        .byte $00,$F4,$E7,$DB,$CF,$C4,$B9,$AF,$A6,$9E,$96,$90,$8B,$86,$83,$82
        .byte $81,$82,$83,$86,$8B,$90,$96,$9E,$A6,$AF,$B9,$C4,$CF,$DB,$E7,$F4

TUNE:   .byte 253,94,0,0,187,125,0,0,147,158,0,0,122,120,1,0
        .byte 147,158,0,0,122,52,2,0,100,152,0,1,108,211,0,0
        .byte 122,188,0,0,147,158,0,0,187,125,0,0,166,140,0,0
        .byte 147,158,0,0,122,120,1,0,90,236,3,0,0

STITLE: .byte "GALAXIA",0
S1:     .byte "DEFEND THE GALAXY!",0
S2:     .byte "FORM   DIVE",0
S3:     .byte "150    400",0
S4:     .byte " 80    160",0
S5:     .byte " 50    100",0
S6:     .byte "HIGH SCORE",0
S7:     .byte "ARROWS MOVE  SPACE FIRES",0
S8:     .byte "ESC QUITS",0
SPRESS: .byte "PRESS SPACE TO START",0
SUP:    .byte "1UP",0
SHIGH:  .byte "HIGH",0
SSTG:   .byte "STAGE",0
SSTAGE: .byte "STAGE ",0
SREADY: .byte "READY",0
SGOVER: .byte "GAME OVER",0
SNEWHI: .byte "NEW HIGH SCORE!",0

TLIST:  .byte 11,46
        .word S1
        .byte 15,60
        .word S2
        .byte 15,72
        .word S3
        .byte 15,88
        .word S4
        .byte 15,104
        .word S5
        .byte 12,124
        .word S6
        .byte 8,140
        .word S7
        .byte 15,176
        .word S8
        .byte $FF
HUDL:   .byte 1,0
        .word SUP
        .byte 25,0
        .word SHIGH
        .byte $FF

; ---- sprite art: 7 color pixels x 8 rows ----
; W=white  B/V=even pixel  O/G=odd pixel
ARTTAB: .word ART0,ART1,ART2,ART3,ART4,ART5
        .word ART6,ART7,ART8,ART9,ART10,ART11
ARTPAL: .byte $80,$80,$80,0,0,0,0,$80,$80,$80,$80,0
ART0:   .byte "...W..."     ; player
        .byte "...W..."
        .byte "..BWB.."
        .byte "O.WWW.O"
        .byte "W.WBW.W"
        .byte "WWWWWWW"
        .byte "WOWWWOW"
        .byte "W.O.O.W"
ART1:   .byte "..O.O.."     ; bee 1
        .byte "B..O..B"
        .byte "BB.W.BB"
        .byte "BBOWOBB"
        .byte ".BOWOB."
        .byte "..OWO.."
        .byte "..OWO.."
        .byte "...O..."
ART2:   .byte "..O.O.."     ; bee 2
        .byte "...O..."
        .byte "B..W..B"
        .byte "BBOWOBB"
        .byte "B.OWO.B"
        .byte "..OWO.."
        .byte "..OWO.."
        .byte "...O..."
ART3:   .byte "V.G.G.V"     ; butterfly 1
        .byte "VV.W.VV"
        .byte "VVVWVVV"
        .byte ".VWWWV."
        .byte ".VWWWV."
        .byte "VVVWVVV"
        .byte "VV.W.VV"
        .byte "V.....V"
ART4:   .byte "..G.G.."     ; butterfly 2
        .byte ".V.W.V."
        .byte ".VVWVV."
        .byte "..WWW.."
        .byte "..WWW.."
        .byte ".VVWVV."
        .byte ".V.W.V."
        .byte "......."
ART5:   .byte "..G.G.."     ; boss 1
        .byte "..GWG.."
        .byte ".GWWWG."
        .byte "GGWVWGG"
        .byte "GWWWWWG"
        .byte "G.GWG.G"
        .byte "G.G.G.G"
        .byte "..G.G.."
ART6:   .byte "..G.G.."     ; boss 2
        .byte "..GWG.."
        .byte ".GWWWG."
        .byte "GGWVWGG"
        .byte "GWWWWWG"
        .byte "GGGWGGG"
        .byte ".G.G.G."
        .byte "G..G..G"
ART7:   .byte "..B.B.."     ; boss damaged
        .byte "..BWB.."
        .byte ".BWWWB."
        .byte "BBWOWBB"
        .byte "BWWWWWB"
        .byte "B.BWB.B"
        .byte "B.B.B.B"
        .byte "..B.B.."
ART8:   .byte "......."     ; explosion 1
        .byte "......."
        .byte "...O..."
        .byte "..OWO.."
        .byte ".OWWWO."
        .byte "..OWO.."
        .byte "...O..."
        .byte "......."
ART9:   .byte "O..O..O"     ; explosion 2
        .byte ".O.W.O."
        .byte "..WOW.."
        .byte "OWO.OWO"
        .byte "..WOW.."
        .byte ".O.W.O."
        .byte "O..O..O"
        .byte "......."
ART10:  .byte "B.....B"     ; explosion 3
        .byte "...O..."
        .byte ".O...O."
        .byte "O..B..O"
        .byte ".O...O."
        .byte "...O..."
        .byte "B.....B"
        .byte "......."
ART11:  .byte "W..W..W"     ; ship burst
        .byte ".W.W.W."
        .byte "..WWW.."
        .byte "WWW.WWW"
        .byte "..WWW.."
        .byte ".W.W.W."
        .byte "W..W..W"
        .byte "..G.G.."

; ---- 5x7 font, ASCII 32-92 ([ = ship, \ = flag) ----
FONT:   .byte $00,$00,$00,$00,$00,$00,$00,$00
        .byte $08,$08,$08,$08,$08,$00,$08,$00
        .res 40,0
        .byte $08,$08,$04,$00,$00,$00,$00,$00
        .res 32,0
        .byte $00,$00,$00,$00,$0C,$08,$04,$00
        .byte $00,$00,$00,$3E,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$0C,$0C,$00
        .byte $00,$20,$10,$08,$04,$02,$00,$00
        .byte $1C,$22,$32,$2A,$26,$22,$1C,$00
        .byte $08,$0C,$08,$08,$08,$08,$1C,$00
        .byte $1C,$22,$20,$18,$04,$02,$3E,$00
        .byte $3E,$20,$10,$18,$20,$22,$1C,$00
        .byte $10,$18,$14,$12,$3E,$10,$10,$00
        .byte $3E,$02,$1E,$20,$20,$22,$1C,$00
        .byte $18,$04,$02,$1E,$22,$22,$1C,$00
        .byte $3E,$20,$10,$08,$04,$04,$04,$00
        .byte $1C,$22,$22,$1C,$22,$22,$1C,$00
        .byte $1C,$22,$22,$3C,$20,$10,$0C,$00
        .byte $00,$0C,$0C,$00,$0C,$0C,$00,$00
        .res 48,0
        .byte $08,$14,$22,$22,$3E,$22,$22,$00
        .byte $1E,$22,$22,$1E,$22,$22,$1E,$00
        .byte $1C,$22,$02,$02,$02,$22,$1C,$00
        .byte $1E,$22,$22,$22,$22,$22,$1E,$00
        .byte $3E,$02,$02,$1E,$02,$02,$3E,$00
        .byte $3E,$02,$02,$1E,$02,$02,$02,$00
        .byte $3C,$02,$02,$32,$22,$22,$3C,$00
        .byte $22,$22,$22,$3E,$22,$22,$22,$00
        .byte $1C,$08,$08,$08,$08,$08,$1C,$00
        .byte $20,$20,$20,$20,$20,$22,$1C,$00
        .byte $22,$12,$0A,$06,$0A,$12,$22,$00
        .byte $02,$02,$02,$02,$02,$02,$3E,$00
        .byte $22,$36,$2A,$2A,$22,$22,$22,$00
        .byte $22,$22,$26,$2A,$32,$22,$22,$00
        .byte $1C,$22,$22,$22,$22,$22,$1C,$00
        .byte $1E,$22,$22,$1E,$02,$02,$02,$00
        .byte $1C,$22,$22,$22,$2A,$12,$2C,$00
        .byte $1E,$22,$22,$1E,$0A,$12,$22,$00
        .byte $3C,$02,$02,$1C,$20,$20,$1E,$00
        .byte $3E,$08,$08,$08,$08,$08,$08,$00
        .byte $22,$22,$22,$22,$22,$22,$1C,$00
        .byte $22,$22,$22,$22,$22,$14,$08,$00
        .byte $22,$22,$22,$2A,$2A,$36,$22,$00
        .byte $22,$22,$14,$08,$14,$22,$22,$00
        .byte $22,$22,$14,$08,$08,$08,$08,$00
        .byte $3E,$20,$10,$08,$04,$02,$3E,$00
        .byte $08,$08,$1C,$1C,$3E,$2A,$00,$00
        .byte $02,$1E,$3E,$1E,$02,$02,$02,$00

; =============== VARIABLES ===============
RNG:    .res 2
HI0:    .res 1
HI1:    .res 1
HI2:    .res 1
SC0:    .res 1
SC1:    .res 1
SC2:    .res 1
NEXTL:  .res 1
LIVES:  .res 1
WAVE:   .res 1
WAVEB:  .res 1
SNDT:   .res 1
SNDP:   .res 1
SNDD:   .res 1
SNDN:   .res 1
SNDID:  .res 1
SSAVE:  .res 1
VCNT:   .res 1
VST:    .res 1
FRAME:  .res 1
FLAP:   .res 1
FORMX:  .res 1
FDIR:   .res 1
SWAYT:  .res 1
GIDX:   .res 1
GSET:   .res 1
LTIM:   .res 1
ENLEFT: .res 1
DIVET:  .res 1
DIVINT: .res 1
MAXDIV: .res 1
FIRECH: .res 1
ENTK:   .res 1
DIVK:   .res 1
KS:     .res 1
GSTATE: .res 1
GDONE:  .res 1
STT:    .res 1
MSGT:   .res 1
MSGON:  .res 1
MSGCOL: .res 1
MSGCS:  .res 1
MSGPL:  .res 1
MSGPH:  .res 1
MSGDUR: .res 1
P_X:    .res 1
P_ALIVE: .res 1
MTIM:   .res 1
MDIR:   .res 1
FIREQ:  .res 1
FCOOL:  .res 1
SCDIRTY: .res 1
LVDIRTY: .res 1
FBUD:   .res 1
EIX:    .res 1
PIX:    .res 1
BIX:    .res 1
XIX:    .res 1
KIX:    .res 1
SYNX:   .res 1
LIX:    .res 1
SX:     .res 1
SY:     .res 1
SS:     .res 1
BX:     .res 1
BY:     .res 1
BT:     .res 1
BML:    .res 1
BMR:    .res 1
TCOL:   .res 1
TROW:   .res 1
TMODE:  .res 1
TIDX:   .res 1
TI2:    .res 1
TCS:    .res 1
THGT:   .res 1
MK0:    .res 1
MK1:    .res 1
BB0:    .res 1
BB1:    .res 1
TFL:    .res 1
PSHP:   .res 1
PPAL:   .res 1
PSH:    .res 1
PROW:   .res 1
PAI:    .res 1
PB0:    .res 1
PB1:    .res 1
PB2:    .res 1
PPX:    .res 1
PCNT:   .res 1
TPER:   .res 1
TCNT:   .res 2
TREST:  .res 1
MSGBUF: .res 16
O_X:    .res NOBJ
O_Y:    .res NOBJ
O_S:    .res NOBJ
D_X:    .res NOBJ
D_Y:    .res NOBJ
D_S:    .res NOBJ
E_ST:   .res NEN
E_XF:   .res NEN
E_YF:   .res NEN
E_HD:   .res NEN
E_PP:   .res NEN
E_PC:   .res NEN
E_TR:   .res NEN
E_MIR:  .res NEN
E_HP:   .res NEN
EX_A:   .res NEXP
EX_K:   .res NEXP
EX_T:   .res NEXP
PB_ON:  .res 2
PB_X:   .res 2
PB_Y:   .res 2
PB_D:   .res 2
PB_DX:  .res 2
PB_DY:  .res 2
EB_ON:  .res NEB
EB_X:   .res NEB
EB_XF:  .res NEB
EB_VX:  .res NEB
EB_Y:   .res NEB
EB_D:   .res NEB
EB_DX:  .res NEB
EB_DY:  .res NEB
ST_C:   .res NSTAR
ST_R:   .res NSTAR
ST_B:   .res NSTAR
ST_V:   .res NSTAR
