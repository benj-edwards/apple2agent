# ld65 Linker Quick Reference

ld65 is the linker from the cc65 toolchain. It combines relocatable object files from ca65 into executables, using configuration files to define memory layout and segment placement.

## Command-Line Options

| Option | Description |
|--------|-------------|
| `-o name` | Output filename |
| `-t sys` | Target system (apple2, apple2enh, c64, nes, etc.) |
| `-C name` | Use custom config file |
| `-m name` | Generate map file |
| `-vm` | Verbose map (includes all symbols) |
| `-v` | Verbose mode |
| `-D sym=val` | Define external symbol |
| `-L path` | Library search directory |
| `--lib-path path` | Library search path |
| `--obj-path path` | Object file search path |
| `--cfg-path path` | Config file search path |
| `-u sym` | Force symbol import |
| `--dbgfile name` | Generate debug information |
| `-Ln name` | Create VICE label file |
| `-(` / `-)` | Library group (resolve circular deps) |

## Search Path Order

For libraries, objects, and config files:

1. Current directory
2. Directories from command-line options
3. Environment variables (`LD65_LIB`, `LD65_OBJ`, `LD65_CFG`)
4. `CC65_HOME/lib`, `CC65_HOME/obj`, `CC65_HOME/cfg`
5. Built-in defaults

## Configuration File Syntax

Config files are case-insensitive for keywords, case-sensitive for identifiers. Comments use `#` to end of line.

A config file contains these sections:

- `MEMORY { }` -- Define physical memory areas
- `SEGMENTS { }` -- Map segments to memory areas
- `FILES { }` -- Output file settings (optional)
- `FEATURES { }` -- Special linker features (optional)
- `SYMBOLS { }` -- Define linker symbols (optional)

---

## MEMORY Section

Defines physical memory regions. Every memory area requires `start` and `size`.

```
MEMORY {
    ZP:    start = $0000, size = $00FF, type = rw;
    RAM:   start = $0800, size = $BF00, type = rw, file = %O;
    ROM:   start = $C000, size = $4000, type = ro, file = %O, fill = yes;
}
```

### MEMORY Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `start` | Yes | Start address of memory area |
| `size` | Yes | Size in bytes |
| `type` | No | `ro` (read-only) or `rw` (read-write, default) |
| `file` | No | Output file (`%O` = default output, `""` = no output) |
| `fill` | No | Fill unused space (`yes`/`no`, default `no`) |
| `fillval` | No | Fill byte value (0-255, default 0) |
| `define` | No | Export `__NAME_START__`, `__NAME_SIZE__`, `__NAME_LAST__` |
| `bank` | No | Bank number (32-bit value) |

The `%O` placeholder expands to the output filename from `-o`.

---

## SEGMENTS Section

Maps code/data segments to memory areas. Every segment requires `load`.

```
SEGMENTS {
    ZEROPAGE: load = ZP,  type = zp;
    CODE:     load = RAM, type = ro;
    RODATA:   load = RAM, type = ro;
    DATA:     load = ROM, run = RAM, type = rw, define = yes;
    BSS:      load = RAM, type = bss, define = yes;
}
```

### SEGMENTS Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `load` | Yes | Memory area where segment is stored in the binary |
| `run` | No | Memory area where segment executes (default = load) |
| `type` | No | Segment type (see below) |
| `align` | No | Alignment boundary (e.g., $100 for page alignment) |
| `start` | No | Fixed start address within memory area |
| `offset` | No | Fixed offset from start of memory area |
| `define` | No | Export `__NAME_LOAD__`, `__NAME_RUN__`, `__NAME_SIZE__` |
| `fillval` | No | Fill byte for alignment gaps |
| `optional` | No | Suppress warning if segment is empty (`yes`/`no`) |

### Segment Types

| Type | Description |
|------|-------------|
| `ro` | Read-only (code, constant data) |
| `rw` | Read-write (initialized variables) |
| `bss` | Uninitialized data (not written to output file) |
| `zp` | Zero page (8-bit addressing) |
| `overwrite` | Overlays content of another segment |

