;===============================================================================
; CLAUDE CODE - Apple IIe Terminal Interface
;
; A full-screen Claude Code experience for Apple IIe with Uthernet II
;
; Features:
; - Full-screen terminal UI (40x24)
; - Input line at bottom
; - Streaming output display
; - Lives in auxiliary RAM (survives BASIC program runs)
; - IP address configuration
; - BAS2 protocol for program injection
;
; Memory Map:
;   Main RAM:
;     $0801-$5FFF  BASIC program area
;     $6000-$7FFF  Claude Code main routines (loaded here initially)
;   Aux RAM:
;     $6000-$9FFF  Claude Code TSR (copied here, stays resident)
;
; Usage:
;   1. BRUN CLAUDE.CODE (or -CLAUDE.CODE for ProDOS)
;   2. Configure IP if needed
;   3. Type your request at the CLAUDE> prompt
;   4. Watch Claude work (streaming output)
;   5. Confirm injection, then RUN your program
;   6. Type & anytime to return to Claude Code
;===============================================================================

        .setcpu "6502"

.include "common.inc"
.include "commonprint.inc"
.include "net.inc"

.export start

.import exit_to_basic
.import print_a
.import get_key
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
; System Equates
;-------------------------------------------------------------------------------

; Screen dimensions
UI_WIDTH    = 40
UI_HEIGHT   = 24
INPUT_LINE      = 23          ; Bottom line for input
STATUS_LINE     = 22          ; Status messages
OUTPUT_START    = 1           ; First line for output
OUTPUT_END      = 21          ; Last line for output

; Text page 1
TEXTPAGE        = $0400

; Key codes
KEY_RETURN      = $8D
KEY_ESC         = $9B
KEY_DELETE      = $FF
KEY_LEFT        = $88
KEY_CTRL_C      = $83

; ROM routines
HOME            = $FC58
COUT            = $FDED
RDKEY           = $FD0C
VTAB            = $FB5B
CLREOL          = $FC9C

; Zero page
BARONE          = $24         ; Horizontal cursor position
CV              = $25         ; Vertical cursor position

; BASIC memory
TXTTAB          = $67
VARTAB          = $69
ARYTAB          = $6B
STREND          = $6D
BASIC_START     = $0801

; IP storage (shared with IP_SET program)
IP_STORAGE      = $0300
IP_SET_FLAG     = $0304
IP_SET_MAGIC    = $A2

; Ampersand hook
AMPER_VECTOR    = $03F5

; Aux memory soft switches (Apple IIe)
RAMRD           = $C002       ; Read main RAM
RAMWRT          = $C004       ; Write main RAM
RAMRDON         = $C003       ; Read aux RAM
RAMWRTON        = $C005       ; Write aux RAM
ALTZPON         = $C009       ; Use aux zero page/stack
ALTZPOFF        = $C008       ; Use main zero page/stack

;-------------------------------------------------------------------------------
; Zero Page Usage
;-------------------------------------------------------------------------------
src_ptr            = $06
dest_ptr            = $08
temp1           = $FA
temp2           = $FB
scroll_top      = $FC         ; Top line of scroll region
scroll_bot      = $FD         ; Bottom line of scroll region

;-------------------------------------------------------------------------------
; Protocol Constants
;-------------------------------------------------------------------------------
PROTO_STATUS    = 'S'         ; Status message: S:text\n
PROTO_ERROR     = 'E'         ; Error: E:text\n
PROTO_READY     = 'R'         ; Ready to inject: R:prompt\n
PROTO_BINARY    = 'B'         ; Binary follows: B:BAS2data

; BAS2 protocol
BAS2_MAGIC_0    = 'B'
BAS2_MAGIC_1    = 'A'
BAS2_MAGIC_2    = 'S'
BAS2_MAGIC_3    = '2'

; Stream states
STATE_LINE          = 0       ; Reading line type
STATE_TEXT          = 1       ; Reading text until \n
STATE_BINARY        = 2       ; Reading BAS2 binary
STATE_BAS2_HDR      = 3       ; Reading BAS2 header
STATE_BAS2_DATA     = 4       ; Reading BAS2 chunk data
STATE_BAS2_CHUNK_SZ = 5       ; Reading chunk size (2 bytes)
STATE_DONE          = 6       ; Transfer complete

