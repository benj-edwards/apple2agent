"""Apple II screen memory decoding.

The Apple II text screen uses an interleaved memory layout:
- Text Page 1: $0400-$07FF (1024 bytes for 40x24 = 960 chars + holes)
- Text Page 2: $0800-$0BFF

The layout is NOT linear. Each group of 8 lines shares a base address,
with 128-byte offsets between lines in the group.
"""

from .encoding import apple2_to_ascii

# Text Page 1 base address
TEXT_PAGE_1 = 0x0400

# Screen dimensions
SCREEN_WIDTH = 40
SCREEN_HEIGHT = 24

# Memory address for each screen line
# The Apple II screen is divided into 3 groups of 8 lines each
# Group 0: lines 0-7   start at $0400, $0480, $0500, $0580, $0600, $0680, $0700, $0780
# Group 1: lines 8-15  start at $0428, $04A8, $0528, $05A8, $0628, $06A8, $0728, $07A8
# Group 2: lines 16-23 start at $0450, $04D0, $0550, $05D0, $0650, $06D0, $0750, $07D0

SCREEN_LINE_ADDRESSES = [
    0x0400,  # Line 0
    0x0480,  # Line 1
    0x0500,  # Line 2
    0x0580,  # Line 3
    0x0600,  # Line 4
    0x0680,  # Line 5
    0x0700,  # Line 6
    0x0780,  # Line 7
    0x0428,  # Line 8
    0x04A8,  # Line 9
    0x0528,  # Line 10
    0x05A8,  # Line 11
    0x0628,  # Line 12
    0x06A8,  # Line 13
    0x0728,  # Line 14
    0x07A8,  # Line 15
    0x0450,  # Line 16
    0x04D0,  # Line 17
    0x0550,  # Line 18
    0x05D0,  # Line 19
    0x0650,  # Line 20
    0x06D0,  # Line 21
    0x0750,  # Line 22
    0x07D0,  # Line 23
]


def get_line_address(line: int) -> int:
    """Get the memory address for the start of a screen line.

    Args:
        line: Line number (0-23)

    Returns:
        Memory address for the start of that line
    """
    if not 0 <= line < SCREEN_HEIGHT:
        raise ValueError(f"Line must be 0-23, got {line}")
    return SCREEN_LINE_ADDRESSES[line]


def screen_address_to_coords(address: int) -> tuple[int, int] | None:
    """Convert a memory address to screen coordinates.

    Args:
        address: Memory address ($0400-$07FF)

    Returns:
        (column, row) tuple, or None if address is in a "hole"
    """
    if not (0x0400 <= address <= 0x07FF):
        return None

    for row, line_addr in enumerate(SCREEN_LINE_ADDRESSES):
        if line_addr <= address < line_addr + SCREEN_WIDTH:
            col = address - line_addr
            return (col, row)

    # Address is in a "hole" (unused bytes between lines)
    return None


def coords_to_screen_address(col: int, row: int) -> int:
    """Convert screen coordinates to memory address.

    Args:
        col: Column (0-39)
        row: Row (0-23)

    Returns:
        Memory address for that screen position
    """
    if not (0 <= col < SCREEN_WIDTH and 0 <= row < SCREEN_HEIGHT):
        raise ValueError(f"Invalid coordinates: ({col}, {row})")

    return SCREEN_LINE_ADDRESSES[row] + col


def decode_screen(memory: bytes | dict[int, int], base: int = TEXT_PAGE_1) -> list[str]:
    """Decode Apple II screen memory into lines of text.

    Args:
        memory: Either raw bytes starting at base address, or dict mapping addresses to values
        base: Base address of the memory dump (default: $0400)

    Returns:
        List of 24 strings, each 40 characters
    """
    lines = []

    for row in range(SCREEN_HEIGHT):
        line_addr = SCREEN_LINE_ADDRESSES[row]
        line_chars = []

        for col in range(SCREEN_WIDTH):
            addr = line_addr + col

            if isinstance(memory, dict):
                byte = memory.get(addr, 0xA0)  # Default to space
            else:
                # Calculate offset from base
                offset = addr - base
                if 0 <= offset < len(memory):
                    byte = memory[offset]
                else:
                    byte = 0xA0  # Default to space

            line_chars.append(apple2_to_ascii(byte))

        lines.append(''.join(line_chars))

    return lines


def format_screen(lines: list[str], include_line_numbers: bool = False,
                  show_cursor: bool = False, cursor_col: int = 0, cursor_row: int = 0) -> str:
    """Format screen lines for display.

    Args:
        lines: List of 24 screen lines
        include_line_numbers: Add line numbers to output
        show_cursor: Show cursor position marker
        cursor_col: Cursor column position
        cursor_row: Cursor row position

    Returns:
        Formatted screen as a single string
    """
    output = []

    for row, line in enumerate(lines):
        if show_cursor and row == cursor_row:
            # Insert cursor marker
            line = line[:cursor_col] + '_' + line[cursor_col + 1:]

        if include_line_numbers:
            output.append(f"{row:2d}| {line}")
        else:
            output.append(line)

    return '\n'.join(output)


def find_text_on_screen(lines: list[str], search: str) -> list[tuple[int, int]]:
    """Find all occurrences of text on screen.

    Args:
        lines: Screen lines from decode_screen()
        search: Text to find (case-sensitive)

    Returns:
        List of (column, row) tuples where text was found
    """
    results = []
    search_upper = search.upper()  # Apple II is uppercase

    for row, line in enumerate(lines):
        col = 0
        while True:
            pos = line.find(search_upper, col)
            if pos == -1:
                break
            results.append((pos, row))
            col = pos + 1

    return results
