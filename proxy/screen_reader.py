#!/usr/bin/env python3
"""
Apple II Screen Reader

Reads the Apple II text screen memory and decodes it to ASCII text.
The Apple II text screen has a non-linear memory layout.

Screen memory: $0400-$07FF (1024 bytes)
24 lines × 40 columns = 960 visible characters
"""

# Apple II text screen line addresses
# The screen is NOT linear - each line starts at a different address
LINE_ADDRESSES = [
    0x0400, 0x0480, 0x0500, 0x0580, 0x0600, 0x0680, 0x0700, 0x0780,  # Lines 0-7
    0x0428, 0x04A8, 0x0528, 0x05A8, 0x0628, 0x06A8, 0x0728, 0x07A8,  # Lines 8-15
    0x0450, 0x04D0, 0x0550, 0x05D0, 0x0650, 0x06D0, 0x0750, 0x07D0,  # Lines 16-23
]

SCREEN_WIDTH = 40
SCREEN_HEIGHT = 24


def apple2_char_to_ascii(byte: int) -> str:
    """Convert Apple II screen character to ASCII.

    Apple II character encoding:
    - $00-$3F: Inverse uppercase + symbols
    - $40-$7F: Flashing uppercase + symbols
    - $80-$BF: Normal uppercase + symbols (high bit set)
    - $C0-$FF: Normal lowercase + symbols (high bit set)

    All map to ASCII by masking with 0x7F, but:
    - Values $00-$1F need +$40 to get printable
    - Values $60-$7F are lowercase
    """
    # Mask off high bit
    char = byte & 0x7F

    # Control characters become spaces
    if char < 0x20:
        # Inverse characters: add 0x40 to get uppercase
        return chr(char + 0x40)
    elif char == 0x7F:
        return ' '  # DEL becomes space
    else:
        return chr(char)


def decode_screen_line(raw_bytes: list[int]) -> str:
    """Decode a line of Apple II screen memory to ASCII string."""
    chars = [apple2_char_to_ascii(b) for b in raw_bytes]
    return ''.join(chars)


class ScreenReader:
    """Reads Apple II text screen via remote shell proxy."""

    def __init__(self, proxy):
        """Initialize with a RemoteProxy instance."""
        self.proxy = proxy

    def read_line(self, line_num: int) -> str:
        """Read a single line from the screen (0-23)."""
        if not 0 <= line_num < SCREEN_HEIGHT:
            raise ValueError(f"Line number must be 0-23, got {line_num}")

        addr = LINE_ADDRESSES[line_num]
        raw_bytes = []

        for i in range(SCREEN_WIDTH):
            val = self.proxy.peek(addr + i)
            if val is None:
                return None  # Read failed
            raw_bytes.append(val)
            # Wait for READY between PEEKs
            self.proxy.wait_response(2)

        return decode_screen_line(raw_bytes)

    def read_screen(self) -> list[str]:
        """Read entire screen (24 lines)."""
        lines = []
        for line_num in range(SCREEN_HEIGHT):
            line = self.read_line(line_num)
            if line is None:
                return None  # Read failed
            lines.append(line)
        return lines

    def read_screen_fast(self) -> list[str]:
        """Read screen using batched reads (faster).

        Reads all 1024 bytes in order, then reorganizes.
        """
        # Read $0400-$07FF (1024 bytes)
        raw = []
        for addr in range(0x0400, 0x0800):
            val = self.proxy.peek(addr)
            if val is None:
                return None
            raw.append(val)
            self.proxy.wait_response(1)

        # Reorganize into lines
        lines = []
        for line_num in range(SCREEN_HEIGHT):
            addr = LINE_ADDRESSES[line_num]
            offset = addr - 0x0400
            line_bytes = raw[offset:offset + SCREEN_WIDTH]
            lines.append(decode_screen_line(line_bytes))

        return lines

    def print_screen(self):
        """Read and print the screen."""
        lines = self.read_screen()
        if lines:
            print("+" + "-" * 40 + "+")
            for line in lines:
                print("|" + line + "|")
            print("+" + "-" * 40 + "+")
        else:
            print("Failed to read screen")


def read_screen_standalone(host='localhost', port=8080) -> list[str]:
    """Standalone function to read screen without existing proxy."""
    import socket

    # Simple sync client
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(5)

    def send_cmd(cmd):
        sock.send((cmd + '\r\n').encode())
        # Wait for response
        data = b''
        while b'\n' not in data:
            data += sock.recv(1024)
        return data.decode().strip()

    def peek(addr):
        # Wait for READY
        data = b''
        while b'READY' not in data:
            data += sock.recv(1024)

        resp = send_cmd(f'P {addr:04X}')
        if resp.startswith('OK '):
            return int(resp[3:5], 16)
        return None

    # Read screen
    lines = []
    for line_num in range(SCREEN_HEIGHT):
        addr = LINE_ADDRESSES[line_num]
        raw_bytes = []
        for i in range(SCREEN_WIDTH):
            val = peek(addr + i)
            if val is None:
                sock.close()
                return None
            raw_bytes.append(val)
        lines.append(decode_screen_line(raw_bytes))

    sock.close()
    return lines


# Test code
if __name__ == '__main__':
    import sys

    # Test character conversion
    print("Character conversion test:")
    test_chars = [0xC1, 0xC2, 0xC3, 0xA0, 0x01, 0x41, 0x61]
    for c in test_chars:
        print(f"  ${c:02X} -> '{apple2_char_to_ascii(c)}'")

    # Test line addresses
    print("\nLine addresses:")
    for i, addr in enumerate(LINE_ADDRESSES):
        print(f"  Line {i:2}: ${addr:04X}")

    # If proxy available, test real read
    if len(sys.argv) > 1 and sys.argv[1] == '--live':
        print("\nLive screen read:")
        lines = read_screen_standalone()
        if lines:
            print("+" + "-" * 40 + "+")
            for line in lines:
                print("|" + line + "|")
            print("+" + "-" * 40 + "+")
