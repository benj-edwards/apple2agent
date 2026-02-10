# Apple II MCP Server — Agent Guide

Call the `help` tool to see this guide from within your session.

## What This Is

An MCP (Model Context Protocol) server that controls an Apple II emulator (Bobbin). Use it to write, test, and run Apple II software — Applesoft BASIC, 6502 assembly, and binary programs.

## Quick Start

### Get to a BASIC prompt (pick one)

```
load_basic_env()      # Bare BASIC (no disk commands) — fastest
load_prodos_env()     # ProDOS BASIC (CAT, PREFIX, BRUN)
load_dos33_env()      # DOS 3.3 BASIC (CATALOG, SAVE, LOAD)
boot(machine="enhanced")  # Full cold boot (slowest)
```

All `load_*_env` tools auto-start the emulator if needed. One call = instant ready.

### Write and run a BASIC program

```
inject_tokenized_basic(source="10 PRINT \"HELLO\"\n20 GOTO 10", auto_run=true)
```

Use the `source` parameter (not `hex_data`) — it tokenizes server-side and avoids wasting tokens on hex strings.

### Write and run 6502 assembly

```
# Small inline snippets:
assemble(source=".org $6000\n  LDA #$41\n  JSR $FDED\n  RTS", load_address=24576)
call(address=24576)

# Large programs (preferred — reads from file, saves tokens):
assemble(source_file="asm/mycode.s", load_address=24576)
call(address=24576)
```

`assemble` auto-loads the binary into emulator memory. Just `call()` to execute. Use `source_file` for anything beyond a few lines — it reads from disk and avoids sending source through the API.

### See what happened

```
read_screen()              # Get 40x24 text screen
capture_hgr(format="png")  # Hi-res graphics screenshot
capture_gr(format="png")   # Lo-res graphics screenshot
```

## Token-Efficient Patterns

These patterns avoid passing large hex strings through the conversation:

| Instead of... | Do this |
|---------------|---------|
| `tokenize()` then `inject_tokenized_basic(hex_data=...)` | `inject_tokenized_basic(source="10 ...")` |
| `assemble(source=<huge source>)` | `assemble(source_file="asm/mycode.s")` — reads from disk |
| `assemble()` then `load_binary(hex_data=...)` | `assemble(source="...")` — auto-loads |
| `load_binary(hex_data="A9 00 8D...")` for data files | `load_file(path="/path/to/file.bin", address=0x6000)` |

NEVER call `tokenize` and then pass the hex result to `inject_tokenized_basic`. Just pass source directly.

NEVER call `assemble` and then pass hex to `load_binary`. `assemble` already loads into memory.

For **large assembly files**, use `assemble(source_file="asm/mycode.s")` instead of `assemble(source=...)`. This reads the source from disk — zero assembly text flows through the API. The source file's directory is automatically added as an include path, so `.include` directives work.

NEVER pass large hex strings via `load_binary`. Write data to a file, then use `load_file` to load it directly into memory. This applies to sprite data, font tables, lookup tables, pre-built binaries, etc.

## Tool Reference

### Emulator Lifecycle

| Tool | Description |
|------|-------------|
| `boot` | Cold boot (machine: "plus" or "enhanced", optional disk image) |
| `shutdown` | Stop emulator |
| `pause` | Pause emulation (saves CPU) |
| `resume` | Resume after pause |
| `reset` | Warm or cold reset |

### Memory

| Tool | Description |
|------|-------------|
| `peek` | Read bytes (format: hex/decimal/ascii) |
| `poke` | Write bytes |
| `load_binary` | Load hex string into memory (prefer `load_file` instead) |
| `load_file` | Load a local file directly into memory (no hex tokens — use this for data files) |

### BASIC Programming

