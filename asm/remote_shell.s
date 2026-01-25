;===============================================================================
; REMOTE SHELL - Claude's Remote Control for Apple IIe
; Auto-connects to proxy, receives commands, executes them, loops forever
; No user input needed - fully autonomous
;
; Protocol:
;   Apple II sends: "READY\r\n"
;   Proxy sends: "P xxxx\r\n" (PEEK) or "O xxxx,yy\r\n" (POKE) or "C xxxx\r\n" (CALL)
;   Apple II sends: "OK xx\r\n" (result) or "OK\r\n" (for POKE/CALL)
;
; Configuration:
;   Loads CONFIG.DAT from disk if present, otherwise uses defaults.
;   Use CONFIG utility to set server IP and port.
;===============================================================================

        .setcpu "6502"

.include "../libs/ip65/inc/common.inc"
.include "../libs/ip65/inc/commonprint.inc"
.include "../libs/ip65/inc/net.inc"

.export start

.import exit_to_basic
.import print_a
.import ip65_process
.import tcp_connect
.import tcp_connect_ip
.import tcp_callback
.import tcp_close
.import tcp_send
.import tcp_send_data_len
.import tcp_inbound_data_ptr
.import tcp_inbound_data_length
.import print_cr
.importzp copy_src

;-------------------------------------------------------------------------------
; ProDOS MLI
;-------------------------------------------------------------------------------
MLI         = $BF00
CMD_OPEN    = $C8
CMD_READ    = $CA
CMD_CLOSE   = $CC

;-------------------------------------------------------------------------------
; Configuration
; Default values (used if no runtime config at $5F00)
;-------------------------------------------------------------------------------
DEFAULT_IP_1   = 192
DEFAULT_IP_2   = 168
DEFAULT_IP_3   = 65
DEFAULT_IP_4   = 1
DEFAULT_PORT   = 8080

;-------------------------------------------------------------------------------
; Runtime config memory location (set by BASIC loader)
; $5F00 = IP octet 1
; $5F01 = IP octet 2
; $5F02 = IP octet 3
; $5F03 = IP octet 4
; $5F04 = Port low byte
; $5F05 = Port high byte
; $5F06 = Magic number (42 = config valid)
;-------------------------------------------------------------------------------
CONFIG_IP     = $5F00
CONFIG_PORT   = $5F04
CONFIG_MAGIC  = $5F06
MAGIC_VALUE   = 42

;-------------------------------------------------------------------------------
; Zero page
;-------------------------------------------------------------------------------
ptr          = $06

; keep LD65 happy
.segment "INIT"
.segment "ONCE"

.segment "STARTUP"

start:
        ; Print banner
        ldax #str_banner
        jsr print
        jsr print_cr

        ; Try to load config from disk
        jsr load_config

        ; Initialize network
        ldax #str_init
        jsr print
        init_ip_via_dhcp
        bcc @net_ok

        ldax #str_fail
        jsr print
        jmp exit_to_basic

@net_ok:
        jsr print_cr
        jsr print_ip_config
        jsr print_cr

;-------------------------------------------------------------------------------
; Main loop - connect and process commands
;-------------------------------------------------------------------------------
main_loop:
        ldax #str_connecting
        jsr print

        ; Check for runtime config (magic number at $5F06)
        lda CONFIG_MAGIC
        cmp #MAGIC_VALUE
        beq @use_runtime_config

        ; Use default config
        lda #DEFAULT_IP_1
        sta tcp_connect_ip
        lda #DEFAULT_IP_2
        sta tcp_connect_ip+1
        lda #DEFAULT_IP_3
        sta tcp_connect_ip+2
        lda #DEFAULT_IP_4
        sta tcp_connect_ip+3
        lda #<DEFAULT_PORT
        sta connect_port
        lda #>DEFAULT_PORT
        sta connect_port+1
        jmp @do_connect

@use_runtime_config:
        ; Load IP from $5F00-$5F03
        lda CONFIG_IP
        sta tcp_connect_ip
        lda CONFIG_IP+1
        sta tcp_connect_ip+1
        lda CONFIG_IP+2
        sta tcp_connect_ip+2
        lda CONFIG_IP+3
        sta tcp_connect_ip+3
        ; Load port from $5F04-$5F05
        lda CONFIG_PORT
        sta connect_port
        lda CONFIG_PORT+1
        sta connect_port+1

@do_connect:
        ; Set callback
        ldax #recv_callback
        stax tcp_callback

        ; Connect using stored port
        lda connect_port
        ldx connect_port+1
        jsr tcp_connect
        bcc @connected

        ldax #str_conn_fail
        jsr print
        jsr print_cr

        ; Wait and retry
        jsr delay
        jmp main_loop

@connected:
        ldax #str_connected
        jsr print
        jsr print_cr

        ; Clear state
        lda #0
        sta got_data
        sta cmd_len

