# Apple II ROM Entry Points

## Monitor Routines ($F800-$FFFF)

### Lo-Res Graphics

| Address | Name | Description |
|---------|------|-------------|
| $F800 | PLOT | Plot lo-res point (Y=row, A=color) |
| $F819 | HLINE | Draw horizontal lo-res line |
| $F828 | VLINE | Draw vertical lo-res line |
| $F832 | CLRSCR | Clear full lo-res screen |
| $F836 | CLRTOP | Clear lo-res screen top only |
| $F847 | GBASCALC | Calculate text/lo-res base address for line in A |
| $F856 | NEXTCOL | Increment horizontal color position |
| $F85F | SETCOL | Set lo-res color from A register |
| $F871 | SCRN | Read lo-res color at (Y,A) position |

#### Lo-Res Graphics Usage

PLOT: Set Y to row (0-47), A to color (0-15). The column must be set in $2C (H2).

```asm
    LDA #$01        ; Color 1 (red)
    JSR $F85F       ; SETCOL
    LDY #$10        ; Row 16
    LDA #$05        ; Column 5
    STA $2C         ; Set H2
    JSR $F800       ; PLOT
```

HLINE: Draws from column in $2C (H2) to column in A, at row Y.

```asm
    LDA #$0D        ; Color 13 (yellow)
    JSR $F85F       ; SETCOL
    LDA #$00        ; Start column
    STA $2C         ; H2
    LDY #$10        ; Row 16
    LDA #$27        ; End column (39)
    JSR $F819       ; HLINE
```

VLINE: Draws from row in A to row in $2D (V2), at column in Y.

```asm
    LDA #$0A        ; Color 10 (gray)
    JSR $F85F       ; SETCOL
    LDA #$00        ; Start row
    LDY #$14        ; Column 20
    LDX #$2F        ; End row (47)
    STX $2D         ; V2
    JSR $F828       ; VLINE
```

### Text Output

| Address | Name | Description |
|---------|------|-------------|
| $FDED | COUT | Print character in A (handles control chars) |
| $FDF0 | COUT1 | Print character in A (no control char processing) |
| $FD8E | CROUT | Print carriage return |
| $FD8B | CROUT1 | Clear to EOL then carriage return |
| $FDDA | PRBYTE | Print A register as two hex digits |
| $FDE3 | PRHEX | Print low nibble of A as hex digit |
| $F940 | PRNTYX | Print Y then X registers as hex |
| $F941 | PRNTAX | Print A then X registers as hex |
| $F944 | PRNTX | Print X register as hex |
| $F948 | PRBLNK | Print three spaces |
| $F94A | PRBL2 | Print X spaces |

#### Text Output Usage

COUT handles control characters and scrolling. Characters should have the high bit set for normal display (add $80 to ASCII).

```asm
    LDA #$C8        ; 'H' + $80
    JSR $FDED       ; COUT
    LDA #$C9        ; 'I' + $80
    JSR $FDED       ; COUT
    JSR $FD8E       ; CROUT (carriage return)
```

PRBYTE prints the accumulator as two hex digits:

```asm
    LDA #$4F        ; Value to display
    JSR $FDDA       ; Prints "4F"
```

### Text Input

| Address | Name | Description |
|---------|------|-------------|
| $FD0C | GETLN | Read line of input to $200, return length in X |
| $FD1B | GETLN1 | Read line with no prompt |
| $FD6A | GETLNZ | Print CR then fall into GETLN |

GETLN prints the prompt character (from $33), then reads characters into the input buffer at $0200 until RETURN is pressed. Returns with X = number of characters entered.

```asm
    LDA #$BD        ; Set prompt to '='
    STA $33
    JSR $FD0C       ; GETLN - input at $0200, length in X
```

### Cursor and Screen Control

