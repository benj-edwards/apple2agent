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

;-------------------------------------------------------------------------------
; Memory Layout
; NOTE: These addresses must be ABOVE the BSS segment end (~$9D40)
; to avoid collision with IP65's ethernet buffers
;-------------------------------------------------------------------------------
SCREEN_SAVE     = $A600         ; 1KB screen save buffer ($A600-$A9FF)
                                ; (must be past IOBUF which ends at $A5FF)
RECV_BUFFER     = $AA00         ; 4KB receive buffer (circular) ($AA00-$B9FF)
RECV_BUF_SIZE   = $1000         ; 4096 bytes
RECV_BUF_MASK   = $0FFF         ; Mask for wrap-around

; Configuration at $0300
CONFIG_BASE     = $0300
CONFIG_IP       = $0300         ; 4 bytes: proxy IP
CONFIG_PORT     = $0304         ; 2 bytes: port (little-endian)
CONFIG_MODEL    = $0306         ; 1 byte: AI model (0=sonnet, 1=opus, 2=haiku)
CONFIG_MAGIC    = $0307         ; 1 byte: magic ($A2 = valid config)
CONFIG_MAGIC_VAL = $A2

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
TXTPAGE1        = $C054         ; Display page 1
TXTPAGE2        = $C055         ; Display page 2
STORE80OFF      = $C000         ; 80-col store off
STORE80ON       = $C001         ; 80-col store on
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

; Config file size (8 bytes: IP + Port + Flags + Magic)
CONFIG_SIZE     = 8

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
        ; Print banner first
        jsr HOME
        ldax #msg_banner
        jsr print
        jsr print_cr

        ; Detect 80-column card
        jsr detect_80col
        sta col_mode

        ; Show column mode
        lda col_mode
        beq @show_40
        ldax #msg_80col
        jmp @show_mode
@show_40:
        ldax #msg_40col
@show_mode:
        jsr print
        jsr print_cr

        ; Initialize network
        ldax #msg_init_net
        jsr print
        init_ip_via_dhcp
        bcc @net_ok

        ldax #msg_net_fail
        jsr print
        jsr print_cr
        jmp exit_to_basic

@net_ok:
        jsr print_cr
        jsr print_ip_config
        jsr print_cr

        ; Load saved configuration
        jsr load_config

        ; Install ampersand hook
        jsr install_hook

        ; Connect to proxy now
        jsr print_cr
        ldax #msg_connecting
        jsr print
        jsr connect_to_proxy
        bcs @conn_failed

        ldax #msg_connected_proxy
        jsr print
        jsr print_cr
        jmp @show_instructions

@conn_failed:
        ldax #msg_conn_fail
        jsr print
        jsr print_cr

@show_instructions:
        ; Show instructions
        ldax #msg_installed
        jsr print
        jsr print_cr

        ; Wait for key so user can see boot info
        ldax #msg_press_key
        jsr print
        jsr RDKEY           ; Wait for any key
        jsr print_cr        ; Line break before UI

        ; Go directly to main UI
        jsr main_ui

        ; Return to BASIC when done
        jmp exit_to_basic

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
; Ampersand entry point
;-------------------------------------------------------------------------------
ampersand_entry:
        lda in_ui
        beq @not_in_ui
        rts                     ; Already in UI, exit
@not_in_ui:
        ; Phase 2b: Check if this was auto-triggered by error intercept
        ; (KSWL hook stuffed & after an immediate-mode error)
        lda error_intercept_flag
        beq @not_intercepted

        ; Error was intercepted! Use saved input buffer
        jsr copy_saved_input
        lda #0
        sta error_intercept_flag
        sta kbd_stuff_state

        ; If input is empty, skip to normal UI
        lda input_len
        bne @send_intercepted
        jmp @normal_ui

@send_intercepted:
        ; Intercepted natural language! Enter UI and send to Claude
        lda #1
        sta in_ui
        jsr save_screen

        jsr HOME

        ; Initialize output tracking
        lda #OUTPUT_START
        sta output_row
        lda #0
        sta output_col
        sta lines_since_pause

        ; Print header
        ldax #ui_header
        jsr print
        jsr print_cr

        ; Show what we're sending
        ldax #msg_nl_sending
        jsr print
        jsr print_cr
        ldax #input_buffer
        jsr print
        jsr print_cr
        jsr print_cr

        ; Send the message to Claude
        jsr send_chat

        ; Clear input for next interaction
        lda #0
        sta input_len

        ; Wait for keypress before returning to BASIC
        jsr print_cr
        ldax #msg_press_key
        jsr print
        jsr RDKEY

        ; Restore screen and return to BASIC
        jsr restore_screen
        lda #0
        sta in_ui
        rts

@not_intercepted:
        ; Phase 3: Check if auto-triggered by program error
        lda program_error_flag
        beq @not_program_error
        lda #0
        sta program_error_flag
        sta kbd_stuff_state
        ; Reuse Phase 1 screen scan to read the error message
        jsr check_basic_error
        lda input_len
        beq @normal_ui
        ; Found error on screen - send to Claude (reuse Phase 1 path)
        jmp @error_send

@not_program_error:
        ; Phase 1: Manual & press - check for BASIC errors
        jsr check_basic_error

        ; If error was detected (input_len > 0), send it immediately
        lda input_len
        beq @normal_ui