### Load vs Run Addresses

When `load` and `run` differ, the binary stores the segment at the `load` address, but the code references the `run` address. Startup code must copy data from load to run location.

```
SEGMENTS {
    DATA: load = ROM, run = RAM, type = rw, define = yes;
}
```

This exports three symbols:
- `__DATA_LOAD__` -- Where data is stored in ROM
- `__DATA_RUN__` -- Where data should be at runtime in RAM
- `__DATA_SIZE__` -- Number of bytes to copy

Startup code to copy:

```asm
.import __DATA_LOAD__, __DATA_RUN__, __DATA_SIZE__

    LDX #<__DATA_SIZE__
    BEQ done
copy:
    LDA __DATA_LOAD__-1,X
    STA __DATA_RUN__-1,X
    DEX
    BNE copy
done:
```

### Overwrite Segments

Allow patching content in previously placed segments:

```
SEGMENTS {
    ORIGINAL: load = ROM, type = ro;
    PATCH:    load = ROM, start = $9000, type = overwrite;
}
```

---

## FILES Section

Controls output file format. Default is raw binary.

```
FILES {
    %O: format = bin;
}
```

### Supported Formats

| Format | Description |
|--------|-------------|
| `bin` | Raw binary (default) |
| `o65` | Relocatable format |
| `atari` | Atari XEX executable |

---

## FEATURES Section

Enables special linker features.

### STARTADDRESS

Sets the default start address:

```
FEATURES {
    STARTADDRESS: default = $0800;
}
```

### CONDES (Constructor/Destructor Tables)

Generates tables from `.constructor`, `.destructor`, and `.interruptor` markers in assembly source:

```
FEATURES {
    CONDES:
        segment = RODATA,
        type = constructor,
        label = __CONSTRUCTOR_TABLE__,
        count = __CONSTRUCTOR_COUNT__;
    CONDES:
        segment = RODATA,
        type = destructor,
        label = __DESTRUCTOR_TABLE__,
        count = __DESTRUCTOR_COUNT__;
}
```

| Attribute | Description |
|-----------|-------------|
| `segment` | Segment to place the table in |
| `type` | `constructor`, `destructor`, `interruptor`, or 0-6 |
| `label` | Symbol name for table start |
| `count` | Symbol name for entry count (optional) |
| `order` | `increasing` or `decreasing` priority (default: increasing) |

---

## SYMBOLS Section

Define, export, or import symbols at link time:

```
SYMBOLS {
    __STACKSIZE__:  type = weak, value = $0800;
    __HEAP_START__: type = export, value = __BSS_RUN__ + __BSS_SIZE__;
    __EXTSYM__:     type = import;
}
```

### Symbol Attributes

| Attribute | Description |
|-----------|-------------|
| `type` | `export`, `import`, or `weak` |
| `value` | Symbol value (not for import) |
| `addrsize` | `zp`/`zeropage`, `abs`/`absolute`, `far`, `long` |

`weak` symbols are overridden by any definition in object files.

---

## Library Groups

Resolve circular dependencies between static libraries:

```
ld65 startup.o -(mylib.a otherlib.a-) main.o -o output
```

The linker repeatedly scans grouped libraries until all references are resolved.

---

## Map File

Generated with `-m mapfile`. Contains:

- Module list with segment contributions
- Segment list with addresses and sizes
- Exported symbols sorted by name and value

Use `-vm` for verbose output including empty segments and all symbols.

---

## Common Configurations

### Minimal Raw Binary (no OS)

For standalone 6502 code loaded at a fixed address:

```
MEMORY {
    RAM: start = $6000, size = $2000, file = %O;
}

SEGMENTS {
    CODE:   load = RAM, type = ro;
    RODATA: load = RAM, type = ro;
    DATA:   load = RAM, type = rw;
    BSS:    load = RAM, type = bss;
}
```

