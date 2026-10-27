; Fill HGR page 1 with stripes, wait for ESC, return to the agent
        .org $4000
start:  lda $C050       ; graphics
        lda $C052       ; full screen
        lda $C054       ; page 1
        lda $C057       ; hi-res
        lda #$20
        sta ptr+1
        lda #0
        sta ptr
        ldy #0
fill:   tya
        and #$7F
        sta (ptr),y
        iny
        bne fill
        inc ptr+1
        lda ptr+1
        cmp #$40
        bne fill
wait:   lda $C000
        bpl wait
        sta $C010
        cmp #$9B
        bne wait
        lda $C051       ; text
        rts
ptr = $FA
