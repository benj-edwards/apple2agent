; GALAXY RAIDERS - hi-res formation shooter
        .org $6000

ptr   = $60
src   = $62
strp  = $64
dst   = $66
col   = $68
cury  = $69
cnth  = $6A
bpage = $6B
bidx  = $6C
tmp   = $6D
tmp2  = $6E
tmp3  = $6F
b0    = $70
b1    = $71
b2    = $72
rnd   = $73
tcol  = $75
trow  = $76
tclr  = $77
tscale= $78
tpg   = $79
mask0 = $7A
mask1 = $7B
hib   = $7C
sidx  = $7D
gr    = $7E
scnt  = $7F
vprev = $80
vcount= $81
tshape= $82
eidx  = $83
ecount= $84
nolist= $85
fwait = $86
curE  = $87
dshape= $88

KBD     = $C000
KBDSTRB = $C010
SPKR    = $C030

NE    = 28
NSTAR = 16
NEB   = 5
PY    = 170

.macro PRINT saddr, c, r, clr, sc
        lda #<saddr
        sta strp
        lda #>saddr
        sta strp+1
        lda #c
        sta tcol
        lda #r
        sta trow
        lda #clr
        sta tclr
        lda #sc
        sta tscale
        jsr drawtext
.endmacro

start:
        cld
        sta $C000       ; 80STORE off so $C055 flips hi-res pages
        sta $C00C       ; 40 columns
        jsr maketables
        jsr preshift
        jsr makefont
        lda #$34
        sta rnd
        lda #$12
        sta rnd+1
        lda #0
        sta h0
        sta h1
        sta h2
        sta s0
        sta s1
        sta s2
        sta vcount
        sta vprev
        jmp title

quit:
        sta $C051
        sta $C054
        jmp $03D0

;---------------------------------------------------------------
; TITLE SCREEN
title:
        sta KBDSTRB
        lda #0
        sta bpage
        sta bidx
        sta tpg
        sta elcnt
        sta elcnt+1
        sta nolist
        sta totitle
        sta frame
        lda #$20
        jsr clrpage
        lda #$40
        jsr clrpage
        sta $C050
        sta $C057
        sta $C052
        sta $C054
        lda #<s_galaxy
        sta strp
        lda #>s_galaxy
        sta strp+1
        lda #2
        sta tcol
        lda #6
        sta trow
        jsr drawlogo
        PRINT s_raiders, 7, 46, 2, 2
        PRINT s_p150, 18, 76, 4, 1
        PRINT s_p80, 18, 92, 4, 1
        PRINT s_p50, 18, 108, 4, 1
        PRINT s_arrows, 7, 128, 0, 1
        PRINT s_space, 9, 140, 0, 1
        PRINT s_esc, 11, 184, 1, 1
        ldy #0
        lda h2
        jsr put2
        lda h1
        jsr put2
        lda h0
        jsr put2
        lda #0
        sta numbuf,y
        PRINT s_hi, 11, 170, 3, 1
        PRINT numbuf, 17, 170, 0, 1
        lda #2
        sta fwait
tloop:
        jsr waitframe
        inc frame
        jsr rand
        lda frame
        and #7
        bne @k
        jsr eraseall
        lda frame
        lsr
        lsr
        lsr
        and #1
        sta anim
        clc
        adc #5
        ldx #46
        ldy #76
        jsr drawspr
        lda anim
        clc
        adc #3
        ldx #46
        ldy #92
        jsr drawspr
        lda anim
        clc
        adc #1
        ldx #46
        ldy #108
        jsr drawspr
        lda frame
        and #31
        bne @k
        lda frame
        and #32
        beq @blank
        PRINT s_press, 6, 154, 3, 1
        jmp @k
@blank: PRINT s_blank, 6, 154, 3, 1
@k:     lda KBD
        bmi :+
        jmp tloop
:
        sta KBDSTRB
        and #$7F
        cmp #27
        bne :+
        jmp quit
:       cmp #' '
        beq newgame
        cmp #13
        beq newgame
        jmp tloop

;---------------------------------------------------------------
newgame:
        lda #0
        sta s0
        sta s1
        sta s2
        sta stage
        sta stgbin
        sta gover
        sta totitle
        sta elcnt
        sta elcnt+1
        sta nolist
        sta frame
        sta anim
        sta dir
        sta pstate
        sta cool
        sta bact
        sta bact+1
        sta fofs
        sta msgt
        sta lastkey
        ldx #NEB-1
:       sta ebact,x
        dex
        bpl :-
        ldx #31
:       sta sthi,x
        dex
        bpl :-
        lda #2
        sta lives
        lda #1
        sta fdir
        lda #62
        sta px
        lda #$20
        jsr clrpage
        lda #$40
        jsr clrpage
        jsr initstars
        lda #0
        sta tpg
        jsr hudstatic
        lda #$20
        sta tpg
        jsr hudstatic
        lda #2
        sta scd
        sta lvd
        lda #1
        sta bidx
        lda #$20
        sta bpage
        sta $C054
        lda #3
        sta fwait
        jsr nextwave

gameloop:
        jsr readinput
        jsr updplayer
        jsr updbullets
        jsr updspawn
        jsr startdive
        jsr updenemies
        jsr updeb
        jsr collide
        jsr updstars
        jsr updmsg
        lda totitle
        beq :+
        jmp title
:       jsr checkwave
        jsr eraseall
        jsr drawstars
        jsr drawmsg
        jsr drawhud
        jsr drawall
        jsr flip
        inc frame
        lda frame
        lsr
        lsr
        lsr
        and #1
        sta anim
        jmp gameloop

;---------------------------------------------------------------
nextwave:
        sed
        lda stage
        clc
        adc #1
        sta stage
        cld
        inc stgbin
        ldx #NE-1