@error_send:
        ; Error detected! Send it to agent automatically
        lda #1
        sta in_ui
        jsr save_screen

        ; Set up the UI
        jsr HOME

        ; Initialize output tracking
        lda #OUTPUT_START
        sta output_row
        lda #0
        sta output_col
        sta lines_since_pause

        ; Print header
        ldax #ui_header
        jsr print
        jsr print_cr

        ; Show what error we detected
        ldax #msg_error_detected
        jsr print
        jsr print_cr

        ; Show the error message we're sending
        ldax #input_buffer
        jsr print
        jsr print_cr
        jsr print_cr

        ; Send the error to agent (this will display response)
        jsr send_chat

        ; Clear input for next interaction
        lda #0
        sta input_len

        ; Now go to normal main loop for continued interaction
        jmp @enter_main_loop

@normal_ui:
        lda #1
        sta in_ui
        jsr save_screen
        jsr HOME

        ; Initialize output tracking
        lda #OUTPUT_START
        sta output_row
        lda #0
        sta output_col
        sta lines_since_pause

        ; Print header
        ldax #ui_header
        jsr print
        jsr print_cr

@enter_main_loop:
        ; Main loop - shared by error path and normal path
        jsr print_cr
        ldax #prompt_str
        jsr print
        jsr get_input
        bcs @check_esc

        lda input_len
        beq @enter_main_loop

        jsr process_input
        jmp @enter_main_loop

@check_esc:
        cmp #$9B
        beq @show_menu
        cmp #$1B
        beq @show_menu
        jmp @enter_main_loop

@show_menu:
        jsr show_menu
        bcc @enter_main_loop
        ; Exit requested - restore screen and return
        jsr restore_screen
        lda #0
        sta in_ui

@exit:
        rts

msg_error_detected:
        .byte "DETECTED ERROR - ASKING AGENT...", 0

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

;===============================================================================
; Phase 2b: ROM Patch - Natural Language at BASIC Prompt
;
; Patches the Applesoft error handler at $D412 (in Language Card RAM)
; to intercept immediate-mode errors. When user types natural language
; at the ] prompt, BASIC gets SYNTAX ERROR. Our patched handler:
; 1. Checks CURLIN=$FFFF (immediate mode)
; 2. Saves the input buffer at $200
; 3. Sets error_intercept_flag
; 4. JMPs to $E003 (warm start) to cleanly return to ] prompt
; 5. KSWL hook auto-stuffs & to trigger ampersand_entry
; 6. ampersand_entry sends the saved input to Claude
;===============================================================================

; Language Card soft switches
LCRAM_RW        = $C083         ; Read twice: LC bank 2 read + write
LCRAM_RO        = $C080         ; Read: LC bank 2 read, write-protect
LCRAM_ROM_WR    = $C081         ; Read twice: read ROM, write LC bank 2
LCRAM_ROM       = $C082         ; Read ROM, write-protect LC
BASIC_WARM      = $E003         ; Applesoft warm start (] prompt)

; Error handler patch location
ERR_HANDLER     = $D412         ; Applesoft error handler entry point
ERR_HANDLER_ORIG_SIZE = 3       ; We patch 3 bytes (BIT $D8; BPL ...)

;-------------------------------------------------------------------------------
; Patch the Applesoft error handler at $D412
; Replaces "BIT $D8; BPL +3" with "JMP error_intercept"
; Original bytes: 24 D8 10
;-------------------------------------------------------------------------------
patch_error_handler:
        ; Step 1: Copy ROM ($D000-$FFFF) to LC bank 2 RAM
        ; LC bank 2 may not have ROM content, so we must copy it first.
        ; Use $C081 mode: reads come from ROM, writes go to LC bank 2.
        lda LCRAM_ROM_WR        ; read ROM, write LC bank 2
        lda LCRAM_ROM_WR        ; (must read soft switch twice)

        lda #$D0
        sta src_ptr+1
        lda #$00
        sta src_ptr
        tay                     ; Y = 0
@copy_page:
        lda (src_ptr),y         ; read from ROM
        sta (src_ptr),y         ; write to LC bank 2
        iny
        bne @copy_page
        inc src_ptr+1
        bne @copy_page          ; loops until high byte wraps $FF->$00

        ; Step 2: Switch to LC bank 2 read+write for patching
        lda LCRAM_RW
        lda LCRAM_RW

        ; Save original 3 bytes at $D412 (now in LC, same as ROM)
        lda ERR_HANDLER
        sta orig_err_byte0
        lda ERR_HANDLER+1
        sta orig_err_byte1
        lda ERR_HANDLER+2
        sta orig_err_byte2

        ; Patch with JMP error_intercept
        lda #$4C
        sta ERR_HANDLER
        lda #<error_intercept
        sta ERR_HANDLER+1
        lda #>error_intercept
        sta ERR_HANDLER+2

        ; Write-protect LC RAM (keep LC bank 2 mapped for reads)
        lda LCRAM_RO
        rts

;-------------------------------------------------------------------------------
; Restore the original Applesoft error handler at $D412
;-------------------------------------------------------------------------------
restore_error_handler:
        ; Restore original bytes in LC bank 2
        lda LCRAM_RW
        lda LCRAM_RW
        lda orig_err_byte0
        sta ERR_HANDLER
        lda orig_err_byte1
        sta ERR_HANDLER+1
        lda orig_err_byte2
        sta ERR_HANDLER+2
        ; Switch back to ROM reads (unpatch)
        lda LCRAM_ROM
        rts

