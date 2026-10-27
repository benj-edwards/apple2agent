; Prints a character then crashes into a BRK - should come back as FIX: ...
        .org $0900
start:  lda #$C1
        jsr $FDED
        brk
        .byte 0
