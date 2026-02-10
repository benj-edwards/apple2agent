# Apple II Soft Switches Reference

Soft switches are memory-mapped I/O addresses in the $C000-$C0FF range. Reading or writing these addresses controls hardware behavior. On the Apple IIe and later, additional switches control auxiliary memory and 80-column display.

## Keyboard

| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| $C000 | KBD | R | Keyboard data (bit 7 = key available, bits 0-6 = ASCII) |
| $C010 | KBDSTRB | R/W | Clear keyboard strobe (reset bit 7 of $C000) |

Read $C000 to check for a keypress. If bit 7 is set, a key is available. Read the low 7 bits for the ASCII code. Then read $C010 to clear the strobe for the next keypress.

## Display Mode Switches

These switches toggle between display modes. They are activated by any access (read or write).

| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| $C050 | TXTCLR | R/W | Switch to graphics mode |
| $C051 | TXTSET | R/W | Switch to text mode |
| $C052 | MIXCLR | R/W | Full-screen graphics (no text window) |
| $C053 | MIXSET | R/W | Mixed mode (4 lines of text at bottom) |
| $C054 | LOWSCR | R/W | Display page 1 |
| $C055 | HISCR | R/W | Display page 2 |
| $C056 | LORES | R/W | Select lo-res graphics (with TXTCLR) |
| $C057 | HIRES | R/W | Select hi-res graphics (with TXTCLR) |

### Display Mode Combinations

| TXTSET | HIRES | MIXSET | Result |
|--------|-------|--------|--------|
| 1 | x | x | 40-column text |
| 0 | 0 | 0 | Full-screen lo-res (40x48) |
| 0 | 0 | 1 | Mixed lo-res (40x40 + 4 text lines) |
| 0 | 1 | 0 | Full-screen hi-res (280x192) |
| 0 | 1 | 1 | Mixed hi-res (280x160 + 4 text lines) |

## Speaker

| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| $C030 | SPKR | R/W | Toggle speaker cone (read to click) |

Each access inverts the speaker diaphragm position. Rapid toggling produces sound.

## Game Controller / Paddles

| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| $C061 | BUTN0 / PB0 | R | Push button 0 (open apple) -- bit 7 |
| $C062 | BUTN1 / PB1 | R | Push button 1 (closed apple) -- bit 7 |
| $C063 | BUTN2 / PB2 | R | Push button 2 (shift key on IIe) -- bit 7 |
| $C064 | PADDL0 | R | Paddle 0 timer -- bit 7 (1=timing, 0=done) |
| $C065 | PADDL1 | R | Paddle 1 timer -- bit 7 |
| $C066 | PADDL2 | R | Paddle 2 timer -- bit 7 |
| $C067 | PADDL3 | R | Paddle 3 timer -- bit 7 |
| $C070 | PTRIG | R/W | Trigger paddle timers (start analog read) |

To read a paddle: access $C070 to start the timers, then repeatedly read $C064-$C067 until bit 7 goes low. The count of reads gives the paddle position (0-255).

## Annunciators

| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| $C058 | AN0OFF | R/W | Annunciator 0 off |
| $C059 | AN0ON | R/W | Annunciator 0 on |
| $C05A | AN1OFF | R/W | Annunciator 1 off |
| $C05B | AN1ON | R/W | Annunciator 1 on |
| $C05C | AN2OFF | R/W | Annunciator 2 off |
| $C05D | AN2ON | R/W | Annunciator 2 on |
| $C05E | AN3OFF / DHIRES ON | R/W | Annunciator 3 off / Enable double hi-res |
| $C05F | AN3ON / DHIRES OFF | R/W | Annunciator 3 on / Disable double hi-res |

On the Apple IIe, AN3 ($C05E/$C05F) also controls double hi-res mode when 80STORE and HIRES are active.

## Cassette (II/II+ only)

| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| $C020 | TAPEOUT | R/W | Cassette output toggle |
| $C060 | TAPEIN | R | Cassette input (bit 7) |

## Apple IIe Auxiliary Memory Switches

These switches control access to the 64KB auxiliary memory bank in the Apple IIe (and later).

