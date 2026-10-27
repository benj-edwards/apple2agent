        .org $0800
start:  sta $C000
        sta $C050
        sta $C057
        sta $C052
        sta $C054
        lda #1
        sta $64         ; bidx: 1 = draw page 2
@loop:  lda $64
        beq @p1
        lda #$40
        bne @g
@p1:    lda #$20
@g:     sta $65         ; page base hi
        ; clear hidden page
        sta $61
        lda #0
        sta $60
        ldx #$20
        ldy #0
@c:     sta ($60),y
        iny
        bne @c
        inc $61
        dex
        bne @c
        ; slow fill with white
        lda $65
        sta $61
        ldx #$20
        ldy #0
@f:     lda #$7F
        sta ($60),y
        lda #3
@d:     sec
        sbc #1
        bne @d
        iny
        bne @f
        inc $61
        dex
        bne @f
        ; wait for start of VBL
@w1:    lda $C019
        bpl @w1
@w2:    lda $C019
        bmi @w2
        lda $64
        bne @s2
        sta $C054
        jmp @t
@s2:    sta $C055
@t:     lda $64
        eor #1
        sta $64
        lda $C000
        bpl @loop
        sta $C010
        sta $C051
        sta $C054
        rts
