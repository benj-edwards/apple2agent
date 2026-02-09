# Apple II MCP Server — Agent Guide

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

All `load_*_env` tools auto-start the emulator if needed.

### Write and run a BASIC program

```
inject_tokenized_basic(source="10 PRINT \"HELLO\"\n20 GOTO 10", auto_run=true)
```

Use the `source` parameter (not `hex_data`) — it tokenizes server-side and avoids wasting tokens on hex strings.

### Write and run 6502 assembly

```
assemble(source=".org $6000\n  LDA #$41\n  JSR $FDED\n  RTS", load_address=24576)
call(address=24576)
```

`assemble` auto-loads the binary into emulator memory. Just `call()` to execute.

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
| `assemble()` then `load_binary(hex_data=...)` | `assemble(source="...")` — auto-loads |

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
| `load_binary` | Load hex string into memory |

**Memory banking**: peek/poke/load_binary respect Apple IIe soft switches (RAMRD, RAMWRT, ALTZP, 80STORE, Language Card). After ProDOS boots, peeking $D000-$FFFF returns ProDOS code, not ROM. After cold boot, all switches are off — you get main RAM and ROM.

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
| `assemble` | Assemble ca65 source and auto-load into memory |
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

## Bootable ProDOS Disks

Do NOT write ProDOS disk structures from scratch. Use the provided tools:

```bash
# Copy a bootable template, then add/remove files
cp disks/ProDOS_2_4.dsk disks/mydisk.dsk
prodos_del(disk="disks/mydisk.dsk", name="UNWANTED.FILE")
prodos_add(disk="disks/mydisk.dsk", file="build/MY.BIN", name="MY.BIN", type="BIN", addr="6000")
```

Requirements for a bootable ProDOS disk:
1. Blocks 0-1: Valid boot code (copy from ProDOS_2_4.dsk)
2. File named `PRODOS` (type SYS) — the OS kernel
3. A `.SYSTEM` file (type SYS) — first one alphabetically runs on boot
4. Correct volume bitmap and directory entries

See `bootable_disk_instructions.md` in the project root for full details.

## Apple II Memory Map

| Address | Contents |
|---------|----------|
| $0000-$00FF | Zero page |
| $0100-$01FF | Stack |
| $0200-$02FF | Input buffer |
| $0300-$03FF | Vectors, DOS hooks |
| $0400-$07FF | Text page 1 / Lo-res page 1 |
| $0800-$0BFF | Text page 2 / Lo-res page 2 |
| $0801+ | BASIC program storage |
| $2000-$3FFF | Hi-res page 1 |
| $4000-$5FFF | Hi-res page 2 |
| $6000-$95FF | Free RAM (good for assembly programs) |
| $C000-$C0FF | Soft switches (I/O) |
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