@l:     lda #0
        sta est,x
        lda slotx,x
        sta eslx,x
        lda sloty,x
        sta esly,x
        lda etype0,x
        sta etype,x
        dex
        bpl @l
        lda #0
        sta si
        lda #50
        sta sptimer
        lda #60
        sta divetmr
        ; difficulty
        lda stgbin
        asl
        asl
        sta tmp
        lda #44
        sec
        sbc tmp
        bcc @d1
        cmp #12
        bcs @d2
@d1:    lda #12
@d2:    sta divedelay
        lda stgbin
        lsr
        clc
        adc #2
        cmp #7
        bcc :+
        lda #6
:       sta maxdiv
        lda stgbin
        asl
        clc
        adc stgbin
        adc #6
        cmp #48
        bcc :+
        lda #48
:       sta firerate
        ; message
        ldx #5
:       lda s_stage,x
        sta msgbuf,x
        dex
        bpl :-
        lda #' '
        sta msgbuf+5
        ldy #6
        lda stage
        jsr put2m
        lda #0
        sta msgbuf+8
        lda #<msgbuf
        sta msg1p
        lda #>msgbuf
        sta msg1p+1
        lda #12
        sta msgc1
        lda #3
        sta msgclr
        lda #0
        sta msg2p+1
        lda #50
        sta msgt
        lda #2
        sta lvd
        rts

put2m:  pha
        lsr
        lsr
        lsr
        lsr
        ora #$30
        sta msgbuf,y
        iny
        pla
        and #$0F
        ora #$30
        sta msgbuf,y
        iny
        rts

put2:   pha
        lsr
        lsr
        lsr
        lsr
        ora #$30
        sta numbuf,y
        iny
        pla
        and #$0F
        ora #$30
        sta numbuf,y
        iny
        rts

checkwave:
        lda gover
        bne @x
        lda si
        cmp #NE
        bcc @x
        ldx #NE-1
@l:     lda est,x
        bne @x
        dex
        bpl @l
        jmp nextwave
@x:     rts

;---------------------------------------------------------------
readinput:
        lda #0
        sta firereq
        sta firehold
        lda KBD
        bpl @held
        sta KBDSTRB
        and #$7F
        cmp #$61
        bcc :+
        and #$DF
:       cmp #27
        bne :+
        jmp quit
:       sta lastkey
        cmp #8
        beq @l
        cmp #'A'
        beq @l
        cmp #'J'
        beq @l
        cmp #21
        beq @r
        cmp #'D'
        beq @r
        cmp #'L'
        beq @r
        cmp #' '
        beq @f
        cmp #'P'
        beq @pause
        lda #0
        sta dir
        jmp @held
@l:     lda #$FF
        sta dir
        jmp @held
@r:     lda #1
        sta dir
        jmp @held
@f:     lda #1
        sta firereq
@held:  lda KBDSTRB
        bmi @down
        lda #0
        sta dir
        jmp @ap
@down:  lda lastkey
        cmp #' '
        bne @ap
        lda #1
        sta firehold
@ap:    lda $C061
        ora $C062
        bpl @x
        lda #1
        sta firehold
@x:     rts
@pause: lda KBD
        bpl @pause
        sta KBDSTRB
        cmp #$9B
        bne :+
        jmp quit
:       lda #0
        sta dir
        rts

;---------------------------------------------------------------
updplayer:
        lda pstate
        bne @dead
        lda dir
        beq @fire
        bmi @left
        lda px
        clc
        adc #2
        cmp #126
        bcc @s
        lda #125
        jmp @s
@left:  lda px
        sec
        sbc #2
        bcs @s
        lda #0
@s:     sta px
@fire:  lda cool
        beq @c0
        dec cool
        rts
@c0:    lda firereq
        ora firehold
        beq @x
        ldx #0
        lda bact
        beq @fb
        inx
        lda bact+1
        bne @x
@fb:    lda #1
        sta bact,x
        lda px
        clc
        adc #3
        sta bx,x
        lda #PY-6
        sta by,x
        lda #3
        sta cool
        jsr sndshot
@x:     rts
@dead:  cmp #1
        bne @wait
        dec ptimer
        bne @x
        lda #2
        sta pstate
        lda #45
        sta ptimer
        rts
@wait:  cmp #2
        bne @x
        dec ptimer
        bne @x
        lda lives
        bne @resp
        lda #3
        sta pstate
        lda #1
        sta gover
        lda #<s_gover
        sta msg1p
        lda #>s_gover
        sta msg1p+1
        lda #11
        sta msgc1
        lda #4
        sta msgclr
        lda #0
        sta msg2p+1
        lda #120
        sta msgt
        rts
@resp:  dec lives
        lda #2
        sta lvd
        lda #62
        sta px
        lda #0
        sta pstate
        sta dir
        lda #<s_ready
        sta msg1p
        lda #>s_ready
        sta msg1p+1
        lda #15
        sta msgc1
        lda #0
        sta msgclr
        sta msg2p+1
        lda #30
        sta msgt
        rts

updbullets:
        ldx #1
@l:     lda bact,x
        beq @n
        lda by,x
        sec
        sbc #8
        sta by,x
        cmp #12
        bcs @n
        lda #0
        sta bact,x
@n:     dex
        bpl @l
        rts

updeb:
        ldx #NEB-1
@l:     lda ebact,x
        beq @n
        lda eby,x
        clc
        adc #4
        sta eby,x
        cmp #178
        bcc @mv
@off:   lda #0
        sta ebact,x
        jmp @n
@mv:    lda frame
        and #3
        bne @n
        lda ebx,x
        clc
        adc ebdx,x
        sta ebx,x
        cmp #133
        bcs @off
@n:     dex
        bpl @l
        rts

