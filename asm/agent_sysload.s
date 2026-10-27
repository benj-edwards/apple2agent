;===============================================================================
; AGENT.SYSTEM loader
;
; ProDOS loads AGENT.SYSTEM at $2000 and jumps here. Copy the agent image
; (stored right after this page) up to $6000 where it was linked to run,
; then start it. Copies from the top down so it stays correct even if the
; image ever grows enough to overlap its destination.
;===============================================================================

        .setcpu "6502"

        .import __STARTUP_LOAD__, __STARTUP_RUN__
        .import __DATA_LOAD__, __DATA_SIZE__
        .import start

IMAGE_LEN = __DATA_LOAD__ + __DATA_SIZE__ - __STARTUP_LOAD__

src             = $FA
dst             = $FC
count           = $FE

        .segment "SYSLOAD"

sysload:
        cld
        lda #<(__STARTUP_LOAD__ + IMAGE_LEN)
        sta src
        lda #>(__STARTUP_LOAD__ + IMAGE_LEN)
        sta src+1
        lda #<(__STARTUP_RUN__ + IMAGE_LEN)
        sta dst
        lda #>(__STARTUP_RUN__ + IMAGE_LEN)
        sta dst+1
        lda #<IMAGE_LEN
        sta count
        lda #>IMAGE_LEN
        sta count+1
        ldy #0
@copy:
        lda src                 ; src--
        bne :+
        dec src+1
:       dec src
        lda dst                 ; dst--
        bne :+
        dec dst+1
:       dec dst
        lda (src),y
        sta (dst),y
        lda count               ; count--
        bne :+
        dec count+1
:       dec count
        lda count
        ora count+1
        bne @copy
        jmp start
