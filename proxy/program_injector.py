#!/usr/bin/env python3
"""
Apple II Program Injector

Injects tokenized Applesoft BASIC programs into Apple II memory
via the remote shell protocol.

Memory Layout:
  $0801+ : Tokenized BASIC program
  $67-$68: TXTTAB - Start of program (points to $0801)
  $69-$6A: VARTAB - Start of variables (end of program + 1)
  $6B-$6C: ARYTAB - Start of arrays (same as VARTAB for new program)
  $6D-$6E: STREND - End of string storage (same as VARTAB)
  $AF-$B0: PRGEND - End of program
"""

import time
from basic_tokenizer_streaming import tokenize_program


# BASIC memory pointers (zero page)
TXTTAB = 0x67      # Start of program text (2 bytes, points to $0801)
VARTAB = 0x69      # Start of simple variable space
ARYTAB = 0x6B      # Start of array space
STREND = 0x6D      # End of string storage (=ARYTAB for empty vars)
FRETOP = 0x6F      # Top of free string space
MEMSIZ = 0xAF      # Highest address used by BASIC (2 bytes)
PRGEND = 0xAF      # End of program (same as MEMSIZ conceptually)

# Where BASIC programs load
PROGRAM_START = 0x0801


class ProgramInjector:
    """Injects BASIC programs into Apple II memory."""

    def __init__(self, proxy):
        """Initialize with a RemoteProxy instance."""
        self.proxy = proxy
        self.stats = {
            'bytes_written': 0,
            'pokes_sent': 0,
            'time_taken': 0.0,
        }

    def poke(self, addr: int, value: int) -> bool:
        """POKE a single byte to memory."""
        result = self.proxy.poke(addr, value)
        if result:
            self.stats['pokes_sent'] += 1
            self.stats['bytes_written'] += 1
        return result

    def poke_word(self, addr: int, value: int) -> bool:
        """POKE a 16-bit word (little-endian)."""
        low = value & 0xFF
        high = (value >> 8) & 0xFF
        return self.poke(addr, low) and self.poke(addr + 1, high)

    def inject_bytes(self, start_addr: int, data: bytes) -> bool:
        """Inject a sequence of bytes into memory."""
        for i, byte in enumerate(data):
            if not self.poke(start_addr + i, byte):
                print(f"Failed to POKE at ${start_addr + i:04X}")
                return False
        return True

    def update_basic_pointers(self, end_addr: int) -> bool:
        """Update BASIC system pointers after program injection.

        Args:
            end_addr: First address AFTER the program (end + 1)
        """
        # TXTTAB points to $0801 (start of program text)
        if not self.poke_word(TXTTAB, PROGRAM_START):
            return False

        # VARTAB, ARYTAB, STREND all point to end of program
        # This clears any old variables
        for ptr in [VARTAB, ARYTAB, STREND]:
            if not self.poke_word(ptr, end_addr):
                return False

        return True

    def inject_basic(self, source: str) -> dict:
        """Inject a BASIC program into Apple II memory.

        Args:
            source: Applesoft BASIC source code

        Returns:
            dict with injection results:
                success: bool
                bytes_written: int
                end_address: int
                time_taken: float
                error: str (if failed)
        """
        self.stats = {
            'bytes_written': 0,
            'pokes_sent': 0,
            'time_taken': 0.0,
        }
        start_time = time.time()

        try:
            # Tokenize the program
            tokenized = tokenize_program(source, PROGRAM_START)
            print(f"Tokenized program: {len(tokenized)} bytes")

            # Calculate end address
            end_addr = PROGRAM_START + len(tokenized)

            # Inject program bytes
            print(f"Injecting to ${PROGRAM_START:04X}-${end_addr-1:04X}...")
            if not self.inject_bytes(PROGRAM_START, tokenized):
                return {
                    'success': False,
                    'error': 'Failed to inject program bytes',
                    'bytes_written': self.stats['bytes_written'],
                    'time_taken': time.time() - start_time,
                }

            # Update BASIC pointers
            print("Updating BASIC pointers...")
            if not self.update_basic_pointers(end_addr):
                return {
                    'success': False,
                    'error': 'Failed to update BASIC pointers',
                    'bytes_written': self.stats['bytes_written'],
                    'time_taken': time.time() - start_time,
                }

            self.stats['time_taken'] = time.time() - start_time

            return {
                'success': True,
                'bytes_written': self.stats['bytes_written'],
                'pokes_sent': self.stats['pokes_sent'],
                'end_address': end_addr,
                'time_taken': self.stats['time_taken'],
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'bytes_written': self.stats['bytes_written'],
                'time_taken': time.time() - start_time,
            }

    def verify_injection(self, source: str) -> bool:
        """Verify that the injected program matches expected bytes.

        Reads back memory and compares to expected tokenized output.
        """
        tokenized = tokenize_program(source, PROGRAM_START)

        for i, expected in enumerate(tokenized):
            addr = PROGRAM_START + i
            actual = self.proxy.peek(addr)
            if actual is None:
                print(f"Failed to read ${addr:04X}")
                return False
            if actual != expected:
                print(f"Mismatch at ${addr:04X}: expected ${expected:02X}, got ${actual:02X}")
                return False

        print(f"Verified {len(tokenized)} bytes OK")
        return True