;---------------------------------------------------------------
updspawn:
        lda si
        cmp #NE
        bcs @x
        dec sptimer
        bne @x
        ldx si
        lda epath0,x
        tay
        lda emir0,x
        sta emir,x
        bne @m
        lda paths,y
        jmp @sx
@m:     lda #132
        sec
        sbc paths,y
@sx:    sta ex,x
        lda paths+1,y
        sta ey,x
        tya
        clc
        adc #2
        sta epp,x
        lda #0
        sta etime,x
        sta ehp,x
        lda #1
        sta est,x
        lda etype,x
        cmp #2
        bne :+
        lda #1
        sta ehp,x
:       lda spdelay,x
        sta sptimer
        inc si
@x:     rts

startdive:
        lda si
        cmp #NE
        bcc @x
        lda pstate
        bne @x
        dec divetmr
        bne @x
        lda divedelay
        sta divetmr
        ldy #0
        ldx #NE-1
@c:     lda est,x
        cmp #3
        beq @d
        cmp #6
        bne @nc
@d:     iny
@nc:    dex
        bpl @c
        cpy maxdiv
        bcs @x
        jsr rand
        and #31
        cmp #NE
        bcc :+
        sbc #NE
:       tax
        ldy #NE
@s:     lda est,x
        cmp #2
        beq @go
        inx
        cpx #NE
        bcc :+
        ldx #0
:       dey
        bne @s
@x:     rts
@go:    lda #3
        sta est,x
        lda #DIVEP
        sta epp,x
        lda #0
        sta etime,x
        lda ex,x
        cmp #66
        lda #0
        rol
        sta emir,x
        rts

updenemies:
        lda frame
        and #3
        bne @ns
        lda fofs
        clc
        adc fdir
        sta fofs
        cmp #10
        beq @rev
        cmp #$F6
        bne @ns
@rev:   lda #0
        sec
        sbc fdir
        sta fdir
@ns:    ldx #NE-1
@loop:  lda est,x
        beq @next
        cmp #1
        beq @path
        cmp #3
        beq @path
        cmp #2
        beq @form
        cmp #5
        beq @home
        cmp #6
        beq @dive2
        dec etmr,x
        bne @next
        lda #0
        sta est,x
        jmp @next
@form:  lda eslx,x
        clc
        adc fofs
        sta ex,x
        lda esly,x
        sta ey,x
        jmp @next
@path:  jsr pathstep
        jmp @next
@home:  jsr homestep
        jmp @next
@dive2: jsr dive2step
@next:  dex
        bpl @loop
        rts

pathstep:
        lda etime,x
        bne @apply
        ldy epp,x
        lda paths+2,y
        beq @end
        sta etime,x
        lda paths+1,y
        sta edy,x
        lda paths,y
        sta edx,x
        lda emir,x
        beq @nm
        lda #0
        sec
        sbc edx,x
        sta edx,x
@nm:    lda epp,x
        clc
        adc #3
        sta epp,x
@apply: lda ex,x
        clc
        adc edx,x
        sta ex,x
        lda ey,x
        clc
        adc edy,x
        sta ey,x
        dec etime,x
        lda est,x
        cmp #3
        bne @r
        jsr maybefire
@r:     rts
@end:   lda est,x
        cmp #1
        bne @d
        lda #5
        sta est,x
        rts
@d:     lda #6
        sta est,x
        rts

homestep:
        lda eslx,x
        clc
        adc fofs
        sta tmp
        lda ex,x
        sec
        sbc tmp
        beq @y
        bmi @xneg
        cmp #3
        bcc @xset
        lda ex,x
        sec
        sbc #2
        sta ex,x
        jmp @y
@xneg:  cmp #$FE
        bcs @xset
        lda ex,x
        clc
        adc #2
        sta ex,x
        jmp @y
@xset:  lda tmp
        sta ex,x
@y:     lda ey,x
        sec
        sbc esly,x
        beq @yd
        bmi @yneg
        cmp #4
        bcc @yset
        lda ey,x
        sec
        sbc #3
        sta ey,x
        rts
@yneg:  cmp #$FD
        bcs @yset
        lda ey,x
        clc
        adc #3
        sta ey,x
        rts
@yset:  lda esly,x
        sta ey,x
@yd:    lda ex,x
        cmp tmp
        bne @r
        lda #2
        sta est,x
@r:     rts

dive2step:
        lda ey,x
        clc
        adc #4
        sta ey,x
        cmp #184
        bcc @mv
        lda #0
        sta ey,x
        lda eslx,x
        clc
        adc fofs
        sta ex,x
        lda #5
        sta est,x
        rts
@mv:    lda pstate
        bne @f
        lda ex,x
        cmp px
        beq @f
        bcc @inc
        dec ex,x
        jmp @f
@inc:   inc ex,x
@f:     jmp maybefire

maybefire:
        lda pstate
        bne @x
        jsr rand
        cmp firerate
        bcs @x
        lda ey,x
        cmp #120
        bcs @x
        ldy #NEB-1
@f:     lda ebact,y
        beq @got
        dey
        bpl @f
@x:     rts
@got:   lda #1
        sta ebact,y
        lda ex,x
        clc
        adc #3
        sta ebx,y
        lda ey,x
        clc
        adc #8
        sta eby,y
        lda #0
        sta ebdx,y
        lda px
        sec
        sbc ex,x
        bmi @neg
        cmp #6
        bcc @r
        lda #1
        sta ebdx,y
        rts
@neg:   cmp #$FA
        bcs @r
        lda #$FF
        sta ebdx,y
@r:     rts

;---------------------------------------------------------------
collide:
        ldy #1
@bl:    lda bact,y
        beq @bn
        ldx #NE-1
