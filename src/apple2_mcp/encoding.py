"""Apple II character encoding utilities.

The Apple II uses a unique character encoding where:
- $00-$1F: Inverse uppercase + symbols
- $20-$3F: Inverse symbols + numbers
- $40-$5F: Flashing uppercase + symbols
- $60-$7F: Flashing symbols + numbers
- $80-$9F: Normal uppercase + symbols
- $A0-$BF: Normal symbols + numbers
- $C0-$DF: Normal uppercase + symbols (duplicate)
- $E0-$FF: Normal lowercase (//e only) or symbols
"""

# Apple II to ASCII conversion table
# Maps Apple II screen codes to displayable ASCII
APPLE2_TO_ASCII = {}

# Build the conversion table
for i in range(256):
    if i < 0x20:
        # Inverse: @, A-Z, [, \, ], ^, _
        APPLE2_TO_ASCII[i] = chr(i + 0x40)
    elif i < 0x40:
        # Inverse: space, !, ", #, etc.
        APPLE2_TO_ASCII[i] = chr(i)
    elif i < 0x60:
        # Flashing: @, A-Z, [, \, ], ^, _
        APPLE2_TO_ASCII[i] = chr(i)
    elif i < 0x80:
        # Flashing: space, !, ", #, etc.
        APPLE2_TO_ASCII[i] = chr(i - 0x40)
    elif i < 0xA0:
        # Normal: @, A-Z, [, \, ], ^, _
        APPLE2_TO_ASCII[i] = chr(i - 0x40)
    elif i < 0xC0:
        # Normal: space, !, ", #, etc.
        APPLE2_TO_ASCII[i] = chr(i - 0x80)
    elif i < 0xE0:
        # Normal: @, A-Z, [, \, ], ^, _ (duplicate)
        APPLE2_TO_ASCII[i] = chr(i - 0x80)
    else:
        # Normal lowercase (//e) or symbols
        APPLE2_TO_ASCII[i] = chr(i - 0x80)


def apple2_to_ascii(byte: int) -> str:
    """Convert a single Apple II screen byte to ASCII character."""
    return APPLE2_TO_ASCII.get(byte, '?')


def apple2_bytes_to_string(data: bytes) -> str:
    """Convert Apple II screen bytes to ASCII string."""
    return ''.join(apple2_to_ascii(b) for b in data)


def ascii_to_apple2(char: str, inverse: bool = False, flashing: bool = False) -> int:
    """Convert ASCII character to Apple II screen code.

    Args:
        char: Single ASCII character
        inverse: If True, return inverse video code
        flashing: If True, return flashing code

    Returns:
        Apple II screen byte value
    """
    c = ord(char.upper())

    if inverse:
        if 0x40 <= c <= 0x5F:  # @, A-Z, [, \, ], ^, _
            return c - 0x40
        elif 0x20 <= c <= 0x3F:  # space, !, ", etc.
            return c
    elif flashing:
        if 0x40 <= c <= 0x5F:
            return c
        elif 0x20 <= c <= 0x3F:
            return c + 0x40
    else:
        # Normal video
        if 0x40 <= c <= 0x5F:
            return c + 0x80
        elif 0x20 <= c <= 0x3F:
            return c + 0x80
        elif 0x60 <= c <= 0x7F:  # lowercase
            return c + 0x80

    return 0xA0  # Default to space


def ascii_string_to_apple2(text: str, inverse: bool = False) -> bytes:
    """Convert ASCII string to Apple II screen bytes."""
    return bytes(ascii_to_apple2(c, inverse=inverse) for c in text)