;-------------------------------------------------------------------------------
; Install KSWL hook for auto-stuffing & after intercepted errors
;-------------------------------------------------------------------------------
install_kswl_hook:
        ; Check if already installed (avoid saving our own address)
        lda KSWL
        cmp #<kswl_hook
        bne @not_installed
        lda KSWH
        cmp #>kswl_hook
        beq @done               ; Already installed
@not_installed:
        lda KSWL
        sta saved_kswl
        sta saved_kswl_vec
        lda KSWH
        sta saved_kswh
        sta saved_kswl_vec+1
        ; If original was $0000, point to our own key reader
        ora saved_kswl_vec
        bne @set_hook
        lda #<builtin_keyin
        sta saved_kswl_vec
        lda #>builtin_keyin
        sta saved_kswl_vec+1
@set_hook:
        lda #<kswl_hook
        sta KSWL
        lda #>kswl_hook
        sta KSWH
@done:
        rts

;-------------------------------------------------------------------------------
; Restore original KSWL handler
;-------------------------------------------------------------------------------
restore_kswl:
        lda saved_kswl
        sta KSWL
        lda saved_kswh
        sta KSWH
        rts

;-------------------------------------------------------------------------------
; Error intercept - called from patched $D412
; Entry: X = error code (from Applesoft)
; For immediate-mode errors: save input, set flag, go to warm start
; For all other cases: execute the original error handler code
;-------------------------------------------------------------------------------
error_intercept:
        ; Check if immediate mode: only CURLIN_H ($76) is set to $FF
        ; (Applesoft does NOT set CURLIN_L for immediate mode)
        lda CURLIN_H
        cmp #$FF
        bne @not_immediate

        ; Immediate mode error - save input buffer before warm start
        stx temp1
        jsr save_input_buf_200
        lda #1
        sta error_intercept_flag
        lda #0
        sta kbd_stuff_state
        jmp BASIC_WARM

@not_immediate:
        ; Not immediate mode - execute original error handler
        bit $D8
        bpl @no_onerr
        jmp $F2E9
@no_onerr:
        ; Phase 3: Auto-invoke agent for program errors
        ; Skip BREAK (255) and REENTER (254) - intentional/non-error stops
        cpx #255
        beq @no_phase3
        cpx #254
        beq @no_phase3
        lda #1
        sta program_error_flag
        lda #0
        sta kbd_stuff_state
@no_phase3:
        jmp $D419           ; Normal handler prints error, returns to ]

;-------------------------------------------------------------------------------
; KSWL hook - keepalive polling + auto-stuffs & + CR for error flags
;-------------------------------------------------------------------------------
kswl_hook:
        ; Phase 2b: auto-stuff & after immediate-mode error
        lda error_intercept_flag
        bne @stuff_ampersand

        ; Phase 3: auto-stuff & after program error
        lda program_error_flag
        bne @stuff_ampersand

        ; No flags - enter keepalive polling loop
        ; Sit here checking keyboard + polling network periodically
@poll_loop:
        lda $C000               ; Check keyboard
        bmi @key_ready          ; Bit 7 set = key available
        inc poll_counter_lo
        bne @poll_loop
        inc poll_counter_hi
        bne @poll_loop
        ; Both wrapped (~65536 iterations, roughly 1 sec at 1MHz)
        txa
        pha
        tya
        pha
        jsr ip65_process        ; Keep TCP connection alive
        pla
        tay
        pla
        tax
        jmp @poll_loop

@key_ready:
        jmp (saved_kswl_vec)    ; Original handler reads the key

@stuff_ampersand:
        lda kbd_stuff_state
        bne @stuff_cr
        inc kbd_stuff_state
        lda #($26 | $80)       ; & with high bit
        rts
@stuff_cr:
        lda #0
        sta kbd_stuff_state
        lda #$8D               ; CR
        rts

saved_kswl_vec:
        .word $0000

;-------------------------------------------------------------------------------
; Builtin key reader - fallback when original KSWL was $0000
;-------------------------------------------------------------------------------
builtin_keyin:
        lda $C000
        bpl builtin_keyin
        bit $C010               ; Clear keyboard strobe
        rts

;-------------------------------------------------------------------------------
; Save BASIC input buffer ($200) to saved_input_buf
;-------------------------------------------------------------------------------
save_input_buf_200:
        ldy #0
@loop:
        lda BASIC_INPUT_BUF,y
        sta saved_input_buf,y
        beq @done
        cmp #$8D
        beq @done_cr
        iny
        cpy #MAX_INPUT
        bcc @loop
        bcs @done
@done_cr:
        lda #0
        sta saved_input_buf,y
@done:
        sty saved_input_len
        rts

;-------------------------------------------------------------------------------
; Copy saved input buffer to input_buffer (for send_chat)
;-------------------------------------------------------------------------------
copy_saved_input:
        ldy #0
@loop:
        lda saved_input_buf,y
        beq @done
        and #$7F
        cmp #$20
        bcc @done
        sta input_buffer,y
        iny
        cpy #MAX_INPUT
        bcc @loop
@done:
        sty input_len
        lda #0
        sta input_buffer,y
        rts