@el:    lda est,x
        beq @en
        cmp #4
        beq @en
        lda by,y
        sec
        sbc ey,x
        clc
        adc #5
        cmp #14
        bcs @en
        lda bx,y
        sec
        sbc ex,x
        cmp #7
        bcs @en
        lda #0
        sta bact,y
        jsr hitenemy
        jmp @bn
@en:    dex
        bpl @el
@bn:    dey
        bpl @bl
        ; player hits
        lda pstate
        bne @done
        ldx #NEB-1
@eb:    lda ebact,x
        beq @ebn
        lda eby,x
        sec
        sbc #PY-3
        cmp #11
        bcs @ebn
        lda ebx,x
        sec
        sbc px
        cmp #7
        bcs @ebn
        lda #0
        sta ebact,x
        jmp killplayer
@ebn:   dex
        bpl @eb
        ldx #NE-1
@dv:    lda est,x
        cmp #3
        beq @chk
        cmp #6
        bne @dn
@chk:   lda ey,x
        sec
        sbc #PY-7
        cmp #14
        bcs @dn
        lda ex,x
        sec
        sbc px
        clc
        adc #5
        cmp #11
        bcs @dn
        lda #4
        sta est,x
        lda #8
        sta etmr,x
        jmp killplayer
@dn:    dex
        bpl @dv
@done:  rts

killplayer:
        lda #1
        sta pstate
        lda #16
        sta ptimer
        jsr sndboom
        jmp sndboom

hitenemy:
        tya
        pha
        lda etype,x
        cmp #2
        bne @kill
        lda ehp,x
        beq @kill
        lda #0
        sta ehp,x
        jsr sndping
        jmp @r
@kill:  lda etype,x
        asl
        tay
        lda est,x
        cmp #3
        beq @dv
        cmp #6
        bne @nd
@dv:    iny
@nd:    lda ptlo,y
        sta tmp
        lda ptmid,y
        sta tmp2
        sed
        clc
        lda s0
        adc tmp
        sta s0
        lda s1
        adc tmp2
        sta s1
        lda s2
        adc #0
        sta s2
        cld
        lda #2
        sta scd
        lda #4
        sta est,x
        lda #8
        sta etmr,x
        jsr sndboom
@r:     pla
        tay
        rts

ptlo:   .byte $50,$00,$80,$60,$50,$00
ptmid:  .byte $00,$01,$00,$01,$01,$04

;---------------------------------------------------------------
updmsg:
        lda msgt
        beq @x
        dec msgt
        bne @x
        lda #88
        sta cury
        lda #24
        sta cnth
        jsr clrrows
        lda gover
        beq @x
        jsr updhi
        lda #1
        sta totitle
@x:     rts

updhi:
        lda s2
        cmp h2
        bcc @x
        bne @set
        lda s1
        cmp h1
        bcc @x
        bne @set
        lda s0
        cmp h0
        bcc @x
        beq @x
@set:   lda s0
        sta h0
        lda s1
        sta h1
        lda s2
        sta h2
@x:     rts

drawmsg:
        lda msgt
        beq @x
        lda bpage
        sta tpg
        lda msg1p
        sta strp
        lda msg1p+1
        sta strp+1
        lda msgc1
        sta tcol
        lda #88
        sta trow
        lda msgclr
        sta tclr
        lda #2
        sta tscale
        jsr drawtext
@x:     rts

hudstatic:
        PRINT s_1up, 0, 1, 4, 1
        PRINT s_hi, 23, 1, 1, 1
        ldy #0
        lda h2
        jsr put2
        lda h1
        jsr put2
        lda h0
        jsr put2
        lda #0
        sta numbuf,y
        PRINT numbuf, 28, 1, 0, 1
        rts

drawhud:
        lda bpage
        sta tpg
        lda scd
        beq @lv
        dec scd
        ldy #0
        lda s2
        jsr put2
        lda s1
        jsr put2
        lda s0
        jsr put2
        lda #0
        sta numbuf,y
        PRINT numbuf, 8, 1, 0, 1
@lv:    lda lvd
        bne :+
        rts
:       dec lvd
        ldx #183
@r:     lda rowlo,x
        sta ptr
        lda rowhi,x
        clc
        adc bpage
        sta ptr+1
        ldy #21
        lda #0
@c:     sta (ptr),y
        dey
        bpl @c
        inx
        cpx #191
        bne @r
        lda #1
        sta nolist
        lda #0
        sta tmp3
@li:    lda tmp3
        cmp lives
        bcs @ld
        cmp #5
        bcs @ld
        asl
        asl
        asl
        clc
        adc #1
        tax
        lda #0
        ldy #183
        jsr drawspr
        inc tmp3
        jmp @li
@ld:    lda #0
        sta nolist
        PRINT s_stage, 24, 184, 4, 1
        ldy #0
        lda stage
        jsr put2
        lda #0
        sta numbuf,y
        PRINT numbuf, 36, 184, 0, 1
        rts

; clear rows cury..+cnth on both pages
clrrows:
@r:     ldx cury
        lda rowlo,x
        sta ptr
        sta src
        lda rowhi,x
        sta ptr+1
        clc
        adc #$20
        sta src+1
        ldy #39
        lda #0
@c:     sta (ptr),y
        sta (src),y
        dey
        bpl @c
        inc cury
        dec cnth
        bne @r
        rts

;---------------------------------------------------------------
drawall:
        lda #0
        sta nolist
        lda pstate
        bne @pe
        lda #0
        ldx px
        ldy #PY
        jsr drawspr
        jmp @en
@pe:    cmp #1
        bne @en
        lda ptimer
        cmp #9
        lda #9
        bcs :+
        lda #10
:       ldx px
        ldy #PY
        jsr drawspr
@en:    ldx #0
@el:    stx curE
        lda est,x
        beq @nx
        cmp #4
        bne @alive
        lda etmr,x
        cmp #5
        lda #9
        bcs @d
        lda #10
        jmp @d
