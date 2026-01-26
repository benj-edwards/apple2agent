;===============================================================================
; CLAUDE AGENT - AMPERSAND HOOK VERSION
; Merges the TSR & hook with the streaming agent
;
; Two modes of operation:
;   1. Run directly: Initializes network, shows CLAUDE> prompt
;   2. & from BASIC: Type & at BASIC prompt to activate Claude console
;
; Protocol: BAS2 + total_len(2) + start_addr(2) + [chunk_size(2) + data]* + 0x0000
;===============================================================================

        .setcpu "6502"

.include "../../libs/ip65/inc/common.inc"
.include "../../libs/ip65/inc/commonprint.inc"
.include "../../libs/ip65/inc/net.inc"

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
.import ascii_to_native
.importzp copy_src

;-------------------------------------------------------------------------------
; BASIC Memory Locations
;-------------------------------------------------------------------------------
TXTTAB   = $67          ; Start of BASIC program (2 bytes)
VARTAB   = $69          ; End of program / Start of variables (2 bytes)
ARYTAB   = $6B          ; Start of arrays (2 bytes)
STREND   = $6D          ; End of arrays (2 bytes)
FRETOP   = $6F          ; Bottom of string storage (2 bytes)
HIMEM    = $73          ; Top of memory (2 bytes)
CURLIN   = $75          ; Current line number (2 bytes) - $FFFF when not running

; ProDOS/DOS33 safe BASIC start
BASIC_START = $0801

; IP address storage (set by IP_SET.BIN)
IP_STORAGE   = $0300        ; 4 bytes: proxy IP address
IP_SET_FLAG  = $0304        ; Flag: $A2 = IP has been set by IP_SET

; ROM routines
HOME     = $FC58        ; Clear screen
COUT     = $FDED        ; Character output
CROUT    = $FD8E        ; Carriage return

;-------------------------------------------------------------------------------
; TSR Constants
;-------------------------------------------------------------------------------
TEXTPAGE1    = $0400        ; Text page 1 base
SCREEN_SAVE  = $8000        ; Screen save area (1KB) - above BASIC

; Ampersand vector location
AMPER_VECTOR = $03F5        ; & command vector (3 bytes: JMP addr)

;-------------------------------------------------------------------------------
; Zero page usage (safe area)
;-------------------------------------------------------------------------------
src_ptr  = $06          ; Source pointer for copy
dst_ptr  = $08          ; Destination pointer for copy (also used for streaming dest)
scr_ptr1 = $FA          ; Screen copy pointer 1
scr_ptr2 = $FC          ; Screen copy pointer 2

;-------------------------------------------------------------------------------
; Flags
;-------------------------------------------------------------------------------
FLAG_ACTIVE      = $01      ; Console is active
FLAG_INSTALLED   = $02      ; TSR is installed

;-------------------------------------------------------------------------------
; Stream state machine constants
;-------------------------------------------------------------------------------
STATE_SKIP_HEADERS   = 0    ; Scanning for CRLFCRLF
STATE_READ_MAGIC     = 1    ; Reading "BAS2" (4 bytes)
STATE_READ_TOTAL_LEN = 2    ; Reading total length (2 bytes)
STATE_READ_START     = 3    ; Reading start address (2 bytes)
STATE_READ_CHUNK_SZ  = 4    ; Reading chunk size (2 bytes)
STATE_READ_CHUNK     = 5    ; Reading chunk data directly to memory
STATE_DONE           = 6    ; All data received
STATE_ERROR          = 7    ; Error occurred

; keep LD65 happy
.segment "INIT"
.segment "ONCE"

.segment "STARTUP"

;===============================================================================
; Entry point
;===============================================================================
start:
        ; Print banner
        ldax #banner_msg
        jsr print
        jsr print_cr

        ; Initialize network first
        ldax #network_init_msg
        jsr print
        init_ip_via_dhcp
        bcc @net_ok

        ldax #fail_msg
        jsr print
        jmp exit_to_basic

@net_ok:
        jsr print_cr
        jsr print_ip_config
        jsr print_cr

        ; Install the & hook
        jsr install_ampersand_hook

        ; Show instructions
        ldax #installed_msg
        jsr print
        jsr print_cr

        ; Return to BASIC - user can type & to activate
        jmp exit_to_basic