;-------------------------------------------------------------------------------
; Command loop - send READY, get command, execute, repeat
;-------------------------------------------------------------------------------
cmd_loop:
        ; Send READY
        ldax #ready_msg
        stax tcp_send_data_len
        lda #7              ; "READY\r\n"
        sta tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1
        ldax #ready_msg
        jsr tcp_send
        bcs @send_err

        ; Wait for command
        lda #0
        sta got_data
        sta timeout_lo
        sta timeout_hi

@wait_cmd:
        jsr ip65_process

        lda got_data
        bne @process_cmd

        inc timeout_lo
        bne @wait_cmd
        inc timeout_hi
        lda timeout_hi
        cmp #$20            ; Timeout
        bcc @wait_cmd

        ; Timeout - reconnect
        jsr tcp_close
        jmp main_loop

@send_err:
        jsr tcp_close
        jmp main_loop

@process_cmd:
        ; Command in cmd_buffer, length in cmd_len
        ; First byte is command type: P=PEEK, O=POKE, C=CALL, Q=QUIT

        lda cmd_buffer
        cmp #'P'
        beq @do_peek
        cmp #'O'
        beq @do_poke
        cmp #'C'
        beq @do_call
        cmp #'Q'
        beq @do_quit

        ; Unknown command - send error and continue
        jmp cmd_loop

@do_peek:
        jsr parse_address   ; Address in ptr
        ldy #0
        lda (ptr),y
        jsr send_byte_result
        jsr tcp_flush       ; Ensure data sent before READY
        jmp cmd_loop

@do_poke:
        jsr parse_address   ; Address in ptr
        jsr parse_value     ; Value in A
        ldy #0
        sta (ptr),y
        jsr send_ok
        jsr tcp_flush       ; Ensure data sent before READY
        jmp cmd_loop

@do_call:
        jsr parse_address   ; Address in ptr
        jsr call_ptr
        jsr send_ok
        jsr tcp_flush       ; Ensure data sent before READY
        jmp cmd_loop

@do_quit:
        jsr tcp_close
        jmp exit_to_basic

;-------------------------------------------------------------------------------
; Parse hex address from cmd_buffer+2 into ptr
; Format: "P 1234" - address starts at position 2
;-------------------------------------------------------------------------------
parse_address:
        ldx #2
        jsr parse_hex_byte
        sta ptr+1           ; High byte first
        jsr parse_hex_byte
        sta ptr             ; Low byte
        rts

;-------------------------------------------------------------------------------
; Parse hex byte at cmd_buffer,X - returns in A, advances X
;-------------------------------------------------------------------------------
parse_hex_byte:
        lda cmd_buffer,x
        jsr hex_digit
        asl
        asl
        asl
        asl
        sta temp
        inx
        lda cmd_buffer,x
        jsr hex_digit
        ora temp
        inx
        rts

hex_digit:
        cmp #'A'
        bcs @letter
        sec
        sbc #'0'
        rts
@letter:
        sec
        sbc #'A'-10
        rts

;-------------------------------------------------------------------------------
; Parse value after comma for POKE
; Format: "O 1234,FF" - value at position 7
;-------------------------------------------------------------------------------
parse_value:
        ldx #7
        jsr parse_hex_byte
        rts

;-------------------------------------------------------------------------------
; Call address in ptr
;-------------------------------------------------------------------------------
call_ptr:
        jmp (ptr)

;-------------------------------------------------------------------------------
; Send "OK xx\r\n" where xx is hex byte in A
;-------------------------------------------------------------------------------
send_byte_result:
        pha
        lda #'O'
        sta send_buffer
        lda #'K'
        sta send_buffer+1
        lda #' '
        sta send_buffer+2
        pla
        pha
        lsr
        lsr
        lsr
        lsr
        jsr nibble_to_hex
        sta send_buffer+3
        pla
        and #$0F
        jsr nibble_to_hex
        sta send_buffer+4
        lda #13
        sta send_buffer+5
        lda #10
        sta send_buffer+6

        lda #7
        sta tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1
        ldax #send_buffer
        jsr tcp_send
        ; Process TCP stack to ensure data is sent
        jsr ip65_process
        jsr ip65_process
        rts

nibble_to_hex:
        cmp #10
        bcs @letter
        clc
        adc #'0'
        rts
@letter:
        clc
        adc #'A'-10
        rts

;-------------------------------------------------------------------------------
; Send "OK\r\n"
;-------------------------------------------------------------------------------
send_ok:
        lda #'O'
        sta send_buffer
        lda #'K'
        sta send_buffer+1
        lda #13
        sta send_buffer+2
        lda #10
        sta send_buffer+3

        lda #4
        sta tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1
        ldax #send_buffer
        jsr tcp_send
        ; Process TCP stack to ensure data is sent
        jsr ip65_process
        jsr ip65_process
        rts