### Read Switches (Read address to check status, bit 7 = active)

| Address | Name | R | Description |
|---------|------|---|-------------|
| $C011 | RDLCBNK2 | R | Language card bank 2 selected? (bit 7) |
| $C012 | RDLCRAM | R | Language card RAM read enabled? (bit 7) |
| $C013 | RDRAMRD | R | Aux memory read enabled? (bit 7) |
| $C014 | RDRAMWRT | R | Aux memory write enabled? (bit 7) |
| $C015 | RDCXROM | R | Internal slot ROM enabled? (bit 7) |
| $C016 | RDALTZP | R | Aux zero page/stack enabled? (bit 7) |
| $C017 | RDC3ROM | R | Internal slot 3 ROM enabled? (bit 7) |
| $C018 | RD80STORE | R | 80STORE enabled? (bit 7) |
| $C019 | RDVBLBAR | R | Vertical blanking? (bit 7, IIe rev B+) |
| $C01A | RDTEXT | R | Text mode active? (bit 7) |
| $C01B | RDMIXED | R | Mixed mode active? (bit 7) |
| $C01C | RDPAGE2 | R | Page 2 displayed? (bit 7) |
| $C01D | RDHIRES | R | Hi-res mode active? (bit 7) |
| $C01E | RDALTCHAR | R | Alternate character set? (bit 7) |
| $C01F | RD80COL | R | 80-column mode active? (bit 7) |

### Write Switches (memory banking)

| Address | Name | W | Description |
|---------|------|---|-------------|
| $C000 | 80STOREOFF | W | Disable 80STORE |
| $C001 | 80STOREON | W | Enable 80STORE (PAGE2 switch selects main/aux) |
| $C002 | RAMRDOFF | W | Read main memory |
| $C003 | RAMRDON | W | Read auxiliary memory |
| $C004 | RAMWRTOFF | W | Write main memory |
| $C005 | RAMWRTON | W | Write auxiliary memory |
| $C006 | INTCXROMOFF | W | Slot ROMs active ($C100-$CFFF) |
| $C007 | INTCXROMON | W | Internal ROM active ($C100-$CFFF) |
| $C008 | ALTZPOFF | W | Use main zero page, stack, LC |
| $C009 | ALTZPON | W | Use aux zero page, stack, LC |
| $C00A | SLOTC3ROMOFF | W | Slot 3 ROM active |
| $C00B | SLOTC3ROMON | W | Internal slot 3 ROM active |

Note: $C000 has dual use -- reads return keyboard data, writes control 80STORE.

### 80-Column / Video Switches

| Address | Name | W | Description |
|---------|------|---|-------------|
| $C00C | 80COLOFF | W | Disable 80-column mode |
| $C00D | 80COLON | W | Enable 80-column mode |
| $C00E | ALTCHAROFF | W | Use primary character set |
| $C00F | ALTCHARON | W | Use alternate character set (MouseText on IIe) |

### 80STORE Mode

When 80STORE is enabled ($C001):
- PAGE2 switch ($C054/$C055) selects between main and aux memory for display pages instead of switching the displayed page
- In text mode: PAGE2=1 accesses aux text page ($400-$7FF aux)
- In hi-res mode with HIRES active: PAGE2=1 also accesses aux hi-res page ($2000-$3FFF aux)
- This is how 80-column text and double hi-res work

## Language Card (Bank-Switched RAM)

The language card provides 16KB of RAM that overlays the ROM at $D000-$FFFF. The $D000-$DFFF range has two 4KB banks.

| Address | Name | R/W | Description |
|---------|------|-----|-------------|
| $C080 | LCBANK2 | R | Read RAM bank 2, write-protect RAM |
| $C081 | ROMIN | R | Read ROM, write-enable RAM (bank 2) |
| $C082 | ROMIN2 | R | Read ROM, write-protect RAM (bank 2) |
| $C083 | LCBANK2RW | R | Read/write RAM bank 2 |
| $C084-$C087 | | | Same as $C080-$C083 (aliases) |
| $C088 | LCBANK1 | R | Read RAM bank 1, write-protect RAM |
| $C089 | ROMIN1 | R | Read ROM, write-enable RAM (bank 1) |
| $C08A | ROMIN12 | R | Read ROM, write-protect RAM (bank 1) |
| $C08B | LCBANK1RW | R | Read/write RAM bank 1 |
| $C08C-$C08F | | | Same as $C088-$C08B (aliases) |