@alive: ldy etype,x
        lda typebase,y
        cpy #2
        bne :+
        ldy ehp,x
        bne :+
        lda #7
:       clc
        adc anim
@d:     sta dshape
        lda ex,x
        cmp #133
        bcs @nx
        lda ey,x
        cmp #10
        bcc @nx
        cmp #176
        bcs @nx
        tay
        lda ex,x
        tax
        lda dshape
        jsr drawspr
        ldx curE
@nx:    inx
        cpx #NE
        bne @el
        ldx #1
@bl:    stx curE
        lda bact,x
        beq @bn
        ldy by,x
        lda bx,x
        tax
        lda #11
        jsr drawspr
        ldx curE
@bn:    dex
        bpl @bl
        ldx #NEB-1
@ebl:   stx curE
        lda ebact,x
        beq @ebn
        ldy eby,x
        lda ebx,x
        tax
        lda #12
        jsr drawspr
        ldx curE
@ebn:   dex
        bpl @ebl
        rts

typebase: .byte 1,3,5

;---------------------------------------------------------------
initstars:
        ldx #NSTAR-1
@l:     jsr newstar
        jsr rand
        and #$7F
        sta tmp
        jsr rand
        and #$1F
        clc
        adc tmp
        adc #10
        sta sy,x
        dex
        bpl @l
        rts

newstar:
        jsr rand
        and #$1F
        sta tmp
        jsr rand
        and #7
        clc
        adc tmp
        sta sx,x
        jsr rand
        and #3
        clc
        adc #1
        sta sspd,x
        jsr rand
        and #7
        tay
        lda startab,y
        sta sbit,x
        rts

startab: .byte $01,$04,$10,$40,$82,$88,$A0,$06

updstars:
        ldx #NSTAR-1
@l:     lda sy,x
        clc
        adc sspd,x
        cmp #182
        bcc @s
        jsr newstar
        lda #10
@s:     sta sy,x
        dex
        bpl @l
        rts

drawstars:
        lda bidx
        beq :+
        lda #NSTAR
:       sta stbase
        tax
        lda #NSTAR
        sta ecount
@e:     lda sthi,x
        beq @en
        sta ptr+1
        lda stlo,x
        sta ptr
        ldy #0
        tya
        sta (ptr),y
@en:    inx
        dec ecount
        bne @e
        ldx #0
@d:     ldy sy,x
        lda rowlo,y
        clc
        adc sx,x
        sta ptr
        lda rowhi,y
        adc bpage
        sta ptr+1
        txa
        clc
        adc stbase
        tay
        lda ptr
        sta stlo,y
        lda ptr+1
        sta sthi,y
        ldy #0
        lda (ptr),y
        ora sbit,x
        sta (ptr),y
        inx
        cpx #NSTAR
        bne @d
        rts

;---------------------------------------------------------------
; sound
sndshot:
        ldy #26
@l:     lda SPKR
        tya
        asl
        tax
@d:     dex
        bne @d
        dey
        bne @l
        rts

sndping:
        ldy #40
@l:     lda SPKR
        ldx #18
@d:     dex
        bne @d
        dey
        bne @l
        rts

sndboom:
        ldy #140
@l:     jsr rand
        bpl :+
        bit SPKR
:       tya
        eor #$FF
        lsr
        lsr
        lsr
        lsr
        tax
        inx
@d:     dex
        bne @d
        dey
        bne @l
        rts

rand:
        lda rnd+1
        lsr
        lda rnd
        ror
        eor rnd+1
        sta rnd+1
        ror
        eor rnd
        sta rnd
        eor rnd+1
        rts

;---------------------------------------------------------------
; frame sync
vblpoll:
        lda $C019
        and #$80
        cmp vprev
        beq @x
        sta vprev
        and #$80
        bne @x
        inc vcount
@x:     rts

waitframe:
@w:     jsr vblpoll
        lda vcount
        cmp fwait
        bcc @w
        lda vprev
        bne @w
        lda #0
        sta vcount
        rts

flip:
        jsr waitframe
        lda bidx
        bne @p2
        sta $C054
        jmp @t
@p2:    sta $C055
@t:     lda bidx
        eor #1
        sta bidx
        lda bpage
        eor #$20
        sta bpage
        rts

;---------------------------------------------------------------
clrpage:
        sta ptr+1
        lda #0
        sta ptr
        ldx #$20
        ldy #0
@c:     sta (ptr),y
        iny
        bne @c
        inc ptr+1
        dex
        bne @c
        rts

; A=shape X=xh Y=y
drawspr:
        sta tshape
        sty cury
        lda coltab,x
        sta col
        lda shtab,x
        sta tmp
        lda tshape
        asl
        asl
        asl
        sec
        sbc tshape
        clc
        adc tmp
        tax
        lda sprlo,x
        sta src
        lda sprhi,x
        sta src+1
        ldx tshape
        lda shph,x
        sta cnth
        lda nolist
        bne @draw
        ldx bidx
        lda elcnt,x
        cmp #64
        bcc :+
        rts
:       inc elcnt,x
        clc
        adc elbase,x
        tax
        lda col
        sta elcol,x
        lda cury
        sta ely,x
        lda cnth
        sta elh,x
@draw:  jsr vblpoll
        ldy #0
@row:   ldx cury
        sty tmp
        lda rowlo,x
        clc
        adc col
        sta ptr
        lda rowhi,x
        adc bpage
        sta ptr+1
        lda ptr
        sec
        sbc tmp
        sta ptr
        bcs :+
        dec ptr+1
:       lda (src),y
        ora (ptr),y
        sta (ptr),y
        iny
        lda (src),y
        ora (ptr),y
        sta (ptr),y
        iny
        lda (src),y
        ora (ptr),y
        sta (ptr),y
        iny
        inc cury
        dec cnth
        bne @row
        rts

