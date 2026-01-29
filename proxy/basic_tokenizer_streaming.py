#!/usr/bin/env python3
"""
Applesoft BASIC Tokenizer

Converts ASCII BASIC source code into the tokenized binary format
used by the Apple II. This runs on the proxy server to offload
processing from the 1MHz 6502.

Binary Format:
  Each line: [next_addr:2][line_num:2][tokenized_content][0x00]
  End of program: [0x00][0x00]

Usage:
    from basic_tokenizer import tokenize_program
    binary = tokenize_program("10 PRINT \"HELLO\"\n20 END")
"""

import re
from typing import Tuple, List, Optional

# Applesoft BASIC tokens (in order they must be checked - longest match first)
# Keywords that are substrings of others must come AFTER the longer ones
TOKENS = [
    # Multi-char tokens that contain other tokens - check first
    ('NOTRACE', 0x9C),
    ('HCOLOR=', 0x92),
    ('HIMEM:', 0xA3),
    ('LOMEM:', 0xA4),
    ('ONERR', 0xA5),
    ('RESUME', 0xA6),
    ('RECALL', 0xA7),
    ('RESTORE', 0xAE),
    ('RETURN', 0xB1),
    ('SHLOAD', 0x9A),
    ('NORMAL', 0x9D),
    ('INVERSE', 0x9E),
    ('SCALE=', 0x99),
    ('SPEED=', 0xA9),
    ('GOSUB', 0xB0),
    ('PRINT', 0xBA),
    ('INPUT', 0x84),
    ('FLASH', 0x9F),
    ('COLOR=', 0xA0),
    ('CLEAR', 0xBD),
    ('TRACE', 0x9B),
    ('STORE', 0xA8),
    ('XDRAW', 0x95),
    ('HPLOT', 0x93),
    ('HTAB', 0x96),
    ('VTAB', 0xA2),
    ('HOME', 0x97),
    ('NEXT', 0x82),
    ('DATA', 0x83),
    ('DRAW', 0x94),
    ('WAIT', 0xB5),
    ('LOAD', 0xB6),
    ('SAVE', 0xB7),
    ('POKE', 0xB9),
    ('CONT', 0xBB),
    ('LIST', 0xBC),
    ('PLOT', 0x8D),
    ('HLIN', 0x8E),
    ('VLIN', 0x8F),
    ('HGR2', 0x90),
    ('CALL', 0x8C),
    ('READ', 0x87),
    ('STOP', 0xB3),
    ('TEXT', 0x89),
    ('GOTO', 0xAB),
    ('THEN', 0xC4),
    ('ROT=', 0x98),
    ('FOR', 0x81),
    ('DIM', 0x86),
    ('DEL', 0x85),
    ('DEF', 0xB8),
    ('END', 0x80),
    ('HGR', 0x91),
    ('GET', 0xBE),
    ('NEW', 0xBF),
    ('RUN', 0xAC),
    ('REM', 0xB2),
    ('LET', 0xAA),
    ('POP', 0xA1),
    ('TAB(', 0xC0),
    ('SPC(', 0xC3),
    ('TO', 0xC1),  # MUST be tokenized for FOR...TO to work!
    ('FN', 0xC2),
    ('NOT', 0xC6),
    ('STEP', 0xC7),
    ('SGN', 0xD2),
    ('INT', 0xD3),
    ('ABS', 0xD4),
    ('USR', 0xD5),
    ('FRE', 0xD6),
    ('SCRN(', 0xD7),
    ('PDL', 0xD8),
    ('POS', 0xD9),
    ('SQR', 0xDA),
    ('RND', 0xDB),
    ('LOG', 0xDC),
    ('EXP', 0xDD),
    ('COS', 0xDE),
    ('SIN', 0xDF),
    ('TAN', 0xE0),
    ('ATN', 0xE1),
    ('PEEK', 0xE2),
    ('LEN', 0xE3),
    ('STR$', 0xE4),
    ('VAL', 0xE5),
    ('ASC', 0xE6),
    ('CHR$', 0xE7),
    ('LEFT$', 0xE8),
    ('RIGHT$', 0xE9),
    ('MID$', 0xEA),
    ('AND', 0xCD),
    ('OR', 0xCE),
    ('PR#', 0x8A),
    ('IN#', 0x8B),
    ('GR', 0x88),
    ('ON', 0xB4),
    ('IF', 0xAD),
    ('AT', 0xC5),
    ('&', 0xAF),
    # Operators ARE tokenized in Applesoft (contrary to some documentation)
    ('+', 0xC8),
    ('-', 0xC9),
    ('*', 0xCA),
    ('/', 0xCB),
    ('^', 0xCC),
    ('>', 0xCF),
    ('=', 0xD0),
    ('<', 0xD1),
]

# Build a dict for quick lookup, but we need ordered checking for tokenization
TOKEN_DICT = {keyword: token for keyword, token in TOKENS}


def parse_line_number(line: str) -> Tuple[Optional[int], str]:
    """
    Extract line number from the beginning of a BASIC line.
    Returns (line_number, remaining_content) or (None, original) if no line number.
    """
    match = re.match(r'^(\d+)\s*(.*)$', line.strip())
    if match:
        return int(match.group(1)), match.group(2)
    return None, line