;-------------------------------------------------------------------------------
; TCP Receive Callback
;-------------------------------------------------------------------------------
recv_callback:
        lda tcp_inbound_data_length
        ora tcp_inbound_data_length+1
        beq @done

        ; Copy to cmd_buffer
        lda tcp_inbound_data_ptr
        sta copy_src
        lda tcp_inbound_data_ptr+1
        sta copy_src+1

        ldy #0
@copy:
        cpy tcp_inbound_data_length
        beq @copy_done
        lda (copy_src),y
        sta cmd_buffer,y
        iny
        cpy #64             ; Max command size
        bne @copy

@copy_done:
        sty cmd_len
        lda #1
        sta got_data

@done:
        rts

;-------------------------------------------------------------------------------
; Simple delay
;-------------------------------------------------------------------------------
delay:
        ldx #0
        ldy #0
@loop:
        dey
        bne @loop
        dex
        bne @loop
        rts

;-------------------------------------------------------------------------------
; Flush TCP output - call ip65_process multiple times to ensure send completes
;-------------------------------------------------------------------------------
tcp_flush:
        ldx #8              ; Process 8 times to ensure flush
@flush_loop:
        txa
        pha
        jsr ip65_process
        pla
        tax
        dex
        bne @flush_loop
        rts

;-------------------------------------------------------------------------------
; Load configuration from CONFIG.DAT
; Sets CONFIG_IP and CONFIG_PORT if file exists
;-------------------------------------------------------------------------------
load_config:
        ; Print loading message
        ldax #str_loading
        jsr print

        ; Open file
        jsr MLI
        .byte CMD_OPEN
        .word cfg_open_params
        bcs @no_config

        ; Save ref num
        lda cfg_open_ref
        sta cfg_read_ref
        sta cfg_close_ref

        ; Read 7 bytes
        jsr MLI
        .byte CMD_READ
        .word cfg_read_params
        bcs @close_err

        ; Close file
        jsr MLI
        .byte CMD_CLOSE
        .word cfg_close_params

        ; Copy to config memory
        lda cfg_buffer
        sta CONFIG_IP
        lda cfg_buffer+1
        sta CONFIG_IP+1
        lda cfg_buffer+2
        sta CONFIG_IP+2
        lda cfg_buffer+3
        sta CONFIG_IP+3
        lda cfg_buffer+4
        sta CONFIG_PORT
        lda cfg_buffer+5
        sta CONFIG_PORT+1
        lda #MAGIC_VALUE
        sta CONFIG_MAGIC

        ldax #str_cfg_ok
        jsr print
        jsr print_cr
        rts

@close_err:
        jsr MLI
        .byte CMD_CLOSE
        .word cfg_close_params

@no_config:
        ldax #str_cfg_default
        jsr print
        jsr print_cr
        rts

;-------------------------------------------------------------------------------
; ProDOS parameter blocks for config
;-------------------------------------------------------------------------------
cfg_open_params:
        .byte 3                 ; Param count
        .word cfg_filename      ; Pathname
        .word $0800             ; I/O buffer
cfg_open_ref:
        .byte 0                 ; Ref num (returned)

cfg_read_params:
        .byte 4                 ; Param count
cfg_read_ref:
        .byte 0                 ; Ref num
        .word cfg_buffer        ; Data pointer
        .word 7                 ; Byte count
        .word 0                 ; Bytes read (returned)

cfg_close_params:
        .byte 1                 ; Param count
cfg_close_ref:
        .byte 0                 ; Ref num

cfg_filename:
        .byte 10                ; Length
        .byte "CONFIG.DAT"

cfg_buffer:
        .res 7                  ; IP (4) + Port (2) + Magic (1)

;===============================================================================
; DATA
;===============================================================================

.segment "RODATA"

str_banner:
        .byte "REMOTE SHELL V1.0", 13, 0

str_init:
        .byte "INIT NETWORK...", 0

str_fail:
        .byte "NETWORK FAILED", 13, 0

str_connecting:
        .byte "CONNECTING...", 0

str_connected:
        .byte "CONNECTED!", 0

str_conn_fail:
        .byte "FAILED, RETRY", 0

str_loading:
        .byte "LOADING CONFIG...", 0

str_cfg_ok:
        .byte "OK", 0

str_cfg_default:
        .byte "USING DEFAULTS", 0

ready_msg:
        .byte "READY", 13, 10

;===============================================================================
; BSS
;===============================================================================

.segment "BSS"

got_data:        .res 1
cmd_len:         .res 1
cmd_buffer:      .res 64
send_buffer:     .res 16
timeout_lo:      .res 1
timeout_hi:      .res 1
temp:            .res 1
connect_port:    .res 2
