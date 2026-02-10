# ca65 Assembler Quick Reference

ca65 is the macro assembler from the cc65 toolchain, targeting the 6502, 65C02, and 65816 CPUs. It produces relocatable object files linked by ld65.

## Command-Line Options

| Option | Description |
|--------|-------------|
| `-o file` | Output file name |
| `-l file` | Create listing file |
| `-g` / `--debug-info` | Generate debug symbols |
| `-t sys` / `--target sys` | Target system (apple2, apple2enh, c64, nes, etc.) |
| `--cpu type` | Set default CPU (6502, 65c02, 65816, etc.) |
| `-D sym[=val]` | Define symbol on command line |
| `-I dir` | Add include search path |
| `--bin-include-dir dir` | Binary include search path |
| `-i` / `--ignore-case` | Case-insensitive identifiers |
| `-s` / `--smart` | Smart operand sizing (65816) |
| `-v` / `--verbose` | Verbose output |
| `-W n` | Warning level (1-2) |
| `--warnings-as-errors` | Treat warnings as errors |
| `-x` / `--expand-macros` | Show macro expansion in listing |

## Number Formats

| Format | Syntax | Example |
|--------|--------|---------|
| Hexadecimal | `$nn` or `0xnn` | `$1A`, `0x1A` |
| Binary | `%nnnn` or `0bnnnn` | `%11010`, `0b11010` |
| Decimal | `nn` | `26` |
| Character | `'c'` | `'A'` (returns $41) |

## Segments

Segments group code and data for placement by the linker. Use predefined segment names or define custom ones.

### Predefined Segments

| Directive | Segment Name | Typical Use |
|-----------|-------------|-------------|
| `.CODE` | CODE | Executable code |
| `.DATA` | DATA | Initialized read-write data |
| `.BSS` | BSS | Uninitialized data (zero-filled) |
| `.RODATA` | RODATA | Read-only data (constants, strings) |
| `.ZEROPAGE` | ZEROPAGE | Zero page variables |

### Custom Segments

```asm
.segment "LOWCODE"      ; Switch to custom segment
    ; code here
.segment "CODE"          ; Switch back to CODE
```

### Save/Restore Segment

```asm
.pushseg                 ; Save current segment
.segment "RODATA"
msg: .asciiz "hello"
.popseg                  ; Restore previous segment
```

## Data Definition Directives

| Directive | Size | Description |
|-----------|------|-------------|
| `.byte` / `.byt` | 1 | Byte values or string literals |
| `.word` | 2 | 16-bit words (little-endian) |
| `.dword` | 4 | 32-bit double words |
| `.dbyt` | 2 | 16-bit words (big-endian / swapped) |
| `.addr` | 2 | 16-bit address values |
| `.faraddr` | 3 | 24-bit far addresses (65816) |
| `.res n [,fill]` | n | Reserve n bytes, optionally filled |
| `.asciiz "str"` | n+1 | Null-terminated string |
| `.incbin "file"` | varies | Include binary file contents |
| `.lobytes` | 1 each | Low bytes of a list of values |
| `.hibytes` | 1 each | High bytes of a list of values |
| `.bankbytes` | 1 each | Bank bytes of a list of values |

### Examples

```asm
.byte $00, $FF, "Hello"
.word $1234, label
.addr start, end
.res 256, $00            ; 256 zero bytes
.asciiz "Press any key"
.incbin "sprite.bin"
.lobytes table, table+1, table+2
.hibytes table, table+1, table+2
```

## Character Mapping

```asm
.charmap $41, $C1        ; Map 'A' to $C1 (Apple II high ASCII)
.pushcharmap             ; Save current mapping
.popcharmap              ; Restore previous mapping
```

Affects string arguments in `.byte` and `.asciiz`.

## Alignment and Address Control