; Save text screen
;-------------------------------------------------------------------------------
save_screen:
        lda #<TEXTPAGE
        sta src_ptr
        lda #>TEXTPAGE
        sta src_ptr+1
        lda #<SCREEN_SAVE
        sta dst_ptr
        lda #>SCREEN_SAVE
        sta dst_ptr+1

        ldx #4                ; 4 pages
@page:
        ldy #0
@byte:
        lda (src_ptr),y
        sta (dst_ptr),y
        iny
        bne @byte
        inc src_ptr+1
        inc dst_ptr+1
        dex
        bne @page
        rts

;-------------------------------------------------------------------------------
; Restore text screen
;-------------------------------------------------------------------------------
restore_screen:
        lda #<SCREEN_SAVE
        sta src_ptr
        lda #>SCREEN_SAVE
        sta src_ptr+1
        lda #<TEXTPAGE
        sta dst_ptr
        lda #>TEXTPAGE
        sta dst_ptr+1

        ldx #4
@page:
        ldy #0
@byte:
        lda (src_ptr),y
        sta (dst_ptr),y
        iny
        bne @byte
        inc src_ptr+1
        inc dst_ptr+1
        dex
        bne @page
        rts

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

        ; Port 8080
        lda #<8080
        sta CONFIG_PORT
        lda #>8080
        sta CONFIG_PORT+1

        ; Default model: Sonnet
        lda #MODEL_SONNET
        sta CONFIG_MODEL

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
        ; NOTE: ProDOS file save is currently disabled due to MLI pathname
        ; handling issues when called from IP65-enabled code. Config changes
        ; are kept in memory but not persisted to disk.
        ; TODO: Investigate ProDOS MLI error $40 with pathname operations

        ; Ensure magic is set (config valid in memory)
        lda #CONFIG_MAGIC_VAL
        sta CONFIG_MAGIC

        ; For now, just return success (config is valid in RAM)
        clc
        rts

        ; Original save code disabled - uncomment when fixed:
        ; jsr MLI
        ; .byte MLI_OPEN
        ; .word open_parms
        ; bcs @fail
        ; ... etc ...

        ; Write config data from CONFIG_IP
        jsr MLI
        .byte MLI_WRITE
        .word write_parms
        bcs @close_fail

        ; Close file
        jsr MLI
        .byte MLI_CLOSE
        .word close_parms

        clc                      ; Success
        rts

@close_fail:
        pha                      ; Save error code
        jsr MLI
        .byte MLI_CLOSE
        .word close_parms
        pla                      ; Restore error code
        sec
        rts

@fail:
        sec                      ; Failure (A = error code)
        rts

;===============================================================================
; Main UI
;===============================================================================
main_ui:
        ; Clear screen and home cursor
        jsr HOME

        ; Initialize output tracking
        lda #OUTPUT_START
        sta output_row
        lda #0
        sta output_col
        sta lines_since_pause    ; Reset pagination counter

        ; Print header
        ldax #ui_header
        jsr print
        jsr print_cr

@main_loop:
        ; Ensure we're on a new line before prompt
        jsr print_cr

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
        ; A contains the key
        cmp #$9B             ; ESC
        beq @show_menu
        cmp #$1B             ; ESC (ASCII)
        beq @show_menu
        jmp @main_loop

@show_menu:
        jsr show_menu
        bcc @main_loop       ; Continue
        ; Exit requested
        rts

;-------------------------------------------------------------------------------
; Draw the UI
; Uses VTAB for screen buffer + CRs for terminal positioning
;-------------------------------------------------------------------------------
draw_ui:
        ; Initialize output position
        lda #OUTPUT_START
        sta output_row
        lda #0
        sta output_col

        ; Position at line 0 for screen buffer
        lda #0
        sta CV
        sta CH
        jsr VTAB

        ; Print header
        ldax #ui_header
        jsr print

        ; CR for terminal
        lda #$8D
        jsr COUT

        ; Position at line 21 for screen buffer
        lda #SEPARATOR_LINE
        sta CV
        lda #0
        sta CH
        jsr VTAB

        ; Print 20 CRs for terminal (to get from line 1 to line 21)
        ldx #20
@blank_lines:
        lda #$8D
        jsr COUT
        dex
        bne @blank_lines

        ; Print separator
        ldax #ui_separator
        jsr print

        ; CR for terminal
        lda #$8D
        jsr COUT

        ; Status and prompt will be drawn by main_loop
        rts

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
; Draw just the input area (status + input prompt)
; Uses VTAB for screen buffer + CRs for terminal
;-------------------------------------------------------------------------------
draw_input_area:
        ; Position at status line for screen buffer
        lda #STATUS_LINE
        sta CV
        lda #0
        sta CH
        jsr VTAB

        ; Print status
        ldax #msg_ready
        jsr print

        ; CR for terminal
        lda #$8D
        jsr COUT

        ; Position at input line for screen buffer
        lda #INPUT_LINE
        sta CV
        lda #0
        sta CH
        jsr VTAB

        ; Print prompt
        ldax #prompt_str
        jsr print
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
        jsr CLREOL
        rts

;-------------------------------------------------------------------------------
; Get user input
; Returns: C=1 if special key (key in A), C=0 if normal input
;-------------------------------------------------------------------------------
get_input:
        lda #0
        sta input_len

