# 6502 Instruction Set Reference

## Registers

| Register | Size | Purpose |
|----------|------|---------|
| A | 8-bit | Accumulator |
| X | 8-bit | Index register |
| Y | 8-bit | Index register |
| PC | 16-bit | Program counter |
| SP | 8-bit | Stack pointer ($0100-$01FF) |
| P | 8-bit | Status register (NV-BDIZC) |

## Status Flags

| Bit | Flag | Name |
|-----|------|------|
| 7 | N | Negative (bit 7 of result) |
| 6 | V | Overflow |
| 5 | - | Unused (always 1) |
| 4 | B | Break (set by BRK, not by IRQ) |
| 3 | D | Decimal mode |
| 2 | I | Interrupt disable |
| 1 | Z | Zero |
| 0 | C | Carry |

## Addressing Modes

| Mode | Syntax | Bytes | Example |
|------|--------|-------|---------|
| Implied | | 1 | CLC |
| Accumulator | A | 1 | LSR A |
| Immediate | #nn | 2 | LDA #$42 |
| Zero Page | nn | 2 | LDA $42 |
| Zero Page,X | nn,X | 2 | LDA $42,X |
| Zero Page,Y | nn,Y | 2 | LDX $42,Y |
| Absolute | nnnn | 3 | LDA $1234 |
| Absolute,X | nnnn,X | 3 | LDA $1234,X |
| Absolute,Y | nnnn,Y | 3 | LDA $1234,Y |
| Indirect | (nnnn) | 3 | JMP ($1234) |
| (Indirect,X) | (nn,X) | 2 | LDA ($42,X) |
| (Indirect),Y | (nn),Y | 2 | LDA ($42),Y |
| Relative | +/-nn | 2 | BNE label |

Note: Modes marked with * add 1 cycle if page boundary crossed. Branches add 1 cycle if taken, 2 if taken across page boundary.

## Instructions by Category

### Load/Store

| Mnemonic | Description | Flags | Modes |
|----------|-------------|-------|-------|
| LDA | Load Accumulator | NZ | imm,zp,zp.X,abs,abs.X*,abs.Y*,(ind.X),(ind).Y* |
| LDX | Load X Register | NZ | imm,zp,zp.Y,abs,abs.Y* |
| LDY | Load Y Register | NZ | imm,zp,zp.X,abs,abs.X* |
| STA | Store Accumulator | - | zp,zp.X,abs,abs.X,abs.Y,(ind.X),(ind).Y |
| STX | Store X | - | zp,zp.Y,abs |
| STY | Store Y | - | zp,zp.X,abs |

### Transfer

| Mnemonic | Description | Flags | Cycles |
|----------|-------------|-------|--------|
| TAX | A -> X | NZ | 2 |
| TAY | A -> Y | NZ | 2 |
| TXA | X -> A | NZ | 2 |
| TYA | Y -> A | NZ | 2 |
| TSX | SP -> X | NZ | 2 |
| TXS | X -> SP | - | 2 |

### Stack

| Mnemonic | Description | Flags | Cycles |
|----------|-------------|-------|--------|
| PHA | Push A | - | 3 |
| PLA | Pull A | NZ | 4 |
| PHP | Push P (status) | - | 3 |
| PLP | Pull P (status) | all | 4 |

### Arithmetic

| Mnemonic | Description | Flags | Modes |
|----------|-------------|-------|-------|
| ADC | Add with Carry | NVZC | imm,zp,zp.X,abs,abs.X*,abs.Y*,(ind.X),(ind).Y* |
| SBC | Subtract with Carry | NVZC | imm,zp,zp.X,abs,abs.X*,abs.Y*,(ind.X),(ind).Y* |
| CMP | Compare A | NZC | imm,zp,zp.X,abs,abs.X*,abs.Y*,(ind.X),(ind).Y* |
| CPX | Compare X | NZC | imm,zp,abs |
| CPY | Compare Y | NZC | imm,zp,abs |

### Logic