| Directive | Description |
|-----------|-------------|
| `.align n [,fill]` | Align PC to boundary of n bytes |
| `.org addr` | Set program counter (use sparingly with relocatable code) |
| `.reloc` | Return to relocatable mode after .org |

```asm
.align 256               ; Align to page boundary
.align 4, $EA            ; Align to 4 bytes, fill with NOP
```

## Labels and Symbols

### Label Types

```asm
label:                   ; Standard label (global within scope)
@loop:                   ; Cheap local label (scoped between standard labels)
.proc name               ; Procedure label (defines scope)
```

### Symbol Definitions

```asm
CONSTANT = $C000         ; Numeric constant
label := expression      ; Label assignment (marked as label in debugger)
symbol .set value        ; Mutable variable (can be reassigned)
```

### Import/Export

```asm
.export symbol           ; Make symbol available to other modules
.exportzp symbol         ; Export zero-page symbol
.import symbol           ; Import symbol from another module
.importzp symbol         ; Import zero-page symbol
.global symbol           ; Export if defined, import if not
.autoimport +            ; Auto-import undefined symbols
```

## Scoping

### Procedures

```asm
.proc my_routine
    LDA #$00
    RTS
.endproc
```

The label `my_routine` is visible outside; labels inside are scoped.

### Named Scopes

```asm
.scope MyData
    value1: .byte $00
    value2: .byte $00
.endscope

; Access from outside:
LDA MyData::value1
```

### Scope Resolution

```asm
scope::symbol            ; Access symbol in named scope
::symbol                 ; Access global scope explicitly
outer::inner::symbol     ; Nested scope access
```

## Macros

### Basic Macros

```asm
.macro name param1, param2
    LDA param1
    STA param2
.endmacro

; Usage:
name #$42, $0300
```

### Macro Features

```asm
.macro push_regs
    PHA
    TXA
    PHA
    TYA
    PHA
.endmacro

.macro add16 addr, value
    .local skip
    CLC
    LDA addr
    ADC #<(value)
    STA addr
    LDA addr+1
    ADC #>(value)
    STA addr+1
skip:
.endmacro
```

| Feature | Description |
|---------|-------------|
| `.local sym` | Declare local symbol (unique per expansion) |
| `.exitmacro` / `.exitmac` | Exit macro early |
| `.delmacro name` / `.delmac` | Delete a macro |
| `.paramcount` | Number of parameters passed |

### Define Macros (Token Replacement)

```asm
.define SCREEN $0400
.define COLS 40
.undefine SCREEN
```

Note: `.define` performs low-level token substitution without scoping. Prefer `.macro` or `=` for most uses.

### Macro Packages

```asm
.macpack generic         ; add, sub, bge, blt, etc.
.macpack longbranch      ; jne, jeq, jcc, jcs, etc. (auto-expand)
.macpack apple2          ; scrcode (screen code strings)
```

Available packages: `generic`, `longbranch`, `apple2`, `atari`, `cbm`, `module`.

## Conditional Assembly

### Expression-Based

```asm
.if expression
    ; assembled if expression is non-zero
.elseif expression
    ; alternative condition
.else
    ; fallback
.endif
```

### Symbol-Based

```asm
.ifdef SYMBOL            ; true if SYMBOL is defined
.ifndef SYMBOL           ; true if SYMBOL is not defined
.ifref SYMBOL            ; true if SYMBOL has been referenced
.ifnref SYMBOL           ; true if SYMBOL has not been referenced
```

### Argument-Based (in macros)

```asm
.ifblank arg             ; true if macro argument is blank
.ifnblank arg            ; true if macro argument is not blank
```

### Constant Check

```asm
.ifconst expression      ; true if expression is a compile-time constant
```

### CPU-Based

```asm
.ifp02                   ; true if current CPU is NMOS 6502
.ifpc02                  ; true if 65C02
.ifp816                  ; true if 65816
```

## Repeat Blocks