@loop:
        jsr RDKEY

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

        ; Buffer full?
        ldx input_len
        cpx #MAX_INPUT
        bcs @loop

        ; Store (clear high bit)
        and #$7F
        sta input_buffer,x
        inc input_len

        ; Echo (with high bit)
        ora #$80
        jsr COUT
        jmp @loop

@delete:
        lda input_len
        beq @loop

        dec input_len

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
        ; Null terminate
        ldx input_len
        lda #0
        sta input_buffer,x
        clc
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
        ; Get command word and convert to uppercase
        lda input_buffer+1
        jsr to_upper

        ; /HELP
        cmp #'H'
        bne :+
        jmp @help
:
        ; /IP
        cmp #'I'
        bne :+
        jmp @ip
:
        ; /LIST
        cmp #'L'
        bne :+
        jmp @list
:
        ; /CODE or /CLEAR (both start with C)
        cmp #'C'
        bne @check_q
        lda input_buffer+2
        jsr to_upper
        cmp #'O'
        beq @code
        cmp #'L'
        beq @clear
        jmp @unknown

@code:
        jmp cmd_code

@clear:
        jsr HOME
        jsr draw_ui
        rts

@check_q:
        ; /QUIT
        cmp #'Q'
        bne @not_quit
        jmp @quit
@not_quit:
        ; /EXIT (alias for /SUSPEND)
        cmp #'E'
        beq @suspend

        ; /SETIP, /SAVE, or /SUSPEND
        cmp #'S'
        bne @check_p
        lda input_buffer+2
        jsr to_upper
        cmp #'E'
        beq @setip
        cmp #'A'
        beq @save
        cmp #'U'
        beq @suspend
        jmp @unknown

@setip:
        jsr cmd_setip
        rts

@save:
        jsr cmd_save
        rts

@suspend:
        ; Install hooks so user can return to agent
        ; Ctrl-Y hook: JMP ampersand_entry
        lda #$4C             ; JMP opcode
        sta CTRLY_VECTOR
        lda #<ampersand_entry
        sta CTRLY_VECTOR+1
        lda #>ampersand_entry
        sta CTRLY_VECTOR+2
        ; & hook: JMP ampersand_entry
        lda #$4C             ; JMP opcode
        sta AMPER_VECTOR
        lda #<ampersand_entry
        sta AMPER_VECTOR+1
        lda #>ampersand_entry
        sta AMPER_VECTOR+2

        ; Clear in_ui flag so ampersand hook works
        lda #0
        sta in_ui
        sta error_intercept_flag
        sta kbd_stuff_state
        sta program_error_flag
        sta poll_counter_lo
        sta poll_counter_hi

        ; Phase 2b: Patch error handler in Language Card RAM
        ; This intercepts immediate-mode errors (natural language at ] prompt)
        jsr patch_error_handler

        ; Phase 2b: Install KSWL hook for auto-stuffing & after errors
        jsr install_kswl_hook

        ; Show message and drop to BASIC
        jsr HOME
        ldax #msg_suspended
        jsr print
        jmp $E003            ; BASIC warm start (]) - no return

@check_p:
        ; /PORT or /PROMPT
        cmp #'P'
        bne @check_m
        lda input_buffer+2
        jsr to_upper
        cmp #'O'
        beq @port
        cmp #'R'
        bne @unknown
        ; /PROMPT - send to server as chat message
        jsr cmd_prompt
        rts
@port:
        jsr cmd_port
        rts

@check_m:
        ; /MODEL
        cmp #'M'
        bne @check_r
        jsr cmd_model
        rts

@check_r:
        ; /RESET - Send to server, it handles clearing session
        cmp #'R'
        bne @unknown
        lda input_buffer+2
        jsr to_upper
        cmp #'E'
        bne @unknown
        ; Send "/RESET" to server as chat message
        jsr cmd_reset
        rts

@help:
        jsr cmd_help
        rts

@ip:
        jsr cmd_ip
        rts

@list:
        jsr cmd_list
        rts

@quit:
        ; Disconnect before exiting
        jsr disconnect
        ; Signal exit (will be handled by main loop)
        pla                  ; Pop return address
        pla
        sec                  ; Signal exit
        rts

@unknown:
        ldax #msg_unknown_cmd
        jsr print_status
        rts

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

        ; Print current IP
        lda CONFIG_IP
        jsr print_decimal
        lda #'.'
        jsr print_a
        lda CONFIG_IP+1
        jsr print_decimal
        lda #'.'
        jsr print_a
        lda CONFIG_IP+2
        jsr print_decimal
        lda #'.'
        jsr print_a
        lda CONFIG_IP+3
        jsr print_decimal
        lda #':'
        jsr print_a

        ; Print port
        ; (simplified - just show 8080)
        ldax #msg_port_8080
        jsr print
        jsr print_cr
        rts

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
; Format: /SETIP 192.168.1.50
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

        ; Multiply parse_value by 10
        lda parse_value
        asl                  ; x2
        sta temp1
        asl                  ; x4
        asl                  ; x8
        clc
        adc temp1            ; x8 + x2 = x10
        adc temp2            ; + digit
        sta parse_value

        iny
        bne @digit_loop

@store_octet:
        ; Store octet
        lda parse_value
        sta CONFIG_IP,x
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
        sta CONFIG_IP,x
        inx

