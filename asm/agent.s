;===============================================================================
; APPLE II AGENT - Unified Binary for Claude AI Chat
;
; Features:
; - A2P Protocol (reliable packet-based communication)
; - 40/80 column auto-detection
; - Full-screen chat interface
; - IP address configuration with save/load
; - BASIC code injection
; - Reconnection with exponential backoff
;
; Memory Map:
;   $0300-$030F   Configuration (IP, port, flags)
;   $03F5-$03F7   Ampersand hook vector
;   $0400-$07FF   Text screen
;   $0801-$5FFF   BASIC program area (~22KB)
;   $6000-$7FFF   AGENT.BIN code
;   $8000-$8FFF   Receive buffer (4KB circular)
;   $9000-$93FF   Screen save buffer
;
; A2P Protocol Packet Format:
;   [A2][Type][Len:2][Seq][Data...][Checksum]
;
; Usage:
;   BRUN AGENT
;   Type messages at AGENT> prompt
;   Press ESC for menu
;
;===============================================================================

        .setcpu "6502"

.include "../libs/ip65/inc/common.inc"
.include "../libs/ip65/inc/commonprint.inc"
.include "../libs/ip65/inc/net.inc"

.export start

.import __BSS_RUN__, __BSS_SIZE__
.import print_a
.import get_key
.import ip65_process
.import tcp_rx_count, tcp_bad_cksum          ; (patched IP65) for the stall report
.import tcp_connect_ack_number, tcp_connect_last_received_seq_number
.import w5100_rx_resyncs
.import tcp_connect
.import tcp_connect_ip
.import tcp_callback
.import tcp_close
.import tcp_send
.import tcp_send_data_len
.import tcp_inbound_data_ptr
.import tcp_inbound_data_length
.import tcp_state
.import print_cr
.importzp copy_src
; UDP, for finding the proxy (find_proxy)
.import udp_add_listener
.import udp_remove_listener
.import udp_callback
.import udp_send
.import udp_send_dest
.import udp_send_src_port
.import udp_send_dest_port
.import udp_send_len
.import udp_inp
.import ip_inp
.importzp udp_data
.importzp ip_src

;-------------------------------------------------------------------------------
; A2P Protocol Constants
;-------------------------------------------------------------------------------
A2P_MAGIC_0     = 'A'           ; Protocol magic bytes
A2P_MAGIC_1     = '2'

; Packet types
PKT_INIT        = $00           ; Initialize connection
PKT_CHAT        = $01           ; User chat message
PKT_RESP        = $02           ; AI response chunk
PKT_CODE        = $03           ; BASIC code chunk
PKT_STATUS      = $04           ; Status message
PKT_ACK         = $05           ; Acknowledgment
PKT_NACK        = $06           ; Request retransmit
PKT_ERR         = $0F           ; Error message

; Capability flags (in INIT packet)
CAP_40_COL      = $00           ; 40-column mode
CAP_80_COL      = $01           ; 80-column mode
CAP_LOWERCASE   = $02           ; Supports lowercase
CAP_MOUSE       = $04           ; Has mouse card

; Response flags (in RESP packet)
RESP_FLAG_FINAL = $01           ; This is the final chunk

TCP_ESTABLISHED = 3             ; IP65 tcp_state when connected
DEFAULT_PORT    = 6502          ; Proxy port

; Configuration at $0300
CONFIG_BASE     = $0300
CONFIG_IP       = $0300         ; 4 bytes: proxy IP
CONFIG_PORT     = $0304         ; 2 bytes: port (little-endian)
CONFIG_MODEL    = $0306         ; 1 byte: AI model (0=sonnet, 1=opus, 2=haiku)
CONFIG_MAGIC    = $0307         ; 1 byte: magic ($A2 = valid config)
CONFIG_DISPLAY   = $0308         ; 1 byte: display mode (0=40U, 1=40L, 2=80)
CONFIG_WATCHDOG  = $0309         ; 1 byte: stall watchdog seconds, 0 = off (9-byte files: 20)
DEFAULT_WATCHDOG = 20
CONFIG_MAGIC_VAL = $A2

