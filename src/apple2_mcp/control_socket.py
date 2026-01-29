"""Bobbin control socket client.

Provides a Python interface to Bobbin's Unix socket control protocol.
This allows reliable AI/MCP integration without pexpect/PTY issues.

Protocol: JSON commands over Unix socket, newline-delimited responses.
"""

import json
import socket
import time
from typing import Optional, Any

DEFAULT_SOCKET_PATH = "/tmp/bobbin.sock"


class ControlSocketError(Exception):
    """Error from control socket communication."""
    pass


class BobbinControlSocket:
    """Client for Bobbin's Unix socket control interface."""

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        """Initialize the control socket client.

        Args:
            socket_path: Path to the Unix socket
        """
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None

    def connect(self, timeout: float = 5.0) -> bool:
        """Connect to the Bobbin control socket.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully
        """
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(timeout)
                self.sock.connect(self.socket_path)
                return True
            except (socket.error, FileNotFoundError):
                if self.sock:
                    self.sock.close()
                    self.sock = None
                time.sleep(0.1)
        return False

    def disconnect(self):
        """Disconnect from the control socket."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_command(self, cmd: dict, timeout: float = 5.0) -> dict:
        """Send a command and receive the response.

        Args:
            cmd: Command dictionary (must have "cmd" key)
            timeout: Response timeout

        Returns:
            Response dictionary

        Raises:
            ControlSocketError: On communication error
        """
        if not self.sock:
            raise ControlSocketError("Not connected")

        try:
            # Send command
            cmd_str = json.dumps(cmd) + "\n"
            self.sock.sendall(cmd_str.encode())

            # Receive response (read until newline)
            self.sock.settimeout(timeout)
            response = b""
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise ControlSocketError("Connection closed")
                response += chunk
                if b"\n" in response:
                    break

            # Parse response
            response_str = response.decode().strip()
            result = json.loads(response_str)

            if "error" in result:
                raise ControlSocketError(result["error"])

            return result

        except json.JSONDecodeError as e:
            raise ControlSocketError(f"Invalid JSON response: {e}")
        except socket.timeout:
            raise ControlSocketError("Response timeout")
        except socket.error as e:
            raise ControlSocketError(f"Socket error: {e}")

    # =========================================================================
    # Basic Commands
    # =========================================================================

    def ping(self) -> dict:
        """Ping the emulator to check connection.

        Returns:
            Dict with version, machine type, and paused state
        """
        return self.send_command({"cmd": "ping"})

    def quit(self):
        """Quit the emulator."""
        try:
            self.send_command({"cmd": "quit"})
        except ControlSocketError:
            pass  # Connection will close

    # =========================================================================
    # Memory Commands
    # =========================================================================

    def peek(self, addr: int, length: int = 1) -> list[int]:
        """Read bytes from memory.

        Args:
            addr: Starting address (0-65535)
            length: Number of bytes to read (1-4096)

        Returns:
            List of byte values
        """
        result = self.send_command({"cmd": "peek", "addr": addr, "len": length})
        return result.get("data", [])

    def poke(self, addr: int, data: list[int]) -> int:
        """Write bytes to memory.

        Args:
            addr: Starting address
            data: List of byte values to write

        Returns:
            Number of bytes written
        """
        result = self.send_command({"cmd": "poke", "addr": addr, "data": data})
        return result.get("count", 0)

    def load(self, addr: int, hex_data: str) -> int:
        """Load hex data into memory.

        Args:
            addr: Starting address
            hex_data: Hex string (e.g., "A9008D0008")

        Returns:
            Number of bytes loaded
        """
        result = self.send_command({"cmd": "load", "addr": addr, "hex": hex_data})
        return result.get("len", 0)

    # =========================================================================
    # Display Commands
    # =========================================================================

    def read_screen(self) -> list[str]:
        """Read the text screen as decoded ASCII lines.

        Returns:
            List of 24 strings, each 40 characters
        """
        result = self.send_command({"cmd": "screen"})
        return result.get("lines", [])

    def read_screen_raw(self) -> list[int]:
        """Read raw screen memory ($0400-$07FF).

        Returns:
            List of 1024 byte values
        """
        result = self.send_command({"cmd": "screen_raw"})
        return result.get("data", [])

    # =========================================================================
    # Input Commands
    # =========================================================================

    def inject_keys(self, text: str) -> int:
        """Inject keystrokes into the keyboard buffer.

        Args:
            text: Text to inject (will be processed by Apple II)

        Returns:
            Number of characters injected
        """
        result = self.send_command({"cmd": "keys", "text": text})
        return result.get("injected", 0)

    # =========================================================================
    # CPU Commands
    # =========================================================================

    def get_cpu_state(self) -> dict:
        """Get CPU register state.

        Returns:
            Dict with pc, a, x, y, sp, p, cycles, instructions, frames
        """
        return self.send_command({"cmd": "cpu"})

    def reset(self, cold: bool = False):
        """Reset the CPU.

        Args:
            cold: If True, do a cold reset (full reboot)
        """
        self.send_command({"cmd": "reset", "cold": cold})

    def step(self, count: int = 1) -> dict:
        """Single-step one or more instructions.

        Args:
            count: Number of instructions to execute (1-1000)

        Returns:
            Dict with new CPU state (pc, a, x, y, sp, p)
        """
        return self.send_command({"cmd": "step", "count": count})

    def pause(self):
        """Pause emulation."""
        self.send_command({"cmd": "pause"})

    def resume(self):
        """Resume emulation."""
        self.send_command({"cmd": "resume"})

    def call(self, addr: int) -> dict:
        """Call a subroutine (JSR equivalent).

        Args:
            addr: Address to call

        Returns:
            Dict with new pc and return address
        """
        return self.send_command({"cmd": "call", "addr": addr})

    # =========================================================================
    # Breakpoint Commands
    # =========================================================================

    def break_set(self, addr: int) -> dict:
        """Set a breakpoint.

        Args:
            addr: Address to break at

        Returns:
            Dict with breakpoint id
        """
        return self.send_command({"cmd": "break_set", "addr": addr})

    def break_clear(self, id: int = None, addr: int = None):
        """Clear a breakpoint.

        Args:
            id: Breakpoint ID to clear
            addr: Address to clear breakpoint at
        """
        cmd = {"cmd": "break_clear"}
        if id is not None:
            cmd["id"] = id
        if addr is not None:
            cmd["addr"] = addr
        self.send_command(cmd)

    def break_list(self) -> list[dict]:
        """List all breakpoints.

        Returns:
            List of breakpoint dicts with id, addr, enabled, type
        """
        result = self.send_command({"cmd": "break_list"})
        return result.get("breakpoints", [])

    def break_enable(self, id: int):
        """Enable a breakpoint.

        Args:
            id: Breakpoint ID to enable
        """
        self.send_command({"cmd": "break_enable", "id": id})

    def break_disable(self, id: int):
        """Disable a breakpoint.

        Args:
            id: Breakpoint ID to disable
        """
        self.send_command({"cmd": "break_disable", "id": id})

    def watch_set(self, addr: int) -> dict:
        """Set a watchpoint (breaks when memory changes).

        Args:
            addr: Address to watch

        Returns:
            Dict with watchpoint id and current value
        """
        return self.send_command({"cmd": "watch_set", "addr": addr})

    # =========================================================================
    # Disk Commands
    # =========================================================================

    def disk_status(self) -> dict:
        """Get disk drive status.

        Returns:
            Dict with active drive and spinning state
        """
        return self.send_command({"cmd": "disk_status"})

    def disk_insert(self, path: str, drive: int = 1):
        """Insert a disk image.

        Args:
            path: Path to disk image file
            drive: Drive number (1 or 2)
        """
        self.send_command({"cmd": "disk_insert", "path": path, "drive": drive})

    def disk_eject(self, drive: int = 1):
        """Eject a disk.

        Args:
            drive: Drive number (1 or 2)
        """
        self.send_command({"cmd": "disk_eject", "drive": drive})

    # =========================================================================
    # Graphics Commands
    # =========================================================================

    def capture_hgr(self, path: str, page: int = 1, color: bool = False) -> dict:
        """Capture HGR graphics to a PPM file.

        Args:
            path: Output file path
            page: HGR page (1 or 2)
            color: Use color mode

        Returns:
            Dict with path, width, height
        """
        return self.send_command({"cmd": "hgr", "path": path, "page": page, "color": color})

    def capture_gr(self, path: str, page: int = 1) -> dict:
        """Capture GR (lo-res) graphics to a PPM file.

        Args:
            path: Output file path
            page: GR page (1 or 2)

        Returns:
            Dict with path, width, height
        """
        return self.send_command({"cmd": "gr", "path": path, "page": page})

    def capture_dhgr(self, path: str, page: int = 1) -> dict:
        """Capture DHGR (double hi-res) graphics to a PPM file.

        Args:
            path: Output file path
            page: DHGR page (1 or 2)

        Returns:
            Dict with path, width, height
        """
        return self.send_command({"cmd": "dhgr", "path": path, "page": page})

    def capture_dgr(self, path: str, page: int = 1) -> dict:
        """Capture DGR (double lo-res) graphics to a PPM file.

        Args:
            path: Output file path
            page: DGR page (1 or 2)

        Returns:
            Dict with path, width, height
        """
        return self.send_command({"cmd": "dgr", "path": path, "page": page})

    # =========================================================================
    # State Commands
    # =========================================================================

    def save_state(self, path: str) -> dict:
        """Save emulator state to a file.

        Args:
            path: Output file path

        Returns:
            Dict with path
        """
        return self.send_command({"cmd": "save_state", "path": path})

    def load_state(self, path: str) -> dict:
        """Load emulator state from a file.

        Args:
            path: Input file path

        Returns:
            Dict with path
        """
        return self.send_command({"cmd": "load_state", "path": path})

    # =========================================================================
    # Speed and Timing Commands
    # =========================================================================

    def set_speed(self, turbo: bool) -> dict:
        """Set emulation speed.

        Args:
            turbo: True for turbo (unthrottled) mode

        Returns:
            Dict with current turbo state
        """
        return self.send_command({"cmd": "speed", "turbo": turbo})

    def get_cycles(self) -> dict:
        """Get cycle/instruction/frame counts.

        Returns:
            Dict with cycles, instructions, frames
        """
        return self.send_command({"cmd": "cycles"})

    # =========================================================================
    # Trace Commands
    # =========================================================================

    def trace(self, enable: bool) -> dict:
        """Enable or disable instruction tracing.

        Args:
            enable: True to enable tracing

        Returns:
            Dict with tracing state and file path
        """
        return self.send_command({"cmd": "trace", "enable": enable})

    # =========================================================================
    # Mouse Commands
    # =========================================================================

    def mouse(self, x: int = None, y: int = None, button: bool = None) -> dict:
        """Control mouse position and button.

        Args:
            x: X position (0-279 for HGR)
            y: Y position (0-191 for HGR)
            button: Button state

        Returns:
            Dict with current x, y, button, slot
        """
        cmd = {"cmd": "mouse"}
        if x is not None:
            cmd["x"] = x
        if y is not None:
            cmd["y"] = y
        if button is not None:
            cmd["button"] = button
        return self.send_command(cmd)

    # =========================================================================
    # System Commands
    # =========================================================================

    def get_slots(self) -> dict:
        """Get peripheral slot configuration.

        Returns:
            Dict with slots and their contents
        """
        result = self.send_command({"cmd": "slots"})
        return result.get("slots", {})

    def get_softswitches(self) -> dict:
        """Get soft switch states.

        Returns:
            Dict with switch states (text, mixed, page2, hires, etc.)
        """
        result = self.send_command({"cmd": "softswitches"})
        return result.get("switches", {})

    def disasm(self, addr: int = None, count: int = 16) -> list[dict]:
        """Disassemble memory.

        Args:
            addr: Starting address (default: current PC)
            count: Number of instructions (1-64)

        Returns:
            List of dicts with addr and bytes
        """
        cmd = {"cmd": "disasm", "count": count}
        if addr is not None:
            cmd["addr"] = addr
        result = self.send_command(cmd)
        return result.get("lines", [])