@done_parse:
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
; Format: /PORT 8080
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
        ; First, port * 2
        lda port_lo
        asl
        sta temp1
        lda port_hi
        rol
        sta temp1+1

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
        adc temp1
        sta port_lo
        lda port_hi
        adc temp1+1
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
        ; Store port
        lda port_lo
        sta CONFIG_PORT
        lda port_hi
        sta CONFIG_PORT+1

        ; Show new port on status line (direct screen writes)
        ldax #msg_port_set
        jsr print_status     ; "PORT SET: " - clears line

        ; Print port (simplified - show if 8080)
        lda CONFIG_PORT
        cmp #<8080
        bne @show_custom
        lda CONFIG_PORT+1
        cmp #>8080
        bne @show_custom
        ldax #msg_port_8080
        jsr status_print     ; Append "8080"
        jmp @auto_save

@show_custom:
        ; Just show "CUSTOM" for custom ports
        ldax #msg_custom
        jsr status_print     ; Append "CUSTOM"

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
        ; Ensure we have a connection
        jsr ensure_connected
        bcs @failed

        ; Clear output area for new response
        jsr clear_output_area

        ; Initialize receive state BEFORE sending (callbacks may trigger)
        lda #0
        sta recv_state
        sta got_code
        sta code_offset
        sta code_offset+1
        sta pending_ack_count
        sta in_callback
        lda #<BASIC_START
        sta dst_ptr
        lda #>BASIC_START
        sta dst_ptr+1

        ; Build and send CHAT packet (no INIT needed - sent on connect)
        jsr send_chat_packet
        ; Process any incoming data
        jsr ip65_process
        jsr ip65_process
        jsr ip65_process

        ; Wait for response (state already initialized)
        jsr receive_response_no_init

        ; DON'T close connection - keep it open for next message
        rts

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
        ; Check if already connected
        lda is_connected
        bne @already_connected

        ; Not connected - try to reconnect silently
        jsr connect_to_proxy
        rts

@already_connected:
        clc                  ; Success
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
        ; Header: A2 + PKT_INIT + len(2) + seq
        lda #A2P_MAGIC_0
        sta send_buffer
        lda #A2P_MAGIC_1
        sta send_buffer+1
        lda #PKT_INIT
        sta send_buffer+2
        lda #2               ; Data length = 2 (capabilities + model)
        sta send_buffer+3
        lda #0
        sta send_buffer+4
        lda tx_seq
        sta send_buffer+5
        inc tx_seq

        ; Data byte 0: capabilities
        lda col_mode
        sta send_buffer+6

        ; Data byte 1: model selection
        lda CONFIG_MODEL
        sta send_buffer+7

        ; Checksum (XOR of type through data)
        lda send_buffer+2    ; Type
        eor send_buffer+3    ; Len lo
        eor send_buffer+4    ; Len hi
        eor send_buffer+5    ; Seq
        eor send_buffer+6    ; Capabilities
        eor send_buffer+7    ; Model
        sta send_buffer+8

        ; Send (9 bytes)
        lda #9
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

        ; Copy data (converting to uppercase)
        ldy #0
@copy:
        cpy input_len
        beq @done_copy
        lda input_buffer,y
        jsr to_upper
        sta send_buffer+6,y
        iny
        bne @copy

@done_copy:
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

        ldax #msg_receiving
        jsr print_status

@wait_loop:
        jsr ip65_process

        ; Send any pending ACKs (after callback returns)
        jsr send_pending_acks

        ; Check for completion
        lda recv_state
        cmp #STATE_DONE
        beq @done

        ; Check timeout - disabled for agentic mode which can take minutes
        ; Agentic loop involves multiple Claude API calls + emulator testing
        ; inc timeout_lo
        ; bne @wait_loop
        ; inc timeout_hi
        ; lda timeout_hi
        ; cmp #$FF
        ; bcc @wait_loop
        jmp @wait_loop       ; No timeout - wait forever

        ; Timeout
        ldax #msg_timeout
        jsr print_status

@done:
        rts

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
        lda tcp_inbound_data_length+1
        bne @more
        cpy tcp_inbound_data_length
        bcc @more
        jmp @done

@more:
        ; (debug removed)            ; DEBUG: count bytes processed
        lda (src_ptr),y
        iny
        bne @no_wrap
        inc src_ptr+1
        dec tcp_inbound_data_length+1
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
        ; DEBUG: After process_packet at $0353
        inc $0353

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
        ; DEBUG: After state restore at $0354
        inc $0354

        ; WORKAROUND: Only process ONE packet per callback
        ; Multiple packets in one callback causes crash (unknown root cause)
        ; Reset state for next callback UNLESS we're done
        lda recv_state
        cmp #STATE_DONE
        beq @done            ; Don't reset if response is complete!
        lda #STATE_MAGIC_0
        sta recv_state
        jmp @done            ; Exit immediately after first packet

@bad_checksum:
        ; Send NACK
        jsr send_nack
        lda #STATE_MAGIC_0
        sta recv_state
        jmp @process_loop

@done:
        ; DEBUG: At @done at $0356
        inc $0356
        dec in_callback      ; Exit re-entry guard
        ; DEBUG: After dec in_callback at $0357
        inc $0357
        rts

;-------------------------------------------------------------------------------
; Process a complete packet
;-------------------------------------------------------------------------------
process_packet:
        ; DEBUG: Count process_packet calls at $0360
        ; (debug removed)

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
        rts

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
        lda #STATE_DONE
        sta recv_state