;===============================================================================
; Code segment - loaded at $6000
;===============================================================================

; Linker segments
.segment "INIT"
.segment "ONCE"
.segment "STARTUP"

start:
;-------------------------------------------------------------------------------
; Entry point - initialize and show UI
;-------------------------------------------------------------------------------
        ; Save current screen (in case we want to restore later)
        ; For now, just clear and start fresh

        ; Initialize network
        jsr init_network
        bcs @net_failed

        ; Install & hook
        jsr install_hook

        ; Show main UI
        jmp main_ui

@net_failed:
        ldax #msg_net_fail
        jsr print
        jsr print_cr
        jmp exit_to_basic

;-------------------------------------------------------------------------------
; Initialize network via DHCP
;-------------------------------------------------------------------------------
init_network:
        ldax #msg_init_net
        jsr print

        init_ip_via_dhcp
        bcs @fail

        jsr print_cr
        jsr print_ip_config
        jsr print_cr
        clc
        rts

@fail:
        sec
        rts

;-------------------------------------------------------------------------------
; Install ampersand hook
;-------------------------------------------------------------------------------
install_hook:
        lda #$4C              ; JMP opcode
        sta AMPER_VECTOR
        lda #<ampersand_entry
        sta AMPER_VECTOR+1
        lda #>ampersand_entry
        sta AMPER_VECTOR+2
        rts

;-------------------------------------------------------------------------------
; Ampersand entry point (from BASIC prompt)
;-------------------------------------------------------------------------------
ampersand_entry:
        ; Check if already in Claude Code
        lda in_claude
        bne @exit

        ; Set flag
        lda #1
        sta in_claude

        ; Run UI
        jsr main_ui

        ; Clear flag
        lda #0
        sta in_claude

@exit:
        rts

;-------------------------------------------------------------------------------
; Main UI - full screen Claude Code interface
;-------------------------------------------------------------------------------
main_ui:
        jsr HOME
        jsr draw_header
        jsr draw_input_line

@main_loop:
        ; Position cursor at input area
        jsr position_input

        ; Get user input
        jsr get_input
        bcs @quit              ; ESC pressed

        ; Check for empty input
        lda input_len
        beq @main_loop

        ; Check for commands
        jsr check_commands
        bcs @main_loop         ; Command handled

        ; Send request to server
        jsr send_request
        bcs @send_failed

        ; Process streaming response
        jsr receive_response

        ; Check if we got a program
        lda got_program
        beq @main_loop

        ; Ask to inject
        jsr prompt_inject
        bcc @main_loop         ; User said no

        ; Inject and exit
        jsr inject_program

        ; Clear screen and return to BASIC
        jsr HOME
        ldax #msg_program_ready
        jsr print
        jsr print_cr
        rts

@send_failed:
        jsr status_line
        ldax #msg_send_fail
        jsr print
        jmp @main_loop

@quit:
        jsr HOME
        ldax #msg_bye
        jsr print
        jsr print_cr
        rts

;-------------------------------------------------------------------------------
; Draw header
;-------------------------------------------------------------------------------
draw_header:
        lda #0
        sta CV
        jsr VTAB

        ldax #header_line1
        jsr print_line_40

        lda #1
        sta CV
        jsr VTAB
        ldax #header_line2
        jsr print_line_40

        rts

;-------------------------------------------------------------------------------
; Draw input line marker
;-------------------------------------------------------------------------------
draw_input_line:
        lda #INPUT_LINE
        sta CV
        jsr VTAB

        ldax #prompt_str
        jsr print
        rts

;-------------------------------------------------------------------------------
; Position cursor at input area
;-------------------------------------------------------------------------------
position_input:
        lda #INPUT_LINE
        sta CV
        jsr VTAB
        lda #8                 ; After "CLAUDE> "
        sta BARONE
        rts

