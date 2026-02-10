# ProDOS Machine Language Interface (MLI) Reference

## Calling the MLI

All MLI calls follow the same pattern: `JSR $BF00` followed by the call number byte and a two-byte pointer to the parameter list.

```asm
    JSR $BF00        ; MLI entry point
    .byte $C8        ; Call number (OPEN in this example)
    .word params     ; Pointer to parameter list (low byte first)
    BCS error        ; Carry set = error, A = error code
```

On return:
- **Success**: Carry flag clear, A = $00
- **Error**: Carry flag set, A = error code

### Parameter List Format

Each call has a fixed-length parameter list. The first byte is always the parameter count. Subsequent bytes are the parameters for that call.

```asm
params:
    .byte $03        ; Parameter count
    .word pathname   ; First parameter (pointer to pathname)
    .word $2000      ; Second parameter (I/O buffer)
    .byte $00        ; Third parameter (ref_num, filled on return)
```

### Pathname Format

ProDOS pathnames are Pascal-style strings: first byte is the length, followed by the characters. Maximum 64 characters. Slash-delimited.

```asm
pathname:
    .byte 13         ; Length
    .byte "/MYVOLUME/FILE"
```

---

## Housekeeping Calls

### CREATE ($C0) -- Create File or Directory

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $07 |
| +1 | 2 | pathname | Pointer to pathname |
| +3 | 1 | access | Access attributes (see below) |
| +4 | 1 | file_type | File type code |
| +5 | 2 | aux_type | Auxiliary type (e.g., load address for BIN) |
| +7 | 1 | storage_type | $01=seedling, $02=sapling, $0D=directory |
| +8 | 2 | create_date | Creation date |
| +10 | 2 | create_time | Creation time |

### DESTROY ($C1) -- Delete File

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $01 |
| +1 | 2 | pathname | Pointer to pathname |

### RENAME ($C2) -- Rename File

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $02 |
| +1 | 2 | pathname | Pointer to old pathname |
| +3 | 2 | new_pathname | Pointer to new pathname |

### SET_FILE_INFO ($C3) -- Set File Attributes

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $07 |
| +1 | 2 | pathname | Pointer to pathname |
| +3 | 1 | access | New access attributes |
| +4 | 1 | file_type | New file type |
| +5 | 2 | aux_type | New auxiliary type |
| +7 | 3 | (unused) | Must be present but ignored |
| +10 | 2 | mod_date | Modification date |
| +12 | 2 | mod_time | Modification time |

### GET_FILE_INFO ($C4) -- Get File Attributes

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $0A |
| +1 | 2 | pathname | in | Pointer to pathname |
| +3 | 1 | access | out | Access attributes |
| +4 | 1 | file_type | out | File type |
| +5 | 2 | aux_type | out | Auxiliary type |
| +7 | 1 | storage_type | out | Storage type |
| +8 | 2 | blocks_used | out | Blocks used on disk |
| +10 | 2 | mod_date | out | Modification date |
| +12 | 2 | mod_time | out | Modification time |
| +14 | 2 | create_date | out | Creation date |
| +16 | 2 | create_time | out | Creation time |

### ON_LINE ($C5) -- List Volumes

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $02 |
| +1 | 1 | unit_num | Unit number ($00 = all devices) |
| +2 | 2 | data_buffer | Pointer to 256-byte buffer |

Returns volume names. Unit number format: `DSSS0000` (D=drive, S=slot).

### SET_PREFIX ($C6) -- Set Current Directory

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $01 |
| +1 | 2 | pathname | Pointer to pathname |

### GET_PREFIX ($C7) -- Get Current Directory

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $01 |
| +1 | 2 | data_buffer | Pointer to 64-byte buffer (filled with prefix) |

---

## Filing Calls

### OPEN ($C8) -- Open File

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $03 |
| +1 | 2 | pathname | in | Pointer to pathname |
| +3 | 2 | io_buffer | in | Pointer to 1024-byte I/O buffer (page-aligned) |
| +5 | 1 | ref_num | out | Reference number for subsequent calls |

The I/O buffer must be page-aligned (low byte = $00) and 1024 bytes.

### NEWLINE ($C9) -- Set Newline Mode

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $03 |
| +1 | 1 | ref_num | File reference number |
| +2 | 1 | enable_mask | AND mask for newline detection ($00=disable, $7F=typical) |
| +3 | 1 | newline_char | Newline character ($0D = carriage return) |

When enabled, READ stops at newline characters. The mask is ANDed with each byte before comparing to newline_char.

### READ ($CA) -- Read Data

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $04 |
| +1 | 1 | ref_num | in | File reference number |
| +2 | 2 | data_buffer | in | Pointer to destination buffer |
| +4 | 2 | request_count | in | Number of bytes to read |
| +6 | 2 | trans_count | out | Actual bytes transferred |

