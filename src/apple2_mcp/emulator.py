"""Bobbin emulator process manager.

Uses pexpect to control the Bobbin Apple II emulator interactively.
Now with optional Unix socket control channel for reliable AI/MCP integration.

Provides methods for:
- Starting/stopping the emulator
- Sending keystrokes
- Entering debugger and executing commands
- Reading/writing memory
- Managing snapshots
"""

from __future__ import annotations

import atexit
import os
import re
import signal
import time
import shutil
from pathlib import Path
from typing import Optional

import pexpect
from pexpect import popen_spawn

from .screen import decode_screen, SCREEN_LINE_ADDRESSES, SCREEN_WIDTH, SCREEN_HEIGHT
from .control_socket import BobbinControlSocket, ControlSocketError

# PID file for tracking emulator process
BOBBIN_PID_FILE = "/tmp/bobbin.pid"

# Path where Bobbin writes screen dump on SIGUSR1
SIGUSR1_SCREEN_PATH = "/tmp/bobbin_screen.txt"


def _kill_stale_bobbin():
    """Kill any stale Bobbin process from PID file."""
    if os.path.exists(BOBBIN_PID_FILE):
        try:
            with open(BOBBIN_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            # Check if process exists
            os.kill(pid, 0)
            # Process exists, try graceful then forceful kill
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Already dead
        except (ValueError, ProcessLookupError, FileNotFoundError, PermissionError):
            pass  # PID invalid or process doesn't exist
        finally:
            try:
                os.remove(BOBBIN_PID_FILE)
            except OSError:
                pass


def _write_pid_file(pid: int):
    """Write PID file for tracking."""
    try:
        with open(BOBBIN_PID_FILE, 'w') as f:
            f.write(str(pid))
    except OSError:
        pass  # Non-fatal


def _remove_pid_file():
    """Remove PID file."""
    try:
        os.remove(BOBBIN_PID_FILE)
    except OSError:
        pass

# Default control socket path
DEFAULT_CONTROL_SOCKET = "/tmp/bobbin.sock"


class BobbinError(Exception):
    """Error from Bobbin emulator."""
    pass


class Emulator:
    """Manages a Bobbin emulator process."""

    # Debugger prompt pattern - Bobbin uses "BOBBIN> " or may just use ">"
    # We match either for flexibility
    DEBUGGER_PROMPT_PATTERN = r'(?:BOBBIN> |^> |\n> )'

    # Default Bobbin path (can be overridden)
    DEFAULT_BOBBIN_PATH = None

    def __init__(self, bobbin_path: Optional[str] = None,
                 control_socket: Optional[str] = DEFAULT_CONTROL_SOCKET):
        """Initialize emulator manager.

        Args:
            bobbin_path: Path to bobbin executable. If None, searches common locations.
            control_socket: Path to control socket. Set to None to disable.
        """
        self.bobbin_path = bobbin_path or self._find_bobbin()
        self.process: Optional[pexpect.spawn] = None
        self.in_debugger = False
        self.machine_type = "enhanced"
        self.control_socket_path = control_socket
        self.control_socket: Optional[BobbinControlSocket] = None

    def _find_bobbin(self) -> str:
        """Find the bobbin executable."""
        # Check common locations
        candidates = [
            # Relative to this package (development) - go up from src/apple2_mcp/
            Path(__file__).parent.parent.parent / "bobbin" / "src" / "bobbin",
            # System installed
            Path("/usr/local/bin/bobbin"),
            Path("/opt/homebrew/bin/bobbin"),
            # In PATH
            shutil.which("bobbin"),
        ]

        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(Path(candidate).resolve())

        raise BobbinError(
            "Could not find bobbin executable. "
            "Please provide bobbin_path or install bobbin."
        )

    @property
    def is_running(self) -> bool:
        """Check if emulator process is running."""
        return self.process is not None and self.process.isalive()

    def boot(self, machine: str = "enhanced", disk: Optional[str] = None,
             timeout: float = 60.0, uthernet2: bool = False,
             mouse: bool = False, wait_for_prompt: bool = True) -> str:
        """Start the emulator and optionally wait for BASIC prompt.

        Args:
            machine: Machine type (plus, enhanced, twoey, original)
            disk: Optional disk image path to load
            timeout: Timeout in seconds for boot (default 60)
            uthernet2: Enable Uthernet II network card emulation in slot 3
            mouse: Enable AppleMouse card emulation in slot 4
            wait_for_prompt: Wait for BASIC prompt (set False for ProDOS selector disks)

        Returns:
            Initial screen contents
        """
        if self.is_running:
            self.shutdown()

        # Kill any stale emulator from previous sessions
        _kill_stale_bobbin()

        self.machine_type = machine

        # Build command
        # --remain keeps bobbin running even if stdin gets EOF
        cmd = [self.bobbin_path, "--simple", "--remain", "-m", machine]
        if disk:
            cmd.extend(["--disk", disk])
        if uthernet2:
            cmd.append("--uthernet2")
        if mouse:
            cmd.append("--mouse")

        # Add control socket if configured
        if self.control_socket_path:
            cmd.extend(["--control-socket", self.control_socket_path])

        # Start process with PTY
        self.process = pexpect.spawn(
            cmd[0],
            cmd[1:],
            encoding='latin-1',  # Apple II uses high-bit ASCII
            timeout=timeout,
            ignore_sighup=True,
        )
        self.process.setecho(False)

        # Track PID for cleanup on restart
        _write_pid_file(self.process.pid)

        # Wait for the BASIC prompt (] at start of line) if requested
        # Use \n] pattern to match the actual BASIC prompt, not ] in Bobbin banner
        if wait_for_prompt:
            try:
                self.process.expect(r'\n\]', timeout=timeout)
            except pexpect.TIMEOUT:
                raise BobbinError("Timeout waiting for BASIC prompt")
        else:
            # Just wait a moment for emulator to start
            time.sleep(2.0)

        # Give emulator time to settle and aggressively drain all buffered output
        # This prevents stale data from interfering with subsequent commands
        time.sleep(0.2)
        for _ in range(5):
            try:
                data = self.process.read_nonblocking(4096, timeout=0.05)
                if not data:
                    break
            except pexpect.TIMEOUT:
                break
            except pexpect.EOF:
                # Check if process is actually dead
                if not self.process.isalive():
                    raise BobbinError("Emulator process died during boot")
                break
            time.sleep(0.02)

        self.in_debugger = False

        # Connect to control socket if configured
        if self.control_socket_path:
            time.sleep(0.3)  # Give socket time to initialize
            self.control_socket = BobbinControlSocket(self.control_socket_path)
            if self.control_socket.connect(timeout=2.0):
                try:
                    self.control_socket.ping()
                except ControlSocketError:
                    self.control_socket = None
            else:
                self.control_socket = None

        return (self.process.before or "") + "]"

    def shutdown(self):
        """Stop the emulator."""
        # Disconnect control socket first
        if self.control_socket:
            try:
                self.control_socket.quit()
            except Exception:
                pass
            self.control_socket.disconnect()
            self.control_socket = None

        if self.process:
            try:
                # Try graceful exit via debugger
                self.enter_debugger()
                self.process.sendline("q")
                self.process.expect(pexpect.EOF, timeout=2)
            except Exception:
                pass
            finally:
                if self.process.isalive():
                    self.process.terminate(force=True)
                self.process = None
                self.in_debugger = False

        # Clean up PID file
        _remove_pid_file()

    def pause(self):
        """Pause emulation to save CPU. Call resume() before next operation."""
        if self.control_socket:
            try:
                self.control_socket.pause()
            except ControlSocketError:
                pass

    def resume(self):
        """Resume emulation after pause."""
        if self.control_socket:
            try:
                self.control_socket.resume()
            except ControlSocketError:
                pass

    def _ensure_running(self):
        """Ensure emulator is running (not paused). Call before operations."""
        self.resume()

    def enter_debugger(self, timeout: float = 2.0, max_retries: int = 3) -> bool:
        """Enter the Bobbin debugger (Ctrl-C twice).

        Uses retry logic to handle intermittent failures caused by timing
        issues or stale state.

        Args:
            timeout: Timeout for each attempt
            max_retries: Maximum number of attempts before giving up

        Returns:
            True if now in debugger
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Try multiple times with increasing delays
        for attempt in range(max_retries):
            # Clear stale state - the debugger may have exited naturally
            # (e.g., 'keys' command auto-exits) but the flag wasn't updated
            if attempt > 0:
                self.in_debugger = False
                time.sleep(0.1 * attempt)  # Increasing backoff

            if self.in_debugger:
                # Verify we're actually in debugger by sending 'help' command
                # IMPORTANT: Do NOT send empty line - it triggers single-step mode!
                try:
                    self.process.sendline("help")
                    self.process.expect(r'BOBBIN> ', timeout=0.5)
                    return True
                except pexpect.TIMEOUT:
                    # Not actually in debugger, clear flag and try again
                    self.in_debugger = False

            # Drain any buffered output before sending Ctrl-C
            for _ in range(5):
                try:
                    data = self.process.read_nonblocking(4096, timeout=0.02)
                    if not data:
                        break
                except pexpect.TIMEOUT:
                    break
                except pexpect.EOF:
                    # Check if process is actually dead
                    if not self.process.isalive():
                        raise BobbinError("Emulator process died unexpectedly")
                    break
            time.sleep(0.05)

            # Send Ctrl-C twice via stdin to enter debugger
            # Bobbin explicitly says "Ctrl-C *TWICE* to enter debugger"
            self.process.sendcontrol('c')
            time.sleep(0.15)
            self.process.sendcontrol('c')

            # Small delay to let the debugger activate
            time.sleep(0.3)

            # Wait for debugger prompt - try multiple patterns
            # Bobbin uses "BOBBIN> " as its prompt
            try:
                # Use a simpler, more reliable pattern
                self.process.expect(r'BOBBIN> ', timeout=timeout)
                self.in_debugger = True

                # Drain any buffered output to ensure clean state
                time.sleep(0.05)
                for _ in range(3):
                    try:
                        self.process.read_nonblocking(4096, timeout=0.02)
                    except pexpect.TIMEOUT:
                        break
                    except pexpect.EOF:
                        if not self.process.isalive():
                            raise BobbinError("Emulator died in debugger")
                        break

                return True
            except pexpect.TIMEOUT:
                # Check if we got partial output that indicates debugger
                if self.process.before and 'BOBBIN' in self.process.before:
                    self.in_debugger = True
                    return True
                # Try again on next iteration
                continue

        # All retries exhausted
        return False

    def exit_debugger(self, timeout: float = 2.0) -> bool:
        """Exit debugger and continue emulation.

        Returns:
            True if exited debugger
        """
        # Only try to exit if we think we're in debugger
        if not self.in_debugger:
            return True

        # IMPORTANT: Do NOT send empty lines - they trigger single-step mode!
        # Just send 'c' to continue execution
        self.process.sendline("c")

        # Wait for "Continuing..." message
        try:
            self.process.expect(r'Continuing\.\.\.', timeout=1.0)
        except pexpect.TIMEOUT:
            pass

        # Wait a moment for emulator to resume
        time.sleep(0.3)

        # Drain any remaining output
        for _ in range(5):
            try:
                self.process.read_nonblocking(4096, timeout=0.05)
            except pexpect.TIMEOUT:
                break
            except pexpect.EOF:
                if not self.process.isalive():
                    raise BobbinError("Emulator died exiting debugger")
                break

        self.in_debugger = False
        return True

    def debugger_command(self, cmd: str, timeout: float = 2.0,
                         stay_in_debugger: bool = True) -> str:
        """Execute a debugger command and return output.

        Args:
            cmd: Command to execute
            timeout: Timeout for command response
            stay_in_debugger: If True, stay in debugger after command.
                              If False, always exit debugger after command.

        Returns:
            Command output
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        was_in_debugger = self.in_debugger
        if not was_in_debugger:
            if not self.enter_debugger():
                raise BobbinError("Failed to enter debugger")

        self.process.sendline(cmd)

        # Wait for next prompt
        try:
            self.process.expect(r'BOBBIN> ', timeout=timeout)
            output = self.process.before
        except pexpect.TIMEOUT:
            # Check if we got partial output
            output = self.process.before if self.process.before else ""

        # Exit debugger if caller doesn't want to stay
        # Always try to exit to ensure clean state
        if not stay_in_debugger:
            self.exit_debugger()

        return output.strip()

    def debugger_help(self) -> str:
        """Get debugger help - for debugging purposes."""
        if not self.is_running:
            raise BobbinError("Emulator not running")

        if not self.in_debugger:
            if not self.enter_debugger():
                raise BobbinError("Failed to enter debugger")

        self.process.sendline("help")

        try:
            self.process.expect(r'BOBBIN> ', timeout=5.0)
            output = self.process.before
        except pexpect.TIMEOUT:
            output = self.process.before if self.process.before else ""

        return output

    def peek(self, address: int, count: int = 1) -> list[int]:
        """Read bytes from memory.

        Args:
            address: Starting address (0-65535)
            count: Number of bytes to read

        Returns:
            List of byte values
        """
        # Use control socket if available (much more reliable)
        if self.control_socket:
            try:
                return self.control_socket.peek(address, count)
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        # Use longer timeout for large reads (1 second per 256 bytes, minimum 3 seconds)
        read_timeout = max(3.0, count / 256)

        if count == 1:
            # Single byte
            output = self.debugger_command(f"{address:04X}", timeout=read_timeout, stay_in_debugger=False)
        else:
            # Range
            end_addr = min(address + count - 1, 0xFFFF)
            output = self.debugger_command(f"{address:04X}.{end_addr:04X}", timeout=read_timeout, stay_in_debugger=False)

        # Parse hex output
        # Format: "0400: A0 A0 A0 A0 A0 A0 A0 A0"
        bytes_list = []
        for line in output.split('\n'):
            # Extract hex bytes after the colon
            if ':' in line:
                hex_part = line.split(':', 1)[1]
            else:
                hex_part = line

            # Parse hex values
            for token in hex_part.split():
                token = token.strip()
                if re.match(r'^[0-9A-Fa-f]{2}$', token):
                    bytes_list.append(int(token, 16))

        return bytes_list[:count]

    def poke(self, address: int, data: int | list[int] | bytes) -> bool:
        """Write bytes to memory.

        Args:
            address: Starting address
            data: Byte value, list of bytes, or bytes object

        Returns:
            True if successful
        """
        if isinstance(data, int):
            data = [data]
        elif isinstance(data, bytes):
            data = list(data)

        # Use control socket if available (much more reliable)
        if self.control_socket:
            try:
                self.control_socket.poke(address, data)
                return True
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        # Build command: "addr: val val val..."
        hex_values = ' '.join(f"{b:02X}" for b in data)
        cmd = f"{address:04X}: {hex_values}"

        self.debugger_command(cmd, stay_in_debugger=False)
        return True

    def load(self, address: int, hex_data: str) -> int:
        """Load hex data into memory. More efficient than poke for large blocks.

        Args:
            address: Starting address
            hex_data: Hex string (e.g., "A9008D0008")

        Returns:
            Number of bytes loaded
        """
        if self.control_socket:
            try:
                return self.control_socket.load(address, hex_data)
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to poke via debugger
        data = bytes.fromhex(hex_data.replace(' ', ''))
        self.poke(address, list(data))
        return len(data)

    def read_screen_memory(self) -> dict[int, int]:
        """Read the entire text screen memory.

        Returns:
            Dict mapping addresses to byte values
        """
        memory = {}

        # Read text page 1 ($0400-$07FF) using debugger_command
        # stay_in_debugger=False ensures we exit cleanly
        end_addr = 0x0400 + 0x0400 - 1  # 0x07FF
        output = self.debugger_command(f"0400.{end_addr:04X}", stay_in_debugger=False)

        # Parse hex output
        bytes_list = []
        for line in output.split('\n'):
            if ':' in line:
                hex_part = line.split(':', 1)[1]
            else:
                hex_part = line
            for token in hex_part.split():
                token = token.strip()
                if len(token) == 2 and all(c in '0123456789ABCDEFabcdef' for c in token):
                    bytes_list.append(int(token, 16))

        for i, byte in enumerate(bytes_list[:0x0400]):
            memory[0x0400 + i] = byte

        return memory

    def read_screen(self) -> list[str]:
        """Read the current screen contents as text.

        Returns:
            List of 24 strings, each 40 characters
        """
        # Use control socket if available (much more reliable)
        if self.control_socket:
            try:
                return self.control_socket.read_screen()
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        memory = self.read_screen_memory()
        return decode_screen(memory)

    def read_screen_nonblocking(self, timeout: float = 1.0) -> list[str]:
        """Read the screen without stopping emulation.

        Uses control socket if available (preferred), otherwise falls back
        to SIGUSR1-based capture.

        Args:
            timeout: Maximum time to wait for screen file to appear

        Returns:
            List of 24 strings, each 40 characters
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Use control socket if available (much more reliable)
        if self.control_socket:
            try:
                return self.control_socket.read_screen()
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to SIGUSR1 method
        # Remove old screen file if it exists
        try:
            os.unlink(SIGUSR1_SCREEN_PATH)
        except FileNotFoundError:
            pass

        # Send SIGUSR1 to Bobbin process
        os.kill(self.process.pid, signal.SIGUSR1)

        # Wait for screen file to appear
        start_time = time.time()
        while time.time() - start_time < timeout:
            if os.path.exists(SIGUSR1_SCREEN_PATH):
                # Small delay to ensure file is fully written
                time.sleep(0.05)
                try:
                    with open(SIGUSR1_SCREEN_PATH, 'r') as f:
                        lines = f.read().split('\n')
                    # Return first 24 lines, padded to 40 chars
                    result = []
                    for i in range(24):
                        if i < len(lines):
                            line = lines[i][:40].ljust(40)
                        else:
                            line = ' ' * 40
                        result.append(line)
                    return result
                except (IOError, OSError):
                    pass  # File not ready yet, keep waiting
            time.sleep(0.02)

        raise BobbinError("Timeout waiting for screen capture via SIGUSR1")

    def inject_keys(self, text: str, include_return: bool = False) -> None:
        """Inject keystrokes via debugger for reliable AI agent input.

        This method uses Bobbin's keyboard injection queue, which bypasses
        timing issues that can occur with stdin-based input.

        IMPORTANT: The Bobbin 'keys' command auto-exits the debugger after
        injecting keystrokes. We must NOT call exit_debugger() afterward,
        as that would send 'c' to the Apple II keyboard instead of the debugger.

        Args:
            text: Text to inject (will be uppercased)
            include_return: Add RETURN at end
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Auto-resume if paused - CPU needs to process keystrokes
        self._ensure_running()

        # Apple II is uppercase
        text = text.upper()
        if include_return:
            text += '\r'

        # Use control socket if available (much more reliable)
        if self.control_socket:
            try:
                self.control_socket.inject_keys(text)
                return
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        # Escape special characters for the keys command
        # Backslashes and quotes need escaping for Bobbin's command parser
        escaped = text.replace('\\', '\\\\')
        escaped = escaped.replace('"', '\\"')
        escaped = escaped.replace('\r', '\\r')

        # Enter debugger for key injection
        if not self.enter_debugger():
            raise BobbinError("Failed to enter debugger for key injection")

        # Send the keys command - this auto-exits the debugger
        self.process.sendline(f"keys {escaped}")

        # Wait for the "Injected N characters" confirmation
        try:
            self.process.expect(r'Injected \d+ characters\.', timeout=2.0)
        except pexpect.TIMEOUT:
            pass

        # keys command auto-exits debugger
        self.in_debugger = False

        # Wait for BASIC prompt to confirm ready for next command
        try:
            self.process.expect(r'\]', timeout=1.0)
        except pexpect.TIMEOUT:
            pass

        # Drain remaining output
        time.sleep(0.2)
        for _ in range(5):
            try:
                self.process.read_nonblocking(4096, timeout=0.03)
            except pexpect.TIMEOUT:
                break
            except pexpect.EOF:
                if not self.process.isalive():
                    raise BobbinError("Emulator died after key injection")
                break

    def type_text(self, text: str, delay: float = 0.02,
                  include_return: bool = False, use_inject: bool = True) -> None:
        """Type text into the emulator.

        Args:
            text: Text to type (will be uppercased)
            delay: Delay between keystrokes (ignored if use_inject=True)
            include_return: Add RETURN at end
            use_inject: Use reliable keyboard injection (default True for AI agents)
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Auto-resume if paused - CPU needs to process keystrokes
        self._ensure_running()

        # Use reliable injection by default
        if use_inject:
            self.inject_keys(text, include_return)
            return

        # stdin-based input
        if self.in_debugger:
            self.exit_debugger()

        # Drain any pending output before typing
        # This ensures clean state after debugger operations
        for _ in range(5):
            try:
                self.process.read_nonblocking(4096, timeout=0.02)
            except pexpect.TIMEOUT:
                break
            except pexpect.EOF:
                if not self.process.isalive():
                    raise BobbinError("Emulator died before typing")
                break

        # Small delay to ensure emulator is ready
        time.sleep(0.1)

        # Apple II is uppercase
        text = text.upper()

        for char in text:
            self.process.send(char)
            if delay > 0:
                time.sleep(delay)

        if include_return:
            self.process.send('\r')

        # Give emulator time to process the input
        time.sleep(0.2)

    def send_return(self) -> None:
        """Send RETURN key."""
        if self.in_debugger:
            self.exit_debugger()
        self.process.send('\r')

    def send_control(self, char: str) -> None:
        """Send a control character.

        Args:
            char: Character to send with Ctrl (e.g., 'C' for Ctrl-C)
        """
        if self.in_debugger:
            self.exit_debugger()
        self.process.sendcontrol(char.lower())

    def get_registers(self) -> dict:
        """Get CPU register values.

        Returns:
            Dict with A, X, Y, SP, PC, and flags
        """
        # Use control socket if available (much more reliable)
        if self.control_socket:
            try:
                cpu = self.control_socket.get_cpu_state()
                # Map control socket format to our format
                p = cpu.get('p', 0)
                return {
                    'A': cpu.get('a', 0),
                    'X': cpu.get('x', 0),
                    'Y': cpu.get('y', 0),
                    'SP': cpu.get('sp', 0),
                    'PC': cpu.get('pc', 0),
                    'N': bool(p & 0x80),
                    'V': bool(p & 0x40),
                    'B': bool(p & 0x10),
                    'D': bool(p & 0x08),
                    'I': bool(p & 0x04),
                    'Z': bool(p & 0x02),
                    'C': bool(p & 0x01),
                }
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        if not self.in_debugger:
            self.enter_debugger()

        # The debugger shows registers on entry
        # ACC: A0  X: 00  Y: 05  SP: F4          [N]   V   [U]  [B]   D    I    Z    C
        output = self.debugger_command("")

        registers = {
            'A': 0, 'X': 0, 'Y': 0, 'SP': 0, 'PC': 0,
            'N': False, 'V': False, 'B': False,
            'D': False, 'I': False, 'Z': False, 'C': False
        }

        # Parse ACC, X, Y, SP
        acc_match = re.search(r'ACC:\s*([0-9A-Fa-f]{2})', output)
        if acc_match:
            registers['A'] = int(acc_match.group(1), 16)

        x_match = re.search(r'X:\s*([0-9A-Fa-f]{2})', output)
        if x_match:
            registers['X'] = int(x_match.group(1), 16)

        y_match = re.search(r'Y:\s*([0-9A-Fa-f]{2})', output)
        if y_match:
            registers['Y'] = int(y_match.group(1), 16)

        sp_match = re.search(r'SP:\s*([0-9A-Fa-f]{2})', output)
        if sp_match:
            registers['SP'] = int(sp_match.group(1), 16)

        # Parse PC from instruction line (e.g., "0300:   B1 28")
        pc_match = re.search(r'^([0-9A-Fa-f]{4}):', output, re.MULTILINE)
        if pc_match:
            registers['PC'] = int(pc_match.group(1), 16)

        # Parse flags (bracketed = set)
        for flag in ['N', 'V', 'B', 'D', 'I', 'Z', 'C']:
            if f'[{flag}]' in output:
                registers[flag] = True

        return registers

    def reset(self, cold: bool = False) -> None:
        """Reset the emulator.

        Args:
            cold: If True, do a cold reset (full reboot). Otherwise warm reset.
        """
        # Auto-resume if paused
        self._ensure_running()

        # Use control socket if available (much more reliable)
        if self.control_socket:
            try:
                self.control_socket.reset(cold=cold)
                return
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        if not self.in_debugger:
            self.enter_debugger()

        if cold:
            self.debugger_command("rr")
        else:
            self.debugger_command("r")

        self.in_debugger = False

    def save_ram(self, filepath: str) -> bool:
        """Dump all RAM to a file.

        Args:
            filepath: Path to save RAM dump

        Returns:
            True if successful
        """
        self.debugger_command(f"save-ram {filepath}")
        return Path(filepath).exists()

    def wait_for_prompt(self, prompt: str = "]", timeout: float = 10.0) -> str:
        """Wait for a specific prompt character at start of line.

        Args:
            prompt: Prompt character to wait for
            timeout: Maximum wait time

        Returns:
            Text before the prompt
        """
        if self.in_debugger:
            self.exit_debugger()

        try:
            # Match prompt at start of line to avoid matching ] in other contexts
            # Use exact string match for reliability
            self.process.expect_exact('\n' + prompt, timeout=timeout)
            return self.process.before
        except pexpect.TIMEOUT:
            raise BobbinError(f"Timeout waiting for prompt '{prompt}'")

    def run_basic_command(self, command: str, timeout: float = 30.0) -> str:
        """Type a BASIC command and wait for the prompt to return.

        Uses stdin-based typing for reliable input, then waits and reads the screen.

        Args:
            command: BASIC command to execute
            timeout: Maximum wait time for command to complete

        Returns:
            Output from the command (screen contents)
        """
        # Use stdin-based typing - more reliable than debugger injection
        # because debugger entry via Ctrl-C can leak characters to Apple II
        command = command.upper()
        self.type_text(command, include_return=True, use_inject=False)

        # Wait for command to complete and fully process
        time.sleep(0.5)

        # Read screen using the standard method
        lines = self.read_screen()
        return '\n'.join(line.rstrip() for line in lines).strip()

    def capture_hgr(self, filepath: str, page: int = 1,
                    format: str = "ppm", color: bool = False) -> bool:
        """Capture HGR graphics to a file.

        Args:
            filepath: Output file path
            page: HGR page (1 or 2)
            format: Output format ('ascii', 'ppm')
            color: Use color mode for PPM (artifact colors)

        Returns:
            True if successful
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Use control socket if available (much more reliable)
        # Note: control socket only supports PPM format
        if self.control_socket and format == "ppm":
            try:
                result = self.control_socket.capture_hgr(filepath, page=page, color=color)
                return 'path' in result
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        was_in_debugger = self.in_debugger
        if not was_in_debugger:
            self.enter_debugger()

        # Build command based on format and page
        if format == "ascii":
            cmd = f"sha{'' if page == 1 else '2'} {filepath}"
        elif format == "ppm" and color:
            cmd = f"save-hgr{'' if page == 1 else '2'}-ppm-color {filepath}"
        else:  # ppm mono
            cmd = f"shp{'' if page == 1 else '2'} {filepath}"

        output = self.debugger_command(cmd)

        if not was_in_debugger:
            self.exit_debugger()

        return "Saved" in output

    def capture_gr(self, filepath: str, page: int = 1,
                   format: str = "ppm", native: bool = False) -> bool:
        """Capture GR (lo-res) graphics to a file.

        Args:
            filepath: Output file path
            page: GR page (1 or 2)
            format: Output format ('ascii', 'ppm')
            native: If True, save at native 40x48 resolution (ppm only)

        Returns:
            True if successful
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Use control socket if available (much more reliable)
        # Note: control socket only supports PPM format (scaled, not native)
        if self.control_socket and format == "ppm" and not native:
            try:
                result = self.control_socket.capture_gr(filepath, page=page)
                return 'path' in result
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        was_in_debugger = self.in_debugger
        if not was_in_debugger:
            self.enter_debugger()

        # Build command based on format and page
        page_suffix = "" if page == 1 else "2"
        if format == "ascii":
            cmd = f"sga{page_suffix} {filepath}"
        elif format == "ppm" and native:
            cmd = f"save-gr{page_suffix}-ppm-native {filepath}"
        else:  # ppm scaled
            cmd = f"sgp{page_suffix} {filepath}"

        output = self.debugger_command(cmd)

        if not was_in_debugger:
            self.exit_debugger()

        return "Saved" in output

    def capture_dhgr(self, filepath: str, page: int = 1,
                     format: str = "ppm") -> bool:
        """Capture DHGR (double hi-res) graphics to a file.

        Requires Apple //e with aux memory (128KB mode).

        Args:
            filepath: Output file path
            page: DHGR page (1 or 2)
            format: Output format ('ascii', 'ppm')

        Returns:
            True if successful
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Use control socket if available (much more reliable)
        # Note: control socket only supports PPM format
        if self.control_socket and format == "ppm":
            try:
                result = self.control_socket.capture_dhgr(filepath, page=page)
                return 'path' in result
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        was_in_debugger = self.in_debugger
        if not was_in_debugger:
            self.enter_debugger()

        # Build command based on format and page
        page_suffix = "" if page == 1 else "2"
        if format == "ascii":
            cmd = f"sdha{page_suffix} {filepath}"
        else:  # ppm
            cmd = f"sdhp{page_suffix} {filepath}"

        output = self.debugger_command(cmd)

        if not was_in_debugger:
            self.exit_debugger()

        return "Saved" in output

    def capture_dgr(self, filepath: str, page: int = 1,
                    format: str = "ppm", native: bool = False) -> bool:
        """Capture DGR (double lo-res) graphics to a file.

        Requires Apple //e with aux memory (128KB mode).

        Args:
            filepath: Output file path
            page: DGR page (1 or 2)
            format: Output format ('ascii', 'ppm')
            native: If True, save at native 80x48 resolution (ppm only)

        Returns:
            True if successful
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Use control socket if available (much more reliable)
        # Note: control socket only supports PPM format (scaled, not native)
        if self.control_socket and format == "ppm" and not native:
            try:
                result = self.control_socket.capture_dgr(filepath, page=page)
                return 'path' in result
            except ControlSocketError as e:
                raise BobbinError(f"Control socket error: {e}")

        # Fall back to debugger method
        was_in_debugger = self.in_debugger
        if not was_in_debugger:
            self.enter_debugger()

        # Build command based on format and page
        page_suffix = "" if page == 1 else "2"
        if format == "ascii":
            cmd = f"sdga{page_suffix} {filepath}"
        elif format == "ppm" and native:
            cmd = f"save-dgr{page_suffix}-ppm-native {filepath}"
        else:  # ppm scaled
            cmd = f"sdgp{page_suffix} {filepath}"

        output = self.debugger_command(cmd)

        if not was_in_debugger:
            self.exit_debugger()

        return "Saved" in output

    def save_state(self, filepath: str) -> dict:
        """Save emulator state (CPU, 128KB RAM, soft switches) to a file.

        Args:
            filepath: Output file path

        Returns:
            Dict with ok=True on success, or error message
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Requires control socket
        if not self.control_socket:
            return {"error": "Control socket not available"}

        try:
            return self.control_socket.save_state(filepath)
        except ControlSocketError as e:
            return {"error": str(e)}

    def load_state(self, filepath: str) -> dict:
        """Load emulator state from a file.

        Instantly restores CPU, 128KB RAM, and soft switches.

        Args:
            filepath: State file to load

        Returns:
            Dict with ok=True and version on success, or error message
        """
        if not self.is_running:
            raise BobbinError("Emulator not running")

        # Requires control socket
        if not self.control_socket:
            return {"error": "Control socket not available"}

        try:
            return self.control_socket.load_state(filepath)
        except ControlSocketError as e:
            return {"error": str(e)}