;-------------------------------------------------------------------------------
; Get input from user
; Returns: carry set if ESC, input in input_buffer, length in input_len
;-------------------------------------------------------------------------------
get_input:
        lda #0
        sta input_len

        ; Clear input area
        jsr position_input
        jsr CLREOL

@get_loop:
        jsr RDKEY

        ; Check ESC
        cmp #KEY_ESC
        beq @esc

        ; Check Return
        cmp #KEY_RETURN
        beq @done

        ; Check Delete
        cmp #KEY_DELETE
        beq @delete
        cmp #$08               ; Backspace
        beq @delete

        ; Printable character?
        cmp #$A0               ; Space (with high bit)
        bcc @get_loop          ; Skip control chars

        ; Buffer full?
        ldx input_len
        cpx #MAX_INPUT
        bcs @get_loop

        ; Store character (clear high bit for ASCII)
        and #$7F
        sta input_buffer,x
        inc input_len

        ; Echo (with high bit for Apple II display)
        ora #$80
        jsr COUT

        jmp @get_loop

@delete:
        lda input_len
        beq @get_loop          ; Nothing to delete

        dec input_len

        ; Move cursor back and clear
        lda #KEY_LEFT
        jsr COUT
        lda #$A0               ; Space
        jsr COUT
        lda #KEY_LEFT
        jsr COUT

        jmp @get_loop

@esc:
        sec
        rts

@done:
        ; Null terminate
        ldx input_len
        lda #0
        sta input_buffer,x

        clc
        rts

;-------------------------------------------------------------------------------
; Check for built-in commands
; Returns: carry set if command handled
;-------------------------------------------------------------------------------
check_commands:
        ; Check "IP"
        lda input_buffer
        cmp #'I'
        bne @not_ip
        lda input_buffer+1
        cmp #'P'
        bne @not_ip
        lda input_buffer+2
        beq @do_ip
        cmp #' '
        bne @not_ip

@do_ip:
        jsr cmd_ip_config
        sec
        rts

@not_ip:
        ; Check "HELP"
        lda input_buffer
        cmp #'H'
        bne @not_help
        ; (simplified check)
        jsr cmd_help
        sec
        rts

@not_help:
        ; Check "CLEAR"
        lda input_buffer
        cmp #'C'
        bne @not_clear
        lda input_buffer+1
        cmp #'L'
        bne @not_clear
        jsr HOME
        jsr draw_header
        jsr draw_input_line
        sec
        rts

@not_clear:
        clc
        rts

;-------------------------------------------------------------------------------
; IP configuration command
;-------------------------------------------------------------------------------
cmd_ip_config:
        jsr scroll_output

        ; Show current IP
        lda IP_SET_FLAG
        cmp #IP_SET_MAGIC
        bne @show_default

        ldax #msg_current_ip
        jsr print
        lda IP_STORAGE
        jsr print_decimal
        lda #'.'
        jsr print_a
        lda IP_STORAGE+1
        jsr print_decimal
        lda #'.'
        jsr print_a
        lda IP_STORAGE+2
        jsr print_decimal
        lda #'.'
        jsr print_a
        lda IP_STORAGE+3
        jsr print_decimal
        jsr print_cr
        rts

@show_default:
        ldax #msg_default_ip
        jsr print
        jsr print_cr
        rts

;-------------------------------------------------------------------------------
; Help command
;-------------------------------------------------------------------------------
cmd_help:
        jsr scroll_output
        ldax #msg_help
        jsr print
        rts

;-------------------------------------------------------------------------------
; Scroll the output area up one line
;-------------------------------------------------------------------------------
scroll_output:
        ; For now, just position at output area
        lda #OUTPUT_START
        sta CV
        jsr VTAB
        rts

;-------------------------------------------------------------------------------
; Status line message
;-------------------------------------------------------------------------------
status_line:
        lda #STATUS_LINE
        sta CV
        jsr VTAB
        jsr CLREOL
        rts