### Apple II Binary (BIN file)

For an Apple II binary loaded at $6000 via BRUN:

```
MEMORY {
    ZP:  start = $0080, size = $0080, type = rw;
    RAM: start = $6000, size = $6000, file = %O;
}

SEGMENTS {
    ZEROPAGE: load = ZP,  type = zp;
    CODE:     load = RAM, type = ro;
    RODATA:   load = RAM, type = ro;
    DATA:     load = RAM, type = rw;
    BSS:      load = RAM, type = bss;
}
```

### Apple II with Header

ProDOS binary files sometimes need a 4-byte header (start address + length). You can handle this with a HEADER segment:

```
MEMORY {
    ZP:     start = $0080, size = $0080, type = rw;
    HEADER: start = $0000, size = $0004, file = %O;
    RAM:    start = $2000, size = $8000, file = %O;
}

SEGMENTS {
    ZEROPAGE: load = ZP,     type = zp;
    HEADER:   load = HEADER, type = ro;
    CODE:     load = RAM,    type = ro;
    RODATA:   load = RAM,    type = ro;
    DATA:     load = RAM,    type = rw;
    BSS:      load = RAM,    type = bss;
}
```

### ROM + RAM Split

For code in ROM with data copied to RAM at startup:

```
MEMORY {
    ZP:  start = $0000, size = $0100, type = rw;
    RAM: start = $0200, size = $0600, type = rw;
    ROM: start = $E000, size = $2000, type = ro, file = %O, fill = yes;
}

SEGMENTS {
    ZEROPAGE: load = ZP,  type = zp;
    STARTUP:  load = ROM, type = ro;
    CODE:     load = ROM, type = ro;
    RODATA:   load = ROM, type = ro;
    DATA:     load = ROM, run = RAM, type = rw, define = yes;
    BSS:      load = RAM, type = bss, define = yes;
}
```

### Page-Aligned Tables

Force a data segment to start on a page boundary:

```
SEGMENTS {
    TABLES: load = RAM, type = ro, align = $100;
}
```

### Multiple Output Files

Generate separate ROM images:

```
MEMORY {
    ROM_LO: start = $8000, size = $4000, file = "rom_lo.bin";
    ROM_HI: start = $C000, size = $4000, file = "rom_hi.bin";
}
```

---

## Special Segments

| Segment | Purpose |
|---------|---------|
| `STARTUP` | Runtime initialization, placed at lowest program address |
| `LOWCODE` | Guaranteed non-banked code (safe for interrupt handlers) |
| `ONCE` | One-time initialization code (overlapped after startup) |
| `INIT` | Uninitialized data for constructor use |
| `ZPSAVE` | Original zero-page values (must not be initialized) |

---

## Exported Symbols

When `define = yes` is set on a memory area or segment, these symbols are automatically exported:

### Memory Area Symbols

| Symbol | Description |
|--------|-------------|
| `__NAME_START__` | Start address |
| `__NAME_SIZE__` | Size in bytes |
| `__NAME_LAST__` | Last address (start + size - 1) |

### Segment Symbols

| Symbol | Description |
|--------|-------------|
| `__NAME_LOAD__` | Load address (where stored in binary) |
| `__NAME_RUN__` | Run address (where executed at runtime) |
| `__NAME_SIZE__` | Size in bytes |

---

## Complete Workflow Example

```bash
# Assemble source files
ca65 -t apple2 -o main.o main.s
ca65 -t apple2 -o utils.o utils.s

# Link with custom config
ld65 -C apple2.cfg -o program.bin main.o utils.o

# Link with map file for debugging
ld65 -C apple2.cfg -m program.map -o program.bin main.o utils.o

# Link with debug info
ld65 -C apple2.cfg --dbgfile program.dbg -o program.bin main.o utils.o

# Link with library
ld65 -C apple2.cfg -o program.bin main.o utils.o apple2.lib
```