### WRITE ($CB) -- Write Data

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $04 |
| +1 | 1 | ref_num | in | File reference number |
| +2 | 2 | data_buffer | in | Pointer to source buffer |
| +4 | 2 | request_count | in | Number of bytes to write |
| +6 | 2 | trans_count | out | Actual bytes transferred |

### CLOSE ($CC) -- Close File

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $01 |
| +1 | 1 | ref_num | File reference number ($00 = close all) |

### FLUSH ($CD) -- Flush File Buffer

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $01 |
| +1 | 1 | ref_num | File reference number ($00 = flush all) |

### SET_MARK ($CE) -- Set File Position

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $02 |
| +1 | 1 | ref_num | File reference number |
| +2 | 3 | position | New position (3-byte, little-endian) |

### GET_MARK ($CF) -- Get File Position

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $02 |
| +1 | 1 | ref_num | in | File reference number |
| +2 | 3 | position | out | Current position (3-byte) |

### SET_EOF ($D0) -- Set File Size

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $02 |
| +1 | 1 | ref_num | File reference number |
| +2 | 3 | eof | New end-of-file (3-byte) |

### GET_EOF ($D1) -- Get File Size

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $02 |
| +1 | 1 | ref_num | in | File reference number |
| +2 | 3 | eof | out | End-of-file position (3-byte) |

### SET_BUF ($D2) -- Change I/O Buffer

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $02 |
| +1 | 1 | ref_num | File reference number |
| +2 | 2 | io_buffer | Pointer to new 1024-byte buffer (page-aligned) |

### GET_BUF ($D3) -- Get I/O Buffer Address

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $02 |
| +1 | 1 | ref_num | in | File reference number |
| +2 | 2 | io_buffer | out | Current buffer address |

---

## System Calls

### GET_TIME ($82) -- Read System Clock

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $00 (no parameters) |

Stores date/time in the ProDOS global page:
- `$BF90-$BF91`: Date (7-bit year, 4-bit month, 5-bit day)
- `$BF92-$BF93`: Time (5-bit hour, 6-bit minute)

### ALLOC_INTERRUPT ($40) -- Register Interrupt Handler

| Offset | Size | Parameter | Direction | Description |
|--------|------|-----------|-----------|-------------|
| +0 | 1 | param_count | in | $02 |
| +1 | 1 | int_num | out | Assigned interrupt number |
| +2 | 2 | int_code | in | Pointer to interrupt handler |

The handler must end with `CLC; RTS` if it handled the interrupt, or `SEC; RTS` if not.

### DEALLOC_INTERRUPT ($41) -- Remove Interrupt Handler

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $01 |
| +1 | 1 | int_num | Interrupt number to remove |

### READ_BLOCK ($80) -- Read Disk Block

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $03 |
| +1 | 1 | unit_num | Unit number (slot/drive) |
| +2 | 2 | data_buffer | Pointer to 512-byte buffer |
| +4 | 2 | block_num | Block number to read |

### WRITE_BLOCK ($81) -- Write Disk Block

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $03 |
| +1 | 1 | unit_num | Unit number (slot/drive) |
| +2 | 2 | data_buffer | Pointer to 512-byte buffer |
| +4 | 2 | block_num | Block number to write |

### QUIT ($65) -- Quit Application

| Offset | Size | Parameter | Description |
|--------|------|-----------|-------------|
| +0 | 1 | param_count | $04 |
| +1 | 1 | quit_type | $00 for standard quit |
| +2 | 2 | (reserved) | Must be $0000 |
| +4 | 1 | (reserved) | Must be $00 |
| +5 | 2 | (reserved) | Must be $0000 |

---

## Access Attributes

Bit field used in CREATE and SET_FILE_INFO:

| Bit | Value | Meaning |
|-----|-------|---------|
| 7 | $80 | Destroy enabled |
| 6 | $40 | Rename enabled |
| 5 | $20 | Backup needed (set when file modified) |
| 2 | $04 | (reserved) |
| 1 | $02 | Write enabled |
| 0 | $01 | Read enabled |

Standard access: `$C3` (destroy + rename + write + read).

---

## File Types