;-------------------------------------------------------------------------------
; Send request to proxy server
;-------------------------------------------------------------------------------
send_request:
        jsr status_line
        ldax #msg_connecting
        jsr print

        ; Set callback
        ldax #recv_callback
        stax tcp_callback

        ; Get IP (use stored or default)
        lda IP_SET_FLAG
        cmp #IP_SET_MAGIC
        bne @use_default

        lda IP_STORAGE
        sta tcp_connect_ip
        lda IP_STORAGE+1
        sta tcp_connect_ip+1
        lda IP_STORAGE+2
        sta tcp_connect_ip+2
        lda IP_STORAGE+3
        sta tcp_connect_ip+3
        jmp @connect

@use_default:
        ; Default: 192.168.64.1
        lda #192
        sta tcp_connect_ip
        lda #168
        sta tcp_connect_ip+1
        lda #64
        sta tcp_connect_ip+2
        lda #1
        sta tcp_connect_ip+3

@connect:
        ; Connect to port 8080
        ldax #8080
        jsr tcp_connect
        bcs @conn_fail

        lda #'.'
        jsr print_a

        ; Build and send HTTP request
        jsr build_http_request
        jsr send_http_request
        bcs @send_fail

        lda #'.'
        jsr print_a
        jsr print_cr

        clc
        rts

@conn_fail:
@send_fail:
        jsr tcp_close
        sec
        rts

;-------------------------------------------------------------------------------
; Build HTTP POST request for /claude/stream
;-------------------------------------------------------------------------------
build_http_request:
        ldx #0

        ; POST /claude/stream HTTP/1.0\r\n
        ldy #0
@copy_post:
        lda http_post,y
        beq @copy_headers
        sta send_buffer,x
        inx
        iny
        bne @copy_post

@copy_headers:
        ; Headers
        ldy #0
@copy_hdr:
        lda http_headers,y
        beq @add_length
        sta send_buffer,x
        inx
        iny
        bne @copy_hdr

@add_length:
        ; Content-Length: (input_len as decimal)
        lda input_len
        jsr byte_to_decimal_str
        ; decimal_str now has the number

        ldy #0
@copy_len:
        lda decimal_str,y
        beq @add_crlf
        sta send_buffer,x
        inx
        iny
        bne @copy_len

@add_crlf:
        ; \r\n\r\n
        lda #13
        sta send_buffer,x
        inx
        lda #10
        sta send_buffer,x
        inx
        lda #13
        sta send_buffer,x
        inx
        lda #10
        sta send_buffer,x
        inx

        ; Copy input
        ldy #0
@copy_input:
        cpy input_len
        beq @done
        lda input_buffer,y
        sta send_buffer,x
        inx
        iny
        bne @copy_input

@done:
        stx send_len
        lda #0
        sta send_len+1
        rts

;-------------------------------------------------------------------------------
; Send the HTTP request
;-------------------------------------------------------------------------------
send_http_request:
        lda send_len
        sta tcp_send_data_len
        lda send_len+1
        sta tcp_send_data_len+1

        ldax #send_buffer
        jsr tcp_send
        rts

;-------------------------------------------------------------------------------
; Receive and process streaming response
;-------------------------------------------------------------------------------
receive_response:
        ; Initialize state
        lda #0
        sta got_program
        sta recv_state
        sta line_pos
        sta output_line
        lda #OUTPUT_START
        sta output_line

        ; Timeout counter
        lda #0
        sta timeout_lo
        sta timeout_hi

@recv_loop:
        jsr ip65_process

        ; Check if done
        lda recv_state
        cmp #STATE_DONE
        beq @done

        ; Check timeout
        inc timeout_lo
        bne @recv_loop
        inc timeout_hi
        lda timeout_hi
        cmp #$80               ; Long timeout for API
        bcc @recv_loop

        ; Timeout
        jsr status_line
        ldax #msg_timeout
        jsr print

@done:
        jsr tcp_close
        rts

;-------------------------------------------------------------------------------
; TCP receive callback - process streaming protocol
;-------------------------------------------------------------------------------
recv_callback:
        lda tcp_inbound_data_length
        ora tcp_inbound_data_length+1
        bne @have_data
        rts

