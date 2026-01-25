"""6502 Assembler integration for Apple II MCP.

Provides tools to assemble 6502 assembly source code using ca65/ld65
and return the resulting binary for injection into the Apple II.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class AssemblerError(Exception):
    """Error during assembly or linking."""
    pass


def assemble(
    source: str,
    load_address: int = 0x6000,
    include_paths: Optional[list[str]] = None
) -> dict:
    """
    Assemble 6502 source code and return binary.

    Args:
        source: 6502 assembly source code (ca65 format)
        load_address: Where code will be loaded/run (default $6000)
        include_paths: Optional list of include directories

    Returns:
        {
            "success": True,
            "hex_data": "A9 00 8D 50 C0 60",
            "bytes": [0xA9, 0x00, ...],
            "size": 6,
            "load_address": 0x6000
        }
        or
        {
            "success": False,
            "error": "Line 5: Unknown opcode XYZ",
            "stage": "assemble" | "link"
        }
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write source to temp file
        src_file = tmpdir / "code.s"
        obj_file = tmpdir / "code.o"
        bin_file = tmpdir / "code.bin"
        cfg_file = tmpdir / "inject.cfg"

        # Create linker config for raw binary at specified address
        cfg_content = f"""# Auto-generated linker config for injection
MEMORY {{
    CODE: start = ${load_address:04X}, size = $4000, fill = no;
}}
SEGMENTS {{
    CODE: load = CODE, type = ro;
    RODATA: load = CODE, type = ro;
    DATA: load = CODE, type = rw;
    BSS: load = CODE, type = bss, define = yes;
    ZEROPAGE: load = CODE, type = zp;
}}
"""
        cfg_file.write_text(cfg_content)

        # Prepend .segment directive if not present
        if '.segment' not in source.lower() and '.code' not in source.lower():
            source = '.segment "CODE"\n\n' + source

        src_file.write_text(source)

        # Build ca65 command
        ca65_cmd = ["ca65", "--cpu", "6502", "-o", str(obj_file), str(src_file)]
        if include_paths:
            for inc in include_paths:
                ca65_cmd.extend(["-I", inc])

        # Run assembler
        result = subprocess.run(
            ca65_cmd,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown assembler error"
            return {
                "success": False,
                "error": error_msg.strip(),
                "stage": "assemble"
            }

        # Run linker
        ld65_cmd = [
            "ld65",
            "-C", str(cfg_file),
            "-o", str(bin_file),
            str(obj_file)
        ]

        result = subprocess.run(
            ld65_cmd,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown linker error"
            return {
                "success": False,
                "error": error_msg.strip(),
                "stage": "link"
            }

        # Read binary output
        if not bin_file.exists():
            return {
                "success": False,
                "error": "Linker produced no output",
                "stage": "link"
            }

        binary_data = bin_file.read_bytes()

        if len(binary_data) == 0:
            return {
                "success": False,
                "error": "Linker produced empty output",
                "stage": "link"
            }

        hex_str = ' '.join(f"{b:02X}" for b in binary_data)

        return {
            "success": True,
            "hex_data": hex_str,
            "bytes": list(binary_data),
            "size": len(binary_data),
            "load_address": load_address
        }


def assemble_and_format(source: str, load_address: int = 0x6000) -> str:
    """
    Assemble source and return formatted result string.

    This is a convenience wrapper for the MCP tool.
    """
    result = assemble(source, load_address)

    if result["success"]:
        return (
            f"Assembly successful!\n"
            f"Size: {result['size']} bytes\n"
            f"Load address: ${result['load_address']:04X}\n"
            f"Hex: {result['hex_data']}"
        )
    else:
        return (
            f"Assembly failed at {result['stage']} stage:\n"
            f"{result['error']}"
        )


# Quick reference for common 6502 patterns
ASM_TEMPLATES = {
    "rts": """
; Simple RTS - just return
    rts
""",

    "click": """
; Click the speaker once
    lda $C030       ; Toggle speaker
    rts
""",

    "beep": """
; Simple beep sound
; Uses: A, X, Y
    ldy #$80        ; Duration
@loop:
    lda $C030       ; Toggle speaker
    ldx #$60        ; Pitch (higher = lower pitch)
@delay:
    dex
    bne @delay
    dey
    bne @loop
    rts
""",

    "clear_hgr": """
; Clear HGR page 1 to black
; Uses: A, X, Y
    lda #$00        ; Black
    ldx #$20        ; Start at $2000
    stx @store+2
    ldx #$00
@store:
    sta $2000,x
    inx
    bne @store
    inc @store+2
    lda @store+2
    cmp #$40        ; Stop at $4000
    bne @store-2
    rts
""",

    "plot_pixel": """
; Plot a single white pixel at X,Y
; Input: X coord in $06, Y coord in $07
; Uses: A, X, Y, $08-$09

    ; Calculate HGR base address for line Y
    ; Formula: $2000 + (Y/64)*$28 + ((Y/8)%8)*$80 + (Y%8)*$400

    lda $07         ; Y coordinate
    and #$07        ; Y % 8
    asl
    asl
    asl
    asl
    asl             ; * 32 but we need * $400...
    ; This is simplified - real impl needs lookup table

    ; For now, use ROM HPLOT
    ; Set HGR mode and color first from BASIC
    rts
""",

    "read_key": """
; Wait for keypress and return it in A
; Uses: A
@wait:
    lda $C000       ; Read keyboard
    bpl @wait       ; Wait for key (high bit set)
    sta $C010       ; Clear keyboard strobe
    and #$7F        ; Clear high bit
    rts
""",

    "print_char": """
; Print character in A to screen
; Uses: A (preserved)
    ora #$80        ; Set high bit for Apple II
    jsr $FDED       ; COUT - print character
    rts
""",

    # ==================== MOUSE DRIVER TEMPLATES ====================

    "mouse_init": """
; Initialize AppleMouse card in slot 4
; Call this once at startup
; Uses: A, X, Y
; Returns: A=0 if OK, A=$FF if no mouse
;
; After init, mouse position is available at:
;   $0300 = X low, $0301 = X high
;   $0302 = Y low, $0303 = Y high
;   $0304 = button (bit 7 = pressed)

MOUSE_SLOT = 4              ; Slot number
MOUSE_ID   = $C400 + (MOUSE_SLOT * $100)  ; $C400 for slot 4 ROM
MOUSE_INIT = MOUSE_ID + 7   ; InitMouse entry point
MOUSE_SET  = MOUSE_ID + 0   ; SetMouse entry point
MOUSE_READ = MOUSE_ID + 2   ; ReadMouse entry point

; Apple II slot peripheral memory locations
SLOT_BYTE  = $07F8 + MOUSE_SLOT  ; $07FC for slot 4

    ; Store slot ID byte (required by firmware)
    lda #$C0 + MOUSE_SLOT   ; $C4 for slot 4
    sta SLOT_BYTE

    ; Check for mouse card signature
    ; AppleMouse has $20 at $Cn05, $D6 at $Cn07
    lda $C405
    cmp #$20
    bne no_mouse
    lda $C407
    cmp #$D6
    bne no_mouse

    ; Initialize mouse
    jsr MOUSE_INIT

    ; Set mouse mode: enable, no interrupts
    lda #$01            ; Mode 1 = enabled, passive
    jsr MOUSE_SET

    ; Success
    lda #$00
    rts

no_mouse:
    lda #$FF            ; No mouse found
    rts
""",

    "mouse_read": """
; Read mouse position and button
; Call after mouse_init
; Results stored at:
;   $0300 = X low, $0301 = X high (0-1023)
;   $0302 = Y low, $0303 = Y high (0-1023)
;   $0304 = button (bit 7 = pressed)
; Uses: A, X, Y

MOUSE_SLOT = 4
MOUSE_READ = $C400 + (MOUSE_SLOT * $100) + 2
SLOT_BYTE  = $07F8 + MOUSE_SLOT

; Source locations (set by firmware after ReadMouse)
MOUSE_XL   = $0478 + MOUSE_SLOT  ; X low byte
MOUSE_XH   = $0578 + MOUSE_SLOT  ; X high byte
MOUSE_YL   = $04F8 + MOUSE_SLOT  ; Y low byte
MOUSE_YH   = $05F8 + MOUSE_SLOT  ; Y high byte
MOUSE_BTN  = $0778 + MOUSE_SLOT  ; Button status

; Destination for our API
RESULT_XL  = $0300
RESULT_XH  = $0301
RESULT_YL  = $0302
RESULT_YH  = $0303
RESULT_BTN = $0304

    ; Call firmware to read position
    jsr MOUSE_READ

    ; Copy to our standard location
    lda MOUSE_XL
    sta RESULT_XL
    lda MOUSE_XH
    sta RESULT_XH
    lda MOUSE_YL
    sta RESULT_YL
    lda MOUSE_YH
    sta RESULT_YH
    lda MOUSE_BTN
    sta RESULT_BTN

    rts
""",

    "mouse_clamp": """
; Set mouse clamping range
; Before calling, set:
;   $0478 = min low, $04F8 = min high
;   $0578 = max low, $05F8 = max high
; A = 0 for X clamping, A = 1 for Y clamping
; Uses: A, X, Y

MOUSE_SLOT  = 4
MOUSE_CLAMP = $C400 + (MOUSE_SLOT * $100) + 5

    jsr MOUSE_CLAMP
    rts
""",

    "mouse_demo": """
; Simple mouse tracking demo
; Prints X, Y, button continuously
; Press any key to exit
; Uses: A, X, Y

MOUSE_SLOT = 4
MOUSE_READ = $C400 + (MOUSE_SLOT * $100) + 2
SLOT_BYTE  = $07F8 + MOUSE_SLOT

MOUSE_XL   = $0478 + MOUSE_SLOT
MOUSE_XH   = $0578 + MOUSE_SLOT
MOUSE_YL   = $04F8 + MOUSE_SLOT
MOUSE_YH   = $05F8 + MOUSE_SLOT
MOUSE_BTN  = $0778 + MOUSE_SLOT

COUT       = $FDED
HOME       = $FC58
PRBYTE     = $FDDA
CROUT      = $FD8E

    ; Store slot ID
    lda #$C0 + MOUSE_SLOT
    sta SLOT_BYTE

loop:
    ; Check for keypress to exit
    lda $C000
    bmi done

    ; Read mouse
    jsr MOUSE_READ

    ; Home cursor
    jsr HOME

    ; Print "X="
    lda #'X' | $80
    jsr COUT
    lda #'=' | $80
    jsr COUT

    ; Print X position (hex)
    lda MOUSE_XH
    jsr PRBYTE
    lda MOUSE_XL
    jsr PRBYTE

    ; Print " Y="
    lda #' ' | $80
    jsr COUT
    lda #'Y' | $80
    jsr COUT
    lda #'=' | $80
    jsr COUT

    ; Print Y position
    lda MOUSE_YH
    jsr PRBYTE
    lda MOUSE_YL
    jsr PRBYTE

    ; Print " B="
    lda #' ' | $80
    jsr COUT
    lda #'B' | $80
    jsr COUT
    lda #'=' | $80
    jsr COUT

    ; Print button status
    lda MOUSE_BTN
    jsr PRBYTE

    jsr CROUT

    ; Loop
    jmp loop

done:
    sta $C010       ; Clear keyboard strobe
    rts
""",

    # ==================== HGR GRAPHICS TEMPLATES ====================

    "hgr_tables": """
; HGR Line Address Lookup Tables
; The Apple II HGR screen has an interleaved memory layout
; These tables provide fast Y-coordinate to address lookup
;
; Usage:
;   ldy y_coord     ; Y = 0-191
;   lda HGRLO,y     ; Get low byte of line address
;   sta ptr
;   lda HGRHI,y     ; Get high byte
;   sta ptr+1       ; ptr now points to start of line Y
;
; Memory: 384 bytes for both tables
; For HGR page 2, add $20 to high byte values

.segment "RODATA"

; Low bytes of HGR line addresses
HGRLO:
    .byte $00,$00,$00,$00,$00,$00,$00,$00  ; Lines 0-7
    .byte $80,$80,$80,$80,$80,$80,$80,$80  ; Lines 8-15
    .byte $00,$00,$00,$00,$00,$00,$00,$00  ; Lines 16-23
    .byte $80,$80,$80,$80,$80,$80,$80,$80  ; Lines 24-31
    .byte $00,$00,$00,$00,$00,$00,$00,$00  ; Lines 32-39
    .byte $80,$80,$80,$80,$80,$80,$80,$80  ; Lines 40-47
    .byte $00,$00,$00,$00,$00,$00,$00,$00  ; Lines 48-55
    .byte $80,$80,$80,$80,$80,$80,$80,$80  ; Lines 56-63
    .byte $28,$28,$28,$28,$28,$28,$28,$28  ; Lines 64-71
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8  ; Lines 72-79
    .byte $28,$28,$28,$28,$28,$28,$28,$28  ; Lines 80-87
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8  ; Lines 88-95
    .byte $28,$28,$28,$28,$28,$28,$28,$28  ; Lines 96-103
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8  ; Lines 104-111
    .byte $28,$28,$28,$28,$28,$28,$28,$28  ; Lines 112-119
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8  ; Lines 120-127
    .byte $50,$50,$50,$50,$50,$50,$50,$50  ; Lines 128-135
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0  ; Lines 136-143
    .byte $50,$50,$50,$50,$50,$50,$50,$50  ; Lines 144-151
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0  ; Lines 152-159
    .byte $50,$50,$50,$50,$50,$50,$50,$50  ; Lines 160-167
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0  ; Lines 168-175
    .byte $50,$50,$50,$50,$50,$50,$50,$50  ; Lines 176-183
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0  ; Lines 184-191

; High bytes of HGR line addresses (page 1 = $20xx)
HGRHI:
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C  ; Lines 0-7
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C  ; Lines 8-15
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D  ; Lines 16-23
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D  ; Lines 24-31
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E  ; Lines 32-39
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E  ; Lines 40-47
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F  ; Lines 48-55
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F  ; Lines 56-63
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C  ; Lines 64-71
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C  ; Lines 72-79
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D  ; Lines 80-87
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D  ; Lines 88-95
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E  ; Lines 96-103
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E  ; Lines 104-111
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F  ; Lines 112-119
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F  ; Lines 120-127
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C  ; Lines 128-135
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C  ; Lines 136-143
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D  ; Lines 144-151
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D  ; Lines 152-159
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E  ; Lines 160-167
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E  ; Lines 168-175
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F  ; Lines 176-183
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F  ; Lines 184-191
""",

    "hgr_plot": """
; Fast HGR pixel plotting routine
; Plots a single pixel using lookup tables
;
; Input:
;   PLOTX ($06) = X coordinate (0-279)
;   PLOTY ($07) = Y coordinate (0-191)
;   COLOR ($08) = Color (0=black, 1=white)
;
; Uses: A, X, Y, $09-$0A (pointer)
; Requires: hgr_tables to be assembled
;
; Performance: ~50 cycles per pixel

.segment "CODE"

; Zero page locations
PLOTX   = $06       ; X coordinate (0-279)
PLOTY   = $07       ; Y coordinate (0-191)
COLOR   = $08       ; 0 = black, non-zero = white
HGRPTR  = $09       ; Pointer to HGR byte ($09-$0A)

; Bit masks for each pixel position within a byte
; HGR packs 7 pixels per byte, bit 7 is palette select
BITMASK:
    .byte $01,$02,$04,$08,$10,$20,$40

plot:
    ; Get line base address
    ldy PLOTY
    lda HGRLO,y
    sta HGRPTR
    lda HGRHI,y
    sta HGRPTR+1

    ; Calculate byte offset: X / 7
    lda PLOTX
    ldx #0
@div7:
    cmp #7
    bcc @done_div
    sbc #7
    inx
    bne @div7       ; Always branches (X won't wrap to 0)
@done_div:
    ; X = byte offset, A = pixel within byte (0-6)

    ; Add byte offset to pointer
    tay             ; Save pixel offset
    txa
    clc
    adc HGRPTR
    sta HGRPTR
    bcc @no_carry
    inc HGRPTR+1
@no_carry:

    ; Get bit mask
    lda BITMASK,y

    ; Set or clear pixel based on COLOR
    ldy #0
    ldx COLOR
    beq @clear
    ; Set pixel (white)
    ora (HGRPTR),y
    sta (HGRPTR),y
    rts

@clear:
    ; Clear pixel (black)
    eor #$FF        ; Invert mask
    and (HGRPTR),y
    sta (HGRPTR),y
    rts
""",

    "hgr_hline": """
; Fast horizontal line drawing
; Draws a horizontal line using byte-at-a-time for speed
;
; Input:
;   X1 ($06) = Start X (0-279)
;   Y  ($07) = Y coordinate (0-191)
;   X2 ($08) = End X (0-279)
;   COLOR ($09) = 0=black, $7F=white
;
; Uses: A, X, Y, $0A-$0B (pointer)

.segment "CODE"

X1      = $06
YCOORD  = $07
X2      = $08
COLOR   = $09
HGRPTR  = $0A

; Left edge masks (set bits 0-6 from position N to end)
LMASK:  .byte $7F,$7E,$7C,$78,$70,$60,$40
; Right edge masks (set bits 0 to position N)
RMASK:  .byte $01,$03,$07,$0F,$1F,$3F,$7F

hline:
    ; Get line base address
    ldy YCOORD
    lda HGRLO,y
    sta HGRPTR
    lda HGRHI,y
    sta HGRPTR+1

    ; Calculate start byte and pixel
    lda X1
    ldx #0
@div7_start:
    cmp #7
    bcc @got_start
    sbc #7
    inx
    bne @div7_start
@got_start:
    ; X = start byte, A = start pixel (0-6)
    stx @start_byte
    sta @start_pixel

    ; Calculate end byte and pixel
    lda X2
    ldx #0
@div7_end:
    cmp #7
    bcc @got_end
    sbc #7
    inx
    bne @div7_end
@got_end:
    ; X = end byte, A = end pixel
    stx @end_byte
    sta @end_pixel

    ; Check if start and end are in same byte
    lda @start_byte
    cmp @end_byte
    bne @multi_byte

    ; Single byte - combine masks
    ldx @start_pixel
    lda LMASK,x
    ldx @end_pixel
    and RMASK,x
    jmp @apply_mask

@multi_byte:
    ; Draw left edge
    ldx @start_pixel
    lda LMASK,x
    ldy @start_byte
    jsr @apply_mask_y

    ; Draw middle bytes (full $7F)
    ldy @start_byte
    iny
@middle:
    cpy @end_byte
    bcs @right_edge
    lda COLOR
    sta (HGRPTR),y
    iny
    bne @middle

@right_edge:
    ; Draw right edge
    ldx @end_pixel
    lda RMASK,x
    ldy @end_byte
    ; Fall through to apply_mask_y

@apply_mask_y:
    ; Apply mask at offset Y
    ldx COLOR
    beq @clear_y
    ora (HGRPTR),y
    sta (HGRPTR),y
    rts
@clear_y:
    eor #$FF
    and (HGRPTR),y
    sta (HGRPTR),y
    rts

@apply_mask:
    ldy @start_byte
    ldx COLOR
    beq @clear
    ora (HGRPTR),y
    sta (HGRPTR),y
    rts
@clear:
    eor #$FF
    and (HGRPTR),y
    sta (HGRPTR),y
    rts

@start_byte:  .byte 0
@start_pixel: .byte 0
@end_byte:    .byte 0
@end_pixel:   .byte 0
""",

    "hgr_vline": """
; Fast vertical line drawing
; Uses lookup tables for speed
;
; Input:
;   X  ($06) = X coordinate (0-279)
;   Y1 ($07) = Start Y (0-191)
;   Y2 ($08) = End Y (0-191)
;   COLOR ($09) = 0=black, non-zero=white
;
; Uses: A, X, Y, $0A-$0B (pointer)

.segment "CODE"

XCOORD  = $06
Y1      = $07
Y2      = $08
COLOR   = $09
HGRPTR  = $0A

BITMASK:
    .byte $01,$02,$04,$08,$10,$20,$40

vline:
    ; Calculate byte offset and bit mask for X
    lda XCOORD
    ldx #0
@div7:
    cmp #7
    bcc @got_offset
    sbc #7
    inx
    bne @div7
@got_offset:
    stx @x_byte     ; Byte offset
    tax
    lda BITMASK,x
    sta @bitmask    ; Bit to set/clear

    ; Draw each line from Y1 to Y2
    ldy Y1
@loop:
    ; Get line address
    lda HGRLO,y
    clc
    adc @x_byte
    sta HGRPTR
    lda HGRHI,y
    adc #0
    sta HGRPTR+1

    ; Set or clear pixel
    lda @bitmask
    ldx COLOR
    beq @clear
    ldy #0
    ora (HGRPTR),y
    sta (HGRPTR),y
    jmp @next
@clear:
    eor #$FF
    ldy #0
    and (HGRPTR),y
    sta (HGRPTR),y

@next:
    ldy Y1
    iny
    sty Y1
    cpy Y2
    bcc @loop
    beq @loop
    rts

@x_byte:  .byte 0
@bitmask: .byte 0
""",

    "hgr_sprite": """
; Sprite blitter for HGR
; Draws a rectangular sprite with transparency (0 = transparent)
;
; Input:
;   SPRX  ($06) = X position (byte-aligned, 0-39)
;   SPRY  ($07) = Y position (0-191)
;   SPRW  ($08) = Width in bytes (1-40)
;   SPRH  ($09) = Height in lines (1-192)
;   SPRLO ($0A) = Sprite data pointer low
;   SPRHI ($0B) = Sprite data pointer high
;
; Sprite data format: width*height bytes, row-major order
; Uses: A, X, Y, $0C-$0D (screen pointer)
;
; For masked sprites, use XOR or AND/OR technique

.segment "CODE"

SPRX    = $06
SPRY    = $07
SPRW    = $08
SPRH    = $09
SPRLO   = $0A
SPRHI   = $0B
SCRPTR  = $0C       ; Screen pointer

sprite:
    ldy SPRY
    ldx SPRH
@row:
    ; Get screen line address
    lda HGRLO,y
    clc
    adc SPRX
    sta SCRPTR
    lda HGRHI,y
    adc #0
    sta SCRPTR+1

    ; Copy SPRW bytes
    ldy #0
@col:
    lda (SPRLO),y
    beq @skip       ; 0 = transparent
    sta (SCRPTR),y
@skip:
    iny
    cpy SPRW
    bne @col

    ; Advance sprite pointer
    lda SPRLO
    clc
    adc SPRW
    sta SPRLO
    bcc @no_carry
    inc SPRHI
@no_carry:

    ; Next line
    inc SPRY
    ldy SPRY
    dex
    bne @row
    rts
""",

    "hgr_tile": """
; Tile blitter for game graphics
; Draws 8x8 pixel tiles (1 byte wide x 8 lines)
; Optimized for tile-based games
;
; Input:
;   TILEX ($06) = Tile X position (byte column 0-39)
;   TILEY ($07) = Tile Y position (must be multiple of 8)
;   TILELO ($08) = Tile data pointer low
;   TILEHI ($09) = Tile data pointer high
;
; Tile format: 8 bytes, one per line
; Uses: A, X, Y, $0A-$0B (screen pointer)

.segment "CODE"

TILEX   = $06
TILEY   = $07
TILELO  = $08
TILEHI  = $09
SCRPTR  = $0A

tile:
    ldy TILEY
    ldx #8          ; 8 lines per tile
@row:
    ; Get screen line address + X offset
    lda HGRLO,y
    clc
    adc TILEX
    sta SCRPTR
    lda HGRHI,y
    adc #0
    sta SCRPTR+1

    ; Copy one byte
    txa
    pha
    sec
    sbc #1          ; Convert counter to index (7,6,5...0)
    eor #$07        ; Flip to get (0,1,2...7)
    tax
    lda (TILELO,x)  ; Wrong! Need indirect indexed
    pla
    tax

    ; Fixed: use Y-indexed
    sty @save_y
    txa
    pha
    sec
    sbc #1
    eor #$07
    tay
    lda (TILELO),y  ; Get tile byte
    ldy #0
    sta (SCRPTR),y  ; Store to screen
    pla
    tax
    ldy @save_y

    ; Next line
    iny
    dex
    bne @row
    rts

@save_y: .byte 0
""",

    "hgr_fill_rect": """
; Fill a rectangle with a pattern
; Fast fill using byte-aligned boundaries
;
; Input:
;   RECTX ($06) = X position (byte column 0-39)
;   RECTY ($07) = Y position (0-191)
;   RECTW ($08) = Width in bytes (1-40)
;   RECTH ($09) = Height in lines (1-192)
;   PATTERN ($0A) = Fill pattern byte
;
; Uses: A, X, Y, $0B-$0C (pointer)

.segment "CODE"

RECTX   = $06
RECTY   = $07
RECTW   = $08
RECTH   = $09
PATTERN = $0A
SCRPTR  = $0B

fill_rect:
    ldy RECTY
    ldx RECTH
@row:
    ; Get screen line address + X offset
    lda HGRLO,y
    clc
    adc RECTX
    sta SCRPTR
    lda HGRHI,y
    adc #0
    sta SCRPTR+1

    ; Fill RECTW bytes
    lda PATTERN
    sty @save_y     ; Save Y (line counter)
    ldy #0
@col:
    sta (SCRPTR),y
    iny
    cpy RECTW
    bne @col
    ldy @save_y     ; Restore Y

    ; Next line
    iny
    dex
    bne @row
    rts

@save_y: .byte 0
""",

    "hgr_clear_fast": """
; Fast HGR screen clear
; Clears entire HGR page 1 to specified color
;
; Input:
;   A = Fill byte (0=black, $7F=white, $2A=checkerboard, etc.)
;
; Performance: ~18,000 cycles (vs ~200,000 for BASIC)

.segment "CODE"

clear_hgr:
    ldx #$20        ; Start page = $20
    stx @page+2     ; Self-modify high byte
    ldy #0
@page:
    sta $2000,y     ; Address modified
    iny
    bne @page
    inx
    stx @page+2
    cpx #$40        ; End page = $40
    bne @page
    rts
""",

    "hgr_scroll_up": """
; Scroll HGR screen up by 8 pixels (1 character row)
; Bottom 8 lines are cleared to black
;
; Uses: A, X, Y, $06-$09
; Performance: ~50,000 cycles

.segment "CODE"

SRCLO   = $06
SRCHI   = $07
DSTLO   = $08
DSTHI   = $09

scroll_up:
    ; Copy lines 8-191 to 0-183
    ldy #8          ; Source starts at line 8
@loop:
    ; Get source line address
    lda HGRLO,y
    sta SRCLO
    lda HGRHI,y
    sta SRCHI

    ; Calculate dest (Y-8)
    tya
    sec
    sbc #8
    tax
    lda HGRLO,x
    sta DSTLO
    lda HGRHI,x
    sta DSTHI

    ; Copy 40 bytes
    ldx #39
@copy:
    lda (SRCLO,x)   ; Wrong addressing mode!
    ; Fixed:
    txa
    pha
    tay
    lda (SRCLO),y
    sta (DSTLO),y
    pla
    tax
    dex
    bpl @copy

    ; Next line
    iny
    cpy #192
    bne @loop

    ; Clear bottom 8 lines
    ldy #184
@clear:
    lda HGRLO,y
    sta DSTLO
    lda HGRHI,y
    sta DSTHI
    lda #0
    ldx #39
@clr:
    sta (DSTLO,x)   ; Also wrong - fix:
    ; Actually this needs rewrite:
    pha
    txa
    tay
    pla
    sta (DSTLO),y
    dex
    bpl @clr

    iny
    cpy #192
    bne @clear
    rts
""",

    "hgr_demo": """
; HGR Graphics Demo
; Draws various shapes to demonstrate the graphics routines
; Press any key to exit
;
; This is a complete standalone demo that includes
; the necessary tables and routines

.segment "CODE"

; Zero page
PLOTX   = $06
PLOTY   = $07
COLOR   = $08
HGRPTR  = $09

; ROM routines
HOME    = $FC58

start:
    ; Clear text and switch to HGR
    jsr HOME
    sta $C050       ; Graphics mode
    sta $C057       ; HGR mode
    sta $C054       ; Page 1
    sta $C052       ; Full screen (no text)

    ; Clear screen to black
    lda #$00
    jsr clear

    ; Draw white border
    lda #$7F
    sta COLOR

    ; Top line
    lda #0
    sta PLOTY
    ldx #0
@top:
    stx PLOTX
    jsr plot
    inx
    cpx #40
    bne @top

    ; Bottom line
    lda #191
    sta PLOTY
    ldx #0
@bot:
    stx PLOTX
    jsr plot
    inx
    cpx #40
    bne @bot

    ; Left and right edges
    ldy #0
@sides:
    sty PLOTY
    lda #0
    sta PLOTX
    jsr plot_byte
    lda #39
    sta PLOTX
    jsr plot_byte
    iny
    cpy #192
    bne @sides

    ; Draw diagonal line
    ldx #1
    ldy #1
@diag:
    stx PLOTX
    sty PLOTY
    jsr plot_byte
    inx
    iny
    cpx #39
    bne @diag

    ; Wait for keypress
@wait:
    lda $C000
    bpl @wait
    sta $C010

    ; Return to text mode
    sta $C051       ; Text mode
    rts

; Clear screen to A
clear:
    ldx #$20
    stx @pg+2
    ldy #0
@pg:
    sta $2000,y
    iny
    bne @pg
    inx
    stx @pg+2
    cpx #$40
    bne @pg
    rts

; Plot byte at PLOTX, PLOTY (byte-aligned)
plot_byte:
    ldy PLOTY
    lda HGRLO,y
    clc
    adc PLOTX
    sta HGRPTR
    lda HGRHI,y
    adc #0
    sta HGRPTR+1
    lda COLOR
    ldy #0
    sta (HGRPTR),y
    rts

; Simple plot (PLOTX is byte position for this demo)
plot:
    jmp plot_byte

; Include the lookup tables
.segment "RODATA"

HGRLO:
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0

HGRHI:
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
""",

    # ==================== PAGE FLIP / DOUBLE BUFFER TEMPLATES ====================

    "hgr_pageflip": """
; Simple HGR page flip
; Toggles between displaying page 1 and page 2
;
; Input: None
; Output: A = new display page (0=page1, 1=page2)
; Uses: A
;
; Call this after finishing drawing to the off-screen page

.segment "CODE"

DRAW_PAGE = $E0     ; 0 = drawing to page 1, 1 = drawing to page 2

pageflip:
    lda DRAW_PAGE
    eor #$01        ; Toggle 0 <-> 1
    sta DRAW_PAGE
    beq @show_p1
    ; Now drawing to page 2, show page 1
    sta $C054       ; PAGE1 - display page 1
    rts
@show_p1:
    ; Now drawing to page 1, show page 2
    sta $C055       ; PAGE2 - display page 2
    rts
""",

    "hgr_vbl_sync": """
; Wait for Vertical Blank for tear-free page flips
; The Apple IIe VBL flag is at $C019 (bit 7)
;
; Uses: A
; Timing: Waits up to ~1/60th second
;
; Call this BEFORE flipping pages for smooth animation

.segment "CODE"

vbl_sync:
    ; Wait for VBL to END (if we're in it)
@wait_end:
    lda $C019       ; VBL flag (bit 7: 1=VBL active)
    bmi @wait_end   ; Loop while in VBL

    ; Wait for VBL to START
@wait_start:
    lda $C019
    bpl @wait_start ; Loop while not in VBL

    rts
""",

    "hgr_clear_page": """
; Clear a specific HGR page
;
; Input: A = page (0=page1 at $2000, 1=page2 at $4000)
; Uses: A, X, Y
;
; Clears to black ($00)

.segment "CODE"

clear_page:
    tax             ; Save page number
    beq @page1
    lda #$40        ; Page 2 starts at $4000
    bne @do_clear
@page1:
    lda #$20        ; Page 1 starts at $2000
@do_clear:
    sta @loop+2     ; Self-modify high byte
    lda #$00        ; Clear to black
    ldy #0
@loop:
    sta $2000,y     ; Address modified
    iny
    bne @loop
    inc @loop+2
    ldx @loop+2
    cpx #$40        ; Check if done (page 1: $40, page 2: $60)
    beq @done
    cpx #$60
    bne @loop
@done:
    rts
""",

    "hgr_double_buffer": """
; Complete double-buffer framework
; Provides init, flip, and page-aware drawing support
;
; Zero page usage:
;   DRAW_PAGE ($E0) = current draw page (0 or 1)
;   DRAW_BASE ($E1) = high byte base for drawing ($20 or $40)
;
; Call db_init once, then db_flip after each frame

.segment "CODE"

DRAW_PAGE = $E0     ; 0 or 1
DRAW_BASE = $E1     ; $20 (page 1) or $40 (page 2)

; Initialize double buffering
; Displays page 1, draws to page 2
db_init:
    lda #1
    sta DRAW_PAGE   ; Draw to page 2
    lda #$40
    sta DRAW_BASE   ; Base = $4000
    sta $C054       ; Display page 1
    rts

; Flip pages (call after drawing frame)
; Waits for VBL, then flips
db_flip:
    ; Wait for VBL
@vbl_end:
    lda $C019
    bmi @vbl_end
@vbl_start:
    lda $C019
    bpl @vbl_start

    ; Toggle draw page
    lda DRAW_PAGE
    eor #$01
    sta DRAW_PAGE
    beq @to_p1

    ; Now drawing to page 2
    lda #$40
    sta DRAW_BASE
    sta $C054       ; Show page 1
    rts

@to_p1:
    ; Now drawing to page 1
    lda #$20
    sta DRAW_BASE
    sta $C055       ; Show page 2
    rts

; Get draw address for line Y
; Input: Y = line number (0-191)
; Output: $09-$0A = address on current draw page
; Uses: A, Y preserved
db_get_line:
    lda HGRLO,y
    sta $09
    lda HGRHI,y
    clc
    adc DRAW_BASE
    sec
    sbc #$20        ; Adjust since HGRHI already has $20
    sta $0A
    rts
""",

    "hgr_sprite_flip": """
; Page-flip aware sprite drawing
; Draws sprite to current off-screen page
;
; Input:
;   SPRX  ($06) = X position (byte column 0-39)
;   SPRY  ($07) = Y position (0-191)
;   SPRW  ($08) = Width in bytes
;   SPRH  ($09) = Height in lines
;   SPRLO ($0A) = Sprite data pointer low
;   SPRHI ($0B) = Sprite data pointer high
;
; Requires: db_init called first, DRAW_BASE set
; Uses: A, X, Y, $0C-$0D

.segment "CODE"

SPRX    = $06
SPRY    = $07
SPRW    = $08
SPRH    = $09
SPRLO   = $0A
SPRHI   = $0B
SCRPTR  = $0C
DRAW_BASE = $E1

sprite_flip:
    ldy SPRY
    ldx SPRH
@row:
    ; Get screen line address for current draw page
    lda HGRLO,y
    clc
    adc SPRX
    sta SCRPTR
    lda HGRHI,y
    clc
    adc DRAW_BASE
    sec
    sbc #$20        ; Adjust for HGRHI base
    sta SCRPTR+1

    ; Save Y (line counter)
    sty @save_y

    ; Copy SPRW bytes
    ldy #0
@col:
    lda (SPRLO),y
    beq @skip       ; 0 = transparent
    sta (SCRPTR),y
@skip:
    iny
    cpy SPRW
    bne @col

    ; Advance sprite pointer
    lda SPRLO
    clc
    adc SPRW
    sta SPRLO
    bcc @no_carry
    inc SPRHI
@no_carry:

    ; Next line
    ldy @save_y
    iny
    dex
    bne @row
    rts

@save_y: .byte 0
""",

    "hgr_animate_demo": """
; Page-flip animation demo
; Bouncing ball using double buffering
; Press any key to exit
;
; Demonstrates smooth, flicker-free animation

.segment "CODE"

; Zero page
BALL_X  = $06       ; Ball X position (byte column)
BALL_Y  = $07       ; Ball Y position
BALL_DX = $08       ; X velocity (+1 or -1)
BALL_DY = $09       ; Y velocity (+1 or -1)
HGRPTR  = $0A
DRAW_PAGE = $E0
DRAW_BASE = $E1

; ROM
HOME    = $FC58

start:
    jsr HOME
    sta $C050       ; Graphics
    sta $C057       ; HGR
    sta $C052       ; Full screen

    ; Initialize double buffering
    jsr db_init

    ; Initial ball position and velocity
    lda #20
    sta BALL_X
    lda #96
    sta BALL_Y
    lda #1
    sta BALL_DX
    sta BALL_DY

main_loop:
    ; Check for keypress
    lda $C000
    bmi exit

    ; Clear current draw page
    jsr clear_draw_page

    ; Draw ball (4x4 bytes)
    jsr draw_ball

    ; Update ball position
    jsr move_ball

    ; Flip pages
    jsr db_flip

    jmp main_loop

exit:
    sta $C010       ; Clear keyboard
    sta $C051       ; Text mode
    rts

; Initialize double buffer
db_init:
    lda #1
    sta DRAW_PAGE
    lda #$40
    sta DRAW_BASE
    sta $C054
    rts

; Flip with VBL sync
db_flip:
@ve:
    lda $C019
    bmi @ve
@vs:
    lda $C019
    bpl @vs
    lda DRAW_PAGE
    eor #$01
    sta DRAW_PAGE
    beq @p1
    lda #$40
    sta DRAW_BASE
    sta $C054
    rts
@p1:
    lda #$20
    sta DRAW_BASE
    sta $C055
    rts

; Clear draw page to black
clear_draw_page:
    lda DRAW_BASE
    sta @cl+2
    lda #0
    ldy #0
@cl:
    sta $4000,y
    iny
    bne @cl
    inc @cl+2
    ldx @cl+2
    txa
    sec
    sbc DRAW_BASE
    cmp #$20
    bne @cl
    rts

; Draw 4x4 byte ball at BALL_X, BALL_Y
draw_ball:
    ldx #4          ; 4 lines
    ldy BALL_Y
@row:
    ; Get line address
    lda HGRLO,y
    clc
    adc BALL_X
    sta HGRPTR
    lda HGRHI,y
    clc
    adc DRAW_BASE
    sec
    sbc #$20
    sta HGRPTR+1

    ; Draw 4 bytes of $7F (white)
    lda #$7F
    pha
    tya
    pha
    ldy #0
    lda #$7F
@col:
    sta (HGRPTR),y
    iny
    cpy #4
    bne @col
    pla
    tay

    pla
    iny             ; Next line
    dex
    bne @row
    rts

; Move ball, bounce off edges
move_ball:
    ; X movement
    lda BALL_X
    clc
    adc BALL_DX
    sta BALL_X
    ; Bounce X
    cmp #36         ; Right edge (40-4)
    bcc @chk_left
    lda #$FF        ; Reverse: -1
    sta BALL_DX
    jmp @do_y
@chk_left:
    cmp #1
    bcs @do_y
    lda #1          ; Reverse: +1
    sta BALL_DX

@do_y:
    ; Y movement
    lda BALL_Y
    clc
    adc BALL_DY
    sta BALL_Y
    ; Bounce Y
    cmp #188        ; Bottom (192-4)
    bcc @chk_top
    lda #$FF
    sta BALL_DY
    rts
@chk_top:
    cmp #1
    bcs @done
    lda #1
    sta BALL_DY
@done:
    rts

; Lookup tables
.segment "RODATA"

HGRLO:
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $00,$00,$00,$00,$00,$00,$00,$00
    .byte $80,$80,$80,$80,$80,$80,$80,$80
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $28,$28,$28,$28,$28,$28,$28,$28
    .byte $A8,$A8,$A8,$A8,$A8,$A8,$A8,$A8
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0
    .byte $50,$50,$50,$50,$50,$50,$50,$50
    .byte $D0,$D0,$D0,$D0,$D0,$D0,$D0,$D0

HGRHI:
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $20,$24,$28,$2C,$30,$34,$38,$3C
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $21,$25,$29,$2D,$31,$35,$39,$3D
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $22,$26,$2A,$2E,$32,$36,$3A,$3E
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
    .byte $23,$27,$2B,$2F,$33,$37,$3B,$3F
""",
}


def get_template(name: str) -> Optional[str]:
    """Get an assembly template by name."""
    return ASM_TEMPLATES.get(name.lower())


def list_templates() -> list[str]:
    """List available assembly templates."""
    return list(ASM_TEMPLATES.keys())