| Code | Name | Description |
|------|------|-------------|
| $00 | UNK | Unknown/typeless |
| $01 | BAD | Bad blocks file |
| $04 | TXT | ASCII text file |
| $06 | BIN | Binary file (aux_type = load address) |
| $0F | DIR | Directory |
| $19 | ADB | AppleWorks database |
| $1A | AWP | AppleWorks word processor |
| $1B | ASP | AppleWorks spreadsheet |
| $EF | PAS | Pascal area |
| $F0 | CMD | ProDOS added command |
| $FA | INT | Integer BASIC program |
| $FB | IVR | Integer BASIC variables |
| $FC | BAS | Applesoft BASIC program (aux_type = $0801) |
| $FD | VAR | Applesoft BASIC variables |
| $FE | REL | Relocatable code (EDASM) |
| $FF | SYS | ProDOS system file (aux_type = $2000) |

---

## Date/Time Format

### Date Word (2 bytes)

```
Bits: 15-9    8-5     4-0
      YYYYYYY MMMM    DDDDD
      year    month   day
```

Year is 0-99 (add 1900, or 2000 if < 40).

### Time Word (2 bytes)

```
Bits: 15-13   12-8    7-5     4-0
      000     HHHHH   000     MMMMMM
              hour            minute
```

---

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| $00 | | No error |
| $01 | | Bad system call number |
| $04 | | Bad parameter count |
| $25 | | Interrupt table full |
| $27 | | I/O error |
| $28 | | No device connected |
| $2B | | Disk write protected |
| $2E | | Disk switched |
| $40 | | Invalid pathname syntax |
| $42 | | File Control Block table full (too many open files) |
| $43 | | Invalid reference number |
| $44 | | Path not found (directory in path does not exist) |
| $45 | | Volume directory not found |
| $46 | | File not found |
| $47 | | Duplicate filename |
| $48 | | Overrun error (volume full) |
| $49 | | Volume directory full |
| $4B | | Unsupported storage type |
| $4C | | End of file encountered |
| $4D | | Position out of range |
| $4E | | Access error (file locked or insufficient permissions) |
| $50 | | File is open (cannot destroy/rename open file) |
| $51 | | Directory count error |
| $52 | | Not a ProDOS disk |
| $53 | | Invalid parameter |
| $55 | | Volume Control Block table full |
| $56 | | Bad buffer address (not page-aligned for I/O buffer) |
| $57 | | Duplicate volume |
| $5A | | Bitmap disk address is impossible |

---

## ProDOS Global Page ($BF00-$BFFF)

Key locations in the ProDOS global page:

| Address | Name | Description |
|---------|------|-------------|
| $BF00 | MLI | Entry point (JMP instruction) |
| $BF06-$BF09 | | MLI version and compatibility |
| $BF10-$BF2F | | Device table |
| $BF30 | DEVNUM | Last device accessed |
| $BF90-$BF91 | DATE | Current date |
| $BF92-$BF93 | TIME | Current time |
| $BF94 | LEVEL | Current interrupt level |
| $BF98 | MACHID | Machine identification byte |
| $BFFF | | End of ProDOS global page |

### Machine ID Byte ($BF98)

| Bit | Meaning |
|-----|---------|
| 7-6 | Machine type: 00=II, 01=II+, 10=IIe, 11=IIc/IIgs |
| 4 | 80-column card present |
| 3 | 128K memory present |
| 1 | Clock present |

---

## Common Patterns

### Open, Read, Close

```asm
; Open file
    JSR $BF00
    .byte $C8            ; OPEN
    .word open_params
    BCS error

; Read entire file
    JSR $BF00
    .byte $CA            ; READ
    .word read_params
    BCS error

; Close file
    JSR $BF00
    .byte $CC            ; CLOSE
    .word close_params
    BCS error
    RTS

open_params:
    .byte $03            ; 3 parameters
    .word filename       ; Pathname
    .word $4000          ; I/O buffer (page-aligned)
    .byte $00            ; Ref num (filled by OPEN)

read_params:
    .byte $04            ; 4 parameters
    .byte $00            ; Ref num (copy from open_params+5)
    .word $6000          ; Data buffer
    .word $2000          ; Request count
    .word $0000          ; Trans count (filled by READ)

close_params:
    .byte $01            ; 1 parameter
    .byte $00            ; Ref num (copy from open_params+5)

filename:
    .byte 11             ; Length
    .byte "/DISK/MYFILE"
```

### Create and Write File

```asm
; Create file
    JSR $BF00
    .byte $C0            ; CREATE
    .word create_params
    BCS error

; Open, write, close...

create_params:
    .byte $07
    .word filename
    .byte $C3            ; Access: full
    .byte $06            ; File type: BIN
    .word $6000          ; Aux type: load address
    .byte $01            ; Storage type: seedling
    .word $0000          ; Create date
    .word $0000          ; Create time
```

### Quit to ProDOS

```asm
    JSR $BF00
    .byte $65            ; QUIT
    .word quit_params

quit_params:
    .byte $04
    .byte $00
    .word $0000
    .byte $00
    .word $0000
```