def inject_program_standalone(source: str, host='localhost', port=8080) -> dict:
    """Standalone function to inject program without existing proxy."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(5)

    def wait_ready():
        data = b''
        while b'READY' not in data:
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk

    def send_cmd(cmd):
        sock.send((cmd + '\r\n').encode())
        data = b''
        while b'\n' not in data:
            data += sock.recv(1024)
        return data.decode().strip()

    def poke(addr, val):
        wait_ready()
        resp = send_cmd(f'O {addr:04X} {val:02X}')
        return resp.startswith('OK')

    start_time = time.time()

    # Tokenize
    tokenized = tokenize_program(source, PROGRAM_START)
    end_addr = PROGRAM_START + len(tokenized)
    print(f"Tokenized: {len(tokenized)} bytes")

    # Inject program
    print(f"Injecting to ${PROGRAM_START:04X}...")
    for i, byte in enumerate(tokenized):
        if not poke(PROGRAM_START + i, byte):
            sock.close()
            return {'success': False, 'error': f'POKE failed at offset {i}'}
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(tokenized)} bytes...")

    # Update pointers
    print("Updating pointers...")
    for ptr in [TXTTAB]:
        poke(ptr, PROGRAM_START & 0xFF)
        poke(ptr + 1, (PROGRAM_START >> 8) & 0xFF)

    for ptr in [VARTAB, ARYTAB, STREND]:
        poke(ptr, end_addr & 0xFF)
        poke(ptr + 1, (end_addr >> 8) & 0xFF)

    sock.close()

    return {
        'success': True,
        'bytes_written': len(tokenized),
        'end_address': end_addr,
        'time_taken': time.time() - start_time,
    }


# Test code
if __name__ == '__main__':
    import sys

    test_program = '''10 REM TEST PROGRAM
20 HOME
30 PRINT "HELLO FROM INJECTOR!"
40 FOR I = 1 TO 5
50 PRINT I
60 NEXT I
70 END
'''

    print("Test BASIC program:")
    print(test_program)
    print()

    # Show tokenized form
    tokenized = tokenize_program(test_program, PROGRAM_START)
    print(f"Tokenized: {len(tokenized)} bytes")
    print("Hex:", ' '.join(f'{b:02X}' for b in tokenized[:32]), "...")
    print()

    # Calculate what pointers should be
    end_addr = PROGRAM_START + len(tokenized)
    print("Memory layout after injection:")
    print(f"  TXTTAB ($67-$68) -> ${PROGRAM_START:04X}")
    print(f"  Program bytes: ${PROGRAM_START:04X}-${end_addr-1:04X}")
    print(f"  VARTAB ($69-$6A) -> ${end_addr:04X}")
    print(f"  ARYTAB ($6B-$6C) -> ${end_addr:04X}")
    print(f"  STREND ($6D-$6E) -> ${end_addr:04X}")
    print()

    if len(sys.argv) > 1 and sys.argv[1] == '--live':
        print("Live injection test...")
        result = inject_program_standalone(test_program)
        print(f"Result: {result}")