elbase: .byte 0,64

eraseall:
        ldx bidx
        lda elcnt,x
        bne :+
        rts
:       sta ecount
        lda elbase,x
        sta eidx
        lda #0
        sta elcnt,x
@el:    jsr vblpoll
        ldx eidx
        lda elcol,x
        sta col
        lda elh,x
        sta cnth
        ldy ely,x
@er:    lda rowlo,y
        clc
        adc col
        sta ptr
        lda rowhi,y
        adc bpage
        sta ptr+1
        sty tmp
        ldy #0
        lda #0
        sta (ptr),y
        iny
        sta (ptr),y
        iny
        sta (ptr),y
        ldy tmp
        iny
        dec cnth
        bne @er
        inc eidx
        dec ecount
        bne @el
        rts

;---------------------------------------------------------------
; text: strp tcol trow tclr tscale tpg
drawtext:
        ldx tclr
        lda chb,x
        sta hib
        lda tcol
        and #1
        bne @odd
        lda cme,x
        sta mask0
        lda cmo,x
        sta mask1
        jmp @go
@odd:   lda cmo,x
        sta mask0
        lda cme,x
        sta mask1
@go:    lda #0
        sta sidx
@ch:    jsr vblpoll
        ldy sidx
        lda (strp),y
        bne :+
        rts
:       sec
        sbc #32
        sta src
        lda #0
        sta src+1
        asl src
        rol src+1
        asl src
        rol src+1
        asl src
        rol src+1
        asl src
        rol src+1
        lda src
        clc
        adc #<fontbuf
        sta src
        lda src+1
        adc #>fontbuf
        sta src+1
        lda trow
        sta cury
        lda #0
        sta gr
@row:   lda tscale
        sta scnt
@rep:   ldx cury
        lda rowlo,x
        clc
        adc tcol
        sta ptr
        lda rowhi,x
        adc tpg
        sta ptr+1
        ldy gr
        lda (src),y
        and mask0
        ora hib
        ldy #0
        sta (ptr),y
        ldy gr
        iny
        lda (src),y
        and mask1
        ora hib
        ldy #1
        sta (ptr),y
        inc cury
        dec scnt
        bne @rep
        lda gr
        clc
        adc #2
        sta gr
        cmp #16
        bne @row
        lda tcol
        clc
        adc #2
        sta tcol
        inc sidx
        jmp @ch

; 0 white 1 violet 2 green 3 blue 4 orange
cme:    .byte $7F,$55,$2A,$55,$2A
cmo:    .byte $7F,$2A,$55,$2A,$55
chb:    .byte $00,$00,$00,$80,$80

; big logo: each font pixel = 1 byte x 4 rows
drawlogo:
        lda #0
        sta sidx
@ch:    ldy sidx
        lda (strp),y
        bne :+
        rts
:       sec
        sbc #32
        sta tmp
        lda #0
        sta src+1
        lda tmp
        asl
        rol src+1
        asl
        rol src+1
        asl
        rol src+1
        sec
        sbc tmp
        sta src
        lda src+1
        sbc #0
        sta src+1
        lda src
        clc
        adc #<fontraw
        sta src
        lda src+1
        adc #>fontraw
        sta src+1
        lda trow
        sta cury
        lda #0
        sta gr
@fr:    ldx gr
        lda logoclr,x
        sta tclr
        ldy gr
        lda (src),y
        asl
        asl
        asl
        sta tmp2
        lda #4
        sta scnt
@sub:   ldx cury
        lda rowlo,x
        clc
        adc tcol
        sta ptr
        lda rowhi,x
        adc tpg
        sta ptr+1
        lda tmp2
        sta tmp3
        ldy #0
@px:    asl tmp3
        lda #0
        bcc @st
        ldx tclr
        tya
        clc
        adc tcol
        and #1
        bne @o
        lda cme,x
        ora chb,x
        jmp @st
@o:     lda cmo,x
        ora chb,x
@st:    sta (ptr),y
        iny
        cpy #5
        bne @px
        inc cury
        dec scnt
        bne @sub
        inc cury
        inc gr
        lda gr
        cmp #7
        bne @fr
        lda tcol
        clc
        adc #6
        sta tcol
        inc sidx
        jmp @ch

logoclr: .byte 4,4,0,0,3,3,1

;---------------------------------------------------------------
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
        lsr
        and #3
        clc
        adc tmp
        adc #$20
        sta rowhi,y
        tya
        and #8
        beq :+
        lda #$80
:       sta tmp
        tya
        lsr
        lsr
        lsr
        lsr
        lsr
        lsr
        tax
        lda mul28,x
        clc
        adc tmp
        sta rowlo,y
        iny
        cpy #192
        bne @r
        ldx #0
        lda #0
        sta tmp
        sta tmp2
@c:     lda tmp
        sta coltab,x
        lda tmp2
        sta shtab,x
        lda tmp2
        clc
        adc #2
        cmp #7
        bcc :+
        sbc #7
        inc tmp
:       sta tmp2
        inx
        cpx #140
        bne @c
        rts
mul28:  .byte 0,$28,$50

shift1:
        asl b0
        asl b1
        asl b2
        lda b1
        bpl :+
        inc b2
        and #$7F
        sta b1
:       lda b0
        bpl :+
        inc b1
        and #$7F
        sta b0
:       rts

preshift:
        lda #<sprbuf
        sta dst
        lda #>sprbuf
        sta dst+1
        lda #0
        sta tshape
        sta tmp3
@s:     lda #0
        sta tmp2
@h:     ldx tmp3
        lda dst
        sta sprlo,x
        lda dst+1
        sta sprhi,x
        lda tshape
        asl
        asl
        asl
        asl
        sta src
        lda #0
        sta cury