| Address | Name | Description |
|---------|------|-------------|
| $FC58 | HOME | Clear screen and home cursor |
| $FC62 | CLREOL | Clear from cursor to end of line |
| $FC66 | CLREOP | Clear from cursor to end of page |
| $FC10 | BS | Move cursor left (backspace) |
| $FC1A | UP | Move cursor up one line |
| $FC22 | VTAB | Position cursor using CV ($25) |
| $FC24 | VTABZ | Position cursor at row A |
| $FC42 | CLREOLZ | Clear to end of line (internal) |
| $FC9C | CLRLN | Clear current line |
| $FC70 | SCROLL | Scroll text window up one line |

#### Cursor Positioning

To position the cursor, set CH ($24) for column and CV ($25) for row, then call VTAB:

```asm
    LDA #$0A        ; Column 10
    STA $24         ; CH
    LDA #$05        ; Row 5
    STA $25         ; CV
    JSR $FC22       ; VTAB (sets base address from CV)
```

Or use VTABZ to set row directly from A:

```asm
    LDA #$0A        ; Column 10
    STA $24         ; CH
    LDA #$05        ; Row 5
    JSR $FC24       ; VTABZ
```

### Text Mode Settings

| Address | Name | Description |
|---------|------|-------------|
| $FE80 | SETINV | Set inverse text mode |
| $FE84 | SETNORM | Set normal text mode |
| $FE89 | SETKBD | Reset input to keyboard |
| $FE93 | SETVID | Reset output to screen |

SETINV sets $32 (INVFLG) to $3F. SETNORM sets it to $FF. These affect COUT output.

```asm
    JSR $FE80       ; Inverse mode
    LDA #$C8        ; 'H'
    JSR $FDED       ; Prints in inverse
    JSR $FE84       ; Back to normal
```

### Miscellaneous Monitor Routines

| Address | Name | Description |
|---------|------|-------------|
| $FF2D | PRERR | Print "ERR" |
| $FF3A | BELL | Sound bell (beep) |
| $FF3F | RESTORE | Restore registers from $45-$48 |
| $FF4A | SAVE | Save registers to $45-$48 |
| $FF59 | IORTS | Known RTS instruction (useful for indirect jumps) |
| $FF65 | MON | Enter Monitor |
| $FF69 | MONZ | Enter Monitor (alternate) |

SAVE stores A, X, Y, and P to $45-$48. RESTORE loads them back. Useful for debugging or context switching.

```asm
    JSR $FF4A       ; SAVE - saves A,X,Y,P to $45-$48
    ; ... do something ...
    JSR $FF3F       ; RESTORE - restores A,X,Y,P from $45-$48
```

IORTS at $FF59 is simply an RTS instruction. It can be used as a no-op target for indirect JMP or JSR hooks.

### Wait Routine

| Address | Name | Description |
|---------|------|-------------|
| $FCA8 | WAIT | Delay loop. A = delay value. Waits approximately (A^2)/2 microseconds at 1MHz. |

```asm
    LDA #$80        ; Medium delay
    JSR $FCA8       ; WAIT
```

### Key Input

| Address | Name | Description |
|---------|------|-------------|
| $FD0C | GETLN | Read full line into $200 |
| $FD35 | RDKEY | Read one keypress (waits, returns in A) |
| $FB1E | KEYIN | Low-level keyboard read |

RDKEY calls through the keyboard switch vector ($38-$39), handles flashing cursor, and waits for a keypress. Returns the character in A with high bit set.

```asm
    JSR $FD35       ; RDKEY - wait for key, result in A
    AND #$7F        ; Strip high bit to get ASCII
    CMP #$0D        ; Was it RETURN?
    BEQ got_return
```

---

## Applesoft BASIC ROM ($D000-$F7FF)

### Entry Points

| Address | Name | Description |
|---------|------|-------------|
| $E000 | COLD | Cold start (full initialization) |
| $E003 | WARM | Warm start (to BASIC prompt) |
| $D365 | RUN | Execute program from start |
| $D566 | NEWSTT | Execute next statement |
| $D7D2 | GOTO | Go to line number |
| $D912 | CLEARC | Clear variables (CLEAR command) |
| $DA46 | LIST | List program |
| $DBA0 | FOR | Begin FOR loop |
| $DCF9 | NEXT | NEXT iteration |
| $E6F2 | CLEARSTACK | Clear return stack |