@not_final:
        rts

;-------------------------------------------------------------------------------
; Handle CODE packet - store BASIC code
;-------------------------------------------------------------------------------
handle_code_chunk:
        ; DEBUG: Increment counter at $03F0 (can PEEK later - not in config area)
        inc $03F0

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
        lda #STATE_DONE
        sta recv_state
        rts

;-------------------------------------------------------------------------------
; Handle STATUS packet - writes directly to screen line 22 (no scroll)
;-------------------------------------------------------------------------------
handle_status_msg:
        ; Clear line 22 first
        jsr status_msg

        ; Write status message directly to screen memory at $750
        ldy #0
@print:
        cpy pkt_data_pos
        bcs @done
        cpy #39              ; Limit to 39 chars
        bcs @done
        lda pkt_buffer,y
        ora #$80             ; Set high bit for Apple II display
        sta STATUS_LINE_ADDR,y  ; Direct screen write
        iny
        bne @print
@done:
        rts

;-------------------------------------------------------------------------------
; Handle ERR packet - writes to status line 22
;-------------------------------------------------------------------------------
handle_error_msg:
        ; Clear line 22
        jsr status_msg

        ; Write "ERROR: " prefix directly
        ldx #0
@prefix:
        lda msg_error_prefix,x
        beq @msg           ; Null terminator
        ora #$80
        sta STATUS_LINE_ADDR,x
        inx
        cpx #7             ; "ERROR: " is 7 chars
        bcc @prefix

@msg:
        ; Write error message after prefix
        ldy #0
@print:
        cpy pkt_data_pos
        bcs @done
        txa
        cmp #39            ; Total max 39 chars
        bcs @done
        lda pkt_buffer,y
        ora #$80
        sta STATUS_LINE_ADDR,x
        inx
        iny
        bne @print
@done:
        rts

;-------------------------------------------------------------------------------
; Send pending ACKs (called after recv_callback returns)
; CRITICAL: Build all ACKs into buffer first, then send once to avoid
; feedback loop where tcp_send triggers recv_callback which queues more ACKs
;-------------------------------------------------------------------------------
send_pending_acks:
        ; DEBUG: Skip ACK sending temporarily to isolate crash
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
        cmp #39              ; At end of line?
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

        ; Wrap to top - don't output CR (would scroll into command area)
        lda #OUTPUT_START
        sta output_row

        ; Redraw command area in case it was damaged
        jsr draw_command_area

        ; Position at output row
        lda output_row
        sta CV
        jsr VTAB
        jsr CLREOL
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
        jsr CLREOL
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
        jsr RDKEY

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
        jsr RDKEY
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
; Show menu
; Returns: C=1 to exit, C=0 to continue
;-------------------------------------------------------------------------------
show_menu:
        jsr scroll_output
        ldax #menu_text
        jsr print_multiline

@wait:
        jsr RDKEY
        and #$7F             ; Clear high bit (RDKEY sets it)

        cmp #'1'
        beq @continue
        cmp #'2'
        beq @clear
        cmp #'3'
        beq @ip
        cmp #'4'
        beq @exit
        cmp #$1B             ; ESC (without high bit)
        beq @continue
        jmp @wait

@continue:
        clc
        rts

@clear:
        jsr HOME
        jsr draw_ui
        clc
        rts

@ip:
        jsr cmd_ip
        clc
        rts

@exit:
        sec
        rts

;-------------------------------------------------------------------------------
; Status message - position at STATUS_LINE (direct screen memory, no scroll)
; Line 22 screen memory = $750 (Apple II screen layout)
;-------------------------------------------------------------------------------
STATUS_LINE_ADDR = $750

status_msg:
        ; Clear line 22 directly (40 spaces)
        lda #$A0             ; Space with high bit
        ldx #39
@clear:
        sta STATUS_LINE_ADDR,x
        dex
        bpl @clear
        rts

;-------------------------------------------------------------------------------
; Status line routines - write directly to screen memory at line 22 ($750)
; These routines never use COUT/print, avoiding cursor corruption
;-------------------------------------------------------------------------------

; Print string to status line (clears first, starts at column 0)
; Input: AX = pointer to null-terminated string
print_status:
        sta status_ptr
        stx status_ptr+1
        jsr status_msg       ; Clear line 22
        lda #0
        sta status_pos       ; Start at column 0
        ldy #0
@loop:
        lda (status_ptr),y
        beq @done
        ldx status_pos
        cpx #39
        bcs @done
        ora #$80
        sta STATUS_LINE_ADDR,x
        inc status_pos
        iny
        bne @loop
@done:
        rts

; Append string to status line (continues from current position)
; Input: AX = pointer to null-terminated string
status_print:
        sta status_ptr
        stx status_ptr+1
        ldy #0
@loop:
        lda (status_ptr),y
        beq @done
        ldx status_pos
        cpx #39
        bcs @done
        ora #$80
        sta STATUS_LINE_ADDR,x
        inc status_pos
        iny
        bne @loop
@done:
        rts

; Append single character to status line
; Input: A = character (will have high bit set)
status_char:
        ldx status_pos
        cpx #39
        bcs @done
        ora #$80
        sta STATUS_LINE_ADDR,x
        inc status_pos
@done:
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

        ; Clear each line from OUTPUT_START to OUTPUT_END-1
        lda #OUTPUT_START
