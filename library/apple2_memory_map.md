# Apple II Memory Map

## Full Memory Map ($0000-$FFFF)

| Address Range | Size | Description |
|---------------|------|-------------|
| $0000-$00FF | 256 | Zero Page (see below) |
| $0100-$01FF | 256 | 6502 Stack |
| $0200-$02FF | 256 | Input buffer (GETLN stores input here) |
| $0300-$03CF | 208 | Free (often used for small routines) |
| $03D0-$03FF | 48 | DOS/ProDOS vectors and system pointers |
| $0400-$07FF | 1K | Text/Lo-res Page 1 |
| $0800-$0BFF | 1K | Text/Lo-res Page 2 |
| $0800-$0FFF | | Applesoft BASIC program (start, if no DOS) |
| $0C00-$1FFF | 5K | Free RAM (used by BASIC programs) |
| $2000-$3FFF | 8K | Hi-res Page 1 |
| $4000-$5FFF | 8K | Hi-res Page 2 |
| $6000-$95FF | ~14K | Free RAM (common for ML programs) |
| $9600-$BFFF | ~10.5K | DOS 3.3 (if loaded) |
| $9600-$9FFF | | ProDOS BASIC.SYSTEM (if loaded) |
| $A000-$BEFF | | ProDOS (if loaded) |
| $BF00-$BFFF | 256 | ProDOS global page |
| $C000-$C0FF | 256 | I/O soft switches |
| $C100-$C7FF | 1.75K | Slot ROM space (256 bytes per slot) |
| $C800-$CFFF | 2K | Shared expansion ROM |
| $D000-$DFFF | 4K | Applesoft or Language Card RAM Bank 1/2 |
| $E000-$F7FF | 6K | Applesoft ROM (or Language Card RAM) |
| $F800-$FFFF | 2K | Monitor ROM (or Language Card RAM) |

## Memory Availability

### With DOS 3.3

| Address Range | Available For |
|---------------|---------------|
| $0800-$95FF | BASIC programs and variables (~36K) |
| $0300-$03CF | Small ML routines |
| $6000-$95FF | Machine language programs |

### With ProDOS

| Address Range | Available For |
|---------------|---------------|
| $0800-$BEFF | BASIC programs and variables (~46K, minus BASIC.SYSTEM) |
| $0300-$03CF | Small ML routines |
| $2000-$9FFF | Machine language programs (if not using HGR) |
| $6000-$9FFF | Machine language programs (typical) |

### Bare (No DOS)

| Address Range | Available For |
|---------------|---------------|
| $0800-$BFFF | Nearly 48K free |

---

## Text/Lo-Res Screen Memory ($0400-$07FF)

The text and lo-res graphics screens use a non-linear memory layout. Each screen line maps to a different base address.

### Text Page 1 Line Addresses

| Line | Address | Line | Address | Line | Address |
|------|---------|------|---------|------|---------|
| 0 | $0400 | 8 | $0428 | 16 | $0450 |
| 1 | $0480 | 9 | $04A8 | 17 | $04D0 |
| 2 | $0500 | 10 | $0528 | 18 | $0550 |
| 3 | $0580 | 11 | $05A8 | 19 | $05D0 |
| 4 | $0600 | 12 | $0628 | 20 | $0650 |
| 5 | $0680 | 13 | $06A8 | 21 | $06D0 |
| 6 | $0700 | 14 | $0728 | 22 | $0750 |
| 7 | $0780 | 15 | $07A8 | 23 | $07D0 |

Each line is 40 bytes. The 8 bytes after each 40-byte line are "screen holes" (not displayed). Screen holes are at offsets +40 through +47 from each line base.

### Text Page 2 Line Addresses

Same pattern as Page 1, but add $0400 (base is $0800-$0BFF).

### Screen Address Formula

```
base = $0400 + ($80 * (line AND 7)) + ($28 * (line / 8))
char_addr = base + column
```