@have_data:
        ; Reset timeout
        lda #0
        sta timeout_lo
        sta timeout_hi

        ; Set up source pointer
        lda tcp_inbound_data_ptr
        sta src_ptr
        lda tcp_inbound_data_ptr+1
        sta src_ptr+1

        ldy #0

@process_loop:
        ; Check if done with this chunk
        cpy tcp_inbound_data_length
        bne @check_hi
        jmp @chunk_done
@check_hi:
        lda tcp_inbound_data_length+1
        bne @more_data
        cpy tcp_inbound_data_length
        bcc @more_data
        jmp @chunk_done

@more_data:
        lda (src_ptr),y
        iny

        ; Process based on state (use trampolines for far branches)
        ldx recv_state
        cpx #STATE_LINE
        beq @state_line
        cpx #STATE_TEXT
        beq @state_text
        cpx #STATE_BAS2_HDR
        bne @check_chunk_sz
        jmp @state_bas2_hdr
@check_chunk_sz:
        cpx #STATE_BAS2_CHUNK_SZ
        bne @check_data
        jmp @state_chunk_sz
@check_data:
        cpx #STATE_BAS2_DATA
        bne @check_done
        jmp @state_bas2_data
@check_done:
        cpx #STATE_DONE
        bne @do_process_loop
        jmp @chunk_done
@do_process_loop:
        jmp @process_loop

@state_line:
        ; Reading line type character
        cmp #PROTO_STATUS
        beq @got_status
        cmp #PROTO_ERROR
        beq @got_error
        cmp #PROTO_READY
        beq @got_ready
        cmp #PROTO_BINARY
        beq @got_binary
        jmp @process_loop

@got_status:
@got_error:
@got_ready:
        sta line_type
        lda #STATE_TEXT
        sta recv_state
        lda #0
        sta line_pos
        jmp @process_loop

@got_binary:
        lda #STATE_BAS2_HDR
        sta recv_state
        lda #0
        sta bas2_pos
        jmp @process_loop

@state_text:
        ; Skip the : after type
        cmp #':'
        beq @process_loop

        ; Check for newline
        cmp #10
        beq @end_line
        cmp #13
        bne @not_cr
        jmp @process_loop      ; Skip CR
@not_cr:
        ; Store in line buffer
        ldx line_pos
        cpx #38                ; Max line length
        bcc @store_char
        jmp @process_loop
@store_char:
        sta line_buffer,x
        inc line_pos
        jmp @process_loop

@end_line:
        ; Null terminate
        ldx line_pos
        lda #0
        sta line_buffer,x

        ; Display the line
        jsr display_output_line

        ; Reset for next line
        lda #STATE_LINE
        sta recv_state
        lda #0
        sta line_pos

        ; If this was READY, set flag
        lda line_type
        cmp #PROTO_READY
        bne @not_ready
        lda #1
        sta got_ready_prompt

@not_ready:
        jmp @process_loop

@state_bas2_hdr:
        ; Collecting BAS2 header (skip "BAS2", get length and address)
        ldx bas2_pos
        sta bas2_header,x
        inc bas2_pos

        ; Need 8 bytes: BAS2 + len(2) + addr(2)
        lda bas2_pos
        cmp #8
        bcs @hdr_complete
        jmp @process_loop
@hdr_complete:

        ; Verify magic
        lda bas2_header
        cmp #BAS2_MAGIC_0
        bne @bad_magic
        lda bas2_header+1
        cmp #BAS2_MAGIC_1
        bne @bad_magic
        lda bas2_header+2
        cmp #BAS2_MAGIC_2
        bne @bad_magic
        lda bas2_header+3
        cmp #BAS2_MAGIC_3
        bne @bad_magic

        ; Get total length
        lda bas2_header+4
        sta bas2_total_len
        lda bas2_header+5
        sta bas2_total_len+1

        ; Get start address
        lda bas2_header+6
        sta bas2_addr
        sta dest_ptr
        lda bas2_header+7
        sta bas2_addr+1
        sta dest_ptr+1

        ; Now read chunk size
        lda #0
        sta bas2_pos
        sta bas2_bytes_written
        sta bas2_bytes_written+1
        lda #STATE_BAS2_CHUNK_SZ
        sta recv_state
        jmp @process_loop