| Mnemonic | Description | Flags | Modes |
|----------|-------------|-------|-------|
| AND | Bitwise AND | NZ | imm,zp,zp.X,abs,abs.X*,abs.Y*,(ind.X),(ind).Y* |
| ORA | Bitwise OR | NZ | imm,zp,zp.X,abs,abs.X*,abs.Y*,(ind.X),(ind).Y* |
| EOR | Bitwise XOR | NZ | imm,zp,zp.X,abs,abs.X*,abs.Y*,(ind.X),(ind).Y* |
| BIT | Bit Test (A AND M) | NVZ | zp,abs |

### Shift/Rotate

| Mnemonic | Description | Flags | Modes |
|----------|-------------|-------|-------|
| ASL | Shift Left | NZC | A,zp,zp.X,abs,abs.X |
| LSR | Shift Right | NZC | A,zp,zp.X,abs,abs.X |
| ROL | Rotate Left | NZC | A,zp,zp.X,abs,abs.X |
| ROR | Rotate Right | NZC | A,zp,zp.X,abs,abs.X |

### Increment/Decrement

| Mnemonic | Description | Flags | Modes |
|----------|-------------|-------|-------|
| INC | Increment Memory | NZ | zp,zp.X,abs,abs.X |
| DEC | Decrement Memory | NZ | zp,zp.X,abs,abs.X |
| INX | Increment X | NZ | implied (2 cycles) |
| INY | Increment Y | NZ | implied (2 cycles) |
| DEX | Decrement X | NZ | implied (2 cycles) |
| DEY | Decrement Y | NZ | implied (2 cycles) |

### Branch (all: 2 bytes, 2+1+1 cycles)

| Mnemonic | Description | Condition |
|----------|-------------|-----------|
| BPL | Branch if Plus | N=0 |
| BMI | Branch if Minus | N=1 |
| BVC | Branch if Overflow Clear | V=0 |
| BVS | Branch if Overflow Set | V=1 |
| BCC | Branch if Carry Clear | C=0 |
| BCS | Branch if Carry Set | C=1 |
| BNE | Branch if Not Equal | Z=0 |
| BEQ | Branch if Equal | Z=1 |

### Jump/Call

| Mnemonic | Description | Cycles |
|----------|-------------|--------|
| JMP abs | Jump | 3 |
| JMP (ind) | Jump Indirect | 5 |
| JSR abs | Jump to Subroutine | 6 |
| RTS | Return from Subroutine | 6 |
| BRK | Software Interrupt | 7 |
| RTI | Return from Interrupt | 6 |

### Flags

| Mnemonic | Description | Cycles |
|----------|-------------|--------|
| CLC | Clear Carry | 2 |
| SEC | Set Carry | 2 |
| CLD | Clear Decimal | 2 |
| SED | Set Decimal | 2 |
| CLI | Clear Interrupt Disable | 2 |
| SEI | Set Interrupt Disable | 2 |
| CLV | Clear Overflow | 2 |

### Other

| Mnemonic | Description | Cycles |
|----------|-------------|--------|
| NOP | No Operation | 2 |

## Cycle Counts by Addressing Mode

| Mode | Read | Read-Modify-Write | Write |
|------|------|--------------------|-------|
| Immediate | 2 | - | - |
| Zero Page | 3 | 5 | 3 |
| Zero Page,X/Y | 4 | 6 | 4 |
| Absolute | 4 | 6 | 4 |
| Absolute,X | 4* | 7 | 5 |
| Absolute,Y | 4* | 7 | 5 |
| (Indirect,X) | 6 | - | 6 |
| (Indirect),Y | 5* | - | 6 |

\* Add 1 cycle if page boundary crossed (read instructions only). Write and RMW instructions always take the extra cycle on absolute indexed modes.

## Opcode Matrix