Or equivalently:
```
group = line / 8       (0, 1, or 2)
row_in_group = line AND 7   (0-7)
base = $0400 + (row_in_group * $0080) + (group * $0028)
```

### Lo-Res Graphics

Lo-res uses the same memory as text. Each byte represents two stacked pixels:
- Low nibble (bits 0-3): top pixel color
- High nibble (bits 4-7): bottom pixel color

This gives 40x48 pixels (40 columns, 24 rows of 2 pixels each).

### Screen Holes

Bytes in the screen memory that are not displayed. These are used by various hardware and firmware for storage:

| Addresses | Usage |
|-----------|-------|
| $0478-$047F | Slot scratchpad (low bytes) |
| $04F8-$04FF | Slot scratchpad (high bytes) |
| $0578-$057F | Slot scratchpad |
| $05F8-$05FF | Slot scratchpad |
| $0678-$067F | Slot scratchpad |
| $06F8-$06FF | Slot scratchpad |
| $0778-$077F | Slot scratchpad |
| $07F8-$07FF | Slot scratchpad |

---

## Hi-Res Screen Memory

### HGR Page 1 ($2000-$3FFF)

8KB. 280 pixels wide by 192 lines. The memory layout is interleaved in groups of 8 lines.

### HGR Line Address Formula

```
base = $2000 + (line/64)*$28 + ((line%64)/8)*$80 + (line%8)*$400
```

Or broken down:
```
section = line / 64        (0, 1, or 2)
group = (line / 8) AND 7   (0-7)
row = line AND 7           (0-7)

address = $2000 + (row * $0400) + (group * $0080) + (section * $0028)
```

### HGR Page 1 Line Addresses (first 24 of 192)

| Line | Address | Line | Address | Line | Address |
|------|---------|------|---------|------|---------|
| 0 | $2000 | 8 | $2080 | 16 | $2100 |
| 1 | $2400 | 9 | $2480 | 17 | $2500 |
| 2 | $2800 | 10 | $2880 | 18 | $2900 |
| 3 | $2C00 | 11 | $2C80 | 19 | $2D00 |
| 4 | $3000 | 12 | $3080 | 20 | $3100 |
| 5 | $3400 | 13 | $3480 | 21 | $3500 |
| 6 | $3800 | 14 | $3880 | 22 | $3900 |
| 7 | $3C00 | 15 | $3C80 | 23 | $3D00 |

Each line is 40 bytes. Within each byte:
- Bit 7: color palette select (0=green/violet, 1=orange/blue)
- Bits 0-6: 7 pixels (LSB = leftmost)

### HGR Page 2 ($4000-$5FFF)

Same layout, add $2000 to all addresses.

### HGR Color

In color mode, adjacent pixels combine to form colors:
- Pixels in even columns can be violet or green
- Pixels in odd columns can be blue or orange
- Bit 7 of each byte shifts the color palette
- White = two adjacent on-pixels
- Black = two adjacent off-pixels

---

## Double Hi-Res Memory (Apple IIe)

DHGR uses both main and auxiliary memory for each scan line:

| Memory | Page | Address Range | Pixels |
|--------|------|---------------|--------|
| Aux | 1 | $2000-$3FFF | Even columns (0,2,4...) |
| Main | 1 | $2000-$3FFF | Odd columns (1,3,5...) |
| Aux | 2 | $4000-$5FFF | Even columns (page 2) |
| Main | 2 | $4000-$5FFF | Odd columns (page 2) |

Each byte provides 7 pixels (bit 7 is unused in monochrome DHGR). Total resolution: 560x192 monochrome or 140x192 in 16 colors.

### DHGR Byte Ordering

For each group of 7 screen pixels, the bytes alternate aux/main:

```
Aux byte bits 0-6 | Main byte bits 0-6 | Aux byte bits 0-6 | ...
```

---

## I/O Space ($C000-$CFFF)