;-------------------------------------------------------------------------------
; Install the ampersand (&) hook
;-------------------------------------------------------------------------------
install_ampersand_hook:
        ; The & vector at $03F5 is a 3-byte JMP instruction
        lda #$4C              ; JMP opcode
        sta AMPER_VECTOR
        lda #<ampersand_handler
        sta AMPER_VECTOR+1
        lda #>ampersand_handler
        sta AMPER_VECTOR+2

        ; Mark as installed
        lda #FLAG_INSTALLED
        sta tsr_flags
        rts

;-------------------------------------------------------------------------------
; Ampersand handler - called when user types & at BASIC prompt
;-------------------------------------------------------------------------------
ampersand_handler:
        ; Check if already active (prevent re-entry)
        lda tsr_flags
        and #FLAG_ACTIVE
        bne @already_active

        ; Set active flag
        lda tsr_flags
        ora #FLAG_ACTIVE
        sta tsr_flags

        ; Save current screen
        jsr save_screen

        ; Clear screen for our UI
        jsr HOME

        ; Show header
        ldax #console_header
        jsr print
        jsr print_cr
        jsr print_cr

        ; Run the main Claude loop
        jsr main_loop_internal

        ; Restore screen
        jsr restore_screen

        ; Clear active flag
        lda tsr_flags
        and #<(~FLAG_ACTIVE)
        sta tsr_flags

@already_active:
        ; Return to BASIC
        rts

;-------------------------------------------------------------------------------
; Save text screen to buffer
;-------------------------------------------------------------------------------
save_screen:
        lda #<TEXTPAGE1
        sta scr_ptr1
        lda #>TEXTPAGE1
        sta scr_ptr1+1

        lda #<SCREEN_SAVE
        sta scr_ptr2
        lda #>SCREEN_SAVE
        sta scr_ptr2+1

        ldx #4                ; 4 pages (1KB)
@save_page:
        ldy #0
@save_byte:
        lda (scr_ptr1),y
        sta (scr_ptr2),y
        iny
        bne @save_byte

        inc scr_ptr1+1
        inc scr_ptr2+1
        dex
        bne @save_page

        rts

;-------------------------------------------------------------------------------
; Restore text screen from buffer
;-------------------------------------------------------------------------------
restore_screen:
        lda #<SCREEN_SAVE
        sta scr_ptr1
        lda #>SCREEN_SAVE
        sta scr_ptr1+1

        lda #<TEXTPAGE1
        sta scr_ptr2
        lda #>TEXTPAGE1
        sta scr_ptr2+1

        ldx #4
@rest_page:
        ldy #0
@rest_byte:
        lda (scr_ptr1),y
        sta (scr_ptr2),y
        iny
        bne @rest_byte

        inc scr_ptr1+1
        inc scr_ptr2+1
        dex
        bne @rest_page

        rts

;-------------------------------------------------------------------------------
; Main loop (internal) - get prompt and request code
; Returns when done (after loading program or ESC)
;-------------------------------------------------------------------------------
main_loop_internal:
        ldax #prompt_msg
        jsr print

        ; Get user input
        lda #0
        sta input_pos

@get_char:
        jsr get_key

        cmp #$9B                ; ESC (Apple II)
        beq @quit
        cmp #$1B                ; ESC (ASCII)
        beq @quit

        cmp #$8D                ; CR (Apple II)
        beq @got_input
        cmp #$0D                ; CR (ASCII)
        beq @got_input

        ; Store printable chars
        cmp #$20
        bcc @get_char           ; Skip control chars

        ldx input_pos
        cpx #200
        bcs @get_char           ; Buffer full

        and #$7F                ; Clear high bit
        sta input_buffer,x
        inc input_pos

        ; Echo
        jsr print_a
        jmp @get_char

@quit:
        jsr print_cr
        rts                     ; Return to ampersand_handler

@got_input:
        jsr print_cr

        lda input_pos
        beq main_loop_internal  ; Empty input, loop again

        ; Null terminate
        ldx input_pos
        lda #0
        sta input_buffer,x

        ; Request code from proxy
        jsr request_code

        ; Check if we got valid data
        lda got_valid_basic
        beq main_loop_internal  ; Failed, try again

        ; Inject into BASIC memory
        jsr inject_basic

        ; Show success message
        ldax #injected_msg
        jsr print
        jsr print_cr

        ; Return (screen will be restored, then back to BASIC with program loaded)
        rts

