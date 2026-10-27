; Test program: machine code above $6000 that changes itself.
; Shows how many times this copy has run: 1 on a fresh copy, 2 if /RUN
; replayed memory the last run had modified. Any key returns.
        .org $7000
start:  inc counter
        lda counter
        ora #$B0                ; "1", "2", ...
        sta $0400               ; top-left corner of the text screen
:       lda $C000
        bpl :-
        bit $C010
        rts
counter: .byte 0