# Applesoft BASIC tokens
APPLESOFT_TOKENS = {
    0x80: "END",
    0x81: "FOR",
    0x82: "NEXT",
    0x83: "DATA",
    0x84: "INPUT",
    0x85: "DEL",
    0x86: "DIM",
    0x87: "READ",
    0x88: "GR",
    0x89: "TEXT",
    0x8A: "PR#",
    0x8B: "IN#",
    0x8C: "CALL",
    0x8D: "PLOT",
    0x8E: "HLIN",
    0x8F: "VLIN",
    0x90: "HGR2",
    0x91: "HGR",
    0x92: "HCOLOR=",
    0x93: "HPLOT",
    0x94: "DRAW",
    0x95: "XDRAW",
    0x96: "HTAB",
    0x97: "HOME",
    0x98: "ROT=",
    0x99: "SCALE=",
    0x9A: "SHLOAD",
    0x9B: "TRACE",
    0x9C: "NOTRACE",
    0x9D: "NORMAL",
    0x9E: "INVERSE",
    0x9F: "FLASH",
    0xA0: "COLOR=",
    0xA1: "POP",
    0xA2: "VTAB",
    0xA3: "HIMEM:",
    0xA4: "LOMEM:",
    0xA5: "ONERR",
    0xA6: "RESUME",
    0xA7: "RECALL",
    0xA8: "STORE",
    0xA9: "SPEED=",
    0xAA: "LET",
    0xAB: "GOTO",
    0xAC: "RUN",
    0xAD: "IF",
    0xAE: "RESTORE",
    0xAF: "&",
    0xB0: "GOSUB",
    0xB1: "RETURN",
    0xB2: "REM",
    0xB3: "STOP",
    0xB4: "ON",
    0xB5: "WAIT",
    0xB6: "LOAD",
    0xB7: "SAVE",
    0xB8: "DEF",
    0xB9: "POKE",
    0xBA: "PRINT",
    0xBB: "CONT",
    0xBC: "LIST",
    0xBD: "CLEAR",
    0xBE: "GET",
    0xBF: "NEW",
    0xC0: "TAB(",
    0xC1: "TO",
    0xC2: "FN",
    0xC3: "SPC(",
    0xC4: "THEN",
    0xC5: "AT",
    0xC6: "NOT",
    0xC7: "STEP",
    0xC8: "SGN",
    0xC9: "+",
    0xCA: "-",
    0xCB: "*",
    0xCC: "/",
    0xCD: "^",
    0xCE: "AND",
    0xCF: "OR",
    0xD0: ">",
    0xD1: "=",
    0xD2: "<",
    0xD3: "SGN",
    0xD4: "INT",
    0xD5: "ABS",
    0xD6: "USR",
    0xD7: "FRE",
    0xD8: "SCRN(",
    0xD9: "PDL",
    0xDA: "POS",
    0xDB: "SQR",
    0xDC: "RND",
    0xDD: "LOG",
    0xDE: "EXP",
    0xDF: "COS",
    0xE0: "SIN",
    0xE1: "TAN",
    0xE2: "ATN",
    0xE3: "PEEK",
    0xE4: "LEN",
    0xE5: "STR$",
    0xE6: "VAL",
    0xE7: "ASC",
    0xE8: "CHR$",
    0xE9: "LEFT$",
    0xEA: "RIGHT$",
    0xEB: "MID$",
}

# Reverse mapping: token name to byte
TOKEN_TO_BYTE = {v: k for k, v in APPLESOFT_TOKENS.items()}


def detokenize_byte(byte: int, in_string: bool = False, in_rem: bool = False) -> str:
    """Convert a tokenized BASIC byte to its string representation.

    Args:
        byte: The byte value
        in_string: True if currently inside a string literal
        in_rem: True if after a REM statement

    Returns:
        String representation of the byte
    """
    if in_string or in_rem:
        # Inside strings/REM, everything is literal ASCII
        if 0x20 <= byte <= 0x7F:
            return chr(byte)
        return f"[{byte:02X}]"

    if byte in APPLESOFT_TOKENS:
        return " " + APPLESOFT_TOKENS[byte] + " "

    if 0x20 <= byte <= 0x7F:
        return chr(byte)

    return f"[{byte:02X}]"