### Expression Evaluation

| Address | Name | Description |
|---------|------|-------------|
| $DD67 | FRMNUM | Evaluate numeric expression, result in FAC |
| $DD7B | FRMEVL | Evaluate any expression |
| $E3D5 | LINGET | Get line number from BASIC text |

### Type Conversion

| Address | Name | Description |
|---------|------|-------------|
| $EB27 | GIVAYF | Convert A (high), Y (low) to floating point in FAC |
| $EB53 | SNGFLT | Convert A to floating point in FAC |
| $EBB2 | FLOAT | Convert 16-bit integer at $62-63 to FAC |

### Output

| Address | Name | Description |
|---------|------|-------------|
| $E10C | OUTDO | Output character in A via COUT with modifications |
| $EE8D | PRNTFAC | Print FAC as decimal number |
| $EF09 | FOUT | Convert FAC to ASCII string at $0100 |

### Error Handling

| Address | Name | Description |
|---------|------|-------------|
| $DF4F | ERROR | Generate error, error number in X |
| $E199 | SYNERR | Generate SYNTAX ERROR |

### Program Structure

| Address | Name | Description |
|---------|------|-------------|
| $DEB8 | PRGEND | Find end of program, set pointers |
| $E752 | GETARYPT | Find or create array variable |
| $E7A0 | NXTSPC | Find next array entry |

### Hi-Res Graphics

| Address | Name | Description |
|---------|------|-------------|
| $F661 | HPLOT | HPLOT routine (plot point at current position) |
| $F411 | HCLR | Clear current hi-res page |
| $F3E2 | HGR2 | Initialize HGR2 mode (page 2, full screen) |
| $F3DE | HGR | Initialize HGR mode (page 1, mixed) |
| $F457 | HFIND | Find Y coordinate in hi-res |
| $F53A | HPOSN | Position hi-res cursor (Y,X = X coord, A = Y coord) |
| $F601 | HLINRL | Draw hi-res line relative |
| $F5CB | HLIN | Draw hi-res line to absolute coordinates |

#### HGR Usage from Assembly

```asm
; Initialize HGR mode
    JSR $F3DE       ; HGR (page 1, mixed mode, clears screen)

; Set color
    LDA #$03        ; White (both bit patterns)
    STA $1C         ; HGR_COLOR ($E5 in enhanced IIe)

; Position cursor at (100, 80)
    LDY #$64        ; X low byte = 100
    LDX #$00        ; X high byte = 0
    LDA #$50        ; Y = 80
    JSR $F53A       ; HPOSN

; Draw line to (200, 120)
    LDY #$C8        ; X low byte = 200
    LDX #$00        ; X high byte = 0
    LDA #$78        ; Y = 120
    JSR $F5CB       ; HLIN (draw line to this point)
```

---

## Keyboard

| Address | Register | Description |
|---------|----------|-------------|
| $C000 | KBD | Read keyboard (bit 7 = key pressed) |
| $C010 | KBDSTRB | Clear keyboard strobe |

```asm
check_key:
    LDA $C000       ; Read keyboard
    BPL no_key      ; Bit 7 clear = no key
    STA $C010       ; Clear strobe
    AND #$7F        ; Strip high bit
    ; A now contains ASCII code
no_key:
```

## Speaker

| Address | Description |
|---------|-------------|
| $C030 | Toggle speaker (read to click) |

```asm
; Simple beep
    LDX #$80
beep:
    LDA $C030       ; Click
    LDY #$20
delay:
    DEY
    BNE delay
    DEX
    BNE beep
```

## Useful Vectors ($03D0-$03FF)