@r:     lda cury
        asl
        clc
        adc src
        tax
        lda rawspr,x
        sta b0
        lda rawspr+1,x
        sta b1
        lda #0
        sta b2
        ldx tmp2
        beq @ns
@sh:    jsr shift1
        dex
        bne @sh
@ns:    ldx tshape
        lda shpal,x
        sta hib
        ldy #0
        lda b0
        beq :+
        ora hib
:       sta (dst),y
        iny
        lda b1
        beq :+
        ora hib
:       sta (dst),y
        iny
        lda b2
        beq :+
        ora hib
:       sta (dst),y
        lda dst
        clc
        adc #3
        sta dst
        bcc :+
        inc dst+1
:       inc cury
        lda cury
        cmp #8
        bne @r
        inc tmp3
        inc tmp2
        lda tmp2
        cmp #7
        bne @h
        inc tshape
        lda tshape
        cmp #NSHAPE
        beq :+
        jmp @s
:       rts

makefont:
        lda #<fontbuf
        sta dst
        lda #>fontbuf
        sta dst+1
        lda #<fontraw
        sta src
        lda #>fontraw
        sta src+1
        lda #59
        sta tmp3
@g:     lda #0
        sta cury
@r:     ldy cury
        lda (src),y
        sta tmp
        lda #0
        sta b0
        sta b1
        ldx #0
@j:     lda tmp
        and bitj,x
        beq @nj
        lda b0
        ora dlo,x
        sta b0
        lda b1
        ora dhi,x
        sta b1
@nj:    inx
        cpx #5
        bne @j
        lda cury
        asl
        tay
        lda b0
        and #$7F
        sta (dst),y
        lda b0
        asl
        lda b1
        rol
        and #$7F
        iny
        sta (dst),y
        inc cury
        lda cury
        cmp #7
        bne @r
        ldy #14
        lda #0
        sta (dst),y
        iny
        sta (dst),y
        lda src
        clc
        adc #7
        sta src
        bcc :+
        inc src+1
:       lda dst
        clc
        adc #16
        sta dst
        bcc :+
        inc dst+1
:       dec tmp3
        beq :+
        jmp @g
:       rts
dlo:    .byte $0C,$30,$C0,$00,$00
dhi:    .byte $00,$00,$00,$03,$0C
bitj:   .byte $10,$08,$04,$02,$01

;---------------------------------------------------------------
s_galaxy: .byte "GALAXY",0
s_raiders: .byte "R A I D E R S",0
s_p150:  .byte "150 PTS",0
s_p80:   .byte " 80 PTS",0
s_p50:   .byte " 50 PTS",0
s_arrows: .byte "ARROWS: MOVE",0
s_space: .byte "SPACE: FIRE",0
s_esc:   .byte "ESC QUITS",0
s_press: .byte "PRESS SPACE !",0
s_blank: .byte "             ",0
s_hi:    .byte "HI",0
s_1up:   .byte "1UP",0
s_stage: .byte "STAGE",0
s_gover: .byte "GAME OVER",0
s_ready: .byte "READY",0

;---------------------------------------------------------------
NSHAPE = 13
PATHA = 0
PATHB = 32
DIVEP = 69
rawspr:
        .byte $40,$01,$40,$01,$70,$06,$48,$11,$7E,$5F,$4F,$79,$43,$61,$02,$40
        .byte $08,$10,$60,$05,$7A,$57,$72,$46,$70,$07,$78,$16,$42,$41,$00,$00
        .byte $08,$10,$60,$05,$70,$07,$7A,$56,$7A,$57,$78,$16,$40,$01,$00,$00
        .byte $05,$28,$15,$2A,$54,$0B,$70,$07,$54,$0B,$15,$2A,$05,$28,$00,$00
        .byte $00,$00,$05,$28,$55,$2B,$70,$07,$55,$2B,$05,$28,$00,$00,$00,$00
        .byte $60,$05,$78,$17,$5E,$5B,$7E,$5F,$62,$45,$4A,$51,$22,$44,$00,$00
        .byte $60,$05,$78,$17,$5E,$5B,$7E,$5F,$68,$15,$42,$41,$08,$10,$00,$00
        .byte $60,$05,$78,$17,$5E,$5B,$7E,$5F,$62,$45,$4A,$51,$22,$44,$00,$00
        .byte $60,$05,$78,$17,$5E,$5B,$7E,$5F,$68,$15,$42,$41,$08,$10,$00,$00
        .byte $00,$00,$20,$04,$48,$11,$70,$07,$48,$11,$20,$04,$00,$00,$00,$00
        .byte $42,$41,$08,$10,$00,$01,$4B,$71,$00,$01,$08,$10,$42,$41,$00,$00
        .byte $03,$00,$03,$00,$03,$00,$03,$00,$03,$00,$03,$00,$00,$00,$00,$00
        .byte $02,$00,$03,$00,$03,$00,$02,$00,$00,$00,$00,$00,$00,$00,$00,$00
shph:
        .byte $08,$08,$08,$08,$08,$08,$08,$08,$08,$08,$08,$06,$04
shpal:
        .byte $80,$80,$80,$00,$00,$00,$00,$80,$80,$80,$80,$00,$80
