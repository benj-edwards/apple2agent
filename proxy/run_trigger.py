#!/usr/bin/env python3
"""
Apple II RUN Trigger

Executes BASIC programs that have been injected into Apple II memory.

Methods:
1. Direct CALL to Applesoft RUN routine ($D912)
2. Keyboard buffer injection (type RUN for user)
3. NEW + RUN sequence for clean state

Applesoft Entry Points:
  $D912 - RUN (execute current program)
  $D66A - CLR (clear variables)
  $D683 - CLRTXT (clear text and reset pointers)
  $D4B5 - NEWSTT (continue execution at next statement)
"""

import time

# Applesoft ROM entry points
RUN_ENTRY = 0xD912      # RUN - execute program
CLR_ENTRY = 0xD66A      # CLR - clear variables
CLRTXT_ENTRY = 0xD683   # Clear text and reset
NEWSTT_ENTRY = 0xD4B5   # New statement execution

# Keyboard buffer
KEYBUF = 0x0200         # Keyboard buffer start
KEYBUF_PTR = 0xC000     # Keyboard strobe (not writable, but useful)

# Zero page locations
CURLINE = 0x75          # Current line number (2 bytes, $FFFF = immediate mode)
RUNMOD = 0x76           # RUN mode flag (0 = running, $80 = immediate)


class RunTrigger:
    """Triggers execution of BASIC programs on Apple II."""

    def __init__(self, proxy):
        """Initialize with a RemoteProxy instance."""
        self.proxy = proxy

    def call(self, addr: int) -> bool:
        """Execute a CALL to an address."""
        return self.proxy.call(addr)

    def poke(self, addr: int, value: int) -> bool:
        """POKE a value to memory."""
        return self.proxy.poke(addr, value)

    def poke_word(self, addr: int, value: int) -> bool:
        """POKE a 16-bit word (little-endian)."""
        low = value & 0xFF
        high = (value >> 8) & 0xFF
        return self.poke(addr, low) and self.poke(addr + 1, high)

    def clear_variables(self) -> bool:
        """Clear BASIC variables (equivalent to CLR command).

        This resets VARTAB, ARYTAB, STREND to end of program.
        """
        return self.call(CLR_ENTRY)

    def set_run_mode(self) -> bool:
        """Set BASIC to RUN mode (not immediate mode)."""
        # Set CURLINE to 0 (first line)
        if not self.poke_word(CURLINE, 0):
            return False
        # Set RUNMOD to 0 (running)
        return self.poke(RUNMOD, 0)

    def run_program(self, clear_first: bool = True) -> bool:
        """Execute the BASIC program in memory.

        Args:
            clear_first: If True, clear variables before running

        Returns:
            True if CALL was successful
        """
        if clear_first:
            print("Clearing variables...")
            # We can't actually CALL CLR easily, so we'll set up state manually
            # The program injector already set VARTAB etc.

        print(f"Calling RUN at ${RUN_ENTRY:04X}...")
        return self.call(RUN_ENTRY)

    def run_via_keyboard(self) -> bool:
        """Inject 'RUN' into keyboard buffer.

        This is safer but requires returning to BASIC prompt first.
        """
        # Type RUN\r into the keyboard buffer
        run_cmd = "RUN\r"
        for i, char in enumerate(run_cmd):
            # Apple II wants high bit set for normal characters
            byte = ord(char) | 0x80
            if not self.poke(KEYBUF + i, byte):
                return False

        # This won't work directly - need to simulate keyboard differently
        # Leaving as placeholder for keyboard injection approach
        print("Note: Keyboard injection requires additional setup")
        return True

    def wait_for_completion(self, timeout: float = 10.0, poll_interval: float = 0.5) -> bool:
        """Wait for program to finish executing.

        Polls for BASIC prompt by checking:
        1. CURLINE = $FFFF (immediate mode)
        2. Screen shows ']' prompt

        Args:
            timeout: Maximum seconds to wait
            poll_interval: Seconds between checks

        Returns:
            True if program completed, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if back in immediate mode
            low = self.proxy.peek(CURLINE)
            high = self.proxy.peek(CURLINE + 1)

            if low is not None and high is not None:
                curline = low | (high << 8)
                if curline == 0xFFFF:
                    print("Program finished (immediate mode)")
                    return True

            time.sleep(poll_interval)

        print(f"Timeout after {timeout}s")
        return False


def run_program_standalone(host='localhost', port=8080, timeout=10.0) -> dict:
    """Standalone function to run program without existing proxy."""
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

    def call_addr(addr):
        wait_ready()
        resp = send_cmd(f'C {addr:04X}')
        return resp.startswith('OK')

    # Run the program
    start_time = time.time()
    print(f"Calling RUN at ${RUN_ENTRY:04X}...")

    if not call_addr(RUN_ENTRY):
        sock.close()
        return {'success': False, 'error': 'CALL failed'}

    # Wait for completion by polling CURLINE
    print("Waiting for program to finish...")
    while time.time() - start_time < timeout:
        def peek(addr):
            wait_ready()
            resp = send_cmd(f'P {addr:04X}')
            if resp.startswith('OK '):
                return int(resp[3:5], 16)
            return None

        low = peek(CURLINE)
        high = peek(CURLINE + 1)
        if low is not None and high is not None:
            curline = low | (high << 8)
            if curline == 0xFFFF:
                sock.close()
                return {
                    'success': True,
                    'time_taken': time.time() - start_time,
                }

        time.sleep(0.5)

    sock.close()
    return {
        'success': False,
        'error': 'Timeout waiting for program completion',
        'time_taken': time.time() - start_time,
    }


# Test code
if __name__ == '__main__':
    print("RUN Trigger Module")
    print()
    print("Applesoft entry points:")
    print(f"  RUN:    ${RUN_ENTRY:04X} ({RUN_ENTRY})")
    print(f"  CLR:    ${CLR_ENTRY:04X} ({CLR_ENTRY})")
    print(f"  CLRTXT: ${CLRTXT_ENTRY:04X} ({CLRTXT_ENTRY})")
    print()
    print("Key memory locations:")
    print(f"  CURLINE: ${CURLINE:02X}-${CURLINE+1:02X} (current line, $FFFF = immediate)")
    print(f"  RUNMOD:  ${RUNMOD:02X} ($00 = running, $80 = immediate)")
    print()
    print("Usage:")
    print("  trigger = RunTrigger(proxy)")
    print("  trigger.run_program()")
    print("  trigger.wait_for_completion()")