| Address | Name | Description |
|---------|------|-------------|
| $03D0 | WARMSTART | JMP to DOS/ProDOS warm start |
| $03D3 | | JMP to DOS/ProDOS cold start |
| $03EA | DISCONNECT | Disconnect DOS |
| $03F0 | BRKV | Break vector (BRK handler address) |
| $03F2 | SOFTEV | Soft entry vector (Reset handler) |
| $03F4 | PWREDUP | Power-up byte (must match $03F3 EOR #$A5) |
| $03F5-$03F7 | AMPERV | Ampersand (&) vector |
| $03F8-$03FA | USRVEC | USR() function vector |
| $03FB | NMI | Non-maskable interrupt vector |
| $03FE-$03FF | IRQV | IRQ/BRK vector |

### Using the Ampersand Vector

The & command in Applesoft jumps through $03F5. Install your own handler:

```asm
    LDA #$4C        ; JMP opcode
    STA $03F5
    LDA #<handler
    STA $03F6
    LDA #>handler
    STA $03F7
    RTS

handler:
    ; Parse any arguments from BASIC text via CHRGET
    ; TXTPTR ($B8-$B9) points to character after &
    RTS
```

### Setting the Reset Vector

To survive a Ctrl-Reset, set SOFTEV and the power-up byte:

```asm
    LDA #<my_reset
    STA $03F2
    LDA #>my_reset
    STA $03F3
    EOR #$A5
    STA $03F4       ; PWREDUP validation byte
```

### Installing an IRQ Handler

```asm
    SEI             ; Disable interrupts
    LDA #<my_irq
    STA $03FE
    LDA #>my_irq
    STA $03FF
    CLI             ; Enable interrupts

my_irq:
    PHA
    ; Handle interrupt
    PLA
    RTI
```

---

## Floating Point Accumulator (FAC)

The FAC is Applesoft's primary floating point register, located in zero page:

| Address | Description |
|---------|-------------|
| $9D | Exponent (excess-128: $80 = 1.0 exponent) |
| $9E | Mantissa byte 1 (MSB, high bit is assumed 1) |
| $9F | Mantissa byte 2 |
| $A0 | Mantissa byte 3 |
| $A1 | Mantissa byte 4 (LSB) |
| $A2 | Sign ($00 = positive, $FF = negative) |

The secondary accumulator (ARG) is at $A5-$AB with the same format.

### Converting Integer to Float

```asm
; Convert 16-bit value in A (high) and Y (low) to FAC
    LDA #>value     ; High byte
    LDY #<value     ; Low byte
    JSR $EB27       ; GIVAYF

; Convert 8-bit value in A to FAC
    LDA #$2A        ; Value = 42
    JSR $EB53       ; SNGFLT
```

### Printing a Number

```asm
; Print the value currently in FAC
    JSR $EE8D       ; PRNTFAC - prints FAC as decimal

; Or convert to string first
    JSR $EF09       ; FOUT - string at $0100
```

---

## Common ROM Routine Patterns

### Print a String

```asm
print_string:
    LDY #$00
@loop:
    LDA message,Y
    BEQ @done
    ORA #$80        ; Set high bit for COUT
    JSR $FDED       ; COUT
    INY
    BNE @loop
@done:
    RTS

message:
    .byte "HELLO WORLD", $0D, $00
```

### Print a Decimal Number (0-255)

```asm
; Print value in A as decimal
print_dec:
    LDX #$00        ; Suppress leading zeros flag
    CMP #200
    BCC @no200
    SBC #200
    LDX #$02
@no200:
    CMP #100
    BCC @no100
    SBC #100
    INX
@no100:
    PHA
    TXA
    BEQ @no_hundreds
    ORA #$B0        ; Convert to ASCII+$80
    JSR $FDED       ; COUT
@no_hundreds:
    PLA
    TAY
    LDA #$00
    ; Continue with tens/units...
```

For simpler but slower hex output:

```asm
    LDA value
    JSR $FDDA       ; PRBYTE - prints as hex
```

### Clear Screen and Print at Position

```asm
    JSR $FC58       ; HOME
    LDA #$05
    STA $25         ; CV = row 5
    JSR $FC22       ; VTAB
    LDA #$0A
    STA $24         ; CH = column 10
    ; Now print...
    LDA #$C8        ; 'H'
    JSR $FDED
```