### Write-Enable Protocol

To enable writes to language card RAM, the write-enable switch must be accessed twice in succession. A single read enables read-from-RAM but not write. Two consecutive reads of $C081 or $C083 (or their bank 1 equivalents) enable writing.

### Summary Table

| Address | Read From | Write To |
|---------|-----------|----------|
| $C080 | RAM bank 2 | ROM (write-protected) |
| $C081 (x2) | ROM | RAM bank 2 |
| $C082 | ROM | ROM (write-protected) |
| $C083 (x2) | RAM bank 2 | RAM bank 2 |
| $C088 | RAM bank 1 | ROM (write-protected) |
| $C089 (x2) | ROM | RAM bank 1 |
| $C08A | ROM | ROM (write-protected) |
| $C08B (x2) | RAM bank 1 | RAM bank 1 |

## Slot I/O Space

| Address Range | Description |
|---------------|-------------|
| $C080-$C08F | Language card / memory bank switches |
| $C090-$C09F | Slot 1 I/O (typically printer) |
| $C0A0-$C0AF | Slot 2 I/O (typically Super Serial Card) |
| $C0B0-$C0BF | Slot 3 I/O (typically 80-column card / Uthernet) |
| $C0C0-$C0CF | Slot 4 I/O (typically mouse card) |
| $C0D0-$C0DF | Slot 5 I/O (typically SmartPort / disk) |
| $C0E0-$C0EF | Slot 6 I/O (typically Disk II) |
| $C0F0-$C0FF | Slot 7 I/O (typically ProDOS RAM card) |

Each slot gets 16 bytes of I/O space. Slot ROMs occupy $C100-$C7FF (256 bytes per slot) and $C800-$CFFF (shared 2KB expansion ROM space).

## Slot ROM Space

| Address Range | Description |
|---------------|-------------|
| $C100-$C1FF | Slot 1 ROM |
| $C200-$C2FF | Slot 2 ROM |
| $C300-$C3FF | Slot 3 ROM (or internal 80-col firmware) |
| $C400-$C4FF | Slot 4 ROM |
| $C500-$C5FF | Slot 5 ROM |
| $C600-$C6FF | Slot 6 ROM (Disk II boot ROM) |
| $C700-$C7FF | Slot 7 ROM |
| $C800-$CFFF | Shared expansion ROM (selected by slot access) |

## Double Hi-Res Mode Setup

To enable double hi-res (560x192 monochrome or 140x192 color):

```asm
    STA $C00D        ; 80COL on
    STA $C001        ; 80STORE on
    STA $C057        ; HIRES
    STA $C050        ; Graphics mode
    STA $C052        ; Full screen (no mixed)
    STA $C05E        ; AN3 off (DHIRES on)
```

To disable:

```asm
    STA $C05F        ; AN3 on (DHIRES off)
    STA $C00C        ; 80COL off
    STA $C000        ; 80STORE off
```

## Double Lo-Res Mode Setup

To enable double lo-res (80x48, 16 colors):

```asm
    STA $C00D        ; 80COL on
    STA $C001        ; 80STORE on
    STA $C056        ; LORES
    STA $C050        ; Graphics mode
    STA $C052        ; Full screen
    STA $C05E        ; AN3 off (double mode)
```

## Vertical Blanking

| Address | Name | R | Description |
|---------|------|---|-------------|
| $C019 | RDVBLBAR | R | Bit 7: 0 during VBL, 1 during active display (IIe+) |

Use vertical blanking to update display memory without visible flicker:

```asm
wait_vbl:
    LDA $C019
    BMI wait_vbl     ; Wait until VBL starts (bit 7 = 0)
```

Note: On original IIe, the polarity may be inverted. On IIe rev B and later, bit 7 = 0 means VBL is active.