;-------------------------------------------------------------------------------
; Request code from proxy (binary mode)
;-------------------------------------------------------------------------------
request_code:
        ; Clear state - initialize streaming state machine
        lda #0
        sta got_data
        sta got_valid_basic
        sta cr_count
        sta header_pos
        sta bytes_written
        sta bytes_written+1
        lda #STATE_SKIP_HEADERS
        sta stream_state

        ; Get proxy IP from $0300 (set by IP_SET.BIN) or use default
        lda IP_SET_FLAG
        cmp #$A2                ; Magic value = IP was set
        bne @use_default_ip

        ; Use IP from $0300-$0303
        lda IP_STORAGE
        sta tcp_connect_ip
        lda IP_STORAGE+1
        sta tcp_connect_ip+1
        lda IP_STORAGE+2
        sta tcp_connect_ip+2
        lda IP_STORAGE+3
        sta tcp_connect_ip+3
        jmp @ip_done

@use_default_ip:
        ; Default: 192.168.64.1 (MAME vmnet)
        lda #192
        sta tcp_connect_ip
        lda #168
        sta tcp_connect_ip+1
        lda #64
        sta tcp_connect_ip+2
        lda #1
        sta tcp_connect_ip+3

@ip_done:

        ldax #connecting_msg
        jsr print

        ; Set callback
        ldax #recv_callback
        stax tcp_callback

        ; Connect to port 8080
        ldax #8080
        jsr tcp_connect
        bcc @connected

        ldax #conn_fail_msg
        jsr print
        jsr print_cr
        rts

@connected:
        lda #'.'
        jsr print_a

        ; Build HTTP request for binary endpoint
        jsr build_request

        ; Send it
        lda send_len
        sta tcp_send_data_len
        lda send_len+1
        sta tcp_send_data_len+1
        ldax #send_buffer
        jsr tcp_send
        bcc @send_ok
        jmp send_fail

@send_ok:
        lda #'.'
        jsr print_a

        ; Wait for response - keep processing until DONE or timeout
        ldx #0
        stx timeout_lo
        stx timeout_hi
        stx last_bytes_lo       ; Track bytes received to detect new data
        stx last_bytes_hi

@wait_loop:
        jsr ip65_process

        ; Check if streaming is complete
        lda stream_state
        cmp #STATE_DONE
        beq @got_response       ; Done! Exit wait loop
        cmp #STATE_ERROR
        beq @got_response       ; Error! Exit wait loop

        ; Check if we received new data (bytes_written changed)
        lda bytes_written
        cmp last_bytes_lo
        bne @got_new_data
        lda bytes_written+1
        cmp last_bytes_hi
        beq @no_new_data

@got_new_data:
        ; New data received - reset timeout and update tracker
        lda bytes_written
        sta last_bytes_lo
        lda bytes_written+1
        sta last_bytes_hi
        lda #0
        sta timeout_lo
        sta timeout_hi
        jmp @wait_loop

@no_new_data:
        ; No new data this iteration - increment timeout
        inc timeout_lo
        bne @wait_loop
        inc timeout_hi

        ; Check if we got ANY data at all
        lda got_data
        bne @got_some_data

        ; No data yet - wait longer for API response (can take 10+ seconds)
        lda timeout_hi
        cmp #$FF                ; ~15 seconds at 1MHz
        bcc @wait_loop
        jmp @real_timeout

@got_some_data:
        ; Got some data but stream incomplete - wait for more
        lda timeout_hi
        cmp #$40                ; Shorter timeout once data is flowing
        bcc @wait_loop

@real_timeout:
        ; Timeout
        ldax #timeout_msg
        jsr print
        jsr print_cr
        jsr tcp_close
        rts

@got_response:
        lda #'.'
        jsr print_a
        jsr print_cr

        ; Check streaming state
        lda stream_state
        cmp #STATE_DONE
        beq @stream_ok
        cmp #STATE_ERROR
        beq @stream_err
        ; Still in progress after data stopped - incomplete response
        ldax #parse_err_msg
        jsr print
        jsr print_cr
        jsr tcp_close
        rts

@stream_err:
        ldax #not_binary_msg
        jsr print
        jsr print_cr
        jsr tcp_close
        rts

@stream_ok:
        ; Show length received
        ldax #len_msg
        jsr print
        lda basic_len+1
        jsr print_hex_byte
        lda basic_len
        jsr print_hex_byte
        jsr print_cr

        jsr tcp_close
        rts

