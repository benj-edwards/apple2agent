"""Bobbin Control Socket client.

Provides a direct control channel to Bobbin emulator via Unix socket,
bypassing the fragile pexpect/PTY/signal mechanism.
"""

import json
import socket
import os
from typing import Optional


class ControlSocketError(Exception):
    """Error from control socket communication."""
    pass


class BobbinControlSocket:
    """Client for Bobbin's Unix socket control interface."""

    DEFAULT_SOCKET_PATH = "/tmp/bobbin.sock"

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        """Initialize control socket client.

        Args:
            socket_path: Path to Bobbin's control socket
        """
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None

    def connect(self, timeout: float = 5.0) -> bool:
        """Connect to the control socket.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully
        """
        if self.sock is not None:
            return True

        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect(self.socket_path)
            return True
        except (socket.error, OSError) as e:
            self.sock = None
            return False

    def disconnect(self) -> None:
        """Disconnect from the control socket."""
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to the socket."""
        return self.sock is not None

    def send_command(self, cmd: dict, timeout: float = 5.0) -> dict:
        """Send a command and receive response.

        Args:
            cmd: Command dictionary
            timeout: Response timeout in seconds

        Returns:
            Response dictionary

        Raises:
            ControlSocketError: On communication error
        """
        if self.sock is None:
            raise ControlSocketError("Not connected")

        try:
            # Send command as JSON + newline
            cmd_json = json.dumps(cmd) + "\n"
            self.sock.settimeout(timeout)
            self.sock.sendall(cmd_json.encode('utf-8'))

            # Receive response (newline-delimited)
            response = b""
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise ControlSocketError("Connection closed")
                response += chunk
                if b"\n" in response:
                    break

            # Parse JSON response
            response_str = response.decode('utf-8').strip()
            return json.loads(response_str)

        except socket.timeout:
            raise ControlSocketError("Timeout waiting for response")
        except json.JSONDecodeError as e:
            raise ControlSocketError(f"Invalid JSON response: {e}")
        except (socket.error, OSError) as e:
            self.disconnect()
            raise ControlSocketError(f"Socket error: {e}")

    # High-level convenience methods

    def ping(self) -> dict:
        """Ping the emulator.

        Returns:
            Dict with version and machine info
        """
        return self.send_command({"cmd": "ping"})

    def peek(self, addr: int, length: int = 1) -> list[int]:
        """Read memory.

        Args:
            addr: Starting address (0-65535)
            length: Number of bytes to read (1-4096)

        Returns:
            List of byte values
        """
        resp = self.send_command({"cmd": "peek", "addr": addr, "len": length})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return resp.get("data", [])

    def poke(self, addr: int, data: list[int]) -> int:
        """Write memory.

        Args:
            addr: Starting address
            data: List of byte values to write

        Returns:
            Number of bytes written
        """
        resp = self.send_command({"cmd": "poke", "addr": addr, "data": data})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return resp.get("count", 0)

    def load(self, addr: int, data: bytes) -> int:
        """Load binary data into memory.

        Args:
            addr: Starting address
            data: Binary data to load

        Returns:
            Number of bytes loaded
        """
        hex_data = data.hex()
        resp = self.send_command({"cmd": "load", "addr": addr, "hex": hex_data})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return resp.get("len", 0)

    def read_screen(self) -> list[str]:
        """Read text screen as list of strings.

        Returns:
            List of 24 strings, each 40 characters
        """
        resp = self.send_command({"cmd": "screen"})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return resp.get("lines", [])

    def read_screen_raw(self) -> list[int]:
        """Read raw screen memory ($0400-$07FF).

        Returns:
            List of 1024 byte values
        """
        resp = self.send_command({"cmd": "screen_raw"})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return resp.get("data", [])

    def inject_keys(self, text: str) -> int:
        """Inject keystrokes into keyboard buffer.

        Args:
            text: Text to inject (will be uppercased by Apple II)

        Returns:
            Number of characters injected
        """
        resp = self.send_command({"cmd": "keys", "text": text})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return resp.get("injected", 0)

    def get_cpu_state(self) -> dict:
        """Get CPU register state.

        Returns:
            Dict with pc, a, x, y, sp, p (flags)
        """
        resp = self.send_command({"cmd": "cpu"})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return {
            "pc": resp.get("pc", 0),
            "a": resp.get("a", 0),
            "x": resp.get("x", 0),
            "y": resp.get("y", 0),
            "sp": resp.get("sp", 0),
            "p": resp.get("p", 0),
        }

    def reset(self, cold: bool = False) -> bool:
        """Reset the CPU.

        Args:
            cold: If True, do a cold reset (full reboot)

        Returns:
            True if successful
        """
        resp = self.send_command({"cmd": "reset", "cold": cold})
        return resp.get("ok", False)

    def pause(self) -> bool:
        """Pause emulation (enter debugger).

        Returns:
            True if successful
        """
        resp = self.send_command({"cmd": "pause"})
        return resp.get("ok", False)

    def resume(self) -> bool:
        """Resume emulation (exit debugger).

        Returns:
            True if successful
        """
        resp = self.send_command({"cmd": "resume"})
        return resp.get("ok", False)

    def disk_status(self) -> dict:
        """Get disk drive status.

        Returns:
            Dict with active drive number and spinning status
        """
        resp = self.send_command({"cmd": "disk_status"})
        if "error" in resp:
            raise ControlSocketError(resp["error"])
        return resp

    def disk_insert(self, drive: int, path: str) -> bool:
        """Insert a disk image.

        Args:
            drive: Drive number (1 or 2)
            path: Path to disk image file

        Returns:
            True if successful
        """
        resp = self.send_command({"cmd": "disk_insert", "drive": drive, "path": path})
        return resp.get("ok", False)

    def disk_eject(self, drive: int) -> bool:
        """Eject a disk.

        Args:
            drive: Drive number (1 or 2)

        Returns:
            True if successful
        """
        resp = self.send_command({"cmd": "disk_eject", "drive": drive})
        return resp.get("ok", False)

    def quit(self) -> bool:
        """Shutdown the emulator.

        Returns:
            True if successful
        """
        try:
            resp = self.send_command({"cmd": "quit"})
            return resp.get("ok", False)
        except ControlSocketError:
            # Connection will close after quit
            return True
        finally:
            self.disconnect()


# Convenience function to check if socket is available
def socket_available(path: str = BobbinControlSocket.DEFAULT_SOCKET_PATH) -> bool:
    """Check if the control socket exists and is connectable.

    Args:
        path: Socket path to check

    Returns:
        True if socket is available
    """
    if not os.path.exists(path):
        return False

    client = BobbinControlSocket(path)
    if client.connect(timeout=1.0):
        try:
            client.ping()
            return True
        except ControlSocketError:
            pass
        finally:
            client.disconnect()
    return False