@bad_magic:
        ; Error
        lda #STATE_DONE
        sta recv_state
        jmp @chunk_done

@state_chunk_sz:
        ; Reading 2-byte chunk size
        ldx bas2_pos
        sta bas2_header,x      ; Reuse header buffer
        inc bas2_pos

        lda bas2_pos
        cmp #2
        bcc @process_loop_jmp

        ; Got chunk size
        lda bas2_header
        sta bas2_chunk_remain
        lda bas2_header+1
        sta bas2_chunk_remain+1

        ; Check for end marker (size = 0)
        lda bas2_chunk_remain
        ora bas2_chunk_remain+1
        beq @transfer_done

        ; Read chunk data
        lda #0
        sta bas2_pos
        lda #STATE_BAS2_DATA
        sta recv_state
        jmp @process_loop

@transfer_done:
        ; All data received!
        lda #1
        sta got_program
        lda #STATE_DONE
        sta recv_state
        jmp @chunk_done

@process_loop_jmp:
        jmp @process_loop

@state_bas2_data:
        ; Write byte to memory
        ldx #0
        sta (dest_ptr,x)

        ; Increment pointer
        inc dest_ptr
        bne @no_ptr_carry
        inc dest_ptr+1
@no_ptr_carry:

        ; Increment bytes written
        inc bas2_bytes_written
        bne @no_bw_carry
        inc bas2_bytes_written+1
@no_bw_carry:

        ; Decrement chunk remain
        lda bas2_chunk_remain
        bne @dec_remain
        dec bas2_chunk_remain+1
@dec_remain:
        dec bas2_chunk_remain

        ; Check if chunk done
        lda bas2_chunk_remain
        ora bas2_chunk_remain+1
        beq @chunk_complete
        jmp @process_loop

@chunk_complete:
        ; Chunk done - read next chunk size
        lda #STATE_BAS2_CHUNK_SZ
        sta recv_state
        lda #0
        sta bas2_pos
        jmp @process_loop

@chunk_done:
        rts


;-------------------------------------------------------------------------------
; Display a line in the output area
;-------------------------------------------------------------------------------
display_output_line:
        ; Position at current output line
        lda output_line
        sta CV
        jsr VTAB
        jsr CLREOL

        ; Print the line
        ldax #line_buffer
        jsr print

        ; Move to next line, scroll if needed
        inc output_line
        lda output_line
        cmp #OUTPUT_END
        bcc @no_scroll

        ; Scroll would be needed - for now just wrap
        lda #OUTPUT_START
        sta output_line

@no_scroll:
        rts

;-------------------------------------------------------------------------------
; Prompt user to inject program
;-------------------------------------------------------------------------------
prompt_inject:
        jsr status_line
        ldax #msg_inject_prompt
        jsr print

@wait_key:
        jsr RDKEY
        and #$DF               ; Upper case

        cmp #'Y'
        beq @yes
        cmp #'N'
        beq @no
        cmp #KEY_RETURN
        beq @yes               ; Default yes
        jmp @wait_key

@yes:
        sec
        rts

@no:
        clc
        rts

;-------------------------------------------------------------------------------
; Inject program into BASIC memory
;-------------------------------------------------------------------------------
inject_program:
        ; Data already written to BASIC area by recv_callback
        ; Just need to set BASIC pointers

        ; TXTTAB = start address
        lda bas2_addr
        sta TXTTAB
        lda bas2_addr+1
        sta TXTTAB+1

        ; VARTAB = end of program
        lda dest_ptr
        sta VARTAB
        sta ARYTAB
        sta STREND
        lda dest_ptr+1
        sta VARTAB+1
        sta ARYTAB+1
        sta STREND+1

        rts

;-------------------------------------------------------------------------------
; Print 40-character line (padded/truncated)
;-------------------------------------------------------------------------------
print_line_40:
        stax src_ptr
        ldy #0