| Address Range | Description |
|---------------|-------------|
| $C000-$C00F | Keyboard and IIe memory switches |
| $C010-$C01F | Keyboard strobe and IIe status reads |
| $C020-$C02F | Cassette output |
| $C030-$C03F | Speaker |
| $C040-$C04F | Utility strobe |
| $C050-$C05F | Display mode switches and annunciators |
| $C060-$C06F | Cassette/button/paddle inputs |
| $C070-$C07F | Paddle trigger and IIe aux memory |
| $C080-$C08F | Language card / RAM bank switches |
| $C090-$C0FF | Slot I/O (16 bytes per slot, slots 1-7) |
| $C100-$C7FF | Slot ROM (256 bytes per slot) |
| $C800-$CFFF | Shared expansion ROM (2KB) |

See `apple2_soft_switches.md` for complete soft switch details.

---

## System Vectors ($03D0-$03FF)

| Address | Name | Description |
|---------|------|-------------|
| $03D0 | WARMSTART | JMP to DOS/ProDOS warm start |
| $03D3 | | JMP to DOS/ProDOS cold start |
| $03D6 | | JMP to file manager |
| $03D9 | | JMP to RWTS (DOS 3.3) |
| $03DC | | (DOS dependent) |
| $03EA | DISCONNECT | Disconnect DOS |
| $03F0 | BRKV | BRK/IRQ vector (address of handler) |
| $03F2 | SOFTEV | Reset vector (soft entry point) |
| $03F4 | PWREDUP | Power-up byte (must = $03F3 EOR #$A5) |
| $03F5-$03F7 | AMPERV | Ampersand (&) vector (JMP instruction) |
| $03F8-$03FA | USRVEC | USR() function vector (JMP instruction) |
| $03FB | NMI | NMI vector |
| $03FE-$03FF | IRQV | IRQ/BRK vector (address, not JMP) |

---

## Zero Page Reference ($00-$FF)

### Monitor Zero Page ($00-$4F)

| Address | Name | Description |
|---------|------|-------------|
| $00-$01 | LOC0/LOC1 | General purpose / Monitor indirect |
| $02-$03 | LOC2/LOC3 | General purpose |
| $04-$05 | | General purpose (free for user) |
| $06-$09 | | General purpose (free for user) |
| $0A-$0F | | General purpose (free for user) |
| $10-$17 | | General purpose (free for user) |
| $18-$1B | | General purpose (free for user) |
| $1C-$1F | | General purpose (free for user) |
| $20 | WNDLFT | Text window left edge (0-39) |
| $21 | WNDWTH | Text window width |
| $22 | WNDTOP | Text window top edge (0-23) |
| $23 | WNDBTM | Text window bottom edge (0-24) |
| $24 | CH | Cursor horizontal position (0-39) |
| $25 | CV | Cursor vertical position (0-23) |
| $26 | GPTS | General purpose temp storage |
| $27 | BARONE | Flag byte |
| $28-$29 | BARONE/BAS | Text base address for current line |
| $2A-$2B | BAS2H/BAS2L | Secondary base address |
| $2C | LMNEM | Mnemonic for Monitor |
| $2D | RMNEM | Mnemonic for Monitor |
| $2E | FORMATV | Format value for Monitor |
| $2F | LENGTH | Length for Monitor disassembly |
| $30 | MASK | AND mask for COUT |
| $31 | MON_MODE | Monitor mode flags |
| $32 | INVFLG | Inverse/flash/normal flag ($FF=normal, $3F=flash, $00=inverse) |
| $33 | PROMPT | Prompt character (default $DD = "]") |
| $34-$35 | YSAVE/CSWL | Monitor temp / Character output hook (low) |
| $36-$37 | CSWH/KSWL | Character output hook (high) / Keyboard input hook (low) |
| $38-$39 | KSWH | Keyboard input hook (high) |
| $3A-$3B | | PCL/PCH - Monitor program counter |
| $3C-$3D | A1L/A1H | General purpose address 1 |
| $3E-$3F | A2L/A2H | General purpose address 2 |
| $40-$41 | A3L/A3H | General purpose address 3 |
| $42-$43 | A4L/A4H | General purpose address 4 |
| $44 | | Monitor accumulator save |
| $45 | XREG | Monitor X register save |
| $46 | YREG | Monitor Y register save |
| $47 | STATUS | Monitor status register save |
| $48 | SPNT | Monitor stack pointer save |
| $49-$4F | | General purpose (free for user) |

### Applesoft BASIC Zero Page ($50-$FF)

| Address | Name | Description |
|---------|------|-------------|
| $50-$51 | LINNUM | Current/target line number |
| $52-$53 | TEMPPT | Temporary string pointer |
| $54-$55 | LASTPT | Last temporary string address |
| $56-$5D | TEMPST | Temporary string descriptor stack |
| $5E-$5F | INDEX | General purpose index/pointer |
| $60-$61 | | Auxiliary index |
| $62-$63 | | Integer value (also used by FLOAT) |
| $64-$65 | TXTTAB | Pointer to start of BASIC program |
| $66-$67 | VARTAB | Pointer to start of variable storage |
| $68-$69 | ARYTAB | Pointer to start of array storage |
| $6A-$6B | STREND | Pointer to end of array storage |
| $6C-$6D | FRETOP | Pointer to top of free string space |
| $6E-$6F | FRESPC | Pointer to new string temp |
| $70-$71 | MEMSIZ | Pointer to highest address used by BASIC |
| $72-$73 | CURLIN | Current line number ($FF.xx = direct mode) |
| $74-$75 | OLDLIN | Previous line number (for CONT) |
| $76-$77 | OLDTEXT | Pointer to saved TXTPTR (for CONT) |
| $78-$79 | DATLIN | DATA line number |
| $7A-$7B | DATPTR | Pointer into DATA |
| $7C-$7D | INPTR | Pointer to input source |
| $7E-$7F | VARNAM | Variable name (2 bytes) |
| $80-$81 | VARPNT | Pointer to variable value |
| $82-$83 | FORPNT | Pointer for FOR/NEXT |
| $84-$87 | | Operator work area |
| $85-$86 | | Expression compare flag, dimension flag |
| $87 | TEMPF3 | Temp for OPTS |
| $88-$8A | | Misc working storage |
| $8B | TYPE | Variable type flag ($00=numeric, $FF=string) |
| $8C-$8D | | Misc working storage |
| $8E-$8F | | Expression temp |
| $90-$92 | | Misc working storage |
| $93-$97 | | Applesoft temp storage |
| $98 | HIGHDS | Destination for block transfer (high) |
| $99 | HIGHTR | Source for block transfer (high) |
| $9A-$9B | | Block transfer temp |
| $9C-$9D | FAC | Floating point accumulator (exponent + mantissa start) |
| $9D-$A1 | | FAC mantissa bytes 1-4 |
| $A2 | FACSGN | FAC sign |
| $A3-$A4 | | General purpose pointer |
| $A5-$AA | ARG | Floating point argument (secondary accumulator) |
| $AB | ARGSGN | ARG sign |
| $AC-$AE | | Misc working storage |
| $AF-$B0 | PRGEND | Pointer to end of program (same as VARTAB) |
| $B1-$B7 | CHRGET/CHRGOT | Get-next-character routine (self-modifying code) |
| $B8-$B9 | TXTPTR | Pointer into BASIC text (within CHRGET) |
| $BA-$C8 | | CHRGET subroutine continues |
| $C9-$CD | RND | Random number seed |
| $CE-$CF | | Misc temp |
| $D0-$D5 | | Applesoft working storage |
| $D6 | LOCK | Applesoft ONERR flag |
| $D8 | ERRFLG | ONERR flag |
| $DA-$DB | ERRLIN | Line number of last error |
| $DC-$DD | ERRPOS | TXTPTR at last error |
| $DE | ERRNUM | Last error number |
| $DF-$E1 | | Applesoft temp |
| $E2-$E3 | HGR_X | Hi-res cursor X position (9 bits) |
| $E4 | HGR_Y | Hi-res cursor Y position |
| $E5 | HGR_COLOR | Hi-res color byte |
| $E6 | HGR_HORIZ | Hi-res horizontal byte count |
| $E7 | HGR_PAGE | Hi-res page ($20 or $40) |
| $E8 | HGR_SCALE | HPLOT scale factor |
| $E9-$EA | HGR_SHAPE | Pointer to current shape table entry |
| $EB | HGR_COLLISIONS | Collision count |
| $EC-$EF | | HGR working storage |
| $F0-$F3 | | Applesoft temp |
| $F4-$F8 | | Applesoft numeric working storage |
| $F9 | SPEEDZ | Text output speed ($00=fastest) |
| $FA | FLASH | Flash mask |

### Free Zero Page Locations

The following zero page addresses are generally safe for user programs:

| Range | Notes |
|-------|-------|
| $06-$09 | Free (not used by Monitor or BASIC) |
| $19-$1F | Free when not using Monitor heavily |
| $EB-$EF | Free when not using HGR shape tables |
| $FA-$FF | Free when not using Monitor or certain BASIC features |

**Warning**: Most zero page locations from $50-$FF are actively used by Applesoft BASIC. Machine language programs that coexist with BASIC should use locations below $50 or save/restore BASIC's zero page.

### ProDOS Zero Page Usage

ProDOS itself uses minimal zero page space, but BASIC.SYSTEM uses the same Applesoft locations. ProDOS reserves:

| Address | Description |
|---------|-------------|
| $40-$4F | Used during MLI calls (must not be in use when calling MLI) |

### DOS 3.3 Zero Page Usage

DOS 3.3 uses several zero page locations during file operations:

| Address | Description |
|---------|-------------|
| $00-$01 | Used by RWTS |
| $02-$03 | Used by file manager |
| $3C-$3F | Used as address pointers (A1, A2) |
| $40-$49 | Working storage during disk operations |
| $AA-$AF | Working storage for DOS routines |

---

## Applesoft BASIC Memory Pointers

These pointers define the BASIC program layout in memory:

```
TXTTAB ($64-$65)  --> Start of program
VARTAB ($66-$67)  --> Start of variables (end of program + 1)
ARYTAB ($68-$69)  --> Start of arrays
STREND ($6A-$6B)  --> End of arrays / start of free memory
FRETOP ($6C-$6D)  --> Bottom of string storage (grows downward)
MEMSIZ ($70-$71)  --> Top of BASIC memory
```

```
Low memory                                         High memory
+--------+----------+--------+------+--------+---------+
| Program | Variables | Arrays | Free | Strings | (DOS) |
+--------+----------+--------+------+--------+---------+
^        ^          ^        ^      ^         ^
TXTTAB   VARTAB     ARYTAB   STREND FRETOP    MEMSIZ
```

Default TXTTAB is $0801 (with DOS/ProDOS) or $0800 (without).

---

## Stack Usage ($0100-$01FF)

The 6502 stack grows downward from $01FF. SP starts at $FF and decrements on push. Common stack contents:

| User | Bytes | Description |
|------|-------|-------------|
| JSR | 2 | Return address minus 1 (high byte pushed first) |
| PHA | 1 | Accumulator value |
| PHP | 1 | Status register |
| BRK/IRQ | 3 | Status register + return address |

BASIC uses the stack for FOR/NEXT loops, GOSUB/RETURN, and expression evaluation. Deep nesting or recursion can overflow the stack.

---

## Input Buffer ($0200-$02FF)

The Monitor's GETLN routine reads keyboard input into this 256-byte buffer. Applesoft's INPUT statement also uses this buffer.

| Address | Description |
|---------|-------------|
| $0200-$02FF | 256-byte input buffer |
| X register | Length of input after GETLN returns |