```asm
.repeat 8
    ASL A
.endrep

; With counter:
.repeat 4, i
    .byte i * 16         ; generates $00, $10, $20, $30
.endrep
```

## Structs and Unions

### Structs

```asm
.struct Point
    xpos .word
    ypos .word
.endstruct

; Usage:
player: .tag Point       ; reserves space for struct

LDA player + Point::xpos
```

### Unions

```asm
.union Value
    as_word .word
    as_bytes .byte 2
.endunion
```

### Nested Structs

```asm
.struct Sprite
    pos  .tag Point
    tile .byte
    attr .byte
.endstruct
```

## Enumerations

```asm
.enum Direction
    NORTH                ; = 0
    SOUTH                ; = 1
    EAST                 ; = 2
    WEST                 ; = 3
.endenum

LDA #Direction::NORTH
```

## CPU Selection

| Directive | CPU |
|-----------|-----|
| `.p02` | NMOS 6502 |
| `.psc02` | 65SC02 |
| `.pc02` | 65C02 (Rockwell extensions) |
| `.pwc02` | W65C02 (with WAI/STP) |
| `.p816` | 65816 |
| `.psweet16` | SWEET 16 virtual CPU |
| `.setcpu "type"` | Set CPU by string name |

### 65816-Specific

```asm
.a8 / .a16              ; Set accumulator size
.i8 / .i16              ; Set index register size
.smart                   ; Auto-track REP/SEP for operand sizing
```

### CPU Save/Restore

```asm
.pushcpu                 ; Save current CPU setting
.p816
; 65816 code here
.popcpu                  ; Restore previous CPU
```

## Pseudo Functions

### Address Extraction

| Function | Alias | Description |
|----------|-------|-------------|
| `.lobyte(expr)` | `<expr` | Bits 0-7 |
| `.hibyte(expr)` | `>expr` | Bits 8-15 |
| `.bankbyte(expr)` | `^expr` | Bits 16-23 |
| `.loword(expr)` | | Bits 0-15 |
| `.hiword(expr)` | | Bits 16-31 |

### Type/State Checking

| Function | Returns true when... |
|----------|---------------------|
| `.blank(arg)` | Argument is empty |
| `.const(expr)` | Expression is compile-time constant |
| `.defined(sym)` / `.def(sym)` | Symbol is defined |
| `.referenced(sym)` / `.ref(sym)` | Symbol has been referenced |
| `.definedmacro(name)` | Macro is defined |
| `.ismnemonic(name)` / `.ismnem(name)` | Name is a valid instruction mnemonic |

### String Functions

| Function | Description |
|----------|-------------|
| `.string(value)` | Convert value to string |
| `.strlen(str)` | Length of string |
| `.strat(str, idx)` | Character value at position |
| `.concat(s1, s2, ...)` | Concatenate strings |
| `.sprintf(fmt, ...)` | Formatted string (C-style) |
| `.ident(str)` | Convert string to identifier |

### Token List Functions

| Function | Description |
|----------|-------------|
| `.tcount(list)` | Count tokens in list |
| `.left(n, list)` | First n tokens |
| `.mid(start, n, list)` | Tokens from position |
| `.right(n, list)` | Last n tokens |
| `.match(l1, l2)` | Compare token types |
| `.xmatch(l1, l2)` | Compare token types and values |

### Numeric Functions

| Function | Description |
|----------|-------------|
| `.max(a, b)` | Maximum of two values |
| `.min(a, b)` | Minimum of two values |
| `.sizeof(sym)` | Size of struct, scope, or segment |
| `.addrsize(sym)` | Address size (0=undef, 1=ZP, 2=ABS, 3=FAR) |

## Pseudo Variables

| Variable | Description |
|----------|-------------|
| `*` | Current program counter |
| `.time` | Assembly time (POSIX seconds) |
| `.version` | Assembler version number |
| `.cpu` | Current CPU type |
| `.asize` | Accumulator size in bits (65816) |
| `.isize` | Index register size in bits (65816) |
| `.paramcount` | Parameter count inside macro |