```
     0    1    2    3    4    5    6    7    8    9    A    B    C    D    E    F
0:  BRK  ORA  ---  ---  ---  ORA  ASL  ---  PHP  ORA  ASL  ---  ---  ORA  ASL  ---
1:  BPL  ORA  ---  ---  ---  ORA  ASL  ---  CLC  ORA  ---  ---  ---  ORA  ASL  ---
2:  JSR  AND  ---  ---  BIT  AND  ROL  ---  PLP  AND  ROL  ---  BIT  AND  ROL  ---
3:  BMI  AND  ---  ---  ---  AND  ROL  ---  SEC  AND  ---  ---  ---  AND  ROL  ---
4:  RTI  EOR  ---  ---  ---  EOR  LSR  ---  PHA  EOR  LSR  ---  JMP  EOR  LSR  ---
5:  BVC  EOR  ---  ---  ---  EOR  LSR  ---  CLI  EOR  ---  ---  ---  EOR  LSR  ---
6:  RTS  ADC  ---  ---  ---  ADC  ROR  ---  PLA  ADC  ROR  ---  JMP  ADC  ROR  ---
7:  BVS  ADC  ---  ---  ---  ADC  ROR  ---  SEI  ADC  ---  ---  ---  ADC  ROR  ---
8:  ---  STA  ---  ---  STY  STA  STX  ---  DEY  ---  TXA  ---  STY  STA  STX  ---
9:  BCC  STA  ---  ---  STY  STA  STX  ---  TYA  STA  TXS  ---  ---  STA  ---  ---
A:  LDY  LDA  LDX  ---  LDY  LDA  LDX  ---  TAY  LDA  TAX  ---  LDY  LDA  LDX  ---
B:  BCS  LDA  ---  ---  LDY  LDA  LDX  ---  CLV  LDA  TSX  ---  LDY  LDA  LDX  ---
C:  CPY  CMP  ---  ---  CPY  CMP  DEC  ---  INY  CMP  DEX  ---  CPY  CMP  DEC  ---
D:  BNE  CMP  ---  ---  ---  CMP  DEC  ---  CLD  CMP  ---  ---  ---  CMP  DEC  ---
E:  CPX  SBC  ---  ---  CPX  SBC  INC  ---  INX  SBC  NOP  ---  CPX  SBC  INC  ---
F:  BEQ  SBC  ---  ---  ---  SBC  INC  ---  SED  SBC  ---  ---  ---  SBC  INC  ---
```

Entries marked `---` are undefined opcodes on the NMOS 6502.

## Common Patterns

### 16-bit Addition

```asm
CLC
LDA lo_byte
ADC #$01
STA lo_byte
LDA hi_byte
ADC #$00
STA hi_byte
```

### 16-bit Comparison

```asm
LDA hi_byte
CMP #>target    ; compare high byte first
BNE done
LDA lo_byte
CMP #<target    ; then low byte
done:
```

### Multiply by 2

```asm
ASL A           ; shift left = x2
```

### Divide by 2

```asm
LSR A           ; shift right = /2
```

### Indirect Indexed Loop (common pattern)

```asm
    LDY #$00
loop:
    LDA (ptr),Y
    BEQ done
    JSR process
    INY
    BNE loop
done:
```

### Negate A (two's complement)

```asm
EOR #$FF
CLC
ADC #$01
```

### Copy Memory Block

```asm
    LDY #$00
loop:
    LDA (src),Y
    STA (dst),Y
    INY
    CPY #count
    BNE loop
```

### Delay Loop

```asm
    LDX #$FF
delay:
    DEX
    BNE delay     ; 5 cycles per iteration = 1275 cycles
```

## Gotchas

- **JMP indirect bug**: JMP ($xxFF) reads the low byte from $xxFF and high byte from $xx00 (not $xx00+$0100). Never place an indirect JMP target at a page boundary.
- **Decimal mode**: ADC/SBC behavior changes in decimal mode. Always CLD before normal math.
- **BRK pushes PC+2**: Despite being a 1-byte instruction, BRK pushes PC+2. The byte after BRK is skipped on RTI.
- **Carry for subtraction**: SBC requires SEC first (opposite of ADC which needs CLC).
- **Page crossing penalty**: Indexed modes (abs,X abs,Y (ind),Y) add 1 cycle when crossing a page boundary. Read-modify-write instructions (ASL, LSR, ROL, ROR, INC, DEC) on abs,X always take the extra cycle.
- **Stack wraps**: SP wraps around within $0100-$01FF. Overflow/underflow silently wraps.
- **RTS adds 1 to PC**: JSR pushes PC-1 (address of last byte of JSR instruction). RTS pulls it and adds 1. When using RTS tricks, push target address minus 1.
- **BIT sets N and V from memory**: BIT copies bits 7 and 6 of the memory operand into N and V flags, regardless of the AND result. Useful for testing I/O status registers.