send_fail:
        ldax #send_fail_msg
        jsr print
        jsr print_cr
        jsr tcp_close
        rts

;-------------------------------------------------------------------------------
; Build HTTP request for binary endpoint
;-------------------------------------------------------------------------------
build_request:
        ldx #0                  ; send_buffer index

        ; Copy HTTP header for binary endpoint
        ldy #0
@copy_hdr:
        lda http_hdr_bin,y
        sta send_buffer,x
        inx
        iny
        cpy #http_hdr_bin_len
        bne @copy_hdr

        ; Add Content-Length value
        lda input_pos
        sta num_temp

        ; Hundreds
        cmp #100
        bcc @do_tens
        ldy #0
@h_loop:
        lda num_temp
        cmp #100
        bcc @h_done
        sec
        sbc #100
        sta num_temp
        iny
        bne @h_loop
@h_done:
        tya
        clc
        adc #'0'
        sta send_buffer,x
        inx

@do_tens:
        lda num_temp
        cmp #10
        bcc @do_ones
        ldy #0
@t_loop:
        lda num_temp
        cmp #10
        bcc @t_done
        sec
        sbc #10
        sta num_temp
        iny
        bne @t_loop
@t_done:
        tya
        clc
        adc #'0'
        sta send_buffer,x
        inx

@do_ones:
        lda num_temp
        clc
        adc #'0'
        sta send_buffer,x
        inx

        ; CRLFCRLF
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

        ; Copy user input
        ldy #0
@copy_input:
        cpy input_pos
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
; Inject tokenized BASIC into memory
;-------------------------------------------------------------------------------
inject_basic:
        ; STREAMING VERSION: Data already written directly to memory by recv_callback
        ; Just need to set BASIC pointers
        ;
        ; dst_ptr already points to end of data (updated by recv_callback)
        ; basic_len has total length (from BAS2 header)

        ; Update BASIC pointers
        ; TXTTAB = BASIC_START (should already be set, but make sure)
        lda #<BASIC_START
        sta TXTTAB
        lda #>BASIC_START
        sta TXTTAB+1

        ; VARTAB = End of program (dst_ptr, which was updated during streaming)
        lda dst_ptr
        sta VARTAB
        lda dst_ptr+1
        sta VARTAB+1

        ; ARYTAB = VARTAB (no variables yet)
        lda dst_ptr
        sta ARYTAB
        lda dst_ptr+1
        sta ARYTAB+1

        ; STREND = ARYTAB (no arrays yet)
        lda dst_ptr
        sta STREND
        lda dst_ptr+1
        sta STREND+1

        ; Reset CURLIN to $FFFF (not running any line)
        lda #$FF
        sta CURLIN
        sta CURLIN+1

        rts

;-------------------------------------------------------------------------------
; TCP Receive Callback
;-------------------------------------------------------------------------------
recv_callback:
        ; Streaming state machine callback
        ; Processes incoming data based on current state
        lda tcp_inbound_data_length
        ora tcp_inbound_data_length+1
        bne @have_data
        rts
@have_data:
        ; Set up source pointer
        lda tcp_inbound_data_ptr
        sta copy_src
        lda tcp_inbound_data_ptr+1
        sta copy_src+1

        ; Y = index into incoming data
        ldy #0

        ; Signal we got data
        lda #1
        sta got_data

@cb_loop:
        ; Check if we've processed all incoming data (16-bit compare: Y vs tcp_inbound_data_length)
        lda tcp_inbound_data_length+1     ; Check high byte first
        bne @more_data                    ; If high byte != 0, length > 255, so Y is definitely less
        cpy tcp_inbound_data_length       ; High byte is 0, compare Y with low byte
        bcc @more_data                    ; Y < low_byte means more data
        rts                               ; Done with this callback
@more_data:
        ; Dispatch based on state
        lda stream_state
        beq @st_skip_headers    ; STATE_SKIP_HEADERS = 0
        cmp #STATE_READ_MAGIC
        beq @st_read_magic
        cmp #STATE_READ_TOTAL_LEN
        beq @st_read_header
        cmp #STATE_READ_START
        beq @st_read_header
        cmp #STATE_READ_CHUNK_SZ
        beq @st_read_header
        cmp #STATE_READ_CHUNK
        beq @go_read_chunk
        ; STATE_DONE or STATE_ERROR - just exit
        rts
