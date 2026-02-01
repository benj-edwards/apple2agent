#!/usr/bin/env python3
"""
Emulator Bridge for Apple II Agent Proxy

Provides a control socket interface to Bobbin emulator that matches
the MCP tool calling convention used by agentic_claude.py.

This allows the proxy to run the agentic loop without the MCP server.
"""

import os
import signal
import sys
import subprocess
import time
import tempfile
from typing import Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from apple2_mcp.control_socket import BobbinControlSocket, ControlSocketError

# PID file for tracking emulator (separate from MCP server's)
BRIDGE_PID_FILE = "/tmp/bobbin_bridge.pid"


def _kill_stale_bobbin():
    """Kill any stale Bobbin process from PID file."""
    if os.path.exists(BRIDGE_PID_FILE):
        try:
            with open(BRIDGE_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # Check if exists
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except (ValueError, ProcessLookupError, FileNotFoundError, PermissionError):
            pass
        finally:
            try:
                os.remove(BRIDGE_PID_FILE)
            except OSError:
                pass

# Also need the tokenizer
sys.path.insert(0, os.path.dirname(__file__))
from basic_tokenizer_streaming import tokenize_program


SOCKET_PATH = "/tmp/bobbin.sock"
BOBBIN_PATH = os.path.join(os.path.dirname(__file__), '..', 'bobbin', 'src', 'bobbin')


class EmulatorBridge:
    """Bridge between agentic_claude tool calls and Bobbin control socket."""

    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = socket_path
        self.sock: Optional[BobbinControlSocket] = None
        self.bobbin_process: Optional[subprocess.Popen] = None
        self.emulator_running = False

    def _ensure_connected(self) -> bool:
        """Ensure we're connected to the control socket."""
        if self.sock and self.emulator_running:
            try:
                self.sock.ping()
                return True
            except ControlSocketError:
                self.sock = None

        if self.sock is None:
            self.sock = BobbinControlSocket(self.socket_path)
            if self.sock.connect(timeout=2.0):
                self.emulator_running = True
                return True
            self.sock = None
            return False
        return True

    def boot(self, machine: str = "enhanced", disk: Optional[str] = None,
             uthernet2: bool = False, mouse: bool = False) -> dict:
        """Start the Bobbin emulator."""
        # Kill any existing emulator
        if self.bobbin_process:
            self.shutdown()

        # Kill any stale emulator from previous sessions
        _kill_stale_bobbin()

        # Remove old socket
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

        # Build command
        cmd = [
            BOBBIN_PATH,
            "--simple",
            "--remain",
            "--control-socket", self.socket_path,
            "-m", machine
        ]

        if disk:
            cmd.extend(["--disk", disk])
        if uthernet2:
            cmd.extend(["--slot", "3:uthernet2"])
        if mouse:
            cmd.extend(["--slot", "4:mouse"])

        # Start emulator in background
        self.bobbin_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Track PID for cleanup on restart
        try:
            with open(BRIDGE_PID_FILE, 'w') as f:
                f.write(str(self.bobbin_process.pid))
        except OSError:
            pass

        # Wait for socket
        self.sock = BobbinControlSocket(self.socket_path)
        if not self.sock.connect(timeout=10.0):
            self.bobbin_process.kill()
            self.bobbin_process = None
            return {"error": "Failed to connect to emulator"}

        self.emulator_running = True
        return {"ok": True, "machine": machine}

    def shutdown(self):
        """Stop the emulator."""
        if self.sock:
            try:
                self.sock.quit()
            except ControlSocketError:
                pass
            self.sock.disconnect()
            self.sock = None

        if self.bobbin_process:
            self.bobbin_process.terminate()
            try:
                self.bobbin_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.bobbin_process.kill()
            self.bobbin_process = None

        self.emulator_running = False

        # Clean up PID file
        try:
            os.remove(BRIDGE_PID_FILE)
        except OSError:
            pass

        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

    def call_tool(self, tool_name: str, params: dict) -> Any:
        """
        Call an MCP-style tool and return the result.

        This is the main interface used by agentic_claude.py.
        """
        # Boot tool doesn't require existing connection
        if tool_name == "mcp__apple2-mcp__boot":
            return self.boot(
                machine=params.get("machine", "enhanced"),
                disk=params.get("disk"),
                uthernet2=params.get("uthernet2", False),
                mouse=params.get("mouse", False)
            )

        # All other tools require connection
        if not self._ensure_connected():
            return {"error": "Emulator not running"}

        try:
            return self._dispatch_tool(tool_name, params)
        except ControlSocketError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Tool error: {e}"}

    def _dispatch_tool(self, tool_name: str, params: dict) -> Any:
        """Dispatch a tool call to the appropriate handler."""

        # Screen reading
        if tool_name == "mcp__apple2-mcp__read_screen":
            lines = self.sock.read_screen()
            return "\n".join(lines)

        # Type text
        if tool_name == "mcp__apple2-mcp__type_text":
            text = params.get("text", "")
            press_return = params.get("press_return", True)
            if press_return:
                text += "\r"
            count = self.sock.inject_keys(text.upper())
            return {"ok": True, "injected": count}

        # Run BASIC command
        if tool_name == "mcp__apple2-mcp__run_basic":
            command = params.get("command", "")
            self.sock.inject_keys(command.upper() + "\r")
            # Wait for prompt
            time.sleep(0.5)
            lines = self.sock.read_screen()
            return "\n".join(lines)

        # Tokenize BASIC
        if tool_name == "mcp__apple2-mcp__tokenize":
            source = params.get("source", "")
            try:
                token_bytes = tokenize_program(source)
                hex_str = " ".join(f"{b:02X}" for b in token_bytes)
                return {"hex": hex_str, "bytes": len(token_bytes)}
            except Exception as e:
                return {"error": str(e)}

        # Inject tokenized BASIC
        if tool_name == "mcp__apple2-mcp__inject_tokenized_basic":
            hex_data = params.get("hex_data", "")
            auto_run = params.get("auto_run", False)
            load_addr = params.get("load_address", 0x0801)

            # Parse hex string to bytes
            hex_clean = hex_data.replace(" ", "").replace("\n", "")
            data = [int(hex_clean[i:i+2], 16) for i in range(0, len(hex_clean), 2)]

            # Poke into memory
            self.sock.poke(load_addr, data)

            # Update BASIC pointers
            end_addr = load_addr + len(data)
            # TXTTAB = $67-$68 (start of BASIC)
            self.sock.poke(0x67, [load_addr & 0xFF, (load_addr >> 8) & 0xFF])
            # VARTAB = $69-$6A (end of BASIC / start of variables)
            self.sock.poke(0x69, [end_addr & 0xFF, (end_addr >> 8) & 0xFF])
            # ARYTAB = $6B-$6C
            self.sock.poke(0x6B, [end_addr & 0xFF, (end_addr >> 8) & 0xFF])
            # STREND = $6D-$6E
            self.sock.poke(0x6D, [end_addr & 0xFF, (end_addr >> 8) & 0xFF])

            result = f"Injected {len(data)} bytes at ${load_addr:04X}"

            if auto_run:
                self.sock.inject_keys("RUN\r")
                time.sleep(1.0)
                lines = self.sock.read_screen()
                result += "\n\nRUN output:\n" + "\n".join(lines)

            return result

        # Memory operations
        if tool_name == "mcp__apple2-mcp__peek":
            addr = params.get("address", 0)
            count = params.get("count", 1)
            data = self.sock.peek(addr, count)
            fmt = params.get("format", "hex")
            if fmt == "hex":
                return " ".join(f"{b:02X}" for b in data)
            elif fmt == "decimal":
                return data
            else:  # ascii
                return "".join(chr(b & 0x7F) if 32 <= (b & 0x7F) < 127 else "." for b in data)

        if tool_name == "mcp__apple2-mcp__poke":
            addr = params.get("address", 0)
            data = params.get("data", [])
            count = self.sock.poke(addr, data)
            return {"ok": True, "count": count}

        if tool_name == "mcp__apple2-mcp__load_binary":
            addr = params.get("address", 0x6000)
            hex_data = params.get("hex_data", "")
            count = self.sock.load(addr, hex_data.replace(" ", ""))
            return {"ok": True, "count": count}

        # Graphics capture (ASCII)
        if tool_name == "mcp__apple2-mcp__read_gr_ascii":
            page = params.get("page", 1)
            # Read lo-res memory and convert to ASCII
            base = 0x400 if page == 1 else 0x800
            result = []
            for row in range(24):
                line = ""
                # Calculate row address (Apple II screen has weird memory layout)
                row_base = base + (row & 7) * 0x80 + (row >> 3) * 0x28
                for col in range(40):
                    byte = self.sock.peek(row_base + col, 1)[0]
                    lo = byte & 0x0F
                    hi = (byte >> 4) & 0x0F
                    line += f"{lo:X}{hi:X}"
                result.append(line[:40])  # Top half
            return "\n".join(result)

        if tool_name == "mcp__apple2-mcp__read_hgr_ascii":
            # Simplified HGR to ASCII - just return a placeholder
            return "[HGR screen capture - use capture_hgr for PNG]"

        # CPU operations
        if tool_name == "mcp__apple2-mcp__get_registers":
            return self.sock.get_cpu_state()

        if tool_name == "mcp__apple2-mcp__call":
            addr = params.get("address", 0x6000)
            return self.sock.call(addr)

        if tool_name == "mcp__apple2-mcp__reset":
            cold = params.get("cold", False)
            self.sock.reset(cold)
            return {"ok": True}

        # Assembly (requires external assembler - ca65)
        if tool_name == "mcp__apple2-mcp__assemble":
            source = params.get("source", "")
            load_addr = params.get("load_address", 0x6000)
            return self._assemble(source, load_addr)

        # Send key
        if tool_name == "mcp__apple2-mcp__send_key":
            key = params.get("key", "RETURN")
            key_map = {
                "RETURN": "\r",
                "ESCAPE": "\x1b",
                "CTRL-C": "\x03",
                "CTRL-RESET": None  # Special handling
            }
            if key == "CTRL-RESET":
                self.sock.reset(cold=False)
                return {"ok": True}
            char = key_map.get(key, "\r")
            self.sock.inject_keys(char)
            return {"ok": True}

        # State save/load
        if tool_name == "mcp__apple2-mcp__save_state":
            path = params.get("path", "/tmp/state.bin")
            return self.sock.save_state(path)

        if tool_name == "mcp__apple2-mcp__load_state":
            path = params.get("path", "/tmp/state.bin")
            return self.sock.load_state(path)

        return {"error": f"Unknown tool: {tool_name}"}

    def _assemble(self, source: str, load_addr: int) -> dict:
        """Assemble 6502 code using ca65/ld65."""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                asm_file = os.path.join(tmpdir, "code.s")
                obj_file = os.path.join(tmpdir, "code.o")
                bin_file = os.path.join(tmpdir, "code.bin")
                cfg_file = os.path.join(tmpdir, "code.cfg")

                # Write source with .org directive if not present
                if ".org" not in source.lower():
                    source = f".org ${load_addr:04X}\n" + source

                with open(asm_file, "w") as f:
                    f.write(source)

                # Create linker config
                cfg_content = f"""MEMORY {{
    CODE: start = ${load_addr:04X}, size = $8000, file = %O;
}}
SEGMENTS {{
    CODE: load = CODE, type = rw;
}}
"""
                with open(cfg_file, "w") as f:
                    f.write(cfg_content)

                # Assemble
                result = subprocess.run(
                    ["ca65", "-o", obj_file, asm_file],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    return {"error": f"Assembly error: {result.stderr}"}

                # Link
                result = subprocess.run(
                    ["ld65", "-o", bin_file, "-C", cfg_file, obj_file],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    return {"error": f"Link error: {result.stderr}"}

                # Read binary
                with open(bin_file, "rb") as f:
                    binary = f.read()

                hex_str = " ".join(f"{b:02X}" for b in binary)
                return {
                    "hex": hex_str,
                    "bytes": len(binary),
                    "load_address": load_addr
                }

        except FileNotFoundError:
            return {"error": "ca65/ld65 not found - install cc65 toolchain"}
        except Exception as e:
            return {"error": str(e)}


# Singleton instance
_bridge: Optional[EmulatorBridge] = None


def get_bridge() -> EmulatorBridge:
    """Get the singleton EmulatorBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = EmulatorBridge()
    return _bridge


def mcp_call(tool_name: str, params: dict) -> Any:
    """
    MCP-style tool call interface for agentic_claude.py.

    This is the function to pass as mcp_call parameter.
    """
    return get_bridge().call_tool(tool_name, params)