## Expressions and Operators

### Operator Precedence (highest to lowest)

**1. Unary:**
`+`, `-`, `~` / `.bitnot`, `<` / `.lobyte`, `>` / `.hibyte`, `^` / `.bankbyte`, `!` / `.not`

**2. Multiplicative:**
`*`, `/`, `.mod`, `&` / `.bitand`, `.bitxor`, `<<` / `.shl`, `>>` / `.shr`

**3. Additive:**
`+`, `-`, `|` / `.bitor`

**4. Comparison:**
`=`, `<>`, `<`, `>`, `<=`, `>=`

**5. Boolean:**
`&&` / `.and`, `.xor`, `||` / `.or`

## Error Handling and Assertions

```asm
.assert expression, action, "message"
; action: warning, error, ldwarning, lderror

.error "Unsupported configuration"
.warning "This is deprecated"
.fatal "Cannot continue"
.out "Debug: assembling section X"
```

`ldwarning` and `lderror` defer the check to link time, allowing forward references.

## Includes

```asm
.include "header.inc"    ; Include assembly source
.incbin "data.bin"       ; Include raw binary data
.incbin "data.bin", 10, 256  ; Skip 10 bytes, include 256 bytes
```

## Features

```asm
.feature feature_name [+|-]
```

| Feature | Description |
|---------|-------------|
| `pc_assignment` | Allow `* = $addr` syntax |
| `at_in_identifiers` | Allow `@` in identifiers |
| `dollar_in_identifiers` | Allow `$` in identifiers |
| `leading_dot_in_identifiers` | Allow `.` at start of identifiers |
| `labels_without_colons` | Labels don't need trailing colon |
| `loose_char_term` | Allow `"x"` as character constant |
| `loose_string_term` | Allow `'str'` as string |
| `string_escapes` | Enable `\n`, `\t`, etc. in strings |
| `ubiquitous_idents` | Allow instruction names as identifiers |
| `c_comments` | Allow `/* */` comments |
| `force_range` | Force range checking on `.byte` etc. |
| `underline_in_numbers` | Allow `_` in numeric literals |
| `addrsize` | Allow address size prefix for identifiers |
| `bracket_as_indirect` | Use `[addr]` for indirect addressing |

## Listing Control

```asm
.list                    ; Enable listing output
.listbytes 8             ; Show up to 8 bytes per listing line
.listbytes unlimited     ; Show all bytes
```

## Constructor/Destructor Tables

```asm
.constructor init_func, 10    ; Priority 10 constructor
.destructor cleanup_func, 10  ; Priority 10 destructor
.interruptor irq_handler      ; Interrupt handler
.condes symbol, type [, pri]  ; Generic (type 0-6)
```

Used with ld65 CONDES feature for automatic init/cleanup tables.

## Module Pattern

```asm
; module.s
.include "module.inc"

.export module_init, module_update

.proc module_init
    ; ...
    RTS
.endproc

.proc module_update
    ; ...
    RTS
.endproc
```

```asm
; main.s
.import module_init, module_update

    JSR module_init
    JSR module_update
```

## Common Apple II Patterns

### High ASCII Strings

```asm
.macpack apple2

.rodata
msg: scrcode "HELLO WORLD"    ; Apple II screen codes (high bit set)
     .byte $00                 ; null terminator
```

### Page-Aligned Tables

```asm
.segment "TABLES"
.align 256
sin_table:
    .incbin "sintable.bin"
```

### Long Branches

```asm
.macpack longbranch
    jne far_label            ; Expands to BEQ *+5 / JMP far_label
    jeq far_label            ; Expands to BNE *+5 / JMP far_label
```

Available: `jeq`, `jne`, `jmi`, `jpl`, `jcc`, `jcs`, `jvc`, `jvs`.