fontraw:
        .byte $00,$00,$00,$00,$00,$00,$00,$04,$04,$04,$04,$04,$00,$04,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$1F,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$0C,$0C,$00,$00,$00,$00,$00,$00,$00
        .byte $0E,$11,$13,$15,$19,$11,$0E,$04,$0C,$04,$04,$04,$04,$0E,$0E,$11
        .byte $01,$06,$08,$10,$1F,$1F,$01,$02,$06,$01,$11,$0E,$02,$06,$0A,$12
        .byte $1F,$02,$02,$1F,$10,$1E,$01,$01,$11,$0E,$06,$08,$10,$1E,$11,$11
        .byte $0E,$1F,$01,$02,$04,$08,$08,$08,$0E,$11,$11,$0E,$11,$11,$0E,$0E
        .byte $11,$11,$0F,$01,$02,$0C,$00,$0C,$0C,$00,$0C,$0C,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$1F,$00,$1F
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$0E,$11,$11,$1F,$11,$11,$11,$1E,$11
        .byte $11,$1E,$11,$11,$1E,$0E,$11,$10,$10,$10,$11,$0E,$1E,$11,$11,$11
        .byte $11,$11,$1E,$1F,$10,$10,$1E,$10,$10,$1F,$1F,$10,$10,$1E,$10,$10
        .byte $10,$0E,$11,$10,$17,$11,$11,$0F,$11,$11,$11,$1F,$11,$11,$11,$0E
        .byte $04,$04,$04,$04,$04,$0E,$07,$02,$02,$02,$02,$12,$0C,$11,$12,$14
        .byte $18,$14,$12,$11,$10,$10,$10,$10,$10,$10,$1F,$11,$1B,$15,$15,$11
        .byte $11,$11,$11,$11,$19,$15,$13,$11,$11,$0E,$11,$11,$11,$11,$11,$0E
        .byte $1E,$11,$11,$1E,$10,$10,$10,$0E,$11,$11,$11,$15,$12,$0D,$1E,$11
        .byte $11,$1E,$14,$12,$11,$0F,$10,$10,$0E,$01,$01,$1E,$1F,$04,$04,$04
        .byte $04,$04,$04,$11,$11,$11,$11,$11,$11,$0E,$11,$11,$11,$11,$11,$0A
        .byte $04,$11,$11,$11,$15,$15,$15,$0A,$11,$11,$0A,$04,$0A,$11,$11,$11
        .byte $11,$0A,$04,$04,$04,$04,$1F,$01,$02,$04,$08,$10,$1F
paths:
        .byte $38,$00,$00,$04,$08,$01,$04,$06,$02,$03,$06,$03,$01,$05,$03,$FF
        .byte $05,$02,$FD,$06,$00,$FC,$05,$FE,$FD,$05,$FD,$FF,$04,$00,$00,$00
        .byte $FA,$96,$03,$00,$08,$03,$FE,$06,$02,$FC,$06,$00,$FC,$06,$FE,$FC
        .byte $05,$FD,$FE,$05,$FD,$01,$04,$FF,$03,$05,$01,$04,$04,$03,$02,$04
        .byte $00,$00,$00,$00,$00,$00,$FD,$03,$FF,$FE,$03,$FE,$00,$03,$FE,$02
        .byte $03,$FF,$03,$03,$00,$04,$04,$01,$04,$04,$00,$00,$00
slotx:
        .byte $35,$3E,$47,$50,$23,$2C,$35,$3E,$47,$50,$59,$62,$23,$2C,$35,$3E
        .byte $47,$50,$59,$62,$23,$2C,$35,$3E,$47,$50,$59,$62
sloty:
        .byte $12,$12,$12,$12,$1E,$1E,$1E,$1E,$1E,$1E,$1E,$1E,$2A,$2A,$2A,$2A
        .byte $2A,$2A,$2A,$2A,$36,$36,$36,$36,$36,$36,$36,$36
etype0:
        .byte $02,$02,$02,$02,$01,$01,$01,$01,$01,$01,$01,$01,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
epath0:
        .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$20,$20
        .byte $20,$20,$20,$20,$20,$20,$20,$20,$20,$20,$20,$20
emir0:
        .byte $00,$00,$00,$00,$00,$00,$00,$01,$01,$01,$01,$01,$01,$01,$00,$00
        .byte $00,$00,$00,$00,$00,$01,$01,$01,$01,$01,$01,$01
spdelay:
        .byte $04,$04,$04,$04,$04,$04,$1E,$04,$04,$04,$04,$04,$04,$1E,$04,$04
        .byte $04,$04,$04,$04,$1E,$04,$04,$04,$04,$04,$04,$1E

;---------------------------------------------------------------
; variables
h0: .res 1
h1: .res 1
h2: .res 1
s0: .res 1
s1: .res 1
s2: .res 1
stage: .res 1
stgbin: .res 1
lives: .res 1
gover: .res 1
totitle: .res 1
frame: .res 1
anim: .res 1
dir: .res 1
firereq: .res 1
firehold: .res 1
lastkey: .res 1
cool: .res 1
px: .res 1
pstate: .res 1
ptimer: .res 1
si: .res 1
sptimer: .res 1
divetmr: .res 1
divedelay: .res 1
maxdiv: .res 1
firerate: .res 1
fofs: .res 1
fdir: .res 1
msgt: .res 1
msg1p: .res 2
msg2p: .res 2
msgc1: .res 1
msgclr: .res 1
scd: .res 1
lvd: .res 1
stbase: .res 1
numbuf: .res 8
msgbuf: .res 10
bx: .res 2
by: .res 2
bact: .res 2
ebx: .res NEB
eby: .res NEB
ebact: .res NEB
ebdx: .res NEB
ex: .res NE
ey: .res NE
est: .res NE
etype: .res NE
eslx: .res NE
esly: .res NE
epp: .res NE
etime: .res NE
edx: .res NE
edy: .res NE
emir: .res NE
etmr: .res NE
ehp: .res NE
sx: .res NSTAR
sy: .res NSTAR
sspd: .res NSTAR
sbit: .res NSTAR
stlo: .res 32
sthi: .res 32
elcnt: .res 2
elcol: .res 128
ely: .res 128
elh: .res 128
rowlo: .res 192
rowhi: .res 192
coltab: .res 140
shtab: .res 140
sprlo: .res 96
sprhi: .res 96
fontbuf: .res 944
sprbuf: .res 2184