| Tool | Description |
|------|-------------|
| `inject_tokenized_basic` | Load BASIC program. Use `source` param (preferred) or `hex_data` |
| `run_basic` | Execute a BASIC command and wait for prompt |
| `run_and_capture` | Run program and capture screen (gr/hgr/text) |
| `tokenize` | Tokenize BASIC source (returns hex). Prefer `inject_tokenized_basic(source=)` instead |
| `get_basic_pointers` | Show TXTTAB, VARTAB, etc. |

### 6502 Assembly

| Tool | Description |
|------|-------------|
| `assemble` | Assemble ca65 source and auto-load. Use `source_file` for large files, `source` for small snippets |
| `call` | Execute code at address (JSR — code must end with RTS) |
| `asm_templates` | List/get assembly code templates |

### Screen & Graphics

| Tool | Description |
|------|-------------|
| `read_screen` | Read 40x24 text screen as text |
| `capture_hgr` | Capture hi-res graphics (png/ppm/ascii) |
| `capture_gr` | Capture lo-res graphics (png/ppm/ascii) |
| `capture_dhgr` | Capture double hi-res (//e only) |
| `capture_dgr` | Capture double lo-res (//e only) |
| `read_hgr_ascii` | Hi-res as ASCII art (no file) |
| `read_gr_ascii` | Lo-res as ASCII art (no file) |
| `clear_hgr` | Clear hi-res screen to black |
| `clear_gr` | Clear lo-res screen to color |

### Input

| Tool | Description |
|------|-------------|
| `type_text` | Type text (auto-uppercased, optional RETURN) |
| `send_key` | Send special key (RETURN, ESCAPE, CTRL-C, CTRL-RESET) |
| `send_keys_and_capture` | Send keys then capture screen (for interactive programs) |

### Disk Operations

| Tool | Description |
|------|-------------|
| `create_disk` | Create DOS 3.3 disk image |
| `disk_catalog` | List files on DOS 3.3 disk |
| `save_basic_to_disk` | Save BASIC program to disk (auto-tokenizes) |
| `save_file_to_disk` | Save .bas file to disk |
| `prodos_list` | List files on ProDOS disk |
| `prodos_add` | Add file to ProDOS disk (types: BIN, SYS, BAS, TXT) |
| `prodos_del` | Delete file from ProDOS disk |

### State Management

| Tool | Description |
|------|-------------|
| `save_state` | Save emulator snapshot (CPU + 128KB RAM + soft switches) |
| `load_state` | Restore emulator snapshot |
| `load_basic_env` | Instant bare BASIC environment |
| `load_prodos_env` | Instant ProDOS BASIC environment |
| `load_dos33_env` | Instant DOS 3.3 BASIC environment |

### CPU & Debug

| Tool | Description |
|------|-------------|
| `get_registers` | Read 6502 CPU state (PC, A, X, Y, SP, flags) |
| `type_and_capture` | Type BASIC line, capture tokenization |
| `compare_tokenization` | Compare your tokenization vs native |

### Mouse (requires boot with mouse=true)

| Tool | Description |
|------|-------------|
| `init_mouse` | Initialize AppleMouse card |
| `read_mouse` | Read mouse position and button |
| `set_mouse` | Set mouse position and button |

### Knowledge Base

| Tool | Description |
|------|-------------|
| `record_technique` | Save a discovered technique |
| `query_techniques` | Search saved techniques |

### Help

| Tool | Description |
|------|-------------|
| `help` | Show this guide (tool reference, tips, gotchas, disk instructions) |

---

## Apple II Development Tips & Gotchas

Read this section carefully. These are hard-won lessons that will save you hours of debugging.

### Applesoft BASIC

- **The screen is 40 columns wide.** Lines longer than 40 characters wrap. Design your output accordingly.
- **BASIC keywords must be uppercase.** The Apple II doesn't have lowercase in standard text mode.
- **String variables end with `$`**: `A$`, `NAME$`. Numeric: `A`, `X1`. Integer: `A%` (rarely used, not faster).
- **Line numbers are required.** Every line needs a number. Use increments of 10 so you can insert lines later.
- **`PRINT` with a semicolon** suppresses the newline: `PRINT "HI";` stays on the same line.
- **`CHR$(4)` is the DOS/ProDOS command prefix.** `PRINT CHR$(4);"CATALOG"` runs a disk command from BASIC.
- **`PEEK` and `POKE` are your hardware interface.** `PEEK(49152)` reads the keyboard. `POKE 49168,0` clears the keyboard strobe.
- **Applesoft float math is slow.** For counters and loops, integer variables don't help much — Applesoft converts everything to float internally anyway.
- **`&` is a hook vector.** It calls through the ampersand vector at $3F5-$3F7, not a BASIC command.
- **Max line length is 239 characters** after tokenization.
- **`DATA`/`READ`/`RESTORE`** are the main way to embed tables. No array literals.
- **`DIM` is required for arrays > 10 elements.** `DIM A(100)` — but arrays are 0-based, so this gives 101 elements.
- **`HGR` clears the screen and enters hi-res mode.** `HGR2` uses page 2. Both clear the screen.
- **Hi-res coordinates**: 280 x 192 (0-279 horizontal, 0-191 vertical). `HPLOT X,Y` plots a point. `HPLOT TO X,Y` draws a line from last point.
- **Lo-res coordinates**: 40 x 48 (but bottom 8 rows are text if mixed mode). `GR` enters lo-res. `COLOR=N` sets color (0-15). `PLOT X,Y` plots. `HLIN X1,X2 AT Y` draws horizontal line. `VLIN Y1,Y2 AT X` draws vertical line.
- **`TEXT`** returns to text mode from graphics.
- **`HOME`** clears the text screen and moves cursor to top-left.
- **Error handling**: `ONERR GOTO line` catches errors. `PEEK(222)` gives the error code after an error.

### 6502 Assembly

- **`RTS` is required.** When using `call()`, your code must end with `RTS` or the emulator will crash/hang.
- **The ca65 assembler is used.** Use `.org $6000` for the origin. Labels, `.byte`, `.word`, `.proc` all work.
- **$6000 is the standard load address** for assembly programs. It's in free RAM above BASIC and below DOS.
- **Key ROM routines:**
  - `$FDED` (COUT) — Print character in A register
  - `$FD0C` (GETLN) — Read line of input
  - `$FC58` (HOME) — Clear screen
  - `$FBDD` (BELL) — Beep
  - `$FE89` (SETKBD) — Reset input to keyboard
  - `$FE93` (SETVID) — Reset output to screen
- **Zero page $00-$FF is shared** with BASIC and the system. Use $06-$09 and $EB-$EF for temporary storage.
- **Stack is at $100-$1FF.** Only 256 bytes. Deep recursion will overflow.
- **Self-modifying code works** and is common on the 6502. No instruction cache to worry about.
- **Preserve Y register in loops** — Y register corruption in display routines is a common cause of crashes.

### Memory Banking & Soft Switches

This is the #1 source of confusion for Apple IIe development.

- **peek/poke/load_binary respect Apple IIe soft switches.** They are NOT raw physical RAM access. They go through the same memory banking logic the CPU uses.
- **The Apple IIe has 128KB of RAM** mapped into a 64KB address space via soft switches.
- **After ProDOS boots**, the Language Card is mapped. Peeking $D000-$FFFF returns ProDOS code, not Applesoft ROM. This is normal.
- **After a cold boot with no disk**, all switches are off — peek/poke access main RAM and ROM as expected.
- **If RAMWRT is active**, poking $0800 writes to **aux** RAM, not main RAM. Your data goes somewhere you didn't expect.

Key soft switches:

| Switch | Read Address | Effect |
|--------|-------------|--------|
| RAMRD | $C013 | peek reads aux RAM for $0200-$BFFF |
| RAMWRT | $C014 | poke/load_binary write aux RAM for $0200-$BFFF |
| ALTZP | $C016 | peek/poke access aux zero page + stack ($00-$01FF) |
| 80STORE+PAGE2 | $C018+$C01C | peek/poke access aux text page ($0400-$07FF) and aux HGR ($2000-$3FFF) |
| Language Card | varies | peek $D000-$FFFF reads LC RAM instead of ROM |

### Disk Images — The Big Gotchas

**NEVER try to write ProDOS disk structures from scratch.** The sector interleaving, boot blocks, volume directory headers, bitmap allocation, and directory entry formats are incredibly fiddly. Every project that has tried to write them by hand has spent hours debugging. Use the tools instead.

#### .dsk vs .po Format

| Extension | Format | When to use |
|-----------|--------|-------------|
| `.dsk` | DOS-order | **Always use this.** Works with hardware emulators (FloppyEmu). |
| `.po` | ProDOS-order | Rare. Sequential blocks. Don't use unless you have a reason. |

#### Sector Interleaving (Critical!)

In a `.dsk` file, ProDOS blocks do NOT map to sequential byte offsets. Each 512-byte block spans two 256-byte sectors, and the sectors are interleaved:

```python
PRODOS_INTERLEAVE = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15]

def read_block(disk_data, block_num):
    track = block_num // 8
    block_in_track = block_num % 8
    sector1 = PRODOS_INTERLEAVE[block_in_track * 2]
    sector2 = PRODOS_INTERLEAVE[block_in_track * 2 + 1]
    offset1 = (track * 16 + sector1) * 256
    offset2 = (track * 16 + sector2) * 256
    return disk_data[offset1:offset1+256] + disk_data[offset2:offset2+256]
```

If you read/write blocks at `block * 512` without interleaving, the disk will appear corrupt to ProDOS.

#### Making a Bootable ProDOS Disk

The easy way — copy a template and modify it:

```
# 1. Start from a working ProDOS disk
cp disks/ProDOS_2_4.dsk disks/mydisk.dsk

# 2. Remove files you don't need
prodos_del(disk="disks/mydisk.dsk", name="UNWANTED")

# 3. Add your files
prodos_add(disk="disks/mydisk.dsk", file="build/MY.BIN", name="MY.BIN", type="BIN", addr="6000")

# 4. Verify
prodos_list(disk="disks/mydisk.dsk")
```

Requirements for a ProDOS disk to boot:
1. **Blocks 0-1**: Valid boot loader code (copy from ProDOS_2_4.dsk)
2. **Block 2**: Valid Volume Directory Header
3. **File named `PRODOS`** (type SYS/$FF) — the OS kernel
4. **A `.SYSTEM` file** (type SYS/$FF) — ProDOS runs the first one alphabetically. `BASIC.SYSTEM` gives you the `]` prompt.
5. **Volume bitmap** (block 6) correctly tracks which blocks are free/used
6. **Directory entries** have correct storage types, key blocks, and file sizes

#### Auto-Run a BASIC Program on Boot

Create a file named `STARTUP` (type BAS/$FC, aux $0801) containing your program. `BASIC.SYSTEM` automatically runs it on boot.

#### ProDOS File Types

| Type | Code | Aux Type | Notes |
|------|------|----------|-------|
| BIN | $06 | Load address | Binary, aux = where to load (e.g., $6000) |
| SYS | $FF | $0000 or $2000 | System executable, runs at $2000 |
| BAS | $FC | $0801 | Applesoft BASIC tokenized program |
| TXT | $04 | $0000 | Text file |

**BIN files MUST have correct aux type.** If you add a BIN file with aux type $0000, it loads at address $0000 which overwrites zero page and crashes. Set aux to the actual load address.

#### DOS 3.3 Disks

DOS 3.3 is simpler but a different OS. Use `create_disk()` + `save_basic_to_disk()` for DOS 3.3 disks. They're easier to create but less capable than ProDOS.

### Graphics Modes

| Mode | Resolution | Colors | BASIC Command | Capture Tool |
|------|-----------|--------|---------------|-------------|
| Text | 40x24 chars | 1 | `TEXT` | `read_screen` |
| Lo-res (GR) | 40x48 pixels | 16 | `GR` | `capture_gr` |
| Hi-res (HGR) | 280x192 pixels | 6 | `HGR` | `capture_hgr` |
| Double lo-res | 80x48 pixels | 16 | (//e only) | `capture_dgr` |
| Double hi-res | 560x192 pixels | 16 | (//e only) | `capture_dhgr` |

- **GR and HGR both clear the screen** when called. Plan your drawing order accordingly.
- **Mixed mode**: By default GR and HGR show 4 lines of text at the bottom. `POKE -16302,0` gives full-screen graphics.
- **HGR color is weird.** The Apple II generates color from bit patterns and position. Adjacent pixels affect each other's color. Use `HCOLOR=` to set (0=black1, 1=green, 2=violet, 3=white1, 4=black2, 5=orange, 6=blue, 7=white2).
- **Lo-res colors**: 0=black, 1=magenta, 2=dark blue, 3=purple, 4=dark green, 5=grey1, 6=medium blue, 7=light blue, 8=brown, 9=orange, 10=grey2, 11=pink, 12=green, 13=yellow, 14=aqua, 15=white.

### HGR Row Address Calculation

HGR memory is NOT linear. Rows are interleaved across three 2KB groups. For row Y (0-191):

```
addr = $2000 + (Y & 7) * $0400 + ((Y>>3) & 7) * $0080 + (Y>>6) * $0028
```

- **Y & 7** (sub-row 0-7): selects which 1KB block ($0400 apart)
- **(Y>>3) & 7** (row-in-group 0-7): offset by $0080 each
- **Y >> 6** (group 0-2): offset by $0028 (40 decimal) each

For a fixed range of rows, **use lookup tables** — faster and avoids gnarly 6502 math.

### Double Hi-Res (DHGR) — //e Only

560x192 mono or 140x192 with 16 colors. Uses BOTH main and auxiliary RAM at $2000-$3FFF. Each scan line is 80 bytes: 40 from AUX interleaved with 40 from MAIN.

**Pixel layout per line:** `AUX[0] MAIN[0] AUX[1] MAIN[1] ... AUX[39] MAIN[39]`

Each byte holds 7 pixels (bit 7 unused). 80 bytes x 7 = 560 pixels/line.

**Soft switches to enable DHGR** (order matters — set 80STORE/80COL first):

| Switch | Address | Purpose |
|--------|---------|---------|
| 80STORE on | $C001 | PAGE2 routes $2000-$3FFF to AUX |
| 80COL on | $C00D | Enable 80-column hardware |
| TXTCLR | $C050 | Graphics mode |
| MIXCLR | $C052 | Full screen (no text window) |
| HIRES | $C057 | Hi-res mode |
| AN3OFF | $C05E | Enable double hi-res |

**Writing AUX vs MAIN** (with 80STORE enabled):
- `bit $C055` (PAGE2 on) → writes to $2000-$3FFF go to **AUX** RAM
- `bit $C054` (PAGE2 off) → writes to $2000-$3FFF go to **MAIN** RAM

You must write to both banks to fill the screen.

**DHGR Gotchas:**
- HGR memory is interleaved, not linear — use the row address formula or lookup tables
- Must write BOTH AUX and MAIN or half the pixels are black
- $7F = all 7 pixels on (white), $00 = all off
- 80STORE MUST be on for PAGE2 ($C054/$C055) to bank $2000-$3FFF. Without it, PAGE2 selects display page instead.
- `bit` works for all //e soft switches — they trigger on any access

**To exit DHGR back to text:** `bit $C05F` (AN3ON), `bit $C056` (LORES), `bit $C051` (TXTSET), `bit $C000` (80STORE off), `bit $C00C` (80COL off)

### Common Mistakes

1. **Forgetting `read_screen` or `capture_*` after running code.** You can't see what happened unless you capture the screen.
2. **Using `reset` when you need `shutdown` + `boot`.** Cold reset doesn't reload ProDOS from disk. If things are broken, do a full shutdown + boot.
3. **Writing BASIC in lowercase.** Apple II BASIC is uppercase only. The `type_text` tool auto-uppercases, but `inject_tokenized_basic` expects you to write it correctly.
4. **Not ending assembly with `RTS`.** If you `call()` code that doesn't return, the emulator hangs.
5. **Assuming memory state after ProDOS boot.** The Language Card is mapped, BASIC program space may have a STARTUP program loaded, etc.
6. **Trying to use disk commands without DOS/ProDOS.** `load_basic_env()` gives you bare BASIC — no SAVE, LOAD, CATALOG, etc. Use `load_prodos_env()` or `load_dos33_env()` if you need disk commands.
7. **Building ProDOS disks from scratch.** Just don't. Copy a template. See "Disk Images" section above.
8. **Passing hex through the conversation.** Use `inject_tokenized_basic(source=...)` and `assemble(source=...)` — they handle everything server-side. For binary data files (sprites, fonts, tables), write to a file and use `load_file(path=..., address=...)` instead of `load_binary(hex_data=...)`.

## Apple II Memory Map

| Address | Contents |
|---------|----------|
| $0000-$00FF | Zero page (shared with BASIC/system) |
| $0100-$01FF | Stack |
| $0200-$02FF | Input buffer |
| $0300-$03FF | Vectors, DOS/ProDOS hooks |
| $0400-$07FF | Text page 1 / Lo-res page 1 |
| $0800-$0BFF | Text page 2 / Lo-res page 2 |
| $0801+ | BASIC program storage (starts after length byte) |
| $2000-$3FFF | Hi-res page 1 (8KB) |
| $4000-$5FFF | Hi-res page 2 (8KB) |
| $6000-$95FF | Free RAM (good for assembly programs) |
| $9600-$BFFF | DOS 3.3 / ProDOS area (if loaded) |
| $C000-$C0FF | Soft switches (I/O) |
| $C100-$C7FF | Slot ROM |
| $D000-$FFFF | ROM or Language Card RAM |

## Common Workflows

### Test a BASIC program
```
load_basic_env()
inject_tokenized_basic(source="10 FOR I=1 TO 10\n20 PRINT I\n30 NEXT", auto_run=true)
read_screen()
```

### Test hi-res graphics
```
load_basic_env()
inject_tokenized_basic(source="10 HGR\n20 HPLOT 0,0 TO 279,191", auto_run=true)
capture_hgr(format="png")
```

### Test lo-res graphics
```
load_basic_env()
inject_tokenized_basic(source="10 GR\n20 COLOR=1\n30 FOR I=0 TO 39\n40 VLIN 0,39 AT I\n50 COLOR=COLOR+1\n60 IF COLOR>15 THEN COLOR=0\n70 NEXT", auto_run=true)
capture_gr(format="png")
```

### Assemble and run machine code
```
load_basic_env()
assemble(source=".org $6000\n  LDA #$C1\n  JSR $FDED\n  RTS", load_address=24576)
call(address=24576)
read_screen()
```

### Save program to disk
```
save_basic_to_disk(disk_filename="/tmp/mydisk.dsk", program_name="MYPROG", source="10 PRINT \"HI\"\n20 END")
```

### Interactive program (with GET/keyboard input)
```
load_basic_env()
inject_tokenized_basic(source="10 GET A$\n20 PRINT A$;\n30 GOTO 10", auto_run=true)
# Use send_keys_and_capture to interact:
send_keys_and_capture(keys="HELLO", capture_mode="text")
```