; Display mode constants
DISPLAY_40U      = 0             ; 40-col uppercase (Apple ][/][+)
DISPLAY_40L      = 1             ; 40-col mixed case (//e with ALTCHARSET)
DISPLAY_80       = 2             ; 80-col mixed case (//e with 80-col card)

; Model constants
MODEL_SONNET    = 0
MODEL_OPUS      = 1
MODEL_HAIKU     = 2

; BASIC hooks
AMPER_VECTOR    = $03F5         ; & hook vector
CTRLY_VECTOR    = $03F8         ; Ctrl-Y hook vector

; BASIC memory
TXTTAB          = $67
VARTAB          = $69
ARYTAB          = $6B
STREND          = $6D
PRGEND          = $AF           ; End of program pointer (needed for editing)
BASIC_START     = $0801

; BASIC error variables (for automatic error detection)
ERRNUM          = $DE           ; Error code (set by ONERR)
ERRLIN          = $DA           ; Error line number low byte
ERRLIN_H        = $DB           ; Error line number high byte
ERRFLG          = $D8           ; Bit 7 = ONERR active
CURLIN          = $75           ; Current line ($FF,$FF = immediate mode)
CURLIN_H        = $76
ERR_LASTNUM     = $222          ; Last error number (simpler to use)

; ONERR hook (Phase 2b - natural language at BASIC prompt)
BASIC_INPUT_BUF = $200          ; Applesoft input buffer
KSWL            = $38           ; Keyboard input vector (low)
KSWH            = $39           ; Keyboard input vector (high)
ERR_SYNTAX      = 16            ; SYNTAX ERROR code

; Text screen
TEXTPAGE        = $0400

;-------------------------------------------------------------------------------
; Screen Dimensions
;-------------------------------------------------------------------------------
; 40-column mode
WIDTH_40        = 40
; 80-column mode
WIDTH_80        = 80

; Screen regions (both modes)
HEADER_LINE     = 0             ; Header at top
OUTPUT_START    = 1             ; Output starts at line 1
OUTPUT_END      = 20            ; Output ends at line 20
SEPARATOR_LINE  = 21            ; Separator (fixed)
STATUS_LINE     = 22            ; Status messages (fixed)
INPUT_LINE      = 23            ; Input at bottom (fixed)
HEIGHT          = 24

;-------------------------------------------------------------------------------
; ROM/Monitor Routines
;-------------------------------------------------------------------------------
HOME            = $FC58         ; Clear screen
COUT            = $FDED         ; Character output
COUT1           = $FDF0         ; Character output (no ESC check)
RDKEY           = $FD0C         ; Read key with cursor
VTAB            = $FB5B         ; Set vertical position
CLREOL          = $FC9C         ; Clear to end of line
BEEP            = $FBDD         ; Beep speaker

; Zero page locations used by Monitor
CH              = $24           ; Horizontal cursor position
CV              = $25           ; Vertical cursor position

; Soft switches
KBD             = $C000         ; Keyboard data
KBDSTRB         = $C010         ; Keyboard strobe
BELL1           = $FBDD         ; Beep the speaker (no COUT)
WAIT            = $FCA8         ; Monitor delay: (26 + 27A + 5A*A) / 2 cycles
RDVBLBAR        = $C019         ; bit 7 low during vertical blank (//e)
TXTPAGE1        = $C054         ; Display page 1
TXTPAGE2        = $C055         ; Display page 2
STORE80OFF      = $C000         ; 80-col store off
STORE80ON       = $C001         ; 80-col store on
CLR80VID        = $C00C         ; 40-col mode
SET80VID        = $C00D         ; 80-col mode
CLRALTCHAR      = $C00E         ; Uppercase charset
SETALTCHAR      = $C00F         ; Alternate charset (lowercase)
INIT80COL       = $C300         ; 80-col firmware entry
RDTEXT          = $C01A         ; Read text/graphics flag
RD80COL         = $C01F         ; Read 80-col card status

;-------------------------------------------------------------------------------
; ProDOS MLI
;-------------------------------------------------------------------------------
MLI             = $BF00         ; ProDOS MLI entry point
MLI_CREATE      = $C0           ; Create file
MLI_OPEN        = $C8           ; Open file
MLI_READ        = $CA           ; Read from file
MLI_WRITE       = $CB           ; Write to file
MLI_CLOSE       = $CC           ; Close file
MLI_SET_EOF     = $D0           ; Set end of file

; ProDOS file types
FT_BIN          = $06           ; Binary file

; Config file size (9 bytes: IP + Port + Model + Magic + Display)
CONFIG_SIZE     = 10

;-------------------------------------------------------------------------------
; Zero Page Variables (using safe locations not used by IP65)
; IP65 uses $06-$07 (copy_src) which we import
;-------------------------------------------------------------------------------
src_ptr         = $FA           ; Source pointer (2 bytes)
dst_ptr         = $FC           ; Destination pointer (2 bytes)
pkt_ptr         = $FE           ; Packet data pointer (2 bytes)
status_ptr      = $E8           ; Status line string pointer (2 bytes)
temp1           = $EB           ; Temp variable
temp2           = $EC           ; Temp variable
scroll_cnt      = $ED           ; Scroll counter

;-------------------------------------------------------------------------------
; Linker segments
;-------------------------------------------------------------------------------
        .segment "INIT"
        .segment "ONCE"
        .segment "STARTUP"

;===============================================================================
; Entry Point
;===============================================================================
start:
        ; Fresh variables (nothing zeroes BSS for us)
        lda #<__BSS_RUN__
        sta dst_ptr
        lda #>__BSS_RUN__
        sta dst_ptr+1
        ldx #>__BSS_SIZE__
        ldy #0
        tya
@clear_page:
        cpx #0
        beq @clear_tail
@clear_byte:
        sta (dst_ptr),y
        iny
        bne @clear_byte
        inc dst_ptr+1
        dex
        bne @clear_page
@clear_tail:
        cpy #<__BSS_SIZE__
        beq @cleared
        sta (dst_ptr),y
        iny
        bne @clear_tail
@cleared:

        ; Print banner first
        jsr clear_screen
        ldax #msg_banner
        jsr print
        jsr print_cr

        ; Load saved configuration FIRST (before display mode)
        jsr load_config
        jsr save_config_shadow
        jsr detect_aux_ram
        jsr init_applesoft      ; no BASIC.SYSTEM ran Applesoft's cold start
        jsr init_basic_program

        ; Apply display mode from config
        lda CONFIG_DISPLAY
        cmp #3                  ; Validate (must be 0, 1, or 2)
        bcc @display_ok
        lda #DISPLAY_40U        ; Default if garbage
        sta CONFIG_DISPLAY
@display_ok:
        sta display_mode
        jsr apply_display_mode
        jsr clear_screen        ; the banner again, in the chosen mode
        ldax #msg_banner
        jsr print
        jsr print_cr

        ; Show display mode
        lda display_mode
        cmp #DISPLAY_80
        beq @show_80
        cmp #DISPLAY_40L
        beq @show_40l
        ldax #msg_40col
        jmp @show_mode
@show_40l:
        ldax #msg_40l
        jmp @show_mode
@show_80:
        ldax #msg_80col
@show_mode:
        jsr print
        jsr print_cr

        ; Initialize network
@init_net:
        ldax #msg_init_net
        jsr print
        init_ip_via_dhcp
        bcc @net_ok

        ; A real Uthernet's link can take a few seconds to come up after
        ; power-on, so DHCP may fail at first: retry by itself
        ldax #msg_net_fail
        jsr print
        jsr print_cr
        ldax #msg_net_retry
        jsr print
        lda #50                 ; ~5 seconds, or a key
        jsr wait_key_or_timeout
        jsr print_cr
        jmp @init_net

@net_ok:
        jsr print_cr
        ldax #msg_my_address
        jsr print
        ldax #cfg_ip
        jsr print_dotted_quad
        jsr print_cr

        ; Install ampersand hook
        jsr install_hook
        ; Ctrl-Reset, BRK and $03D0 all lead back to the agent from now on
        jsr install_resident_hooks

        ; Where is the proxy? Ask the network first; fall back to the
        ; saved (or default) address
        jsr print_cr
        ldax #msg_finding
        jsr print
        jsr find_proxy
        bcs @not_found
        ldax #msg_found
        jsr print
        jsr print_proxy_address
        jsr print_cr
        jsr save_if_moved       ; remember it for next time
        jmp @connect
@not_found:
        ldax #msg_not_found
        jsr print
        jsr print_proxy_address
        jsr print_cr

@connect:
        ldax #msg_connecting
        jsr print
        jsr connect_to_proxy
        bcs @conn_failed

        ldax #msg_connected_proxy
        jsr print
        jsr print_cr
        ldax #msg_installed
        jsr print
        jsr print_cr
        lda #20                 ; a moment to read it, then straight in
        jsr wait_key_or_timeout
        jmp @ui

@conn_failed:
        ldax #msg_conn_fail
        jsr print
        jsr print_cr
        ldax #msg_start_proxy
        jsr print
        jsr print_cr

        ; Wait for key so user can see boot info
        ldax #msg_press_key
        jsr print
        jsr read_key           ; Wait for any key
@ui:
        jsr print_cr        ; Line break before UI

        ; Go directly to main UI
        jsr main_ui

        ; Return to BASIC when done ($03D0 now leads back to the agent)
        jmp cmd_suspend

;-------------------------------------------------------------------------------
; Detect 80-column card
; Returns: A=0 for 40-col, A=CAP_80_COL for 80-col
;-------------------------------------------------------------------------------
detect_80col:
        ; Check if 80-col card present by reading soft switch
        lda RD80COL
        bmi @have_80col
        lda #CAP_40_COL
        rts
@have_80col:
        lda #CAP_80_COL
        rts

;-------------------------------------------------------------------------------
; Apply display mode (sets hardware, screen width, col_mode)
; Input: display_mode must be set (0=40U, 1=40L, 2=80)
;-------------------------------------------------------------------------------
apply_display_mode:
        ; 80 columns needs an 80-column card (ProDOS MACHID bit 1); without
        ; one it's 40 columns, mixed case
        lda display_mode
        cmp #DISPLAY_80
        bne :+
        lda MACHID
        and #$02
        bne :+
        lda #DISPLAY_40L
        sta display_mode
        sta CONFIG_DISPLAY
:       lda display_mode
        cmp #DISPLAY_80
        beq @mode_80
        cmp #DISPLAY_40L
        beq @mode_40l
        ; Default: 40U
@mode_40u:
        sta CLR80VID            ; 40-col
        sta STORE80OFF
        sta CLRALTCHAR          ; Uppercase only
        ; Restore CSW to normal COUT1 (in case 80-col firmware changed it)
        lda #<COUT1
        sta $36                 ; CSWL
        lda #>COUT1
        sta $37                 ; CSWH
        lda #39
        sta screen_width_m1
        lda #CAP_40_COL
        sta col_mode
        rts
@mode_40l:
        sta CLR80VID
        sta STORE80OFF
        sta SETALTCHAR          ; Enable lowercase
        ; Restore CSW to normal COUT1
        lda #<COUT1
        sta $36                 ; CSWL
        lda #>COUT1
        sta $37                 ; CSWH
        lda #39
        sta screen_width_m1
        lda #CAP_40_COL
        sta col_mode
        rts
@mode_80:
        ; 80 columns with our own output (agent_screen.s), not the $C300
        ; firmware: COUT goes to vid80_out, which writes aux and main
        sta SET80VID            ; Enable 80-col display
        sta STORE80ON           ; PAGE2 selects aux memory for $0400-$07FF
        sta SETALTCHAR          ; Enable lowercase
        sta TXTPAGE1
        lda #<vid80_out
        sta $36                 ; CSWL
        lda #>vid80_out
        sta $37                 ; CSWH
        lda #79
        sta screen_width_m1
        lda #CAP_80_COL
        sta col_mode
        rts

;-------------------------------------------------------------------------------
; Install ampersand hook
;-------------------------------------------------------------------------------
install_hook:
        lda #$4C              ; & -> JMP RETURN_ENTRY: back to the agent
        sta AMPER_VECTOR
        lda #<RETURN_ENTRY
        sta AMPER_VECTOR+1
        lda #>RETURN_ENTRY
        sta AMPER_VECTOR+2
        rts

;-------------------------------------------------------------------------------
; Check for BASIC error by scanning screen for "?" error messages
; Scans text screen memory for lines starting with "?"
;-------------------------------------------------------------------------------
check_basic_error:
        ; Scan screen lines for "?" at start (error indicator)
        ; Screen lines are at: $400, $480, $500, $580, $600, $680, $700, $780
        ;                      $428, $4A8, $528, $5A8, $628, $6A8, $728, $7A8
        ;                      $450, $4D0, $550, $5D0, $650, $6D0, $750, $7D0

        ; Check the most recent lines (bottom of screen) first
        ; Line 23 = $7D0, Line 22 = $750, Line 21 = $6D0, etc.

        ldx #23                 ; Start from bottom line
@scan_line:
        jsr get_screen_line_addr  ; Get line address in src_ptr
        ldy #0
        lda (src_ptr),y         ; Get first char
        and #$7F                ; Clear high bit (normal/inverse)
        cmp #'?'                ; Error indicator?
        beq @found_error
        dex
        bpl @scan_line
        ; No error found
        rts

@found_error:
        ; Found "?" - copy the error message to input_buffer
        ; Format: "FIX: " + error text from screen
        ldy #0

        ; Add "FIX: " prefix
        lda #'F'
        sta input_buffer,y
        iny
        lda #'I'
        sta input_buffer,y
        iny
        lda #'X'
        sta input_buffer,y
        iny
        lda #':'
        sta input_buffer,y
        iny
        lda #' '
        sta input_buffer,y
        iny

        ; Copy error text from screen (skip the "?")
        sty temp2               ; Save position
        ldy #1                  ; Start after "?"
@copy_error:
        lda (src_ptr),y
        and #$7F                ; Clear high bit
        cmp #$20                ; Space or control char at end?
        bcc @end_copy           ; Control char = end
        ; Store character
        pha
        tya
        clc
        adc temp2
        tax
        pla
        sta input_buffer-1,x    ; -1 because temp2 already has offset
        iny
        cpy #35                 ; Max error length
        bcc @copy_error

@end_copy:
        ; Calculate final length
        tya
        clc
        adc temp2
        sec
        sbc #1                  ; Adjust for offset
        sta input_len

        ; Null terminate
        tax
        lda #0
        sta input_buffer,x

        rts

;-------------------------------------------------------------------------------
; Get screen line address for line X (0-23)
; Returns address in src_ptr
;-------------------------------------------------------------------------------
get_screen_line_addr:
        ; Screen line address table (low bytes)
        ; Lines are not contiguous in memory
        lda screen_addr_lo,x
        sta src_ptr
        lda screen_addr_hi,x
        sta src_ptr+1
        rts

; Screen line address lookup tables
screen_addr_lo:
        .byte <$400, <$480, <$500, <$580, <$600, <$680, <$700, <$780
        .byte <$428, <$4A8, <$528, <$5A8, <$628, <$6A8, <$728, <$7A8
        .byte <$450, <$4D0, <$550, <$5D0, <$650, <$6D0, <$750, <$7D0

screen_addr_hi:
        .byte >$400, >$480, >$500, >$580, >$600, >$680, >$700, >$780
        .byte >$428, >$4A8, >$528, >$5A8, >$628, >$6A8, >$728, >$7A8
        .byte >$450, >$4D0, >$550, >$5D0, >$650, >$6D0, >$750, >$7D0

; Language Card soft switches
LCRAM_RW        = $C083         ; Read twice: LC bank 2 read + write
LCRAM_RO        = $C080         ; Read: LC bank 2 read, write-protect
LCRAM_ROM_WR    = $C081         ; Read twice: read ROM, write LC bank 2
LCRAM_ROM       = $C082         ; Read ROM, write-protect LC
BASIC_WARM      = $E003         ; Applesoft warm start (] prompt)


;-------------------------------------------------------------------------------
; Load configuration from disk (or use defaults)
;-------------------------------------------------------------------------------
load_config:
        ; Try to load from disk first
        jsr load_config_file
        bcc @loaded              ; Success - config loaded

        ; Check if memory config is valid
        lda CONFIG_MAGIC
        cmp #CONFIG_MAGIC_VAL
        beq @done                ; Already valid in memory

@use_defaults:
        ; Set default IP: 192.168.64.1
        lda #192
        sta CONFIG_IP
        lda #168
        sta CONFIG_IP+1
        lda #64
        sta CONFIG_IP+2
        lda #1
        sta CONFIG_IP+3

        ; Port 6502 (of course)
        lda #<DEFAULT_PORT
        sta CONFIG_PORT
        lda #>DEFAULT_PORT
        sta CONFIG_PORT+1

        ; Default model: Opus
        lda #MODEL_OPUS
        sta CONFIG_MODEL

        ; Default display: 40U (uppercase)
        lda #DISPLAY_40U
        sta CONFIG_DISPLAY

        lda #DEFAULT_WATCHDOG
        sta CONFIG_WATCHDOG

        ; Mark as valid
        lda #CONFIG_MAGIC_VAL
        sta CONFIG_MAGIC

@loaded:
@done:
        rts

;-------------------------------------------------------------------------------
; Load config from disk file
; Returns: C=0 success, C=1 failure
;-------------------------------------------------------------------------------
load_config_file:
        ; Open file
        jsr MLI
        .byte MLI_OPEN
        .word open_parms
        bcs @fail

        ; Save ref num
        lda open_refnum
        sta read_refnum
        sta close_refnum

        ; Read config data directly to CONFIG_IP
        jsr MLI
        .byte MLI_READ
        .word read_parms
        bcs @close_fail

        ; Close file
        jsr MLI
        .byte MLI_CLOSE
        .word close_parms

        ; Verify magic byte
        lda CONFIG_MAGIC
        cmp #CONFIG_MAGIC_VAL
        bne @fail

        ; A file from before the watchdog byte: the default
        lda read_trans
        cmp #CONFIG_SIZE
        bcs :+
        lda #DEFAULT_WATCHDOG
        sta CONFIG_WATCHDOG
:
        clc                      ; Success
        rts

@close_fail:
        jsr MLI
        .byte MLI_CLOSE
        .word close_parms

@fail:
        sec                      ; Failure
        rts

;-------------------------------------------------------------------------------
; Save config to disk file
; Returns: C=0 success, C=1 failure
;-------------------------------------------------------------------------------
save_config_file:
        ; Valid in memory either way, and safe from programs that use page 3
        lda #CONFIG_MAGIC_VAL
        sta CONFIG_MAGIC
        jsr save_config_shadow

        ; CLAUDECONF next to AGENT.SYSTEM (ProDOS's prefix is the boot volume)
        jsr MLI
        .byte MLI_CREATE
        .word create_parms
        bcc @open
        cmp #$47                 ; duplicate filename: it's already there
        bne @fail
@open:
        jsr MLI
        .byte MLI_OPEN
        .word open_parms
        bcs @fail
        lda open_refnum
        sta write_refnum
        sta close_refnum

        ; Write config data from CONFIG_IP (overwrites the old one in place)
        jsr MLI
        .byte MLI_WRITE
        .word write_parms
        bcs @close_fail

        ; Close file
        jsr MLI
        .byte MLI_CLOSE
        .word close_parms
        bcs @fail

        clc                      ; Success
        rts

@close_fail:
        pha                      ; Save error code
        jsr MLI
        .byte MLI_CLOSE
        .word close_parms
        pla                      ; Restore error code
@fail:
        ; Settings still work until the next boot; say why they won't stick
        ; ($2B = write-protected disk)
        sta config_save_err
        ldax #msg_not_saved
        jsr print_status
        lda config_save_err
        sec                      ; Failure (A = error code)
        rts

;===============================================================================
; Main UI
;===============================================================================
main_ui:
        jsr draw_ui

main_ui_loop:
@main_loop:
        ; Position cursor at input line (line 23) for prompt
        lda #INPUT_LINE
        sta CV
        jsr VTAB
        lda #0
        sta CH
        jsr clear_eol

        ; Print prompt
        ldax #prompt_str
        jsr print

        ; Get input
        jsr get_input
        bcs @check_esc       ; Special key pressed

        ; Empty input?
        lda input_len
        beq @main_loop

        ; Process input
        jsr process_input
        jmp @main_loop

@check_esc:
        ; ESC clears the line (or does nothing on an empty one - a held ESC
        ; that brought you back from a program repeats into here)
        lda #0
        sta input_len
        jsr redraw_input
        jmp @main_loop

;-------------------------------------------------------------------------------
; Clear the screen and draw the header; the log starts at OUTPUT_START
;-------------------------------------------------------------------------------
draw_ui:
        jsr clear_screen
        lda #OUTPUT_START
        sta output_row
        lda #0
        sta output_col
        sta lines_since_pause
        ldax #ui_header
        jsr print
        jmp print_cr

;-------------------------------------------------------------------------------
; Draw the full command frame (called when wrapping)
; Now just outputs a blank line (no separator)
;-------------------------------------------------------------------------------
draw_command_area:
        ; Output CR to advance line in terminal mode
        lda #$8D
        jsr COUT
        rts

;-------------------------------------------------------------------------------
; Draw input prompt
;-------------------------------------------------------------------------------
draw_prompt:
        lda #INPUT_LINE
        sta CV
        jsr VTAB
        lda #0
        sta CH               ; Start at column 0
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
        lda #8               ; After "AGENT> "
        sta CH
        rts

;-------------------------------------------------------------------------------
; Clear current line
;-------------------------------------------------------------------------------
clear_line:
        jsr clear_eol
        rts

;-------------------------------------------------------------------------------
; Get user input
; Returns: C=1 if special key (key in A), C=0 if normal input
;-------------------------------------------------------------------------------
get_input:
        jsr set_input_visible
        lda prefill_input
        beq @empty
        ; Start with text already in input_buffer (e.g. "FIX: ...")
        lda #0
        sta prefill_input
        jsr redraw_input
        jmp @loop
@empty:
        lda #0
        sta input_len

@loop:
        jsr read_key

        ; Check ESC
        cmp #$9B
        beq @special
        cmp #$1B
        beq @special

        ; Check Return
        cmp #$8D
        beq @done
        cmp #$0D
        beq @done

        ; Check Delete/Backspace (multiple codes for different keyboards)
        cmp #$FF             ; Apple II DELETE key
        beq @delete
        cmp #$08             ; ASCII backspace
        beq @delete
        cmp #$88             ; Backspace with high bit (terminal)
        beq @delete

        ; Printable?
        cmp #$A0             ; Space (high bit set)
        bcc @loop            ; Skip control chars

        ; Buffer full? Say so (a beep), don't just drop the key
        ldx input_len
        cpx #MAX_INPUT
        bcc :+
        jsr BELL1
        jmp @loop
:

        ; Store (clear high bit)
        and #$7F
        sta input_buffer,x
        inc input_len

        ; Echo, or slide the line left once it's full
        ldx input_len
        cpx input_visible
        bcs @redraw
        ora #$80
        jsr COUT
        jmp @loop
@redraw:
        jsr redraw_input
        jmp @loop

@delete:
        lda input_len
        beq @loop

        dec input_len
        ldx input_len           ; was the line scrolled? then redraw it
        inx
        cpx input_visible
        bcs @redraw

        ; Backspace-space-backspace
        lda #$88             ; Left arrow
        jsr COUT
        lda #$A0             ; Space
        jsr COUT
        lda #$88
        jsr COUT
        jmp @loop

@special:
        sec
        rts

@done:
        ; Null terminate - and clear the rest of the buffer: commands read
        ; their argument at a fixed offset, so a bare /PORT must find zeros
        ; there, not the end of an earlier, longer line
        ldx input_len
        lda #0
:       sta input_buffer,x
        inx
        cpx #MAX_INPUT+1
        bcc :-
        clc
        rts

;-------------------------------------------------------------------------------
; Redraw the input line after "AGENT> ", showing the end of input_buffer so
; long requests scroll sideways instead of wrapping (a wrap on the bottom
; row would scroll the whole screen)
;-------------------------------------------------------------------------------
PROMPT_LEN      = 7             ; "AGENT> "

redraw_input:
        jsr set_input_visible
        lda #INPUT_LINE
        sta CV
        jsr VTAB
        lda #PROMPT_LEN
        sta CH
        ldx #0
        lda input_len
        sec
        sbc input_visible
        bcc @from_x
        tax
        inx                     ; leave the last column for the cursor
@from_x:
        cpx input_len
        bcs @clear
        lda input_buffer,x
        ora #$80
        jsr COUT
        inx
        bne @from_x
@clear:
        jsr clear_eol
        rts

; input_visible = columns available for input text (screen width - prompt - 1)
set_input_visible:
        lda screen_width_m1
        sec
        sbc #PROMPT_LEN
        sta input_visible
        rts

;-------------------------------------------------------------------------------
; Process user input
;-------------------------------------------------------------------------------
process_input:
        ; Check for commands starting with /
        lda input_buffer
        cmp #'/'
        beq @command

        ; Regular chat - send to server
        jsr send_chat
        rts

@command:
        ; Parse command
        jsr handle_command
        rts

;-------------------------------------------------------------------------------
; Handle slash command
; NOTE: All comparisons convert to uppercase for case-insensitive matching
;-------------------------------------------------------------------------------
handle_command:
        ; Look the word after "/" up in cmd_table (whole word, any case)
        ldx #0                  ; table offset
@next_entry:
        lda cmd_table,x
        beq @not_local          ; end of table
        ldy #1                  ; input_buffer+1 = first letter
@compare:
        lda cmd_table,x
        beq @word_end
        sta temp1
        lda input_buffer,y
        jsr to_upper
        cmp temp1
        bne @skip_entry
        inx
        iny
        bne @compare
@word_end:
        ; table word ended - input must end too (space or end of line)
        lda input_buffer,y
        beq @found
        cmp #' '
        beq @found
@skip_entry:
        lda cmd_table,x         ; skip rest of word...
        beq @skip_addr
        inx
        bne @skip_entry
@skip_addr:
        inx                     ; ...its zero and handler address
        inx
        inx
        bne @next_entry
@found:
        ; Jump to the handler (RTS trick); its RTS returns to our caller
        lda cmd_table+2,x
        pha
        lda cmd_table+1,x
        pha
        rts
@not_local:
        ; Everything else is the proxy's business (/HELP, /RESET, /UNDO...)
        jmp send_chat

; Commands the Apple II handles itself: word, 0, handler-1
.macro command word, handler
        .byte word, 0
        .word handler-1
.endmacro
cmd_table:
        command "RUN",     cmd_run
        command "EXIT",    cmd_suspend
        command "SUSPEND", cmd_suspend
        command "QUIT",    cmd_suspend
        command "SETIP",   cmd_setip
        command "PORT",    cmd_port
        command "IP",      cmd_ip
        command "SAVE",    cmd_save
        command "LIST",    cmd_list
        command "CODE",    cmd_code
        command "CLEAR",   cmd_clear
        command "MORE",    cmd_more
        command "DISPLAY", cmd_display
        command "MODEL",   cmd_model
        command "RESET",   cmd_reset
        .byte 0

cmd_clear:
        jmp draw_ui

;-------------------------------------------------------------------------------
; /EXIT, /SUSPEND - drop to the ] prompt, & or Ctrl-Y comes back
;-------------------------------------------------------------------------------
cmd_suspend:
        ; Every way back (ESC at ], &, Ctrl-Y, Ctrl-Reset) lands on
        ; RETURN_ENTRY, the same as from a program. (This used to copy the
        ; ROM over the language card to patch Applesoft's error handler -
        ; which wiped out ProDOS - and poll the network from a keyboard hook,
        ; which scribbled on Applesoft's zero page mid-statement.)
        jsr install_resident_hooks
        jsr install_hook        ; & -> RETURN_ENTRY
        lda #$4C                ; Ctrl-Y -> RETURN_ENTRY
        sta CTRLY_VECTOR
        lda #<RETURN_ENTRY
        sta CTRLY_VECTOR+1
        lda #>RETURN_ENTRY
        sta CTRLY_VECTOR+2
        lda #<KSW_HOOK          ; ESC at ] -> RETURN_ENTRY
        sta KSWL
        lda #>KSW_HOOK
        sta KSWH

        lda #0
        sta in_ui
        sta input_len
        jsr init_applesoft      ; IP65 shares Applesoft's zero page ($80-$99)

        ; Show message and drop to BASIC (plain 40 columns, ROM output)
        jsr text40
        jsr HOME
        ldax #msg_suspended
        jsr print
        jmp BASIC_WARM          ; ] prompt - no return

;-------------------------------------------------------------------------------
; Command: /HELP
;-------------------------------------------------------------------------------
cmd_help:
        jsr scroll_output
        ldax #help_text
        jsr print_multiline
        rts

;-------------------------------------------------------------------------------
; Command: /IP
;-------------------------------------------------------------------------------
cmd_ip:
        jsr scroll_output
        ldax #msg_current_ip
        jsr print
        jsr print_proxy_address
        jsr print_cr
        rts

;-------------------------------------------------------------------------------
; Print CONFIG_IP:CONFIG_PORT ("192.168.1.100:6502")
;-------------------------------------------------------------------------------
print_proxy_address:
        ldx #0
@octet:
        txa
        pha
        lda CONFIG_IP,x
        jsr print_decimal
        pla
        tax
        lda #'.'
        cpx #3
        bne :+
        lda #':'
:       jsr print_a
        inx
        cpx #4
        bne @octet
        jsr format_port
        ldax #port_str
        jmp print

;-------------------------------------------------------------------------------
; Format CONFIG_PORT as decimal into port_str (zero terminated)
;-------------------------------------------------------------------------------
format_port:
        lda CONFIG_PORT
        sta port_lo
        lda CONFIG_PORT+1
        sta port_hi
        ldx #0                  ; output position
        ldy #0                  ; power-of-ten index
        lda #0
        sta temp2               ; 1 once a digit has been written
@power:
        lda #0
        sta temp1               ; digit
@sub:
        lda port_lo
        sec
        sbc pow10_lo,y
        pha
        lda port_hi
        sbc pow10_hi,y
        bcc @digit_done
        sta port_hi
        pla
        sta port_lo
        inc temp1
        bne @sub
@digit_done:
        pla
        lda temp1
        ora temp2
        beq @skip               ; no leading zeros
        lda temp1
        ora #'0'
        sta port_str,x
        inx
        lda #1
        sta temp2
@skip:
        iny
        cpy #4
        bcc @power
        lda port_lo             ; ones digit always
        ora #'0'
        sta port_str,x
        inx
        lda #0
        sta port_str,x
        rts

pow10_lo:
        .byte <10000, <1000, <100, <10
pow10_hi:
        .byte >10000, >1000, >100, >10

;-------------------------------------------------------------------------------
; Command: /LIST - Show BASIC program listing
;-------------------------------------------------------------------------------
LIST_ROM = $D6A5         ; Applesoft LIST entry point
LOWTR    = $9B           ; Low line number for LIST range
LINNUM   = $50           ; Current line number

cmd_list:
        jsr print_cr
        jsr print_cr

        ; Set up for LIST all (line 0 to 65535)
        lda #0
        sta LOWTR
        sta LOWTR+1
        lda #$FF
        sta LINNUM
        sta LINNUM+1

        ; Call BASIC LIST routine
        jsr LIST_ROM

        jsr print_cr
        rts

;-------------------------------------------------------------------------------
; Command: /CODE <description>
;-------------------------------------------------------------------------------
cmd_code:
        ; Extract description (skip "/CODE ")
        ldx #0
        ldy #6               ; Skip "/CODE "
@copy:
        lda input_buffer,y
        beq @done_copy
        sta code_request,x
        iny
        inx
        cpx #120
        bcc @copy
@done_copy:
        lda #0
        sta code_request,x
        stx code_request_len

        ; Send code request
        jsr send_code_request
        rts

;-------------------------------------------------------------------------------
; Command: /SETIP <ip>
; Format: /SETIP 192.168.1.100
;-------------------------------------------------------------------------------
cmd_setip:
        ; Skip "/SETIP "
        ldy #7

        ; Parse 4 octets
        ldx #0               ; Octet index
@parse_octet:
        lda #0
        sta parse_value      ; Current value

@digit_loop:
        lda input_buffer,y
        beq @done_octet      ; End of input
        cmp #'.'
        beq @store_octet
        cmp #' '
        beq @done_octet

        ; Must be digit 0-9
        cmp #'0'
        bcc @invalid
        cmp #'9'+1
        bcs @invalid

        ; value = value * 10 + digit
        sec
        sbc #'0'
        sta temp2            ; Save digit

        ; Multiply parse_value by 10 (an octet over 255 is a typo)
        lda parse_value
        cmp #26
        bcs @invalid         ; 26 * 10 > 255
        asl                  ; x2
        sta temp1
        asl                  ; x4
        asl                  ; x8
        clc
        adc temp1            ; x8 + x2 = x10
        adc temp2            ; + digit
        bcs @invalid
        sta parse_value

        iny
        bne @digit_loop

@store_octet:
        ; Store octet (in new_ip: CONFIG_IP only changes if all of it parses)
        lda parse_value
        sta new_ip,x
        inx
        cpx #4
        bcs @done_parse
        iny                  ; Skip the dot
        bne @parse_octet

@done_octet:
        ; Store last octet
        lda parse_value
        cpx #4
        bcs @done_parse
        sta new_ip,x
        inx

@done_parse:
        cpx #4               ; exactly four numbers
        bne @invalid
        ldx #3
:       lda new_ip,x
        sta CONFIG_IP,x
        dex
        bpl :-

        ; Show new IP on status line (direct screen writes)
        ldax #msg_ip_set
        jsr print_status     ; "IP SET: " - clears line and starts writing

        lda CONFIG_IP
        jsr status_decimal
        lda #'.'
        jsr status_char
        lda CONFIG_IP+1
        jsr status_decimal
        lda #'.'
        jsr status_char
        lda CONFIG_IP+2
        jsr status_decimal
        lda #'.'
        jsr status_char
        lda CONFIG_IP+3
        jsr status_decimal

        ; Auto-save to disk
        jsr save_config_file
        rts

@invalid:
        ldax #msg_invalid_ip
        jsr print_status
        rts

;-------------------------------------------------------------------------------
; Command: /PORT <port>
; Format: /PORT 6502
;-------------------------------------------------------------------------------
cmd_port:
        ; Skip "/PORT "
        ldy #6

        ; Parse 16-bit port number
        lda #0
        sta port_lo
        sta port_hi

@digit_loop:
        lda input_buffer,y
        beq @done_parse
        cmp #' '
        beq @done_parse

        ; Must be digit 0-9
        cmp #'0'
        bcc @jmp_invalid
        cmp #'9'+1
        bcs @jmp_invalid
        bcc @is_digit        ; Always taken (less than 10 + '0')

@jmp_invalid:
        jmp @invalid

@is_digit:
        ; port = port * 10 + digit
        sec
        sbc #'0'
        sta temp2            ; Save digit

        ; Multiply port by 10 (16-bit)
        ; First, port * 2 (not in temp1/temp1+1: temp1+1 is temp2, the digit)
        lda port_lo
        asl
        sta port_x2
        lda port_hi
        rol
        sta port_x2+1

        ; port * 8 (shift 3 more)
        lda port_lo
        asl
        sta port_lo
        lda port_hi
        rol
        sta port_hi

        lda port_lo
        asl
        sta port_lo
        lda port_hi
        rol
        sta port_hi

        lda port_lo
        asl
        sta port_lo
        lda port_hi
        rol
        sta port_hi

        ; port*8 + port*2 = port*10
        lda port_lo
        clc
        adc port_x2
        sta port_lo
        lda port_hi
        adc port_x2+1
        sta port_hi

        ; + digit
        lda port_lo
        clc
        adc temp2
        sta port_lo
        lda port_hi
        adc #0
        sta port_hi

        iny
        bne @digit_loop

@done_parse:
        lda port_lo             ; no digits, or port 0: not a port
        ora port_hi
        beq @invalid
        ; Store port
        lda port_lo
        sta CONFIG_PORT
        lda port_hi
        sta CONFIG_PORT+1

        ; Show new port on status line (direct screen writes)
        ldax #msg_port_set
        jsr print_status     ; "PORT SET: " - clears line

        ; Show the port number
        jsr format_port
        ldax #port_str
        jsr status_print

@auto_save:
        ; Auto-save to disk
        jsr save_config_file
        rts

@invalid:
        ldax #msg_invalid_port
        jsr print_status
        rts

;-------------------------------------------------------------------------------
; Command: /SAVE - Save config to disk
;-------------------------------------------------------------------------------
cmd_save:
        ldax #msg_saving
        jsr print_status     ; "SAVING CONFIG..." on status line

        jsr save_config_file
        bcs @failed

        ldax #msg_saved
        jsr print_status     ; "SAVED!" on status line
        rts

@failed:
        ldax #msg_save_failed
        jsr print_status     ; "SAVE FAILED" on status line
        rts

;-------------------------------------------------------------------------------
; Command: /RESET - Reset session on server
;-------------------------------------------------------------------------------
cmd_reset:
        ldax #msg_resetting
        jsr print_status     ; "RESETTING SESSION..."

        ; Copy "/RESET" to input_buffer so send_chat can use it
        ldy #0
@copy:  lda reset_cmd_text,y
        beq @done_copy
        sta input_buffer,y
        iny
        bne @copy
@done_copy:
        sty input_len        ; input_len = 6

        ; Send as chat message - server will clear conversation
        jsr send_chat

        rts

reset_cmd_text:
        .byte "/RESET", 0

;-------------------------------------------------------------------------------
; Command: /PROMPT [text] - Set custom system prompt
;-------------------------------------------------------------------------------
cmd_prompt:
        ; Just send the whole input buffer to server as chat
        ; Server parses "/PROMPT text" and handles it
        ; If no argument, server will clear the prompt
        jsr send_chat
        rts

;-------------------------------------------------------------------------------
; Command: /MORE [ON|OFF] - Toggle [MORE] pagination
;-------------------------------------------------------------------------------
cmd_more:
        ; Check for argument at input_buffer+6 ("/MORE " = 6 chars)
        lda input_buffer+6
        beq @toggle              ; No arg - toggle current state
        jsr to_upper
        cmp #'O'
        bne @show
        ; ON or OFF? Check next char
        lda input_buffer+7
        jsr to_upper
        cmp #'N'
        beq @set_on
        cmp #'F'
        beq @set_off
        jmp @show

@toggle:
        lda more_enabled
        eor #1
        sta more_enabled
        jmp @show

@set_on:
        lda #1
        sta more_enabled
        jmp @show

@set_off:
        lda #0
        sta more_enabled

@show:
        lda more_enabled
        beq @show_off
        ldax #msg_more_on
        jsr print_status
        rts
@show_off:
        ldax #msg_more_off
        jsr print_status
        rts

;-------------------------------------------------------------------------------
; Command: /DISPLAY [40|40L|80] - Set display mode
;-------------------------------------------------------------------------------
cmd_display:
        ; Check for argument at input_buffer+9 ("/DISPLAY " = 9 chars)
        lda input_buffer+9
        beq @show_options

        cmp #'4'
        beq @parse_40
        cmp #'8'
        beq @set_80
        jmp @show_options

@parse_40:
        ; Check for 'L' after "40" -> 40L (lowercase), else 40U
        lda input_buffer+11
        jsr to_upper
        cmp #'L'
        beq @set_40l
        ; Default: 40U (handles "40", "40U", etc.)
@set_40u:
        lda #DISPLAY_40U
        jmp @apply
@set_40l:
        lda #DISPLAY_40L
        jmp @apply
@set_80:
        lda #DISPLAY_80
@apply:
        sta CONFIG_DISPLAY
        sta display_mode
        jsr save_config_file
        jsr apply_display_mode
        jsr draw_ui
        ; Forward to proxy so it adjusts formatting
        jsr send_chat
        rts

@show_options:
        ldax #msg_display_usage
        jsr print_status
        rts

;-------------------------------------------------------------------------------
; Command: /MODEL [S|O|H] - Set AI model
;-------------------------------------------------------------------------------
cmd_model:
        ; Check if argument provided
        lda input_buffer+7       ; Character after "/MODEL "
        beq @show_current        ; No arg - show current

        ; Check which model (convert to uppercase for case-insensitive)
        jsr to_upper
        cmp #'S'
        beq @set_sonnet
        cmp #'O'
        beq @set_opus
        cmp #'H'
        beq @set_haiku

        ; Invalid - show options
        jmp @show_options

@set_sonnet:
        lda #MODEL_SONNET
        jmp @set_model

@set_opus:
        lda #MODEL_OPUS
        jmp @set_model

@set_haiku:
        lda #MODEL_HAIKU

@set_model:
        sta CONFIG_MODEL
        jsr save_config_file     ; Auto-save

        ; Show confirmation on status line
        ldax #msg_model_set
        jsr print_status         ; "MODEL: " - clears line
        jsr status_print_model   ; Append model name
        ; Tell the proxy too (it picks the model per session)
        jsr send_chat
        rts

@show_current:
        jsr scroll_output
        ldax #msg_current_model
        jsr print
        jsr print_model_name
        jsr print_cr
        ; Fall through to show options

@show_options:
        jsr scroll_output
        ldax #msg_model_options
        jsr print_multiline
        rts

;-------------------------------------------------------------------------------
; Print current model name (using COUT - for output area)
;-------------------------------------------------------------------------------
print_model_name:
        lda CONFIG_MODEL
        cmp #MODEL_OPUS
        beq @opus
        cmp #MODEL_HAIKU
        beq @haiku
        ; Default: Sonnet
        ldax #model_sonnet
        jmp @print
@opus:
        ldax #model_opus
        jmp @print
@haiku:
        ldax #model_haiku
@print:
        jsr print
        rts

;-------------------------------------------------------------------------------
; Print model name to status line (using status_print)
;-------------------------------------------------------------------------------
status_print_model:
        lda CONFIG_MODEL
        cmp #MODEL_OPUS
        beq @opus
        cmp #MODEL_HAIKU
        beq @haiku
        ; Default: Sonnet
        ldax #model_sonnet
        jmp @print
@opus:
        ldax #model_opus
        jmp @print
@haiku:
        ldax #model_haiku
@print:
        jsr status_print
        rts

;-------------------------------------------------------------------------------
; Send chat message to server (uses persistent connection)
;-------------------------------------------------------------------------------
send_chat:
        lda #2                   ; one retry if the connection turns out dead
        sta send_attempts
@attempt:
        ; Let IP65 see a FIN/RST that arrived while we sat at the prompt,
        ; so ensure_connected knows whether the connection is really up.
        ; (On a real LAN broadcasts queue up in the W5100 meanwhile - a FIN
        ; can be a dozen frames back - and an idle call costs next to nothing)
        jsr drain_network
        jsr ensure_connected
        bcs @failed

        ; Clear output area for new response
        jsr clear_output_area

        jsr clear_input_line

        ; Initialize receive state BEFORE sending (callbacks may trigger)
        lda #0
        sta recv_state
        sta response_done
        sta got_code
        sta code_offset
        sta code_offset+1
        sta pending_ack_count
        sta in_callback
        sta rx_any
        lda #<BASIC_START
        sta dst_ptr
        lda #>BASIC_START
        sta dst_ptr+1

        ; Build and send CHAT packet (no INIT needed - sent on connect)
        jsr send_chat_packet
        bcs @retry               ; send failed - proxy went away
        ; Process any incoming data
        jsr ip65_process
        jsr ip65_process
        jsr ip65_process
        lda is_connected
        beq @retry

        ; Wait for response (state already initialized)
        jsr receive_response_no_init
        lda is_connected
        bne @got_reply
        lda rx_any               ; dropped before any reply: send it again
        beq @retry
@got_reply:
        lda preview_on
        beq @text
        jsr preview_off
@text:
        ; A program arrived? Offer to run it right now.
        jsr offer_program

        ; DON'T close connection - keep it open for next message
        rts

@retry:
        lda #0
        sta is_connected
        dec send_attempts
        bne @attempt
@failed:
        ldax #msg_conn_fail
        jsr print_status
        rts

;-------------------------------------------------------------------------------
; Connect to proxy at startup
; Returns: C=0 if connected, C=1 if failed
;-------------------------------------------------------------------------------
connect_to_proxy:
        ; Setup TCP callback
        ldax #recv_callback
        stax tcp_callback

        ; Connect using configured IP
        lda CONFIG_IP
        sta tcp_connect_ip
        lda CONFIG_IP+1
        sta tcp_connect_ip+1
        lda CONFIG_IP+2
        sta tcp_connect_ip+2
        lda CONFIG_IP+3
        sta tcp_connect_ip+3

        ; Connect using configured port
        lda CONFIG_PORT
        ldx CONFIG_PORT+1
        jsr tcp_connect
        bcs @connect_failed

        ; Connected! Send INIT packet once
        lda #1
        sta is_connected

        jsr send_init_packet
        jsr ip65_process
        jsr ip65_process
        jsr ip65_process

        clc                  ; Success
        rts

@connect_failed:
        lda #0
        sta is_connected
        sec                  ; Failed
        rts

;-------------------------------------------------------------------------------
; Ensure connection is established (silent - reconnect if needed)
; Returns: C=0 if connected, C=1 if failed
;-------------------------------------------------------------------------------
ensure_connected:
        ; The W5100 was reset (agent_reentry noticed): start over
        lda net_needs_init
        beq :+
        lda #0
        sta net_needs_init
        sta is_connected
        jmp @restart
:
        ; Check if already connected (and IP65 agrees - the proxy may have
        ; gone away while a program was running)
        lda is_connected
        beq @reconnect
        lda tcp_state
        cmp #TCP_ESTABLISHED
        beq @already_connected
@reconnect:
        lda #0
        sta is_connected

        ; Not connected - try to reconnect silently
        jsr connect_to_proxy
        bcc @done
        ; The proxy may have moved (the Mac got a new address) or only just
        ; been started: ask the network where it is
        ldax #msg_finding_status
        jsr print_status
        jsr find_proxy
        bcs @restart
        jsr save_if_moved
        jsr connect_to_proxy
        bcc @done
@restart:
        ; Still nothing: the Uthernet may have been reset (Ctrl-Reset) or the
        ; DHCP lease lapsed during a long program. Start the network over.
        ldax #msg_reinit_net
        jsr print_status
        lda #eth_init_default
        jsr ip65_init
        bcs @done
        jsr dhcp_init
        bcs @done
        jsr find_proxy          ; (keeps the old address if nobody answers)
        jsr connect_to_proxy
@done:
        rts

@already_connected:
        clc                  ; Success
        rts

;-------------------------------------------------------------------------------
; Find the proxy on the local network: broadcast DISCOVERY_ASK to UDP
; DISCOVERY_PORT; the proxy answers DISCOVERY_ANSWER + its TCP port
; (proxy/unified_proxy.py). On an answer, CONFIG_IP = whoever sent it,
; CONFIG_PORT = the port in it, C=0. No answer in ~3 s: C=1, config untouched.
;-------------------------------------------------------------------------------
DISCOVERY_PORT  = 6502
DISCOVERY_ASK_LEN = 8           ; "A2AGENT?" / "A2AGENT!"

find_proxy:
        lda #0
        sta proxy_found
        sta proxy_moved
        ldax #discovery_callback
        stax udp_callback
        ldax #DISCOVERY_PORT
        jsr udp_add_listener    ; (already listening is fine)
        lda #3
        sta discovery_tries
@ask:
        ldx #3
        lda #$FF                ; 255.255.255.255
:       sta udp_send_dest,x
        dex
        bpl :-
        ldax #DISCOVERY_PORT
        stax udp_send_dest_port
        stax udp_send_src_port
        ldax #DISCOVERY_ASK_LEN
        stax udp_send_len
        ldax #discovery_ask
        jsr udp_send
        lda #24                 ; ~1 s for an answer
        sta discovery_wait
@listen:
        jsr ip65_process
        lda proxy_found
        bne @found
        lda #$80                ; ~43 ms
        jsr WAIT
        dec discovery_wait
        bne @listen
        dec discovery_tries
        bne @ask
        ldax #DISCOVERY_PORT
        jsr udp_remove_listener
        sec
        rts
@found:
        ldax #DISCOVERY_PORT
        jsr udp_remove_listener
        clc
        rts

; IP65 calls this for every datagram to DISCOVERY_PORT
discovery_callback:
        ldx #DISCOVERY_ASK_LEN-1
:       lda udp_inp+udp_data,x
        cmp discovery_answer,x
        bne @not_ours
        dex
        bpl :-
        ldx #3
:       lda ip_inp+ip_src,x     ; the proxy is whoever answered
        cmp CONFIG_IP,x
        beq :+
        inc proxy_moved
        sta CONFIG_IP,x
:       dex
        bpl :--
        lda udp_inp+udp_data+DISCOVERY_ASK_LEN
        cmp CONFIG_PORT
        beq :+
        inc proxy_moved
        sta CONFIG_PORT
:       lda udp_inp+udp_data+DISCOVERY_ASK_LEN+1
        cmp CONFIG_PORT+1
        beq :+
        inc proxy_moved
        sta CONFIG_PORT+1
:       lda #1
        sta proxy_found
@not_ours:
        rts

; Save the config only when find_proxy changed it (floppy writes are slow)
save_if_moved:
        lda proxy_moved
        beq :+
        jsr save_config_file
:       rts

;-------------------------------------------------------------------------------
; Wait up to A tenths of a second, or until a key is pressed (the key is
; consumed). Returns C=1 if a key was pressed.
;-------------------------------------------------------------------------------
wait_key_or_timeout:
        sta wait_tenths
@tick:
        ldx #2
@slice:
        lda KBD
        bmi @key
        txa
        pha
        lda #$80                ; ~43 ms
        jsr WAIT
        pla
        tax
        dex
        bne @slice
        dec wait_tenths
        bne @tick
        clc
        rts
@key:
        bit KBDSTRB
        sec
        rts

;-------------------------------------------------------------------------------
; Disconnect from server
;-------------------------------------------------------------------------------
disconnect:
        lda is_connected
        beq @not_connected
        jsr tcp_close
        lda #0
        sta is_connected
@not_connected:
        rts

;-------------------------------------------------------------------------------
; Send code request to server (uses persistent connection)
;-------------------------------------------------------------------------------
send_code_request:
        ; Ensure we have a connection
        jsr ensure_connected
        bcs @failed

        ; Send as CHAT with code request prefix
        ; The proxy will detect /CODE in the message
        jsr send_code_chat_packet

        ; Receive (expecting CODE packets)
        lda #1
        sta expecting_code
        jsr receive_response

        ; DON'T close - keep connection open
        jmp @check_code

@failed:
        ldax #msg_conn_fail
        jsr print_status
        rts

@check_code:

        ; If we got code, offer to inject
        lda got_code
        beq @no_code

        jsr prompt_inject
        bcc @no_code

        jsr inject_program

        ldax #msg_injected
        jsr print_status

@no_code:
        rts

;-------------------------------------------------------------------------------
; Build and send INIT packet
;-------------------------------------------------------------------------------
send_init_packet:
        ; Header: A2 + PKT_INIT + len(3) + seq
        lda #A2P_MAGIC_0
        sta send_buffer
        lda #A2P_MAGIC_1
        sta send_buffer+1
        lda #PKT_INIT
        sta send_buffer+2
        lda #4               ; Data length = 4 (caps + model + display + version)
        sta send_buffer+3
        lda #0
        sta send_buffer+4
        lda tx_seq
        sta send_buffer+5
        inc tx_seq

        ; Data byte 0: capabilities
        lda has_aux_ram
        beq @no_aux
        lda #CAP_AUX_RAM
@no_aux:
        ora #CAP_DEPLOY
        ora col_mode
        sta send_buffer+6

        ; Data byte 1: model selection
        lda CONFIG_MODEL
        sta send_buffer+7

        ; Data byte 2: display mode
        lda display_mode
        sta send_buffer+8

        ; Data byte 3: protocol version
        lda #A2P_VERSION
        sta send_buffer+9

        ; Checksum (XOR of type through data)
        lda send_buffer+2    ; Type
        eor send_buffer+3    ; Len lo
        eor send_buffer+4    ; Len hi
        eor send_buffer+5    ; Seq
        eor send_buffer+6    ; Capabilities
        eor send_buffer+7    ; Model
        eor send_buffer+8    ; Display mode
        eor send_buffer+9    ; Version
        sta send_buffer+10

        ; Send (11 bytes)
        lda #11
        sta tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1
        ldax #send_buffer
        jsr tcp_send
        rts

;-------------------------------------------------------------------------------
; Build and send CHAT packet with user input
;-------------------------------------------------------------------------------
send_chat_packet:
        ; Build packet
        lda #A2P_MAGIC_0
        sta send_buffer
        lda #A2P_MAGIC_1
        sta send_buffer+1
        lda #PKT_CHAT
        sta send_buffer+2

        ; Length = input_len
        lda input_len
        sta send_buffer+3
        lda #0
        sta send_buffer+4

        ; Seq
        lda tx_seq
        sta send_buffer+5
        inc tx_seq

        ; Copy data: as typed on a mixed-case screen, uppercase on a 40U one
        ; and for /commands (the proxy matches those in uppercase)
        lda display_mode
        cmp #DISPLAY_40U
        beq :+
        lda input_buffer
        cmp #'/'
:       php                     ; Z set = uppercase it
        ldy #0
@copy:
        cpy input_len
        beq @done_copy
        lda input_buffer,y
        plp
        php
        bne :+
        jsr to_upper
:       sta send_buffer+6,y
        iny
        bne @copy

@done_copy:
        plp
        ; Calculate checksum
        lda send_buffer+2    ; Start with type
        eor send_buffer+3
        eor send_buffer+4
        eor send_buffer+5
        sta temp1

        ldy #0
@checksum:
        cpy input_len
        beq @done_checksum
        lda send_buffer+6,y
        eor temp1
        sta temp1
        iny
        bne @checksum

@done_checksum:
        ; Store checksum after data
        tya
        clc
        adc #6               ; Header size
        tax
        lda temp1
        sta send_buffer,x

        ; Total length = 6 (header) + input_len + 1 (checksum)
        inx
        stx tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1

        ldax #send_buffer
        jsr tcp_send
        rts

;-------------------------------------------------------------------------------
; Send code request as CHAT packet
;-------------------------------------------------------------------------------
send_code_chat_packet:
        ; Prepend "/CODE " to the request
        ldx #0

        ; Copy "/CODE "
        ldy #0
@prefix:
        lda code_prefix,y
        beq @copy_request
        sta send_buffer+6,x
        inx
        iny
        bne @prefix

@copy_request:
        ldy #0
@copy:
        lda code_request,y
        beq @done_copy
        jsr to_upper
        sta send_buffer+6,x
        inx
        iny
        cpy code_request_len
        bcc @copy

@done_copy:
        stx chat_data_len    ; Save data length

        ; Build header
        lda #A2P_MAGIC_0
        sta send_buffer
        lda #A2P_MAGIC_1
        sta send_buffer+1
        lda #PKT_CHAT
        sta send_buffer+2
        lda chat_data_len
        sta send_buffer+3
        lda #0
        sta send_buffer+4
        lda tx_seq
        sta send_buffer+5
        inc tx_seq

        ; Checksum
        lda send_buffer+2
        eor send_buffer+3
        eor send_buffer+4
        eor send_buffer+5
        sta temp1

        ldy #0
@checksum:
        cpy chat_data_len
        beq @done_checksum
        lda send_buffer+6,y
        eor temp1
        sta temp1
        iny
        bne @checksum

@done_checksum:
        tya
        clc
        adc #6
        tax
        lda temp1
        sta send_buffer,x
        inx

        stx tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1

        ldax #send_buffer
        jsr tcp_send
        rts

;-------------------------------------------------------------------------------
; Receive and process response
;-------------------------------------------------------------------------------
receive_response:
        ; Init state
        lda #0
        sta recv_state
        sta response_done
        sta got_code
        sta code_offset
        sta code_offset+1
        sta pending_ack_count
        sta in_callback

        ; Set destination for code injection
        lda #<BASIC_START
        sta dst_ptr
        lda #>BASIC_START
        sta dst_ptr+1

receive_response_no_init:
        ; Reset timeout (caller may have initialized other state)
        lda #0
        sta timeout_lo
        sta timeout_hi
        sta stop_requested
        sta silent_frames
        sta silent_frames+1
        sta resync_tries
        jsr set_silence_limit

        ldax #msg_receiving
        jsr print_status

@wait_loop:
        ; Call ip65_process multiple times to drain buffered TCP segments
        ; (ip65 may deliver one segment per call even if multiple are queued)
        jsr ip65_process
        jsr ip65_process
        jsr ip65_process

        ; Send any pending ACKs (after callback returns)
        jsr send_pending_acks

        ; Check for completion
        lda response_done
        bne @done

        ; Proxy hung up? Don't wait forever.
        lda is_connected
        bne @still_connected
        ldax #msg_conn_lost
        jsr print_status
        rts
@still_connected:

        ; Keys while waiting: with a preview showing, any key flips back to
        ; the log. Otherwise ESC asks Claude to stop, and ESC again stops
        ; waiting (for when the network has quietly gone away). Other keys
        ; stay in the keyboard latch for the next input.
        lda KBD
        bpl @no_key
        ldx preview_on
        beq @not_preview
        bit KBDSTRB
        jsr preview_off
        jmp @no_key
@not_preview:
        cmp #$9B                ; ESC
        bne @no_key
        bit KBDSTRB
        lda stop_requested
        bne @give_up
        inc stop_requested
        jsr send_stop
        ldax #msg_stopping
        jsr print_status
        jmp @no_key
@give_up:
        lda #0
        sta is_connected        ; reconnect next time
        ldax #msg_gave_up
        jsr print_status
        rts
@no_key:

        ; Check timeout - disabled for agentic mode which can take minutes
        ; Agentic loop involves multiple Claude API calls + emulator testing
        ; inc timeout_lo
        ; bne @wait_loop
        ; inc timeout_hi
        ; lda timeout_hi
        ; cmp #$FF
        ; bcc @wait_loop
        ; Watchdog: while it works the proxy says something at least every
        ; 2 s. 20 s of silence means the connection has stalled (on a real
        ; LAN one did, with 12K stuck in the Mac's queue): start the network
        ; over, reconnect, and ask for what was lost
        jsr count_silent_frame
        bcc :+
        jsr resync_connection   ; C set: gave up (said so)
        bcc :+
        rts
:       jmp @wait_loop       ; No timeout - wait forever

        ; Timeout
        ldax #msg_timeout
        jsr print_status

@done:
        rts

;-------------------------------------------------------------------------------
; Stall watchdog (receive_response_no_init). count_silent_frame counts
; vertical blanks since the last packet: C set once SILENCE_FRAMES have gone by.
;-------------------------------------------------------------------------------
RESYNC_MAX      = 3

; silence_limit = CONFIG_WATCHDOG seconds * 60 frames (0 = never)
set_silence_limit:
        lda CONFIG_WATCHDOG
        sta silence_limit
        lda #0
        sta silence_limit+1
        ldx #2                  ; * 4
:       asl silence_limit
        rol silence_limit+1
        dex
        bne :-
        lda silence_limit       ; keep * 4, then * 16 more = * 64, minus * 4
        sta temp_w
        lda silence_limit+1
        sta temp_w+1
        ldx #4
:       asl silence_limit
        rol silence_limit+1
        dex
        bne :-
        sec
        lda silence_limit
        sbc temp_w
        sta silence_limit
        lda silence_limit+1
        sbc temp_w+1
        sta silence_limit+1
        rts

count_silent_frame:
        lda RDVBLBAR            ; bit 7 low during vertical blank
        and #$80
        tax
        eor vbl_prev
        stx vbl_prev
        beq @check              ; no change
        txa
        bne @check              ; blank just ended: not a new frame
        inc silent_frames
        bne @check
        inc silent_frames+1
@check:
        lda silence_limit
        ora silence_limit+1
        beq @quiet              ; watchdog off
        lda silent_frames+1
        cmp silence_limit+1
        bcc @quiet
        bne @stalled
        lda silent_frames
        cmp silence_limit
        bcc @quiet
@stalled:
        sec
        rts
@quiet:
        clc
        rts

; Start the network over, reconnect and send /RESYNC (the proxy re-sends the
; reply's end and the program). C set when it has given up.
resync_connection:
        lda #0
        sta silent_frames
        sta silent_frames+1
        inc resync_tries
        lda resync_tries
        cmp #RESYNC_MAX+1
        bcc @try
        lda #0
        sta is_connected
        ldax #msg_conn_lost
        jsr print_status
        sec
        rts
@try:
        ldax #msg_stalled
        jsr print_status
        jsr build_stall_report  ; what the stall looks like from here, first
        lda #1                  ; a W5100 left in a bad state is what this is for
        sta net_needs_init
        jsr ensure_connected
        bcs @later              ; no luck: try again after another 20 s
        lda #0                  ; the new connection starts on a packet boundary
        sta recv_state
        sta in_callback
        ldx #0                  ; "/RESYNC" + the report
:       lda diag_buf,x
        sta input_buffer,x
        inx
        cpx diag_len
        bcc :-
        stx input_len
        jsr send_chat_packet
@later:
        clc
        rts

resync_cmd:
        .byte "/RESYNC"
RESYNC_CMD_LEN = * - resync_cmd

; The stall report, in hex (the proxy decodes and logs it):
;   n segments since the last good packet   t/b all segments / bad checksums
;   h W5100 RX ring skips (bad frame header) a A2P packets with a bad checksum
;   s socket 0 status   q bytes waiting in its RX ring
;   e/l the sequence number we expect / last got (low 16 bits)
W5100_ADDR      = W5100_MODE + 1        ; address hi, lo; then data
W5100_DATA      = W5100_MODE + 3

build_stall_report:
        lda #0
        sta diag_len
        ldx #0
:       lda resync_cmd,x
        jsr diag_put
        inx
        cpx #RESYNC_CMD_LEN
        bcc :-
        lda #'N'
        jsr diag_field
        sec
        lda tcp_rx_count
        sbc rx_at_packet
        tax
        lda tcp_rx_count+1
        sbc rx_at_packet+1
        jsr diag_hex
        txa
        jsr diag_hex
        lda #'T'
        ldx #<tcp_rx_count
        ldy #>tcp_rx_count
        jsr diag_word
        lda #'B'
        ldx #<tcp_bad_cksum
        ldy #>tcp_bad_cksum
        jsr diag_word
        lda #'H'
        ldx #<w5100_rx_resyncs
        ldy #>w5100_rx_resyncs
        jsr diag_word
        lda #'A'
        jsr diag_field
        lda a2p_bad
        jsr diag_hex
        lda #'S'                ; W5100 socket 0 status ($0403)
        jsr diag_field
        lda #$04
        sta W5100_ADDR
        lda #$03
        sta W5100_ADDR+1
        lda W5100_DATA
        jsr diag_hex
        lda #'Q'                ; socket 0 RX received size ($0426, hi then lo)
        jsr diag_field
        lda #$04
        sta W5100_ADDR
        lda #$26
        sta W5100_ADDR+1
        lda W5100_DATA
        jsr diag_hex
        lda W5100_DATA          ; (auto-increment)
        jsr diag_hex
        lda #'E'
        ldx #<tcp_connect_ack_number
        ldy #>tcp_connect_ack_number
        jsr diag_word
        lda #'L'
        ldx #<tcp_connect_last_received_seq_number
        ldy #>tcp_connect_last_received_seq_number
        jmp diag_word

; " X=hhhh" for the little-endian word at Y:X (A = the letter)
diag_word:
        stx src_ptr
        sty src_ptr+1
        jsr diag_field
        ldy #1
        lda (src_ptr),y
        jsr diag_hex
        ldy #0
        lda (src_ptr),y
        jmp diag_hex

diag_field:                     ; " X="
        pha
        lda #' '
        jsr diag_put
        pla
        jsr diag_put
        lda #'='
        jmp diag_put

diag_hex:                       ; two hex digits of A
        pha
        lsr
        lsr
        lsr
        lsr
        jsr @digit
        pla
        and #$0F
@digit:
        cmp #10
        bcc :+
        adc #6                  ; (C set: +7 -> 'A')
:       adc #'0'
diag_put:                       ; append A (keeps X)
        ldy diag_len
        sta diag_buf,y
        inc diag_len
        rts

;-------------------------------------------------------------------------------
; Empty the input line while Claude works (the proxy echoes the request,
; word-wrapped, at the top of the log)
;-------------------------------------------------------------------------------
clear_input_line:
        lda input_len           ; input_buffer stays for a resend
        pha
        lda #0
        sta input_len
        jsr redraw_input
        pla
        sta input_len
        rts

;-------------------------------------------------------------------------------
; Handle everything queued in the W5100 (up to 24 frames)
;-------------------------------------------------------------------------------
drain_network:
        lda #24
        sta drain_count
:       jsr ip65_process
        dec drain_count
        bne :-
        rts

;-------------------------------------------------------------------------------
; Ask the proxy to stop the request it's working on (ESC while waiting)
;-------------------------------------------------------------------------------
send_stop:
        ldx #STOP_CMD_LEN-1
:       lda stop_cmd,x
        sta input_buffer,x
        dex
        bpl :-
        lda #STOP_CMD_LEN
        sta input_len
        jmp send_chat_packet

stop_cmd:
        .byte "/STOP"
STOP_CMD_LEN = * - stop_cmd

;-------------------------------------------------------------------------------
; TCP receive callback - A2P protocol parser
;-------------------------------------------------------------------------------
recv_callback:
        ; Prevent re-entry (tcp_send can trigger this callback)
        lda in_callback
        bne @skip_reentry
        inc in_callback

        lda tcp_inbound_data_length
        ora tcp_inbound_data_length+1
        bne @have_data

        dec in_callback
@skip_reentry:
        rts

@have_data:
        ; Length $FFFF = remote end closed the connection
        lda tcp_inbound_data_length
        and tcp_inbound_data_length+1
        cmp #$FF
        bne @real_data
        lda #0
        sta is_connected
        dec in_callback
        rts
@real_data:
        ; Count down our own copy: IP65 adds tcp_inbound_data_length to the
        ; ACK number after we return. (Counting down IP65's acked only the
        ; low byte of segments of 256+ bytes - fine in Bobbin, whose virtual
        ; TCP sends at most 160, but not with a real host's 512-536.)
        lda tcp_inbound_data_length
        sta rx_remaining
        lda tcp_inbound_data_length+1
        sta rx_remaining+1

        ; Reset packet count for this callback
        lda #0
        sta recv_pkt_count

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
        ; Check if more data
        lda rx_remaining+1
        bne @more
        cpy rx_remaining
        bcc @more
        jmp @done

@more:
        ; (debug removed)            ; DEBUG: count bytes processed
        lda (src_ptr),y
        iny
        bne @no_wrap
        inc src_ptr+1
        dec rx_remaining+1
@no_wrap:

        ; State machine - use jump table for far branches
        ldx recv_state

        cpx #STATE_MAGIC_0
        beq @state_magic_0
        cpx #STATE_MAGIC_1
        beq @state_magic_1
        cpx #STATE_TYPE
        beq @state_type
        cpx #STATE_LEN_LO
        beq @state_len_lo
        cpx #STATE_LEN_HI
        beq @state_len_hi
        cpx #STATE_SEQ
        beq @state_seq

        ; Far states - use trampolines
        cpx #STATE_DATA
        beq @jmp_data
        cpx #STATE_CHECKSUM
        beq @jmp_checksum
        cpx #STATE_DONE
        beq @jmp_done
        jmp @process_loop

@jmp_data:
        jmp @state_data
@jmp_checksum:
        jmp @state_checksum
@jmp_done:
        jmp @done

@state_magic_0:
        cmp #A2P_MAGIC_0
        bne @process_loop    ; Keep scanning
        lda #STATE_MAGIC_1
        sta recv_state
        jmp @process_loop

@state_magic_1:
        cmp #A2P_MAGIC_1
        bne @reset_state
        lda #STATE_TYPE
        sta recv_state
        lda #0
        sta pkt_checksum     ; Reset checksum
        jmp @process_loop

@reset_state:
        lda #STATE_MAGIC_0
        sta recv_state
        jmp @process_loop

@state_type:
        sta pkt_type
        eor pkt_checksum
        sta pkt_checksum
        lda #STATE_LEN_LO
        sta recv_state
        jmp @process_loop

@state_len_lo:
        sta pkt_len
        eor pkt_checksum
        sta pkt_checksum
        lda #STATE_LEN_HI
        sta recv_state
        jmp @process_loop

@state_len_hi:
        sta pkt_len+1
        eor pkt_checksum
        sta pkt_checksum
        lda #STATE_SEQ
        sta recv_state
        jmp @process_loop

@state_seq:
        sta pkt_seq
        eor pkt_checksum
        sta pkt_checksum

        ; Garbage length would overrun pkt_buffer - resync instead
        lda pkt_len+1
        bne @bad_length
        lda pkt_len
        cmp #MAX_PKT_DATA+1
        bcs @bad_length

        ; If len=0, go to checksum
        lda pkt_len
        ora pkt_len+1
        beq @to_checksum

        lda #0
        sta pkt_data_pos
        lda #STATE_DATA
        sta recv_state
        jmp @process_loop

@to_checksum:
        lda #STATE_CHECKSUM
        sta recv_state
        jmp @process_loop

@bad_length:
        lda #STATE_MAGIC_0
        sta recv_state
        jmp @process_loop

@state_data:
        ; Store in packet buffer
        pha                  ; Save byte
        eor pkt_checksum
        sta pkt_checksum
        pla

        ldx pkt_data_pos
        sta pkt_buffer,x
        inc pkt_data_pos

        ; Check if got all data
        lda pkt_data_pos
        cmp pkt_len
        bcs @check_hi_len
        jmp @process_loop    ; Need more data

@check_hi_len:
        ; Check high byte (for large packets)
        lda pkt_len+1
        beq @data_complete
        jmp @process_loop    ; More data needed (16-bit length)

@data_complete:
        lda #STATE_CHECKSUM
        sta recv_state
        jmp @process_loop

@state_checksum:
        ; (debug removed)            ; DEBUG: count checksum checks
        ; Verify checksum
        cmp pkt_checksum
        bne @bad_checksum
        ; (debug removed)            ; DEBUG: count checksum passes

        ; Packet valid - process it
        ; Save callback state (tcp_send may clobber them)
        tya
        pha
        lda src_ptr
        pha
        lda src_ptr+1
        pha
        lda tcp_inbound_data_length
        pha
        lda tcp_inbound_data_length+1
        pha

        ; Process the packet
        jsr process_packet

        ; Restore callback state
        pla
        sta tcp_inbound_data_length+1
        pla
        sta tcp_inbound_data_length
        pla
        sta src_ptr+1
        pla
        sta src_ptr
        pla
        tay

        ; Continue processing remaining data in this callback
        lda #STATE_MAGIC_0
        sta recv_state
        jmp @process_loop    ; Process next packet in same callback

@bad_checksum:
        ; Drop it. (No NACK: tcp_send from inside the TCP callback re-enters
        ; IP65.) TCP checks its data, so this shouldn't happen; if it does in
        ; the middle of a program, that program must not run (handle_run)
        lda #1
        sta packet_lost
        inc a2p_bad
        lda #STATE_MAGIC_0
        sta recv_state
        jmp @process_loop

@done:
        dec in_callback      ; Exit re-entry guard
        rts

;-------------------------------------------------------------------------------
; Process a complete packet
;-------------------------------------------------------------------------------
process_packet:
        lda #1
        sta rx_any               ; the proxy is talking to us
        lda #0
        sta silent_frames        ; (the stall watchdog)
        sta silent_frames+1
        lda tcp_rx_count         ; (its report: segments since this one)
        sta rx_at_packet
        lda tcp_rx_count+1
        sta rx_at_packet+1

        ; Queue ACK for later (don't send from callback)
        ldx pending_ack_count
        cpx #8               ; Max 8 pending ACKs
        bcs @skip_queue
        lda pkt_seq
        sta pending_acks,x
        inc pending_ack_count
@skip_queue:

        ; Dispatch by type
        lda pkt_type

        cmp #PKT_RESP
        beq @handle_resp
        cmp #PKT_CODE
        beq @handle_code
        cmp #PKT_STATUS
        beq @handle_status
        cmp #PKT_ERR
        beq @handle_error
        cmp #PKT_ACK
        beq @handle_ack
        cmp #PKT_LOAD
        beq @handle_load
        cmp #PKT_DEPLOY
        beq @handle_deploy
        cmp #PKT_RUN
        beq @handle_run
        cmp #PKT_SHOW
        beq @handle_show
        rts

@handle_load:
        jmp handle_load
@handle_deploy:
        jmp handle_deploy
@handle_run:
        jmp handle_run
@handle_show:
        jmp handle_show

@handle_resp:
        jmp handle_response

@handle_code:
        jmp handle_code_chunk

@handle_status:
        jmp handle_status_msg

@handle_error:
        jmp handle_error_msg

@handle_ack:
        ; ACK received - clear pending
        rts

;-------------------------------------------------------------------------------
; Handle RESP packet - display response text
;-------------------------------------------------------------------------------
handle_response:
        ; First byte is flags
        lda pkt_buffer
        sta temp1            ; Save flags

        ; Display text (starting from byte 1)
        ldy #1
@print_loop:
        cpy pkt_data_pos
        bcs @done

        lda pkt_buffer,y

        ; Convert to Apple II display format
        ora #$80             ; Set high bit
        jsr output_char

        iny
        bne @print_loop

@done:
        ; Check if final
        lda temp1
        and #RESP_FLAG_FINAL
        beq @not_final

        ; Final response - done
        jsr print_cr
        lda #1
        sta response_done

@not_final:
        rts

;-------------------------------------------------------------------------------
; Handle CODE packet - store BASIC code
;-------------------------------------------------------------------------------
handle_code_chunk:

        ; Format: offset(2) + total(2) + data

        ; Get offset
        lda pkt_buffer
        sta code_offset
        lda pkt_buffer+1
        sta code_offset+1

        ; Get total (for progress)
        lda pkt_buffer+2
        sta code_total
        lda pkt_buffer+3
        sta code_total+1

        ; If offset=0, initialize dst_ptr to BASIC_START
        ; This allows code injection in agentic mode without /CODE command
        lda code_offset
        ora code_offset+1
        bne @not_first
        ; First chunk - initialize destination pointer
        lda #<BASIC_START
        sta dst_ptr
        lda #>BASIC_START
        sta dst_ptr+1
@not_first:

        ; Check for end marker (offset == total && no more data)
        lda pkt_data_pos
        cmp #4
        beq @check_end

        ; Copy data to BASIC memory
        ldy #4               ; Data starts at offset 4
@copy:
        cpy pkt_data_pos
        bcs @copy_done

        lda pkt_buffer,y
        ldx #0
        sta (dst_ptr,x)

        ; Increment destination
        inc dst_ptr
        bne @no_carry
        inc dst_ptr+1
@no_carry:

        iny
        bne @copy

@copy_done:
        ; Show progress dot
        lda #'.'
        jsr print_a
        rts

@check_end:
        ; End of code transfer - inject program into BASIC
        jsr inject_program

        ; Show completion message with instructions
        jsr print_cr
        jsr print_cr
        ldax #msg_code_ready
        jsr print
        jsr print_cr

        lda #1
        sta got_code
        sta response_done
        rts

;-------------------------------------------------------------------------------
; Handle STATUS packet - writes directly to screen line 22 (no scroll)
;-------------------------------------------------------------------------------
handle_status_msg:
        ; Check if "DONE" - signals end of agentic response
        lda pkt_data_pos
        cmp #4
        bne @not_done
        lda pkt_buffer
        cmp #'D'
        bne @not_done
        lda pkt_buffer+1
        cmp #'O'
        bne @not_done
        lda pkt_buffer+2
        cmp #'N'
        bne @not_done
        lda pkt_buffer+3
        cmp #'E'
        bne @not_done
        ; It's "DONE" - mark response complete
        lda #1
        sta response_done
        ldax #msg_ready          ; show READY rather than the raw marker
        jmp print_status
@not_done:

        ; Display status on line 22 using COUT (works in --simple terminal mode)
        ; Save cursor position
        lda CV
        sta status_save_cv
        lda CH
        sta status_save_ch

        ; Position at line 22, column 0
        lda #STATUS_LINE
        sta CV
        jsr VTAB
        lda #0
        sta CH

        ; Clear line
        jsr clear_eol

        ; Print status message via COUT
        ldy #0
@print:
        cpy pkt_data_pos
        bcs @restore
        cpy screen_width_m1  ; Limit to screen width
        bcs @restore
        lda pkt_buffer,y
        ora #$80             ; Set high bit for Apple II display
        jsr COUT
        iny
        bne @print

@restore:
        ; Restore cursor position
        lda status_save_cv
        sta CV
        jsr VTAB
        lda status_save_ch
        sta CH
        rts

;-------------------------------------------------------------------------------
; Handle ERR packet - writes to status line 22
;-------------------------------------------------------------------------------
handle_error_msg:
        ; Save cursor
        lda CV
        sta status_save_cv
        lda CH
        sta status_save_ch
        ; Position at line 22
        lda #STATUS_LINE
        sta CV
        jsr VTAB
        lda #0
        sta CH
        jsr clear_eol

        ; Print "ERROR: " prefix via COUT
        ldx #0
@prefix:
        lda msg_error_prefix,x
        beq @msg
        ora #$80
        jsr COUT
        inx
        cpx #7
        bcc @prefix

@msg:
        ; Print error message via COUT
        ldy #0
@print:
        cpy pkt_data_pos
        bcs @done
        txa
        cmp screen_width_m1
        bcs @done
        lda pkt_buffer,y
        ora #$80
        jsr COUT
        inx
        iny
        bne @print
@done:
        ; Restore cursor
        lda status_save_cv
        sta CV
        jsr VTAB
        lda status_save_ch
        sta CH
        rts

;-------------------------------------------------------------------------------
; Send pending ACKs (called after recv_callback returns)
; CRITICAL: Build all ACKs into buffer first, then send once to avoid
; feedback loop where tcp_send triggers recv_callback which queues more ACKs
;-------------------------------------------------------------------------------
send_pending_acks:
        ; ACK sending disabled - tcp_send during receive loop causes
        ; ip65 buffer issues and packet loss. Heartbeat thread on proxy
        ; side keeps the TCP connection alive instead.
        rts

        lda pending_ack_count
        beq @done            ; No ACKs pending

        ; Save count and clear immediately to prevent re-entry issues
        sta ack_batch_count
        lda #0
        sta pending_ack_count

        ; Build all ACK packets into ack_batch_buffer
        ; Each ACK is 8 bytes: A2 05 01 00 00 seq checksum
        lda #0
        sta ack_batch_pos    ; Offset into buffer

        ldx #0               ; Index into pending_acks
@build_loop:
        cpx ack_batch_count
        bcs @send_batch

        ; Get the seq number to ACK
        lda pending_acks,x
        sta ack_seq_temp

        ; Build ACK packet at current position
        ldy ack_batch_pos

        lda #A2P_MAGIC_0
        sta ack_batch_buffer,y
        iny
        lda #A2P_MAGIC_1
        sta ack_batch_buffer,y
        iny
        lda #PKT_ACK
        sta ack_batch_buffer,y
        iny
        lda #1               ; Len = 1
        sta ack_batch_buffer,y
        iny
        lda #0               ; Len high
        sta ack_batch_buffer,y
        iny
        lda #0               ; Seq (ACK packets use seq 0)
        sta ack_batch_buffer,y
        iny
        lda ack_seq_temp     ; Data = seq being ACKed
        sta ack_batch_buffer,y
        iny

        ; Checksum: XOR of type, len_lo, len_hi, seq, data
        lda #PKT_ACK
        eor #1               ; len_lo
        eor #0               ; len_hi
        eor #0               ; seq
        eor ack_seq_temp     ; data
        sta ack_batch_buffer,y
        iny

        sty ack_batch_pos    ; Update position
        inx
        jmp @build_loop

@send_batch:
        ; Send all ACKs in one tcp_send call
        lda ack_batch_pos
        beq @done
        sta tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1
        ldax #ack_batch_buffer
        jsr tcp_send

@done:
        rts

;-------------------------------------------------------------------------------
; Send NACK packet
;-------------------------------------------------------------------------------
send_nack:
        lda #A2P_MAGIC_0
        sta send_buffer
        lda #A2P_MAGIC_1
        sta send_buffer+1
        lda #PKT_NACK
        sta send_buffer+2
        lda #1
        sta send_buffer+3
        lda #0
        sta send_buffer+4
        lda #0
        sta send_buffer+5
        lda pkt_seq
        sta send_buffer+6

        lda #PKT_NACK
        eor #1
        eor #0
        eor #0
        eor pkt_seq
        sta send_buffer+7

        lda #8
        sta tcp_send_data_len
        lda #0
        sta tcp_send_data_len+1
        ldax #send_buffer
        jsr tcp_send
        rts

;-------------------------------------------------------------------------------
; Output character with scrolling
; IMPORTANT: Must preserve Y register (caller uses it as loop index)
;-------------------------------------------------------------------------------
output_char:
        ; Save Y register first (all paths need it preserved)
        sty temp2            ; Use temp2 since temp1 may be used by caller

        ; Form feed: a fresh page of the log (the proxy's closing card)
        cmp #$8C
        bne :+
        jsr clear_output_area
        ldy temp2
        rts
:
        ; Check for newline (CR or LF)
        cmp #$8D             ; CR with high bit
        beq @newline
        cmp #$0D             ; CR without high bit
        beq @newline
        cmp #$8A             ; LF with high bit
        beq @newline
        cmp #$0A             ; LF without high bit
        beq @newline

        ; Save character
        pha

        ; Ensure we're on the output row
        ldy output_row
        cpy CV               ; Already on correct row?
        beq @check_wrap

        ; Switching to output row - restore our cursor position
        sty CV
        jsr VTAB             ; Position to output_row
        lda output_col       ; Restore column position
        sta CH

@check_wrap:
        ; Check line wrap
        lda CH
        cmp screen_width_m1  ; At end of line?
        bcc @print
        jsr do_scroll
        lda #0
        sta CH
        sta output_col       ; Reset column tracker

@print:
        ; Always set cursor position before output to avoid corruption
        lda output_row
        sta CV
        jsr VTAB
        lda output_col       ; MUST set CH - other code may have changed it
        sta CH

        pla                  ; Restore character
        jsr COUT

        ; Save column position for later
        lda CH
        sta output_col

        ldy temp2            ; Restore Y
        rts

@newline:
        jsr do_scroll
        lda #0
        sta CH
        sta output_col       ; Reset column tracker
        ldy temp2            ; Restore Y
        rts

;-------------------------------------------------------------------------------
; Scroll output area
; NOTE: Outputs CR for terminal compatibility (Bobbin --simple mode)
; When wrapping to top, redraws command area to ensure it's intact
; Includes [MORE] pagination for long outputs
;-------------------------------------------------------------------------------
do_scroll:
        ; Check pagination - pause after LINES_PER_PAGE lines
        lda more_enabled
        beq @no_pause            ; Skip if [MORE] disabled
        inc lines_since_pause
        lda lines_since_pause
        cmp #LINES_PER_PAGE
        bcc @no_pause

        ; Show [MORE] prompt and wait for key
        jsr show_more_prompt

@no_pause:
        inc output_row
        lda output_row
        cmp #OUTPUT_END
        bcc @no_wrap
        beq @no_wrap

        ; Wrap to top - clear output area for clean page
        jsr clear_output_area
        jsr draw_command_area
        ; Cursor already positioned at OUTPUT_START by clear_output_area
        rts

@no_wrap:
        ; Only output CR if cursor is in output area
        lda CV
        cmp #OUTPUT_END
        bcs @position         ; Skip CR if CV >= OUTPUT_END

        ; Output CR for terminal compatibility
        lda #$8D             ; CR with high bit
        jsr COUT

@position:
        lda output_row
        sta CV
        jsr VTAB
        lda #0                  ; CLREOL clears from CH on - which may be
        sta CH                  ; wherever the status/input line left it
        jsr clear_eol
        rts

;-------------------------------------------------------------------------------
; Show [MORE] prompt and wait for keypress
; Resets pagination counter after keypress
;-------------------------------------------------------------------------------
show_more_prompt:
        ; Save cursor position
        lda CH
        pha
        lda CV
        pha

        ; Print [MORE] at current position
        ldax #msg_more
        jsr print

        ; Wait for any key
        jsr read_key

        ; Clear the [MORE] text (backspace over it)
        lda #$88             ; Backspace
        jsr COUT
        jsr COUT
        jsr COUT
        jsr COUT
        jsr COUT
        jsr COUT             ; 6 backspaces for "[MORE]"
        ldax #msg_spaces_6
        jsr print            ; Overwrite with spaces

        ; Backspace again to restore cursor position
        lda #$88
        jsr COUT
        jsr COUT
        jsr COUT
        jsr COUT
        jsr COUT
        jsr COUT

        ; Restore cursor position
        pla
        sta CV
        jsr VTAB
        pla
        sta CH

        ; Reset pagination counter
        lda #0
        sta lines_since_pause
        rts

;-------------------------------------------------------------------------------
; Prompt to inject program
;-------------------------------------------------------------------------------
prompt_inject:
        ldax #msg_inject
        jsr print_status     ; "INJECT PROGRAM? (Y/N) " on status line

@wait:
        jsr read_key
        and #$DF             ; Upper case

        cmp #'Y'
        beq @yes
        cmp #'N'
        beq @no
        cmp #$8D             ; Return = yes
        beq @yes
        jmp @wait

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
        ; Set BASIC pointers
        lda #<BASIC_START
        sta TXTTAB
        lda #>BASIC_START
        sta TXTTAB+1

        ; End of program - set all required pointers
        lda dst_ptr
        sta VARTAB
        sta ARYTAB
        sta STREND
        sta PRGEND           ; CRITICAL: needed for BASIC editing to work
        lda dst_ptr+1
        sta VARTAB+1
        sta ARYTAB+1
        sta STREND+1
        sta PRGEND+1

        ; Disable TRON (trace mode) - prevents #nn output during RUN
        lda #0
        sta $F2              ; TRCFLG - BASIC trace flag

        rts

;-------------------------------------------------------------------------------
; Status message - position at STATUS_LINE (direct screen memory, no scroll)
; Line 22 screen memory = $750 (Apple II screen layout)
;-------------------------------------------------------------------------------
STATUS_LINE_ADDR = $750

status_msg:
        ; Clear line 22 using COUT (works in --simple terminal mode)
        ; Save cursor
        lda CV
        sta status_save_cv
        lda CH
        sta status_save_ch
        ; Position at line 22
        lda #STATUS_LINE
        sta CV
        jsr VTAB
        lda #0
        sta CH
        jsr clear_eol
        ; Restore cursor
        lda status_save_cv
        sta CV
        jsr VTAB
        lda status_save_ch
        sta CH
        rts

;-------------------------------------------------------------------------------
; Status line routines - use COUT for terminal compatibility
; Save/restore cursor position so output_char isn't corrupted
;-------------------------------------------------------------------------------

; Print string to status line (clears first, starts at column 0)
; Input: AX = pointer to null-terminated string
print_status:
        sta status_ptr
        stx status_ptr+1
        ; Save cursor
        lda CV
        sta status_save_cv
        lda CH
        sta status_save_ch
        ; Position at line 22
        lda #STATUS_LINE
        sta CV
        jsr VTAB
        lda #0
        sta CH
        sta status_pos
        jsr clear_eol
        ; Print string via COUT
        ldy #0
@loop:
        lda (status_ptr),y
        beq @done
        ldx status_pos
        cpx screen_width_m1
        bcs @done
        ora #$80
        jsr COUT
        inc status_pos
        iny
        bne @loop
@done:
        ; Restore cursor
        lda status_save_cv
        sta CV
        jsr VTAB
        lda status_save_ch
        sta CH
        rts

; Append string to status line (continues from current position)
; Input: AX = pointer to null-terminated string
status_print:
        sta status_ptr
        stx status_ptr+1
        ; Save cursor
        lda CV
        sta status_save_cv
        lda CH
        sta status_save_ch
        ; Position at status line
        lda #STATUS_LINE
        sta CV
        jsr VTAB
        lda status_pos
        sta CH
        ; Print string via COUT
        ldy #0
@loop:
        lda (status_ptr),y
        beq @done
        ldx status_pos
        cpx screen_width_m1
        bcs @done
        ora #$80
        jsr COUT
        inc status_pos
        iny
        bne @loop
@done:
        ; Restore cursor
        lda status_save_cv
        sta CV
        jsr VTAB
        lda status_save_ch
        sta CH
        rts

; Append single character to status line
; Input: A = character (will have high bit set)
status_char:
        pha
        ; Save cursor
        lda CV
        sta status_save_cv
        lda CH
        sta status_save_ch
        ; Position at status line
        lda #STATUS_LINE
        sta CV
        jsr VTAB
        lda status_pos
        sta CH
        ; Print char
        pla
        ldx status_pos
        cpx screen_width_m1
        bcs @done
        ora #$80
        jsr COUT
        inc status_pos
@done:
        ; Restore cursor
        lda status_save_cv
        sta CV
        jsr VTAB
        lda status_save_ch
        sta CH
        rts

; Append decimal number to status line
; Input: A = value (0-255)
status_decimal:
        sta dec_temp
        ldx #0               ; Flag: printed something

        ; Hundreds
        ldy #0
@hund:
        lda dec_temp
        cmp #100
        bcc @tens
        sec
        sbc #100
        sta dec_temp
        iny
        bne @hund

@tens:
        ; Print hundreds if non-zero
        cpy #0
        beq @skip_hund
        tya
        ora #'0'
        jsr status_char
        ldx #1

@skip_hund:
        ldy #0
@tens_loop:
        lda dec_temp
        cmp #10
        bcc @ones
        sec
        sbc #10
        sta dec_temp
        iny
        bne @tens_loop

@ones:
        ; Print tens if hundreds printed or tens > 0
        cpx #0
        bne @print_tens
        cpy #0
        beq @print_ones
@print_tens:
        tya
        ora #'0'
        jsr status_char

@print_ones:
        lda dec_temp
        ora #'0'
        jsr status_char
        rts

dec_temp: .res 1
status_pos: .res 1           ; Current column on status line
status_save_cv: .res 1       ; Saved CV for status line routines
status_save_ch: .res 1       ; Saved CH for status line routines

;-------------------------------------------------------------------------------
; Clear output area and reset cursor for new response
;-------------------------------------------------------------------------------
clear_output_area:
        ; Reset output position
        lda #OUTPUT_START
        sta output_row
        lda #0
        sta output_col
        sta lines_since_pause    ; Reset pagination counter

        ; Clear each line from OUTPUT_START to OUTPUT_END (CLREOL clears
        ; from CH on, so whole lines need CH = 0)
        lda #0
        sta CH
        lda #OUTPUT_START
@clear_loop:
        sta CV
        pha
        jsr VTAB
        jsr clear_eol
        pla
        clc
        adc #1
        cmp #OUTPUT_END+1       ; output uses row OUTPUT_END too
        bcc @clear_loop

        ; Position cursor at start
        lda #OUTPUT_START
        sta CV
        jsr VTAB
        lda #0
        sta CH
        rts

;-------------------------------------------------------------------------------
; Scroll output by one line (simplified)
; NOTE: Only outputs CR when cursor is already in output area
; This prevents scrolling when coming from input line
;-------------------------------------------------------------------------------
scroll_output:
        inc output_row
        lda output_row
        cmp #OUTPUT_END
        bcc @no_wrap
        beq @no_wrap

        ; Wrap to top - clear output area for clean page
        jsr clear_output_area
        jsr draw_command_area
        rts

@no_wrap:
        ; Only output CR if cursor is in output area (not at input line)
        lda CV
        cmp #OUTPUT_END
        bcs @set_pos         ; Skip CR if CV >= OUTPUT_END (in command area)

        ; Output CR for terminal compatibility
        lda #$8D             ; CR with high bit
        jsr COUT

@set_pos:
        lda output_row
        sta CV
        jsr VTAB
        lda #0
        sta CH               ; Start at column 0
        jsr clear_eol
        rts

;-------------------------------------------------------------------------------
; Print multi-line text (0-terminated, uses CR for newlines)
;-------------------------------------------------------------------------------
print_multiline:
        stax src_ptr
        ldy #0
@loop:
        lda (src_ptr),y
        beq @done
        cmp #13              ; CR
        bne @print
        tya                  ; Save Y (scroll_output destroys it via CLREOL)
        pha
        jsr scroll_output
        pla
        tay                  ; Restore Y
        iny
        bne @loop
        beq @done
@print:
        jsr print_a
        iny
        bne @loop
@done:
        rts

;-------------------------------------------------------------------------------
; Convert to uppercase
;-------------------------------------------------------------------------------
to_upper:
        cmp #'a'
        bcc @done
        cmp #'z'+1
        bcs @done
        and #$DF
@done:
        rts

;-------------------------------------------------------------------------------
; Print A as decimal
;-------------------------------------------------------------------------------
print_decimal:
        sta temp1
        ldx #0

        ; Hundreds
        ldy #0
@hund:
        lda temp1
        cmp #100
        bcc @tens
        sec
        sbc #100
        sta temp1
        iny
        bne @hund

@tens:
        ; Print hundreds if non-zero
        cpy #0
        beq @skip_hund
        tya
        ora #'0'
        jsr print_a
        ldx #1               ; Flag: printed something

@skip_hund:
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

@ones:
        ; Print tens if hundreds printed or tens > 0
        cpx #0
        bne @print_tens
        cpy #0
        beq @print_ones
@print_tens:
        tya
        ora #'0'
        jsr print_a

@print_ones:
        lda temp1
        ora #'0'
        jsr print_a
        rts

;===============================================================================
; Data
;===============================================================================

        .segment "RODATA"

msg_banner:
        .byte "APPLE II AGENT V2.0", 0

msg_40col:
        .byte "40-COLUMN UPPERCASE", 0

msg_40l:
        .byte "40-COLUMN MIXED CASE", 0

msg_80col:
        .byte "80-COLUMN MIXED CASE", 0

msg_display_usage:
        .byte "/DISPLAY 40|40L|80", 0

msg_init_net:
        .byte "INITIALIZING NETWORK...", 0

msg_net_fail:
        .byte "NETWORK INIT FAILED", 0

msg_net_retry:
        .byte "CHECK THE UTHERNET II, PRESS A KEY", 0

msg_installed:
        .byte "ASK FOR ANY PROGRAM. ESC OR CTRL-RESET", 13
        .byte "BRINGS YOU BACK HERE FROM IT.", 0

msg_ready:
        .byte "READY", 0

msg_connecting:
        .byte "CONNECTING...", 0

msg_conn_fail:
        .byte "CONNECTION FAILED", 0

msg_conn_lost:
        .byte "CONNECTION LOST - TRY AGAIN", 0

msg_reinit_net:
        .byte "RESTARTING NETWORK...", 0

msg_not_saved:
        .byte "SETTINGS NOT SAVED (WRITE-PROTECTED?)", 0

msg_my_address:
        .byte "THIS APPLE II IS ", 0

msg_finding:
        .byte "LOOKING FOR THE PROXY...", 0

msg_finding_status:
        .byte "LOOKING FOR THE PROXY...", 0

msg_found:
        .byte 13, "FOUND IT: ", 0

msg_not_found:
        .byte 13, "NO ANSWER. TRYING ", 0

msg_start_proxy:
        .byte "START THE PROXY ON YOUR COMPUTER", 13
        .byte "(./PROXY.SH START), THEN JUST TYPE.", 13
        .byte "OR SET ITS ADDRESS: /SETIP X.X.X.X", 0

; find_proxy <-> proxy/unified_proxy.py DISCOVERY_ASK / DISCOVERY_ANSWER
discovery_ask:
        .byte "A2AGENT?"
discovery_answer:
        .byte "A2AGENT!"

msg_connected:
        .byte "CONNECTED", 0

msg_connected_proxy:
        .byte "CONNECTED TO PROXY", 0

msg_press_key:
        .byte "PRESS ANY KEY...", 0

msg_receiving:
        .byte "RECEIVING...", 0

msg_timeout:
        .byte "TIMEOUT", 0

msg_error_prefix:
        .byte "ERROR: ", 0

msg_inject:
        .byte "INJECT PROGRAM? (Y/N) ", 0

msg_injected:
        .byte "PROGRAM LOADED - TYPE RUN", 0

msg_code_ready:
        .byte "PROGRAM READY!", $8D
        .byte "/LIST TO VIEW  /EXIT THEN RUN", $8D
        .byte "RESUME: & OR CTRL-Y", 0

msg_more:
        .byte "[MORE]", 0

msg_spaces_6:
        .byte "      ", 0

msg_current_ip:
        .byte "PROXY IP: ", 0


msg_unknown_cmd:
        .byte "UNKNOWN COMMAND - TYPE /HELP", 0

msg_more_on:
        .byte "[MORE] PAGINATION: ON", 0
msg_more_off:
        .byte "[MORE] PAGINATION: OFF", 0

msg_ip_set:
        .byte "IP SET: ", 0

msg_invalid_ip:
        .byte "INVALID IP - USE: /SETIP 192.168.1.100", 0

msg_port_set:
        .byte "PORT SET: ", 0

msg_invalid_port:
        .byte "INVALID PORT - USE: /PORT 6502", 0

msg_custom:
        .byte "CUSTOM", 0

msg_saving:
        .byte "SAVING CONFIG...", 0

msg_saved:
        .byte "SAVED!", 0

msg_resetting:
        .byte "RESETTING SESSION...", 0

msg_save_failed:
        .byte "SAVE FAILED", 0

msg_stopping:
        .byte "STOPPING CLAUDE - ESC AGAIN TO GIVE UP", 0

msg_gave_up:
        .byte "STOPPED WAITING", 0
msg_stalled:
        .byte "NO WORD FROM THE PROXY - RECONNECTING", 0

msg_model_set:
        .byte "MODEL: ", 0

msg_current_model:
        .byte "CURRENT MODEL: ", 0

msg_model_options:
        .byte "/MODEL O - OPUS (DEFAULT, SMARTEST)", 13
        .byte "/MODEL S - SONNET (FASTER)", 13
        .byte "/MODEL H - HAIKU (FASTEST)", 13, 0

msg_suspended:
        .byte 13
        .byte "APPLESOFT BASIC. ESC (AT THE ] PROMPT),", 13
        .byte "& OR CTRL-Y COMES BACK TO THE AGENT.", 13, 0

model_sonnet:
        .byte "SONNET", 0

model_opus:
        .byte "OPUS", 0

model_haiku:
        .byte "HAIKU", 0

prompt_str:
        .byte "AGENT> ", 0

code_prefix:
        .byte "/CODE ", 0

ui_header:
        .byte "======== APPLE II AI AGENT ========", 0

help_text:
        .byte "/HELP    - SHOW COMMANDS", 13
        .byte "/RUN     - RUN YOUR PROGRAM (AGAIN)", 13
        .byte "/EXIT    - DROP TO BASIC", 13
        .byte "/RESET   - NEW SESSION", 13
        .byte "/PROMPT  - SET AI CONTEXT", 13
        .byte "/DISPLAY - 40, 40L (LOWERCASE) OR 80", 13
        .byte "/IP      - SHOW PROXY IP", 13
        .byte "/SETIP   - SET PROXY IP", 13
        .byte "/PORT    - SET PORT", 13
        .byte "/MODEL   - SET AI MODEL", 13
        .byte "/MORE    - TOGGLE PAGINATION", 13
        .byte "/SAVE    - SAVE CONFIG", 13
        .byte "/CLEAR   - CLEAR SCREEN", 13
        .byte "ESC      - CLEAR THE LINE", 13
        .byte "IN A PROGRAM: ESC OR CTRL-RESET", 13
        .byte "             COMES BACK HERE", 13, 0


;-------------------------------------------------------------------------------
; ProDOS MLI Parameter Blocks (in DATA segment - must be writable)
;-------------------------------------------------------------------------------

        .segment "DATA"

; Filename (Pascal string: length + chars)
config_filename:
        .byte 10                        ; Length = 10 chars
        .byte "CLAUDECONF"              ; Simple filename

; CREATE parameters (create if not exists)
create_parms:
        .byte 7                         ; Param count
        .word config_filename           ; Pathname pointer
        .byte $C3                       ; Access: read/write/destroy
        .byte FT_BIN                    ; File type: BIN
        .word $0300                     ; Aux type: load address
        .byte $01                       ; Storage type: seedling
        .word 0                         ; Create date (0=current)
        .word 0                         ; Create time

; OPEN parameters
open_parms:
        .byte 3                         ; Param count
        .word config_filename           ; Pathname pointer
        .word io_buffer                 ; I/O buffer (1024 bytes, page aligned)
open_refnum:
        .byte 0                         ; Ref num (output)

; READ parameters
read_parms:
        .byte 4                         ; Param count
read_refnum:
        .byte 0                         ; Ref num
        .word CONFIG_IP                 ; Data buffer (read directly to config)
        .word CONFIG_SIZE               ; Request count (8 bytes)
read_trans:
        .word 0                         ; Trans count (output)

; WRITE parameters
write_parms:
        .byte 4                         ; Param count
write_refnum:
        .byte 0                         ; Ref num
        .word CONFIG_IP                 ; Data buffer (write from config)
        .word CONFIG_SIZE               ; Request count (8 bytes)
write_trans:
        .word 0                         ; Trans count (output)

; CLOSE parameters
close_parms:
        .byte 1                         ; Param count
close_refnum:
        .byte 0                         ; Ref num

;===============================================================================
; Variables (BSS)
;===============================================================================

        .segment "BSS"

; State
in_ui:          .res 1
col_mode:       .res 1          ; 0=40col, 1=80col
screen_width_m1: .res 1         ; 39 or 79 (screen width minus 1)
display_mode:    .res 1         ; 0=40U, 1=40L, 2=80
output_row:     .res 1
output_col:     .res 1          ; Column position on output line
is_connected:   .res 1          ; 1=TCP connection open, 0=not connected
lines_since_pause: .res 1       ; Lines output since last [MORE] pause
more_enabled:   .res 1          ; 1=[MORE] pagination on (default), 0=off
LINES_PER_PAGE  = 19            ; Lines before showing [MORE]

; Protocol state
tx_seq:         .res 1
rx_seq:         .res 1
recv_state:     .res 1

; Receive state machine states
STATE_MAGIC_0   = 0
STATE_MAGIC_1   = 1
STATE_TYPE      = 2
STATE_LEN_LO    = 3
STATE_LEN_HI    = 4
STATE_SEQ       = 5
STATE_DATA      = 6
STATE_CHECKSUM  = 7
STATE_DONE      = 8

; Packet being received
pkt_type:       .res 1
pkt_len:        .res 2
pkt_seq:        .res 1
pkt_checksum:   .res 1
pkt_data_pos:   .res 1
pkt_buffer:     .res 140        ; Max packet data
MAX_PKT_DATA    = 136           ; Longer packets are dropped (proxy sends <= 128)

; Timeouts
timeout_lo:     .res 1
timeout_hi:     .res 1

; Input
MAX_INPUT       = 239           ; as long as a ] line (GETLN)
input_buffer:   .res MAX_INPUT+1
input_len:      .res 1
input_visible:  .res 1          ; input columns on screen (set_input_visible)
send_attempts:  .res 1          ; send_chat retries left
rx_remaining:   .res 2          ; recv_callback: bytes left in this segment
response_done:  .res 1          ; a DONE / final packet arrived
stop_requested: .res 1          ; ESC pressed once while waiting
drain_count:    .res 1
proxy_found:    .res 1          ; find_proxy: an answer arrived
proxy_moved:    .res 1          ; ...with a different address or port
discovery_tries: .res 1
discovery_wait: .res 1
wait_tenths:    .res 1          ; wait_key_or_timeout
config_save_err: .res 1
port_x2:        .res 2          ; cmd_port: port * 2
new_ip:         .res 4          ; cmd_setip: the address being parsed
rx_any:         .res 1          ; a packet arrived since the last send
silent_frames:  .res 2          ; frames since the last packet (stall watchdog)
silence_limit:  .res 2          ; ...when it's a stall (CONFIG_WATCHDOG * 60)
temp_w:         .res 2
vbl_prev:       .res 1
resync_tries:   .res 1
packet_lost:    .res 1          ; a packet failed its checksum since the DEPLOY
a2p_bad:        .res 1          ; ...how many ever (the stall report)
rx_at_packet:   .res 2          ; tcp_rx_count at the last good packet
diag_len:       .res 1
diag_buf:       .res 80         ; the stall report (/RESYNC ...)

; Code handling
expecting_code: .res 1
got_code:       .res 1
code_offset:    .res 2
code_total:     .res 2
code_request:   .res 128
code_request_len: .res 1
chat_data_len:  .res 1

; Send buffer
send_buffer:    .res 256

; IP/Port parsing
parse_value:    .res 1
port_lo:        .res 1
port_hi:        .res 1
port_str:       .res 6

; Callback re-entry guard
in_callback:       .res 1       ; Non-zero if inside recv_callback
recv_pkt_count:    .res 1       ; Count of callback invocations (debug)

; Error detection (for smart & handler)
detected_error:    .res 1       ; Non-zero if error was detected
detected_err_code: .res 1       ; Error code (0-255)
detected_err_line: .res 2       ; Line number where error occurred

; Deferred ACK handling (avoid tcp_send during recv_callback)
pending_ack_count: .res 1       ; Number of pending ACKs
pending_acks:      .res 8       ; Sequence numbers to ACK
ack_seq_temp:      .res 1       ; Temp for send_ack_for_seq
ack_batch_count:   .res 1       ; Number of ACKs to send in batch
ack_batch_pos:     .res 1       ; Current position in batch buffer
ack_batch_buffer:  .res 64      ; Buffer for up to 8 ACK packets (8 bytes each)

; ProDOS I/O buffer (must be page-aligned, 1024 bytes)
; Placed in separate IOBUF segment to ensure alignment
        .segment "IOBUF"
io_buffer:      .res 1024
        .segment "BSS"

;===============================================================================
; Deploy / launch / return (program runner)
;===============================================================================
.include "agent_deploy.s"
.include "agent_screen.s"
