#!/usr/bin/env python3
"""
Emulator Bridge for Apple II Agent Proxy

Provides a control socket interface to Bobbin emulator that matches
the MCP tool calling convention used by agentic_claude.py.

This allows the proxy to run the agentic loop without the MCP server.
"""

import os
import signal
import random
import struct
import sys
import subprocess
import time
import tempfile
from typing import Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from apple2_mcp.control_socket import BobbinControlSocket, ControlSocketError

# PID file for tracking emulator (separate from MCP server's)
_BRIDGE_DIR = os.environ.get("APPLE2_BRIDGE_DIR", "/tmp")
BRIDGE_PID_FILE = os.path.join(_BRIDGE_DIR, "bobbin_bridge.pid")


def _is_our_bobbin(pid: int) -> bool:
    """True only if pid is a Bobbin started with the bridge's socket.

    PIDs get reused; never signal a process just because an old PID file
    names it.
    """
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return False
    return "bobbin" in out and SOCKET_PATH in out


def _kill_stale_bobbin():
    """Kill a stale bridge Bobbin left over from a previous proxy run."""
    if os.path.exists(BRIDGE_PID_FILE):
        try:
            with open(BRIDGE_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if not _is_our_bobbin(pid):
                raise ProcessLookupError
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


SOCKET_PATH = os.path.join(_BRIDGE_DIR, "bobbin_bridge.sock")  # Separate from main emulator at /tmp/bobbin.sock
BOBBIN_PATH = os.path.join(os.path.dirname(__file__), '..', 'bobbin', 'src', 'bobbin')
STATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'states')

# Bobbin state file: header, Registers struct, 64K main, 64K aux, switches
STATE_MAIN = 16 + 8
STATE_AUX = STATE_MAIN + 0x10000

# Page 3 hooks exactly as AGENT.BIN installs them at $03C8: BRK stub, the
# $03D0 return entry (filled in separately), then the KSW hook at $03D3 that
# sends ESC at the ] prompt to $03D0. In the test machine $03D0 is a parking
# loop, so "PC at $03D0" means the program came back to the agent.
PAGE3_HOOKS = bytes.fromhex(
    "a9c58dc7034cd003000000201bfdc99bd00e68a86848c9fdf0ee9848a99ba42460")
PAGE3_START = 0x03C8
KSW_HOOK = 0x03D3
CRASH_MARK = 0x03C7
CRASH_MAGIC = 0xC5
RETURN_ENTRY = 0x03D0
GUARD_BYTE = 0xDB

# Key names for test scripts: "{ESC}", "{LEFT}", "{CTRL-C}"...
KEY_GAP = 0.08     # seconds between typed keys (~12 a second)

KEY_NAMES = {
    "ESC": "\x1b", "ESCAPE": "\x1b", "RETURN": "\r", "ENTER": "\r",
    "SPACE": " ", "LEFT": "\x08", "RIGHT": "\x15", "UP": "\x0b",
    "DOWN": "\x0a", "TAB": "\t", "DELETE": "\x7f",
}


def parse_keys(spec: str) -> str:
    """Turn 'AB{LEFT}{RETURN}{CTRL-C}' into raw keystrokes."""
    out = []
    i = 0
    while i < len(spec):
        if spec[i] == '{':
            end = spec.find('}', i)
            if end > i:
                name = spec[i + 1:end].upper()
                if name in KEY_NAMES:
                    out.append(KEY_NAMES[name])
                    i = end + 1
                    continue
                if name.startswith("CTRL-") and len(name) == 6 and name[5].isalpha():
                    out.append(chr(ord(name[5]) - 64))
                    i = end + 1
                    continue
        out.append(spec[i])
        i += 1
    return "".join(out)