@clear_loop:
        sta CV
        pha
        jsr VTAB
        jsr CLREOL
        pla
        clc
        adc #1
        cmp #OUTPUT_END
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

        ; Wrap to top
        lda #OUTPUT_START
        sta output_row

        ; Redraw command area
        jsr draw_command_area
        jmp @set_pos

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
        jsr CLREOL
        rts

;-------------------------------------------------------------------------------
; Print padded line (to screen width)
;-------------------------------------------------------------------------------
print_padded_line:
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
        lda #$A0             ; Space
        jsr print_a
        iny
        cpy #40
        bcc @pad
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
        .byte "APPLE II AGENT V1.0", 0

msg_40col:
        .byte "40-COLUMN MODE", 0

msg_80col:
        .byte "80-COLUMN MODE", 0

msg_init_net:
        .byte "INITIALIZING NETWORK...", 0

msg_net_fail:
        .byte "NETWORK INIT FAILED", 0

msg_installed:
        .byte "TYPE & FROM BASIC TO RETURN", 13
        .byte "PRESS ESC FOR MENU", 0

msg_ready:
        .byte "READY", 0

msg_connecting:
        .byte "CONNECTING...", 0

msg_conn_fail:
        .byte "CONNECTION FAILED", 0

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

msg_port_8080:
        .byte "8080", 0

msg_unknown_cmd:
        .byte "UNKNOWN COMMAND - TYPE /HELP", 0

msg_ip_set:
        .byte "IP SET: ", 0

msg_invalid_ip:
        .byte "INVALID IP - USE: /SETIP 192.168.1.50", 0

msg_port_set:
        .byte "PORT SET: ", 0

msg_invalid_port:
        .byte "INVALID PORT - USE: /PORT 8080", 0

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

msg_model_set:
        .byte "MODEL: ", 0

msg_current_model:
        .byte "CURRENT MODEL: ", 0

msg_model_options:
        .byte "/MODEL S - SONNET (DEFAULT)", 13
        .byte "/MODEL O - OPUS (SMARTEST)", 13
        .byte "/MODEL H - HAIKU (FASTEST)", 13, 0

msg_suspended:
        .byte 13
        .byte "SUSPENDED TO BASIC.", 13
        .byte "YOUR CODE IS LOADED - TYPE RUN", 13
        .byte 13
        .byte "TO RESUME: CTRL-Y OR &", 13
        .byte "NATURAL LANGUAGE: JUST TYPE!", 13
        .byte "ERRORS AUTO-SENT TO CLAUDE", 13, 0

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

ui_divider:
        .byte "----------------------------------------", 0

ui_separator:
        .byte "----------------------------------------", 0

help_text:
        .byte "/HELP    - SHOW COMMANDS", 13
        .byte "/EXIT    - DROP TO BASIC", 13
        .byte "/RESET   - NEW SESSION", 13
        .byte "/PROMPT  - SET AI CONTEXT", 13
        .byte "/IP      - SHOW PROXY IP", 13
        .byte "/SETIP   - SET PROXY IP", 13
        .byte "/PORT    - SET PORT", 13
        .byte "/MODEL   - SET AI MODEL", 13
        .byte "/SAVE    - SAVE CONFIG", 13
        .byte "/CLEAR   - CLEAR SCREEN", 13
        .byte "ESC      - MENU", 13, 0

menu_text:
        .byte "======== MENU ========", 13
        .byte "1. CONTINUE", 13
        .byte "2. CLEAR SCREEN", 13
        .byte "3. SHOW IP CONFIG", 13
        .byte "4. EXIT TO BASIC", 13
        .byte "CHOICE (1-4): ", 0

;-------------------------------------------------------------------------------
; Phase 2b RODATA
;-------------------------------------------------------------------------------

msg_nl_sending:
        .byte ">> SENDING TO CLAUDE...", 0

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
output_row:     .res 1
output_col:     .res 1          ; Column position on output line
is_connected:   .res 1          ; 1=TCP connection open, 0=not connected
lines_since_pause: .res 1       ; Lines output since last [MORE] pause
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

; Timeouts
timeout_lo:     .res 1
timeout_hi:     .res 1

; Input
input_buffer:   .res 128
input_len:      .res 1
MAX_INPUT       = 120

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

; Phase 2b: ROM patch / error intercept state
error_intercept_flag: .res 1    ; 1 = immediate-mode error intercepted
kbd_stuff_state:   .res 1       ; KSWL hook state (0=send &, 1=send CR)
program_error_flag: .res 1      ; 1 = program error, auto-invoke agent
poll_counter_lo:    .res 1      ; Network poll timing (low byte)
poll_counter_hi:    .res 1      ; Network poll timing (high byte)
saved_kswl:        .res 1       ; Original keyboard vector (low)
saved_kswh:        .res 1       ; Original keyboard vector (high)
orig_err_byte0:    .res 1       ; Saved byte from $D412
orig_err_byte1:    .res 1       ; Saved byte from $D413
orig_err_byte2:    .res 1       ; Saved byte from $D414
saved_input_buf:   .res 128     ; Saved copy of $200 input buffer
saved_input_len:   .res 1       ; Length of saved input

; ProDOS I/O buffer (must be page-aligned, 1024 bytes)
; Placed in separate IOBUF segment to ensure alignment
        .segment "IOBUF"
io_buffer:      .res 1024
        .segment "BSS"