@go_read_chunk:
        jmp @st_read_chunk

;--- STATE: Skip HTTP headers (look for CRLFCRLF) ---
@st_skip_headers:
        lda (copy_src),y
        iny
        bne @skip_no_wrap       ; Check if Y wrapped to 0
        inc copy_src+1          ; Adjust pointer for next 256 bytes
        dec tcp_inbound_data_length+1  ; Reduce length high byte
@skip_no_wrap:
        cmp #13                 ; CR
        beq @got_cr
        cmp #10                 ; LF
        beq @got_lf
        ; Not CR or LF, reset counter
        lda #0
        sta cr_count
        jmp @cb_loop

@got_cr:
@got_lf:
        inc cr_count
        lda cr_count
        cmp #4                  ; Found CRLFCRLF (or any 4 CR/LFs)
        bne @cb_loop
        ; Found end of headers - move to read magic
        lda #0
        sta header_pos
        lda #STATE_READ_MAGIC
        sta stream_state
        jmp @cb_loop

;--- STATE: Read header bytes (magic/length/start/chunk_size) ---
@st_read_magic:
@st_read_header:
        lda (copy_src),y
        iny
        bne @hdr_no_wrap        ; Check if Y wrapped to 0
        inc copy_src+1          ; Adjust pointer for next 256 bytes
        dec tcp_inbound_data_length+1  ; Reduce length high byte
@hdr_no_wrap:
        ldx header_pos
        sta header_buf,x
        inc header_pos

        ; Check what we're reading and if complete
        lda stream_state
        cmp #STATE_READ_MAGIC
        bne @not_magic

        ; Reading magic - need 4 bytes
        lda header_pos
        cmp #4
        bne @cb_loop
        ; Verify "BAS2"
        lda header_buf
        cmp #'B'
        bne @bad_magic
        lda header_buf+1
        cmp #'A'
        bne @bad_magic
        lda header_buf+2
        cmp #'S'
        bne @bad_magic
        lda header_buf+3
        cmp #'2'
        bne @bad_magic
        ; Good magic! Move to read total length
        lda #0
        sta header_pos
        lda #STATE_READ_TOTAL_LEN
        sta stream_state
        jmp @cb_loop

@bad_magic:
        lda #STATE_ERROR
        sta stream_state
        rts

@not_magic:
        cmp #STATE_READ_TOTAL_LEN
        bne @not_total_len

        ; Reading total length - need 2 bytes
        lda header_pos
        cmp #2
        beq @got_total_len
        jmp @cb_loop
@got_total_len:
        ; Store total length
        lda header_buf
        sta total_length
        sta basic_len           ; Also in basic_len for compatibility
        lda header_buf+1
        sta total_length+1
        sta basic_len+1
        ; Move to read start address
        lda #0
        sta header_pos
        lda #STATE_READ_START
        sta stream_state
        jmp @cb_loop

@not_total_len:
        cmp #STATE_READ_START
        bne @not_start

        ; Reading start address - need 2 bytes
        lda header_pos
        cmp #2
        beq @got_start
        jmp @cb_loop
@got_start:
        ; Store start address and init dst_ptr
        lda header_buf
        sta basic_start_addr
        sta dst_ptr
        lda header_buf+1
        sta basic_start_addr+1
        sta dst_ptr+1
        ; Init bytes written
        lda #0
        sta bytes_written
        sta bytes_written+1
        ; Move to read first chunk size
        lda #0
        sta header_pos
        lda #STATE_READ_CHUNK_SZ
        sta stream_state
        jmp @cb_loop

@not_start:
        ; Must be STATE_READ_CHUNK_SZ - need 2 bytes
        lda header_pos
        cmp #2
        beq @got_chunk_sz
        jmp @cb_loop
@got_chunk_sz:
        ; Store chunk size
        lda header_buf
        sta chunk_size
        sta chunk_remain
        lda header_buf+1
        sta chunk_size+1
        sta chunk_remain+1
        ; Check for end marker (chunk_size == 0)
        ora header_buf
        beq @stream_done
        ; Move to read chunk data
        lda #STATE_READ_CHUNK
        sta stream_state
        jmp @cb_loop

@stream_done:
        ; All chunks received!
        lda #1
        sta got_valid_basic
        lda #STATE_DONE
        sta stream_state
        rts