@loop:
        lda (src_ptr),y
        beq @pad
        jsr print_a
        iny
        cpy #40
        bcc @loop
        rts
@pad:
        lda #$A0               ; Space
        jsr print_a
        iny
        cpy #40
        bcc @pad
        rts

;-------------------------------------------------------------------------------
; Convert byte to decimal string
;-------------------------------------------------------------------------------
byte_to_decimal_str:
        sta temp1
        ldx #0

        ; Hundreds
        ldy #0
@hundreds:
        lda temp1
        cmp #100
        bcc @tens
        sec
        sbc #100
        sta temp1
        iny
        bne @hundreds
@tens_start:
        tya
        ora #'0'
        sta decimal_str,x
        inx

@tens:
        ldy #0
@tens_loop:
        lda temp1
        cmp #10
        bcc @ones
        sec
        sbc #10
        sta temp1
        iny
        bne @tens_loop
@ones_start:
        ; Only output tens if we had hundreds or tens > 0
        cpx #0
        bne @output_tens
        cpy #0
        beq @ones
@output_tens:
        tya
        ora #'0'
        sta decimal_str,x
        inx

@ones:
        lda temp1
        ora #'0'
        sta decimal_str,x
        inx
        lda #0
        sta decimal_str,x
        rts

;-------------------------------------------------------------------------------
; Print A as decimal
;-------------------------------------------------------------------------------
print_decimal:
        jsr byte_to_decimal_str
        ldax #decimal_str
        jsr print
        rts

;===============================================================================
; DATA
;===============================================================================

.segment "RODATA"

msg_init_net:
        .byte "INITIALIZING NETWORK...", 0

msg_net_fail:
        .byte "NETWORK INIT FAILED", 0

msg_connecting:
        .byte "CONNECTING", 0

msg_send_fail:
        .byte "CONNECTION FAILED", 0

msg_timeout:
        .byte "TIMEOUT", 0

msg_program_ready:
        .byte "PROGRAM LOADED - TYPE RUN", 13
        .byte "TYPE & FOR CLAUDE CODE", 0

msg_bye:
        .byte "BYE - TYPE & TO RETURN", 0

msg_inject_prompt:
        .byte "INJECT PROGRAM? (Y/N) ", 0

msg_current_ip:
        .byte "PROXY IP: ", 0

msg_default_ip:
        .byte "USING DEFAULT 192.168.64.1", 0

msg_help:
        .byte "COMMANDS:", 13
        .byte " IP - SHOW/SET PROXY IP", 13
        .byte " CLEAR - CLEAR SCREEN", 13
        .byte " HELP - THIS MESSAGE", 13
        .byte " ESC - EXIT TO BASIC", 13, 0

header_line1:
        .byte "======= CLAUDE CODE FOR APPLE II =======", 0

header_line2:
        .byte "TYPE REQUEST OR HELP FOR COMMANDS", 0

prompt_str:
        .byte "CLAUDE> ", 0

http_post:
        .byte "POST /claude/stream HTTP/1.0", 13, 10, 0

http_headers:
        .byte "Host: proxy", 13, 10
        .byte "Content-Type: text/plain", 13, 10
        .byte "Content-Length: ", 0

;===============================================================================
; BSS - Variables
;===============================================================================

.segment "BSS"

; State
in_claude:              .res 1
got_program:            .res 1
got_ready_prompt:       .res 1

; Input
input_buffer:           .res 128
input_len:              .res 1
MAX_INPUT               = 120

; Output
output_line:            .res 1
line_buffer:            .res 64
line_pos:               .res 1
line_type:              .res 1

; Network
send_buffer:            .res 512
send_len:               .res 2
recv_state:             .res 1
timeout_lo:             .res 1
timeout_hi:             .res 1

; BAS2 protocol
bas2_header:            .res 16
bas2_pos:               .res 1
bas2_total_len:         .res 2
bas2_addr:              .res 2
bas2_chunk_remain:      .res 2
bas2_bytes_written:     .res 2

; Utility
decimal_str:            .res 8