class EmulatorBridge:
    """Bridge between agentic_claude tool calls and Bobbin control socket."""

    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = socket_path
        self.sock: Optional[BobbinControlSocket] = None
        self.bobbin_process: Optional[subprocess.Popen] = None
        self.emulator_running = False
        self._program = None      # deploy.Program last started by run_program

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
        # --no-turbo: --simple otherwise runs unthrottled (~40x real speed),
        # and Claude judges game speed and timing from these runs - they
        # must look the way the real 1 MHz Apple II will
        cmd = [
            BOBBIN_PATH,
            "--simple",
            "--no-turbo",
            "--remain",
            "--control-socket", self.socket_path,
            "-m", machine
        ]

        if disk:
            cmd.extend(["--disk", disk])
        if uthernet2:
            cmd.append("--uthernet2")
        if mouse:
            cmd.extend(["--slot", "4:mouse"])

        # Start emulator in background
        # Own stdin pipe: Bobbin's --simple interface reads stdin and makes it
        # O_NONBLOCK. Inheriting ours (under the MCP server that's its
        # JSON-RPC pipe) would break whoever else reads it. A pipe we hold
        # open also keeps Bobbin from quitting on EOF.
        self.bobbin_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
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

    def _load_env(self, tool_name: str) -> dict:
        """Boot emulator if needed and load a pre-baked environment state."""
        states_dir = os.path.join(os.path.dirname(__file__), '..', 'states')
        state_map = {
            "mcp__apple2-mcp__load_basic_env": "basic.state",
            "mcp__apple2-mcp__load_prodos_env": "prodos.state",
            "mcp__apple2-mcp__load_dos33_env": "dos33.state",
        }
        state_file = os.path.join(states_dir, state_map[tool_name])
        if not os.path.exists(state_file):
            return {"error": f"State file not found: {state_file}"}

        # Boot emulator if not running
        if not self.emulator_running:
            result = self.boot(machine="enhanced")
            if "error" in result:
                return result

        # Load the state
        result = self.sock.load_state(state_file)
        if result.get("ok"):
            env_name = state_map[tool_name].replace('.state', '').upper()
            return {"ok": True, "env": env_name}
        return result

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

        # Instant environment loaders - boot + load state in one call
        if tool_name in ("mcp__apple2-mcp__load_basic_env",
                         "mcp__apple2-mcp__load_prodos_env",
                         "mcp__apple2-mcp__load_dos33_env"):
            return self._load_env(tool_name)

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

        # ProDOS disk operations
        if tool_name == "mcp__apple2-mcp__prodos_list":
            disk = params.get("disk", "")
            return self._prodos_list(disk)

        if tool_name == "mcp__apple2-mcp__prodos_add":
            disk = params.get("disk", "")
            local_file = params.get("file", "")
            name = params.get("name", "")
            file_type = params.get("type", "TXT")
            aux_addr = params.get("addr", "0000")
            return self._prodos_add(disk, local_file, name, file_type, aux_addr)

        return {"error": f"Unknown tool: {tool_name}"}

    # =========================================================================
    # Program test harness - launches a deploy.Program the way AGENT.BIN
    # does on the real machine, then watches what it does.
    # =========================================================================

    def run_program(self, program) -> dict:
        """Start `program` in a fresh BASIC environment. Returns a launch info dict."""
        if not self.emulator_running:
            result = self.boot(machine="enhanced")
            if "error" in result:
                return result
        state = bytearray(open(os.path.join(STATES_DIR, "basic.state"), "rb").read())

        def put(addr, data, aux=False):
            base = (STATE_AUX if aux else STATE_MAIN) + addr
            state[base:base + len(data)] = data

        # A real Apple II's memory is never clean: the agent's load image,
        # earlier previews, whatever the EXCHANGE swap brought in from aux.
        # A program that assumes zeroed memory must fail here, not there.
        junk = random.Random(0xA2).randbytes(0xBF00 - 0x0800)
        put(0x0800, junk)
        put(0x0800, junk[::-1], aux=True)

        # The agent's memory gets a guard pattern so we can tell if the
        # program would have trampled it on the real machine
        resident = program.mode == 0
        guard = bytes([GUARD_BYTE]) * (0xBF00 - 0x6000)
        put(0x6000, guard, aux=not resident)
        put(0xBF00, bytes([GUARD_BYTE]) * 0x100)

        for addr, data in program.chunks:
            put(addr, data)

        # Page 3 exactly as the agent leaves it
        put(PAGE3_START, PAGE3_HOOKS)
        put(RETURN_ENTRY, bytes([0x4C, RETURN_ENTRY & 0xFF, RETURN_ENTRY >> 8]))
        put(CRASH_MARK, b"\x00")
        put(0x03F0, bytes([PAGE3_START & 0xFF, PAGE3_START >> 8]))  # BRK
        put(0x03F2, bytes([0xD0, 0x03, 0x03 ^ 0xA5]))    # reset
        put(0x03F5, bytes([0x4C, 0xD0, 0x03]))           # &
        put(0x03F8, bytes([0x4C, 0xD0, 0x03]))           # Ctrl-Y
        put(0x36, bytes([0xF0, 0xFD]))                   # CSW = COUT1
        is_basic = program.kind == 0
        put(0x38, bytes([KSW_HOOK & 0xFF, KSW_HOOK >> 8]) if is_basic
            else bytes([0x1B, 0xFD]))

        # Launcher at $0300 (the real one lives in the stack page)
        launcher = bytearray([0xA2, 0xFF, 0x9A, 0x20, 0x58, 0xFC])  # LDX #$FF TXS JSR HOME
        if is_basic:
            w = lambda v: bytes([v & 0xFF, v >> 8])
            put(0x67, w(program.start))
            put(0xAF, w(program.prgend))
            for zp in (0x69, 0x6B, 0x6D):
                put(zp, w(program.lomem))
            put(0x6F, w(program.himem))
            put(0x73, w(program.himem))
            put(0xD8, b"\x00")
            put(0xF2, b"\x00")
            launcher += bytes([0x4C, 0x66, 0xD5])                   # JMP $D566 (RUN)
        else:
            ret = RETURN_ENTRY - 1
            launcher += bytes([0xA9, ret >> 8, 0x48, 0xA9, ret & 0xFF, 0x48,
                               0x4C, program.start & 0xFF, program.start >> 8])
        put(0x0300, bytes(launcher))

        # CPU starts at the launcher
        struct.pack_into('<HBBBBB', state, 16, 0x0300, 0xFF, 0x24, 0, 0, 0)

        path = os.path.join(_BRIDGE_DIR, "bobbin_launch.state")
        with open(path, "wb") as f:
            f.write(state)
        if not self._ensure_connected():
            return {"error": "Emulator not running"}
        result = self.sock.load_state(path)
        if not result.get("ok"):
            return {"error": f"load_state failed: {result}"}
        self._program = program
        self._launched_at = time.time()
        return {"ok": True}

    def send_input(self, keys: str):
        """Type keys into the running program ('{LEFT}', '{ESC}'... allowed).

        Each key goes in as the //e keyboard's own code (bit 7 set), which
        Bobbin passes through untouched - plain LF would arrive as RETURN,
        not the down arrow ($8A). And keys come at a quick typist's pace:
        all at once, a program that flushes the keyboard "drops" them in a
        way a person never sees.
        """
        for ch in parse_keys(keys):
            self.sock.inject_keys(chr(ord(ch) | 0x80))
            time.sleep(KEY_GAP)

    def _snapshot(self) -> bytes:
        path = os.path.join(_BRIDGE_DIR, "bobbin_snap.state")
        self.sock.save_state(path)
        with open(path, "rb") as f:
            return f.read()

    def observe(self, image: bool = True, force_image: bool = False) -> dict:
        """What is the program doing right now?

        Returns dict with: status (one line), screen (text lines), mode,
        image (PNG bytes or None), hgr_page (raw 8K page shown, for
        previews), problems (list of strings).
        """
        snap = self._snapshot()
        main = snap[STATE_MAIN:STATE_MAIN + 0x10000]
        aux = snap[STATE_AUX:STATE_AUX + 0x10000]
        pc, sp = struct.unpack_from('<HB', snap, 16)
        sw = self.sock.get_softswitches()
        sw = sw.get("switches", sw)
        screen = self.sock.read_screen()

        if not sw.get("text", True):
            if sw.get("hires"):
                mode = "dhgr" if sw.get("80col") else "hgr"
            else:
                mode = "gr"
            if sw.get("mixed"):
                mode += "+text"
        else:
            mode = "text80" if sw.get("80col") else "text"
        page = 2 if sw.get("page2") and not sw.get("80store") else 1

        problems = []
        program = getattr(self, "_program", None)
        crashed = main[CRASH_MARK] == CRASH_MAGIC
        returned = RETURN_ENTRY <= pc < RETURN_ENTRY + 3
        # At the ] prompt = inside the KSW hook's JSR KEYIN ($03E1), whose
        # return address $03E3 sits on the stack. (GET doesn't go through it.)
        stack = main[0x100 + sp + 1:0x200]
        immediate = any(stack[i] == 0xE3 and stack[i + 1] == 0x03
                        for i in range(min(len(stack) - 1, 24)))
        error_line = next((l.strip() for l in reversed(screen)
                           if l.strip().startswith("?") and "ERR" in l), None)
        if crashed:
            brk = ((main[0x3B] << 8) | main[0x3A]) - 2
            status = f"CRASHED: hit BRK at ${brk & 0xFFFF:04X} (back at agent)"
        elif returned:
            status = "Program exited back to the agent (ESC/&/RTS)."
        elif error_line and immediate:
            status = f"BASIC stopped with error: {error_line}"
        elif immediate and program is not None and program.kind == 0 and pc >= 0xC000:
            status = "BASIC program ended - waiting at ] prompt."
        else:
            status = f"Running (PC=${pc:04X})."

        if program is not None:
            if program.mode == 0:
                bad = [a for a in range(0x6000, 0xBF00) if main[a] != GUARD_BYTE]
                if bad:
                    problems.append(
                        f"Program wrote agent memory ${bad[0]:04X}-${bad[-1]:04X} "
                        f"(RESIDENT mode allows $0800-$5FFF only) - this would crash "
                        f"the real Apple II.")
            else:
                bad = [a for a in range(0x6000, 0xBF00) if aux[a] != GUARD_BYTE]
                if bad:
                    problems.append(
                        f"Program wrote AUX memory ${bad[0]:04X}-${bad[-1]:04X} where "
                        f"the agent waits during the run - leave aux $6000-$BEFF alone.")
            badpg = [a for a in range(0xBF00, 0xC000) if main[a] != GUARD_BYTE]
            if badpg:
                problems.append(f"Program wrote ${badpg[0]:04X} (ProDOS global page $BF00-$BFFF).")
            if main[0x03F2:0x03F4] != bytes([0xD0, 0x03]):
                problems.append("Program changed the reset vector ($3F2) - Ctrl-Reset won't return to the agent.")

        png = None
        hgr_page = None
        if mode.startswith("hgr"):
            base = 0x4000 if page == 2 else 0x2000
            hgr_page = bytes(main[base:base + 0x2000])
        if image and (force_image or not mode.startswith("text")):
            png = self._capture_png(mode, page)

        return {"status": status, "screen": screen, "mode": mode,
                "image": png, "hgr_page": hgr_page, "problems": problems,
                "pc": pc, "elapsed": time.time() - getattr(self, "_launched_at", time.time())}

    def _capture_png(self, mode: str, page: int) -> Optional[bytes]:
        """Render the current graphics screen as a PNG Claude can look at."""
        try:
            from PIL import Image
        except ImportError:
            return None
        ppm = os.path.join(_BRIDGE_DIR, "bobbin_capture.ppm")
        try:
            if mode.startswith("dhgr"):
                self.sock.capture_dhgr(ppm, page=page, color=True)
            elif mode.startswith("hgr"):
                self.sock.capture_hgr(ppm, page=page, color=True)
            elif mode.startswith("gr"):
                self.sock.capture_gr(ppm, page=page)
            else:
                return None
            img = Image.open(ppm).convert("RGB")
        except Exception:
            return None
        img = img.resize((560, 384), Image.NEAREST)
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def peek_memory(self, addr: int, count: int) -> bytes:
        snap = self._snapshot()
        return snap[STATE_MAIN + addr:STATE_MAIN + addr + count]

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

    def _prodos_list(self, disk: str) -> dict:
        """List files on a ProDOS disk image."""
        try:
            # Get path to prodos.py tool
            tools_dir = os.path.join(os.path.dirname(__file__), '..', 'tools')
            prodos_tool = os.path.join(tools_dir, 'prodos.py')

            result = subprocess.run(
                [sys.executable, prodos_tool, 'list', disk],
                capture_output=True, text=True, cwd=os.path.dirname(__file__) + '/..'
            )
            if result.returncode != 0:
                return {"error": result.stderr or result.stdout}
            return {"catalog": result.stdout}
        except Exception as e:
            return {"error": str(e)}

    def _prodos_add(self, disk: str, local_file: str, name: str, file_type: str, aux_addr: str) -> dict:
        """Add a file to a ProDOS disk image."""
        try:
            # Get path to prodos.py tool
            tools_dir = os.path.join(os.path.dirname(__file__), '..', 'tools')
            prodos_tool = os.path.join(tools_dir, 'prodos.py')

            # Build command: prodos.py add <disk> <local_file> <name> [type] [aux_addr]
            cmd = [sys.executable, prodos_tool, 'add', disk, local_file, name, file_type]
            if aux_addr:
                cmd.append(aux_addr)

            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=os.path.dirname(__file__) + '/..'
            )
            if result.returncode != 0:
                return {"error": result.stderr or result.stdout}
            return {"ok": True, "output": result.stdout}
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