;--- STATE: Read chunk data directly to memory ---
@st_read_chunk:
        ; Copy byte directly to (dst_ptr)
        lda (copy_src),y
        iny
        bne @chunk_no_wrap      ; Check if Y wrapped to 0
        inc copy_src+1          ; Adjust pointer for next 256 bytes
        dec tcp_inbound_data_length+1  ; Reduce length high byte
@chunk_no_wrap:
        ldx #0
        sta (dst_ptr,x)

        ; Increment dst_ptr
        inc dst_ptr
        bne @no_dst_carry
        inc dst_ptr+1
@no_dst_carry:

        ; Increment bytes_written
        inc bytes_written
        bne @no_bw_carry
        inc bytes_written+1
@no_bw_carry:

        ; Decrement chunk_remain
        lda chunk_remain
        bne @dec_low
        dec chunk_remain+1
@dec_low:
        dec chunk_remain

        ; Check if chunk complete
        lda chunk_remain
        ora chunk_remain+1
        beq @chunk_done
        jmp @cb_loop

@chunk_done:
        ; Chunk done - read next chunk size
        lda #0
        sta header_pos
        lda #STATE_READ_CHUNK_SZ
        sta stream_state
        jmp @cb_loop

;-------------------------------------------------------------------------------
; Print A as 2 hex digits
;-------------------------------------------------------------------------------
print_hex_byte:
        pha
        lsr
        lsr
        lsr
        lsr
        jsr @print_nibble
        pla
        and #$0F
@print_nibble:
        cmp #10
        bcc @digit
        adc #6
@digit:
        adc #'0'
        jmp print_a

;===============================================================================
; DATA
;===============================================================================

.segment "RODATA"

banner_msg:
        .byte "CLAUDE AGENT V3.0 AMPERSAND", 13, 0

network_init_msg:
        .byte "INIT NETWORK...", 0

fail_msg:
        .byte "NETWORK FAILED", 13, 0

installed_msg:
        .byte "TYPE & FOR CLAUDE CONSOLE", 13
        .byte "(ESC TO EXIT CONSOLE)", 0

console_header:
        .byte "=== CLAUDE CODE ===", 0

prompt_msg:
        .byte "CLAUDE> ", 0

connecting_msg:
        .byte "CONNECTING", 0

conn_fail_msg:
        .byte " FAILED", 0

send_fail_msg:
        .byte " SEND ERROR", 0

timeout_msg:
        .byte " TIMEOUT", 0

injected_msg:
        .byte "PROGRAM LOADED!", 13
        .byte "TYPE 'LIST' OR 'RUN'", 0

parse_err_msg:
        .byte "ERROR PARSING RESPONSE", 0

not_binary_msg:
        .byte "NOT BINARY RESPONSE", 0

len_msg:
        .byte "BASIC LEN=$", 0

; HTTP header for binary endpoint
http_hdr_bin:
        .byte "POST /claude/binary HTTP/1.0", 13, 10
        .byte "Host: proxy", 13, 10
        .byte "Content-Type: text/plain", 13, 10
        .byte "Content-Length: "
http_hdr_bin_len = * - http_hdr_bin

;===============================================================================
; BSS
;===============================================================================

.segment "BSS"

tsr_flags:       .res 1      ; TSR state flags
input_pos:       .res 1
input_buffer:    .res 256
got_data:        .res 1
got_valid_basic: .res 1
data_wait:       .res 1
timeout_lo:      .res 1
timeout_hi:      .res 1
last_bytes_lo:   .res 1          ; Track bytes_written for new data detection
last_bytes_hi:   .res 1
num_temp:        .res 1
send_len:        .res 2
send_buffer:     .res 384

; Streaming state variables
stream_state:    .res 1      ; Current state machine state
header_buf:      .res 16     ; Small buffer for protocol header
header_pos:      .res 1      ; Position in header buffer
total_length:    .res 2      ; Total BASIC program size
bytes_written:   .res 2      ; Bytes written to BASIC memory
chunk_size:      .res 2      ; Current chunk size
chunk_remain:    .res 2      ; Bytes remaining in current chunk
cr_count:        .res 1      ; Count of consecutive CR/LFs for header scan

; Legacy variables for compatibility
basic_len:       .res 2
basic_start_addr: .res 2

; Small buffer for leftover data between callbacks (not full program)
recv_buffer:     .res 256