def tokenize_line_content(content: str) -> bytearray:
    """
    Tokenize a single line of BASIC (without line number).
    Handles string literals, REM statements, and DATA statements specially.
    """
    result = bytearray()
    i = 0
    content = content.upper()  # Applesoft is case-insensitive

    in_string = False
    in_rem = False
    in_data = False

    while i < len(content):
        char = content[i]

        # Handle string literals - don't tokenize inside quotes
        if char == '"':
            in_string = not in_string
            result.append(ord('"'))
            i += 1
            continue

        if in_string:
            # Inside string - just copy characters
            if ord(char) < 128:
                result.append(ord(char))
            i += 1
            continue

        # After REM, everything is literal text
        if in_rem:
            if ord(char) < 128:
                result.append(ord(char))
            i += 1
            continue

        # Inside DATA statement - copy until colon or end
        if in_data:
            if char == ':':
                in_data = False
                result.append(ord(':'))
                i += 1
                continue
            if ord(char) < 128:
                result.append(ord(char))
            i += 1
            continue

        # Skip spaces entirely - Apple II tokenizer strips them
        # (spaces are only preserved in strings, REM, and DATA - handled above)
        if char == ' ':
            i += 1
            continue

        # Try to match a token (longest match first)
        matched = False
        remaining = content[i:]

        for keyword, token in TOKENS:
            if remaining.startswith(keyword):
                # Check word boundary for alpha keywords to avoid matching
                # OR inside COLOR, AND inside DEMAND, TO inside GOTO, etc.
                # Operators (+, -, *, /, etc.) don't need boundary checks
                if keyword.isalpha() or keyword.endswith('('):
                    # Check if followed by alphanumeric (part of variable name)
                    end_pos = i + len(keyword)
                    if end_pos < len(content) and content[end_pos].isalnum():
                        continue  # Skip - it's part of a variable name
                    # Check if preceded by alphanumeric (part of variable name)
                    if i > 0 and content[i-1].isalnum():
                        continue  # Skip - it's part of a variable name

                result.append(token)
                i += len(keyword)
                matched = True

                # Check for special cases
                if keyword == 'REM':
                    in_rem = True
                elif keyword == 'DATA':
                    in_data = True
                break

        if not matched:
            # No token match - copy character as-is
            if ord(char) < 128:
                result.append(ord(char))
            i += 1

    return result


def tokenize_program(source: str, start_address: int = 0x0801) -> bytes:
    """
    Convert a complete BASIC program to tokenized binary format.

    Args:
        source: ASCII BASIC source code
        start_address: Memory address where program will be loaded (default $0801)

    Returns:
        Tokenized binary data ready for Apple II memory
    """
    output = bytearray()
    current_addr = start_address

    # Split into lines and process
    lines = source.strip().replace('\r\n', '\n').replace('\r', '\n').split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Parse line number
        line_num, content = parse_line_number(line)
        if line_num is None:
            # Skip lines without line numbers (comments, blank)
            continue

        if line_num > 63999:
            raise ValueError(f"Line number {line_num} exceeds maximum 63999")

        # Tokenize the line content
        tokenized = tokenize_line_content(content)

        # Calculate next line address
        # Format: next_addr(2) + line_num(2) + content + null(1)
        line_length = 2 + 2 + len(tokenized) + 1
        next_addr = current_addr + line_length

        # Build the line
        # Next line pointer (little-endian)
        output.append(next_addr & 0xFF)
        output.append((next_addr >> 8) & 0xFF)

        # Line number (little-endian)
        output.append(line_num & 0xFF)
        output.append((line_num >> 8) & 0xFF)

        # Tokenized content
        output.extend(tokenized)

        # Null terminator
        output.append(0x00)

        current_addr = next_addr

    # End of program marker (null pointer)
    output.append(0x00)
    output.append(0x00)

    return bytes(output)


def detokenize_line(data: bytes, offset: int = 0) -> Tuple[int, int, str, int]:
    """
    Detokenize a single BASIC line from binary data.

    Returns:
        (next_addr, line_num, detokenized_content, bytes_consumed)
    """
    # Read next line pointer
    next_addr = data[offset] | (data[offset + 1] << 8)

    if next_addr == 0:
        return 0, 0, "", 2

    # Read line number
    line_num = data[offset + 2] | (data[offset + 3] << 8)

    # Read content until null
    content = bytearray()
    i = offset + 4
    while i < len(data) and data[i] != 0:
        content.append(data[i])
        i += 1

    # Detokenize
    result = []
    j = 0
    in_string = False
    in_rem = False

    while j < len(content):
        byte = content[j]

        if byte == ord('"'):
            in_string = not in_string
            result.append('"')
            j += 1
            continue

        if in_string or in_rem:
            result.append(chr(byte) if byte < 128 else '?')
            j += 1
            continue

        # Check for token
        if byte >= 0x80:
            # Find the token
            for keyword, token in TOKENS:
                if token == byte:
                    result.append(keyword)
                    if keyword == 'REM':
                        in_rem = True
                    break
            else:
                result.append(f'[${byte:02X}]')
        else:
            result.append(chr(byte))

        j += 1

    bytes_consumed = i - offset + 1  # Include null terminator
    return next_addr, line_num, ''.join(result), bytes_consumed


def detokenize_program(data: bytes) -> str:
    """
    Convert tokenized binary back to ASCII BASIC source.
    """
    lines = []
    offset = 0

    while offset < len(data) - 1:
        next_addr, line_num, content, consumed = detokenize_line(data, offset)
        if next_addr == 0:
            break
        lines.append(f"{line_num} {content}")
        offset += consumed

    return '\n'.join(lines)


# Test the tokenizer
if __name__ == "__main__":
    test_program = """10 REM HELLO WORLD PROGRAM
20 HOME
30 PRINT "HELLO, APPLE II!"
40 FOR I = 1 TO 10
50 PRINT I
60 NEXT I
70 END
"""

    print("Original source:")
    print(test_program)

    tokenized = tokenize_program(test_program)
    print(f"\nTokenized ({len(tokenized)} bytes):")
    print(' '.join(f'{b:02X}' for b in tokenized[:64]))
    if len(tokenized) > 64:
        print("...")

    print("\nDetokenized:")
    print(detokenize_program(tokenized))
