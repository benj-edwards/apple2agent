#!/usr/bin/env python3
"""
Unified Proxy Server for Apple II Agent

Single proxy that handles:
1. TCP connections from Apple II via Uthernet II
2. Claude API integration with streaming
3. BASIC tokenization and code injection
4. Emulator testing via Bobbin (--test mode)

Protocol: A2P (Apple II Protocol)
  See a2p_protocol.py for packet format

Usage:
    # Normal mode (real hardware)
    python3 unified_proxy.py

    # Test mode (Bobbin emulator)
    python3 unified_proxy.py --test

    # Custom port
    python3 unified_proxy.py --port 8081

Environment:
    ANTHROPIC_API_KEY - Required for Claude API
"""

import os
import sys

# The MCP server and proxy.sh start us with the system python3; the SDK
# lives in the project's .venv. Hop into it if we can't import anthropic.
_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.venv')
_VENV_PY = os.path.join(_VENV, 'bin', 'python')
if os.path.exists(_VENV_PY) and os.path.realpath(sys.prefix) != os.path.realpath(_VENV):
    try:
        import anthropic  # noqa: F401
    except ImportError:
        os.execv(_VENV_PY, [_VENV_PY, '-u'] + sys.argv)

import socket
import select
import subprocess
import threading
import argparse
import time
import re
from pathlib import Path
from typing import Optional, Callable, Dict

# Force unbuffered output for logging
for _stream in (sys.stdout, sys.stderr):    # line-buffered (a second file object on the
    try:                                    # same fd would close it under a test runner)
        _stream.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

# Handle imports for both direct execution and module import
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# Load .env file if present
_env_file = os.path.join(_script_dir, '.env')
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

# Import protocol and tokenizer
from a2p_protocol import (
    A2PProtocol, A2PConnection, PacketType, Packet,
    CAP_40_COL, CAP_80_COL, CAP_LOWERCASE, CAP_AUX_RAM, CAP_DEPLOY,
    DEPLOY_MAIN, DEPLOY_AUX, PURPOSE_PROGRAM, PURPOSE_PREVIEW, LOAD_CHUNK,
    create_code_packets, create_response_packets,
    MAX_DATA_SIZE
)
from basic_tokenizer_streaming import tokenize_program, detokenize_program
from agentic_claude import (AgenticClaude, MODEL_IDS, MODEL_NAMES as AGENT_MODEL_NAMES,
                            MODEL_SONNET, MODEL_OPUS, MODEL_HAIKU, EFFORTS)
from emulator_bridge import mcp_call as emulator_mcp_call, get_bridge
import deploy
from agentic_claude import WORKSPACE as _AGENT_WORKSPACE


def deploy_workspace():
    """Folder where program sources live (programs/)."""
    return _AGENT_WORKSPACE

# Try to import anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("Warning: anthropic module not found. Install with: pip install anthropic")


# Configuration
DEFAULT_PORT = 6502
BASIC_START = 0x0801
MAX_ITERATIONS = 5
RECV_TIMEOUT = 1.0
CONNECTION_TIMEOUT = 300  # 5 minutes idle timeout
RECONNECT_BACKOFF = [2, 4, 8, 16, 30]  # Exponential backoff seconds

# Model selection (CONFIG_MODEL values) and IDs live in agentic_claude
MODEL_NAMES = {
    MODEL_SONNET: "Sonnet",
    MODEL_OPUS: "Opus",
    MODEL_HAIKU: "Haiku",
}


# System prompt optimized for Apple II BASIC
SYSTEM_PROMPT = """You are an expert Applesoft BASIC programmer for the Apple IIe.

CRITICAL RULES:
1. Respond with ONLY the BASIC code - no explanations, no markdown, no comments outside REM
2. Every line MUST start with a line number (10, 20, 30, etc.)
3. Use standard Applesoft syntax only
4. Keep programs under 20KB (fits in Apple II memory)

APPLESOFT BASICS:
- Line numbers: 0-63999 (use increments of 10)
- Variables: 2 significant chars (AB and ABC are the same!)
- Strings end with $ (A$, NAME$)
- Arrays: DIM A(10) before use
- FOR I=1 TO 10: NEXT I (NEXT must match FOR variable)

COMMON COMMANDS:
- PRINT "text" or PRINT A
- INPUT "prompt";A$
- IF A=1 THEN GOTO 100 (no ELSE in Applesoft!)
- FOR I=1 TO N: NEXT I
- GOSUB 1000: RETURN
- HOME (clear screen)
- HTAB X: VTAB Y (position cursor, 1-40, 1-24)
- END (end program)

GRAPHICS (Lo-Res 40x48):
- GR (init graphics, text window at bottom)
- COLOR=N (0-15)
- PLOT X,Y
- HLIN X1,X2 AT Y
- VLIN Y1,Y2 AT X

GRAPHICS (Hi-Res 280x192):
- HGR (init, page 1)
- HGR2 (page 2, full screen)
- HCOLOR=N (0-7)
- HPLOT X,Y
- HPLOT TO X,Y (draw line)

LO-RES COLORS:
0=Black,1=Magenta,2=DkBlue,3=Purple,4=DkGreen,5=Gray1,6=MedBlue,7=LtBlue
8=Brown,9=Orange,10=Gray2,11=Pink,12=Green,13=Yellow,14=Aqua,15=White

Respond with ONLY the BASIC program, starting with the first line number."""


class ClaudeClient:
    """Claude API client with streaming support."""

    def __init__(self):
        self.client = None
        if HAS_ANTHROPIC:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str, status_callback: Optional[Callable[[str], None]] = None,
                 model: int = MODEL_SONNET) -> str:
        """
        Generate BASIC code from prompt.

        Args:
            prompt: User's request
            status_callback: Optional callback for status updates
            model: Model selection (MODEL_SONNET, MODEL_OPUS, MODEL_HAIKU)

        Returns:
            Generated BASIC code
        """
        def status(msg):
            if status_callback:
                status_callback(msg)

        if not self.client:
            status("No API key - using fallback")
            return self._fallback_code(prompt)

        messages = [{"role": "user", "content": prompt}]
        code = ""
        model_id = MODEL_IDS.get(model, MODEL_IDS[MODEL_SONNET])

        for attempt in range(1, MAX_ITERATIONS + 1):
            status(f"Attempt {attempt}/{MAX_ITERATIONS}")

            try:
                status("Generating...")
                response = self.client.messages.create(
                    model=model_id,
                    max_tokens=16000,
                    output_config={"effort": "low"},
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )

                text = "".join(b.text for b in response.content if b.type == "text")
                code = self._extract_code(text)
                lines = len([l for l in code.split('\n') if l.strip()])
                status(f"Got {lines} lines")

                # Validate syntax
                success, error = self._validate_syntax(code)
                if success:
                    status("Syntax OK")
                    return code

                status(f"Error: {error[:40]}")

                # Ask for fix
                messages.append({"role": "assistant", "content": code})
                messages.append({
                    "role": "user",
                    "content": f"Error: {error}\n\nFix the error and provide the complete corrected program."
                })

            except Exception as e:
                status(f"API error: {str(e)[:30]}")
                if attempt == MAX_ITERATIONS:
                    return self._fallback_code(prompt)

        return code

    def stream_response(self, prompt: str,
                        chunk_callback: Callable[[str, bool], None],
                        status_callback: Optional[Callable[[str], None]] = None,
                        model: int = MODEL_SONNET,
                        custom_prompt: Optional[str] = None,
                        uppercase: bool = True) -> None:
        """
        Stream a chat response (not code generation).

        Args:
            prompt: User's chat message
            chunk_callback: Called with (text_chunk, is_final)
            status_callback: Optional status updates
            model: Model selection (MODEL_SONNET, MODEL_OPUS, MODEL_HAIKU)
            custom_prompt: Optional custom system prompt
        """
        def status(msg):
            if status_callback:
                status_callback(msg)

        if not self.client:
            status("No API key")
            chunk_callback("API KEY NOT SET. EXPORT ANTHROPIC_API_KEY.", True)
            return

        model_id = MODEL_IDS.get(model, MODEL_IDS[MODEL_SONNET])

        # Use custom prompt or default
        system_prompt = custom_prompt if custom_prompt else \
            "You are a helpful assistant chatting with an Apple II user. Keep responses concise (under 200 chars when possible). Use UPPERCASE since Apple II displays uppercase only. Be friendly and retro-themed."

        try:
            status("Thinking...")

            # Use streaming API
            with self.client.messages.stream(
                model=model_id,
                max_tokens=4000,  # thinking counts too; the prompt keeps replies short
                output_config={"effort": "low"},
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                buffer = ""
                for text in stream.text_stream:
                    buffer += text.upper() if uppercase else text
                    # Send when we have enough or hit punctuation
                    if len(buffer) >= 40 or buffer.endswith(('.', '!', '?', '\n')):
                        chunk_callback(buffer, False)
                        buffer = ""

                # Send remaining
                if buffer:
                    chunk_callback(buffer, True)
                else:
                    chunk_callback("", True)

        except Exception as e:
            status(f"Error: {str(e)[:30]}")
            chunk_callback(f"ERROR: {str(e)[:60]}", True)

    def _extract_code(self, response: str) -> str:
        """Extract BASIC code from Claude's response."""
        # Remove markdown code blocks
        if '```' in response:
            match = re.search(r'```(?:\w*\n)?(.*?)```', response, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Find lines starting with numbers
        lines = response.split('\n')
        start_idx = 0
        for i, line in enumerate(lines):
            if re.match(r'^\d+\s', line.strip()):
                start_idx = i
                break

        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if re.match(r'^\d+\s', lines[i].strip()):
                end_idx = i + 1
                break

        return '\n'.join(lines[start_idx:end_idx]).strip()

    def _validate_syntax(self, code: str) -> tuple:
        """Basic syntax validation. Returns (success, error_message)."""
        errors = []
        lines = code.strip().split('\n')
        line_numbers = []
        for_stack = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check line number
            match = re.match(r'^(\d+)\s*(.*)', line)
            if not match:
                errors.append(f"Missing line number: {line[:20]}")
                continue

            line_num = int(match.group(1))
            content = match.group(2).upper()
            line_numbers.append(line_num)

            # Track FOR/NEXT
            in_string = False
            for i, c in enumerate(content):
                if c == '"':
                    in_string = not in_string
                elif not in_string:
                    if content[i:i+4] == 'FOR ':
                        for_stack.append(line_num)
                    elif content[i:i+4] == 'NEXT':
                        if for_stack:
                            for_stack.pop()

        # Check unclosed FOR
        for ln in for_stack:
            errors.append(f"FOR without NEXT at line {ln}")

        # Check line order
        for i in range(1, len(line_numbers)):
            if line_numbers[i] <= line_numbers[i-1]:
                errors.append(f"Line numbers out of order: {line_numbers[i-1]}, {line_numbers[i]}")

        # Try tokenization
        try:
            tokenize_program(code, BASIC_START)
        except Exception as e:
            errors.append(f"Tokenization: {str(e)}")

        if errors:
            return False, "; ".join(errors)
        return True, ""

    def _fallback_code(self, prompt: str) -> str:
        """Generate fallback code when API unavailable."""
        safe = prompt[:16].upper().replace('"', "'")
        return f'''10 REM CLAUDE AGENT
20 HOME
30 PRINT "REQUEST:"
40 PRINT "{safe}"
50 PRINT
60 PRINT "API KEY NOT SET"
70 PRINT "EXPORT ANTHROPIC_API_KEY"
80 END
'''


class AppleIISession:
    """Handles a single Apple II connection."""

    # Pacing for bulk transfers: LOAD packets go out in small batches; TCP
    # flow control (IP65 advertises a 1460-byte window, Bobbin now honors
    # its RX buffer) does the rest
    LOAD_BATCH = 4
    LOAD_PAUSE = 0.01

    def __init__(self, sock: socket.socket, addr: tuple, claude: ClaudeClient,
                 mcp_call: Optional[Callable] = None, proxy: Optional['UnifiedProxy'] = None):
        self.sock = sock
        self.addr = addr
        self.claude = claude
        self.proto = A2PProtocol()
        self.running = True
        self.capabilities = CAP_40_COL
        self.columns = 40
        self.model = MODEL_OPUS  # Default model
        self.custom_prompt = None  # Custom system prompt
        self.agentic_mode = True  # DEFAULT ON - agentic software development
        self.mcp_call = mcp_call  # Function to call MCP tools (for emulator)
        self.proxy = proxy  # Reference to parent proxy for persistent state
        self.max_turns = 60  # Max agentic turns (change with /LIMIT)
        self.keep_history = True  # Keep conversation history between messages
        self.final_response_sent = False  # Track if FINAL response already sent
        self._send_lock = threading.Lock()  # Serialize socket writes
        self._transfer_lock = threading.Lock()  # One DEPLOY/preview at a time
        self.bytes_sent = 0  # Track bytes sent for status display
        self.bytes_recd = 0  # Track bytes received
        self.has_aux = True      # updated from INIT
        self.can_deploy = False  # client speaks DEPLOY/LOAD/RUN/SHOW

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def run(self):
        """Main session loop."""
        print(f"[Session] Connection from {self.addr}")

        self.sock.settimeout(RECV_TIMEOUT)

        try:
            while self.running:
                # Try to receive data
                try:
                    data = self.sock.recv(1024)
                    if not data:
                        print(f"[Session] {self.addr} disconnected")
                        break

                    print(f"[Session] {self.addr} recv {len(data)} bytes: {data[:20].hex()}...")

                    # Decode packets
                    for packet in self.proto.decode_stream(data):
                        self._handle_packet(packet)

                except socket.timeout:
                    continue
                except ConnectionResetError:
                    print(f"[Session] {self.addr} connection reset")
                    break

        finally:
            self.sock.close()
            print(f"[Session] {self.addr} session ended")

    def _handle_packet(self, packet: Packet):
        """Handle a received packet."""
        print(f"[Session] {self.addr} <- {packet.ptype.name}: {packet.data[:30]}...")

        # Send ACK for data packets
        if packet.ptype not in (PacketType.ACK, PacketType.NACK):
            self._send(self.proto.encode_ack(packet.seq))

        if packet.ptype == PacketType.INIT:
            self._handle_init(packet)
        elif packet.ptype == PacketType.CHAT:
            self._handle_chat(packet)

    def _handle_init(self, packet: Packet):
        """Handle INIT packet: capabilities, model, display, version."""
        display_name = None
        if packet.data:
            self.capabilities = packet.data[0]
            self.columns = 80 if (self.capabilities & CAP_80_COL) else 40
            self.has_aux = bool(self.capabilities & CAP_AUX_RAM)
            self.can_deploy = bool(self.capabilities & CAP_DEPLOY)
            if len(packet.data) > 1:
                self.model = packet.data[1] if packet.data[1] in MODEL_IDS else MODEL_OPUS
            if len(packet.data) > 2:
                display_name = {0: '40', 1: '40L', 2: '80'}.get(packet.data[2], '40')
            version = packet.data[3] if len(packet.data) > 3 else 1
            print(f"[Session] caps={self.capabilities:#x} aux={self.has_aux} "
                  f"deploy={self.can_deploy} v{version} model={MODEL_NAMES.get(self.model)}")

        self._send_status(f"CONNECTED - {MODEL_NAMES.get(self.model, 'OPUS').upper()}")

        # The agent (and its conversation) survives reconnects - just point
        # it at this connection
        if self.proxy:
            agent = self.proxy.agentic_claude
            if agent is None:
                agent = AgenticClaude(session=self, mcp_call=self.mcp_call)
                self.proxy.agentic_claude = agent
                print("[Session] Agent created")
            else:
                agent.session = self
                if agent.conversation:
                    print(f"[Session] Resuming with {len(agent.conversation)} messages")
                    self._send_status("SESSION RESUMED")
            if self.custom_prompt:
                agent.set_custom_prompt(self.custom_prompt)
            if display_name:
                self._apply_display_mode_silent(display_name)

    def _handle_chat(self, packet: Packet):
        """Handle CHAT packet - user message."""
        message = packet.data.decode('ascii', errors='replace').strip()
        print(f"[Session] Chat: {message}")

        # Claude works on a worker thread so this loop keeps reading: ESC on
        # the Apple II sends /STOP while it waits. Busy lives on the shared
        # agent: after a reconnect the old request may still be running.
        agent = self._agent()
        if message.upper().startswith('/RESYNC'):
            self._log_stall_report(message[len('/RESYNC'):])
            self._handle_resync()
            return
        if agent and agent.busy:
            if message.upper() == '/STOP':
                agent.request_stop()
                self._send_status("STOPPING...")
            else:
                self._send_status("STILL WORKING - ESC TO STOP")
            return
        if message.upper() == '/STOP':
            self.send_done()                # nothing to stop; just end the wait
            return

        self.final_response_sent = False

        if message.startswith('/'):
            self._handle_command(message)
            return

        self.bytes_sent = 0
        self.bytes_recd = len(packet.data)
        self._send_status("GOT IT - THINKING...")

        if self.agentic_mode:
            if agent:
                agent._line("> " + message)     # heads the cleared log, word-wrapped
                agent.busy = True
            threading.Thread(target=self._agentic_response, args=(message,), daemon=True).start()
        elif any(kw in message.upper() for kw in ['WRITE', 'PROGRAM', 'CODE', 'BASIC', 'MAKE']):
            self._generate_code(message)
        else:
            self._chat_response(message)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _agent(self) -> Optional[AgenticClaude]:
        return self.proxy.agentic_claude if self.proxy else None

    def _handle_command(self, cmd: str):
        """Handle slash commands."""
        parts = cmd[1:].split(maxsplit=1)
        command = parts[0].upper() if parts else ''
        arg = parts[1].strip() if len(parts) > 1 else ''
        agent = self._agent()

        if command == 'HELP':
            self._send_response(
                "JUST TYPE WHAT YOU WANT, LIKE\n"
                "  MAKE A SPACE INVADERS GAME\n"
                "/RUN - RUN YOUR PROGRAM AGAIN\n"
                "/UNDO - BRING BACK THE LAST ONE\n"
                "/RESET - FORGET, START FRESH\n"
                "/MODEL O|S|H - OPUS/SONNET/HAIKU\n"
                "/EFFORT LOW|MEDIUM|HIGH|MAX\n"
                "/PROMPT <TXT> - STANDING ORDERS\n"
                "/DISPLAY 40|40L|80 - SCREEN\n"
                "/LIMIT <N> - MAX STEPS\n"
                "/EXIT - DROP TO BASIC\n"
                "ESC WHILE I WORK - STOP ME\n"
                "IN A PROGRAM: ESC OR CTRL-RESET\n"
                "COMES BACK HERE"
            )
        elif command == 'SUSPEND':
            self._handle_suspend()
        elif command == 'AGENT':
            self._toggle_agentic_mode()
        elif command in ('TURNS', 'LIMIT'):
            if arg.isdigit() and 1 <= int(arg) <= 200:
                self.max_turns = int(arg)
                self._send_response(f"MAX STEPS SET TO {arg}")
            else:
                self._send_response(f"MAX STEPS: {self.max_turns}\nUSE /LIMIT <1-200>")
        elif command == 'EFFORT':
            if agent and arg.lower() in EFFORTS:
                agent.effort = arg.lower()
                self._send_response(f"EFFORT: {arg.upper()}")
            else:
                current = agent.effort.upper() if agent else "MEDIUM"
                self._send_response(f"EFFORT: {current}\nUSE /EFFORT LOW|MEDIUM|HIGH|XHIGH|MAX")
        elif command == 'HISTORY':
            self.keep_history = not self.keep_history
            if self.keep_history:
                self._send_response("HISTORY ON - REMEMBERING CONVERSATION")
            else:
                self._send_response("HISTORY OFF - EACH MESSAGE IS FRESH")
                if agent:
                    agent.clear_conversation()
        elif command in ('CLEAR', 'RESET'):
            if agent:
                agent.clear_conversation()
            self._send_response("FRESH START! WHAT SHALL WE MAKE?" if command == 'RESET'
                                else "CONVERSATION CLEARED")
        elif command == 'CODE':
            self._generate_code(arg or "simple hello world")
        elif command == 'CHAT':
            self._chat_response(arg or "hello")
        elif command == 'PROMPT':
            self.custom_prompt = arg or None
            if agent:
                agent.set_custom_prompt(self.custom_prompt)
            self._send_response(f"PROMPT SET: {arg[:30]}" if arg else "PROMPT CLEARED")
        elif command == 'SEND':
            self._handle_send(arg)
        elif command == 'UNDO':
            self._handle_undo()
        elif command == 'VERSIONS':
            self._handle_versions()
        elif command == 'RERUN':
            self._handle_rerun()
        elif command == 'RUN':
            # Newer clients handle /RUN themselves; this is an old client
            self._send_response("UPDATE AGENT.BIN FOR /RUN.\nFOR NOW: /EXIT THEN RUN")
        elif command == 'IP':
            self._send_response(f"CONNECTED FROM {self.addr[0]}")
        elif command == 'MODEL':
            choice = {'S': MODEL_SONNET, 'SONNET': MODEL_SONNET, 'O': MODEL_OPUS,
                      'OPUS': MODEL_OPUS, 'H': MODEL_HAIKU, 'HAIKU': MODEL_HAIKU}.get(arg.upper())
            if choice is not None:
                self.model = choice
                self._send_response(f"MODEL: {MODEL_NAMES[choice].upper()}")
            else:
                self._send_response(f"MODEL: {MODEL_NAMES.get(self.model, 'OPUS').upper()}\n"
                                    "USE /MODEL O|S|H")
        elif command == 'DISPLAY':
            if arg:
                self._set_display_mode(arg.upper())
            else:
                self._send_response(f"DISPLAY: {self._get_display_mode_name()}\nUSE /DISPLAY 40|40L|80")
        else:
            self._send_response(f"UNKNOWN: {command}\nTYPE /HELP")

    def _handle_send(self, name: str):
        """/SEND <FILE> - send a program from the workspace (programs/) as is."""
        agent = self._agent()
        if not agent:
            self._send_response("AGENT NOT READY")
            return
        if not name:
            files = sorted(p.name for p in deploy_workspace().iterdir()
                           if p.suffix.upper() in ('.BAS', '.S', '.ASM'))
            self._send_response("PROGRAMS: " + (", ".join(files) if files else "NONE") +
                                "\nUSE /SEND <NAME>")
            return
        try:
            program = agent._build(name.split()[0])
        except Exception as e:
            self._send_response(f"CAN'T SEND: {str(e)[:70]}".upper())
            return
        result = self.deploy_program(program)
        agent.deploy_history.append(program)
        self._send_response(result.split('.')[0].upper())

    def _handle_undo(self):
        """/UNDO - send the previous program again."""
        agent = self._agent()
        history = agent.deploy_history if agent else []
        if len(history) < 2:
            self._send_response("NOTHING TO UNDO YET")
            return
        if not self.can_deploy:
            self._send_response("UPDATE AGENT.BIN FOR /UNDO")
            return
        history.pop()
        program = history[-1]
        self._send_status("RESTORING PREVIOUS VERSION...")
        self.deploy_program(program)
        self._send_response(f"RESTORED {program.name.upper()}")

    STALL_FIELDS = {
        "N": "segments since the last good packet", "T": "TCP segments in all",
        "B": "...with a bad checksum", "H": "W5100 RX ring skips (bad frame header)",
        "A": "A2P packets with a bad checksum", "S": "W5100 socket 0 status",
        "Q": "bytes waiting in the W5100 RX ring", "E": "seq expected (low 16)",
        "L": "seq last received (low 16)",
    }

    def _log_stall_report(self, report: str):
        """The Apple II's own view of a stall (asm/agent.s build_stall_report),
        appended to logs/stall_reports.log: it outlives proxy restarts."""
        fields = dict(f.split("=", 1) for f in report.upper().split() if "=" in f)
        lines = [f"{time.strftime('%Y-%m-%d %H:%M:%S')} stall reported by {self.addr[0]}"]
        for key, label in self.STALL_FIELDS.items():
            if key in fields:
                try:
                    lines.append(f"  {key}={fields[key]:>4} ({int(fields[key], 16)})  {label}")
                except ValueError:
                    lines.append(f"  {key}={fields[key]}  {label}")
        if not fields:
            lines.append("  (no report: an older client)")
        text = "\n".join(lines)
        print(f"[Resync] {text}")
        try:
            log_dir = Path(os.environ.get("APPLE2_LOG_DIR") or Path(__file__).resolve().parent.parent / "logs")
            log_dir.mkdir(exist_ok=True)
            with open(log_dir / "stall_reports.log", "a") as f:
                f.write(text + "\n")
        except OSError as e:
            print(f"[Resync] couldn't write the report: {e}")

    def _handle_resync(self):
        """/RESYNC - the Apple II's watchdog reconnected after its connection
        stalled (nothing arrived for 20 s). Whatever went out since may never
        have reached it: the end of the reply and the program."""
        agent = self._agent()
        if agent and agent.busy:
            agent.session = self            # the rest of the request comes here...
            agent._resynced = True          # ...and its end re-sends the program
            self._send_status("RECONNECTED - STILL WORKING")
            return
        self._send_status("RECONNECTED")
        if agent:
            self._resend_last_result(agent, card=True)
        self.send_done()

    def _resend_last_result(self, agent, card: bool):
        """The last request's final message (as the closing card) and program."""
        agent.session = self
        if card and getattr(agent, "_final_text", ""):
            agent._closing_card(agent._final_text)
        if getattr(agent, "_last_request_deployed", False) and agent.deploy_history:
            self.deploy_program(agent.deploy_history[-1])

    def _handle_rerun(self):
        """/RERUN (sent by the Apple II's /RUN) - a fresh copy of the current
        program: machine code that changed itself above $6000 during its last
        run can't be replayed from the Apple's own copy. It runs on arrival."""
        agent = self._agent()
        history = agent.deploy_history if agent else []
        if not history:
            self._send_response("NO PROGRAM YET - ASK FOR ONE!")
            return
        self._send_status("FETCHING A FRESH COPY...")
        self.deploy_program(history[-1])
        self.send_done()

    def _handle_versions(self):
        """/VERSIONS - list programs sent this session."""
        agent = self._agent()
        history = agent.deploy_history if agent else []
        if not history:
            self._send_response("NO PROGRAMS SENT YET")
            return
        lines = [f"{i + 1}. {p.name.upper()} ({p.size} BYTES)" for i, p in enumerate(history[-10:])]
        self._send_response("PROGRAMS THIS SESSION:\n" + "\n".join(lines))

    def _generate_code(self, prompt: str):
        """/CODE: one-shot BASIC generation (no tools)."""
        code = self.claude.generate(prompt, self._send_status, model=self.model)
        try:
            if self.can_deploy:
                program = deploy.build_basic(code, "CODE", self.has_aux)
                self.deploy_program(program)
                self._send_response("PROGRAM SENT")
            else:
                self._send_basic_code(code)
                self._send_status("CODE LOADED - TYPE RUN")
        except Exception as e:
            self._send_error(f"CODE ERROR: {str(e)[:40]}")

    def _chat_response(self, message: str):
        """Send streaming chat response."""
        def send_chunk(text: str, is_final: bool):
            self._send(self.proto.encode_response(text, is_final))

        uppercase = not (self.capabilities & CAP_LOWERCASE)
        self.claude.stream_response(message, send_chunk, self._send_status,
                                    model=self.model, custom_prompt=self.custom_prompt,
                                    uppercase=uppercase)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def _send(self, packet: bytes, pause: float = 0.05):
        """Send raw packet(s), paced for the Apple II."""
        with self._send_lock:
            try:
                self.sock.sendall(packet)
                self.bytes_sent += len(packet)
                time.sleep(pause)
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                print(f"[Session] Send error: {e}")
                self.running = False

    def _send_status(self, message: str):
        self._send(self.proto.encode_status(message[:MAX_DATA_SIZE]))

    def _send_error(self, message: str):
        self._send(self.proto.encode_error(message[:MAX_DATA_SIZE]))

    def _send_stream_line(self, text: str):
        """A line in the scrolling output area (non-final RESP)."""
        self._send(self.proto.encode_response(text + "\n", is_final=False))

    def _send_response(self, text: str):
        """Send complete response (ends the Apple II's wait)."""
        for packet in create_response_packets(self.proto, text):
            self._send(packet)
        self.final_response_sent = True

    def send_page_break(self):
        """Start a fresh page of the Apple II's log (form feed; old clients ignore it)."""
        self._send(self.proto.encode_response("\f", is_final=False))

    # Interface used by AgenticClaude
    send_status = _send_status
    send_stream_line = _send_stream_line

    def send_done(self):
        """End of an agentic response - never throttled or dropped."""
        self._send(self.proto.encode_status("DONE"))

    def _send_loads(self, base: int, data: bytes, progress: Optional[str] = None):
        """Stream bytes to the Apple II as LOAD packets."""
        batch = []
        sent = 0
        next_report = 1024
        for off in range(0, len(data), LOAD_CHUNK):
            batch.append(self.proto.encode_load(base + off, data[off:off + LOAD_CHUNK]))
            sent = min(off + LOAD_CHUNK, len(data))
            if len(batch) >= self.LOAD_BATCH or sent >= len(data):
                self._send(b"".join(batch), pause=self.LOAD_PAUSE)
                batch = []
            if progress and sent >= next_report:
                self._send(self.proto.encode_status(f"{progress} {sent * 100 // len(data)}%"),
                           pause=0)
                next_report += 1024

    def deploy_program(self, program) -> str:
        """Load a deploy.Program into the Apple II; it shows READY."""
        if not self.can_deploy:
            # Old AGENT.BIN: BASIC at $0801 through CODE packets
            if program.kind == deploy.RUN_BASIC and program.start == 0x0801:
                self._send_basic_code_bytes(program.chunks[0][1][1:])
                return ("Sent to an old Apple II client: tell the user to type /EXIT then RUN. "
                        "(Updating AGENT.BIN enables the READY screen and machine code.)")
            return ("This Apple II runs an old AGENT.BIN that can only take BASIC programs. "
                    "Rewrite it in Applesoft BASIC, or ask the user to update AGENT.BIN.")
        with self._transfer_lock:
            mode = DEPLOY_AUX if program.mode == deploy.MODE_EXCHANGE else DEPLOY_MAIN
            self._send(self.proto.encode_deploy(mode, PURPOSE_PROGRAM))
            for addr, data in program.chunks:
                self._send_loads(addr, data, progress="SENDING")
            self._send(self.proto.encode_run(program.descriptor()))
        print(f"[Session] Deployed {program.summary()}")
        return (f"Sent {program.size} bytes to the Apple II. When your reply finishes it shows "
                f"'{program.name.upper()} IS READY!' and the user presses RETURN to run it.")

    def send_preview(self, hgr_page: bytes):
        """Show an HGR screenshot (8K page image) on the Apple II."""
        if not self.can_deploy or len(hgr_page) != 0x2000:
            return
        with self._transfer_lock:
            self._send(self.proto.encode_deploy(DEPLOY_MAIN, PURPOSE_PREVIEW))
            self._send_loads(0x2000, hgr_page)
            self._send(self.proto.encode_show(1))

    def _send_basic_code(self, source: str):
        """Old client path: tokenize at $0801 and send CODE packets."""
        try:
            self._send_basic_code_bytes(tokenize_program(source, BASIC_START))
        except Exception as e:
            self._send_error(f"CODE ERROR: {str(e)[:40]}")

    def _send_basic_code_bytes(self, tokenized: bytes):
        self._send_status(f"CODE: {len(tokenized)} BYTES")
        for packet in create_code_packets(self.proto, tokenized):
            self._send(packet)
        self.final_response_sent = True

    # ------------------------------------------------------------------
    # Modes
    # ------------------------------------------------------------------

    def _handle_suspend(self):
        """Handle /SUSPEND - drop to BASIC prompt."""
        self._send_response(
            "\nYOUR PROGRAM IS LOADED. TYPE: RUN\n"
            "TO COME BACK: & OR CTRL-Y\n")
        self._send(self.proto.encode_suspend())

    def _toggle_agentic_mode(self):
        """Toggle agentic mode on/off."""
        self.agentic_mode = not self.agentic_mode
        if self.agentic_mode:
            self._send_response("AGENT MODE ON - DESCRIBE WHAT YOU WANT!")
        else:
            self._send_response("AGENT MODE OFF - JUST CHATTING")

    def _apply_display(self, mode: str) -> Optional[str]:
        """Set display properties; returns a description or None if unknown."""
        agent = self._agent()
        table = {
            '40': (40, CAP_40_COL, 39, True, "40 UPPERCASE"),
            '40U': (40, CAP_40_COL, 39, True, "40 UPPERCASE"),
            '40L': (40, CAP_40_COL | CAP_LOWERCASE, 39, False, "40 MIXED CASE"),
            '80': (80, CAP_80_COL | CAP_LOWERCASE, 79, False, "80 MIXED CASE"),
        }
        if mode not in table:
            return None
        cols, caps, width, upper, name = table[mode]
        self.columns = cols
        flags = self.capabilities & (CAP_AUX_RAM | CAP_DEPLOY)
        self.capabilities = caps | flags
        if agent:
            agent.display_width = width
            agent.display_uppercase = upper
        return name

    def _set_display_mode(self, mode: str):
        name = self._apply_display(mode)
        self._send_response(f"DISPLAY: {name}" if name else "USE: /DISPLAY 40|40L|80")

    def _apply_display_mode_silent(self, mode: str):
        name = self._apply_display(mode)
        print(f"[Session] Display: {name}")

    def _get_display_mode_name(self) -> str:
        if self.capabilities & CAP_80_COL:
            return "80 MIXED CASE"
        elif self.capabilities & CAP_LOWERCASE:
            return "40 MIXED CASE"
        return "40 UPPERCASE"

    def _agentic_response(self, message: str):
        """Run the agent loop for one message; everything streams out."""
        agent = self._agent()
        if not agent:
            self._send_error("AGENT NOT INITIALIZED")
            return
        if not self.keep_history:
            agent.clear_conversation()
        agent.session = self
        try:
            agent.run_agentic(message, model=MODEL_IDS.get(self.model, MODEL_IDS[MODEL_OPUS]),
                              max_turns=self.max_turns)
        except Exception as e:
            print(f"[Session] Agent crashed: {e!r}")
            self._send_stream_line(f"AGENT ERROR: {str(e)[:60]}".upper())
        finally:
            agent.busy = False
            # After a reconnect the agent talks to the new session: the end of
            # the request goes there, not down the dead connection
            target = agent.session or self
            if getattr(agent, "_resynced", False):
                agent._resynced = False
                try:
                    target._resend_last_result(agent, card=False)   # the card already went there
                except Exception as e:
                    print(f"[Session] resend after resync failed: {e!r}")
            target.send_done()


# Test proxies get their own directory so they never touch the real one's
# PID or shutdown file (proxy.sh / proxyctl / the MCP server use the default)
CONTROL_DIR = os.environ.get('APPLE2_PROXY_CONTROL_DIR', '/tmp/claude')
PID_FILE = f'{CONTROL_DIR}/proxy.pid'
SHUTDOWN_FILE = f'{CONTROL_DIR}/proxy_shutdown'

# The Apple II broadcasts DISCOVERY_ASK to this UDP port at boot; the answer
# carries our TCP port and its source address tells it where we are, so no
# /SETIP is needed on a home network. (asm/agent.s: find_proxy)
DISCOVERY_PORT = int(os.environ.get("APPLE2_DISCOVERY_PORT", "6502"))   # tests use their own
DISCOVERY_ASK = b"A2AGENT?"
DISCOVERY_ANSWER = b"A2AGENT!"


def _lan_address() -> Optional[str]:
    """This machine's address on the local network (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


class UnifiedProxy:
    """Main proxy server."""

    def __init__(self, host: str = '0.0.0.0', port: int = DEFAULT_PORT,
                 mcp_call: Optional[Callable] = None):
        self.host = host
        self.port = port
        self.claude = ClaudeClient()
        self.running = False
        self.sessions: Dict[tuple, AppleIISession] = {}
        self.mcp_call = mcp_call  # Function to call MCP tools (for emulator)

        # Persistent agentic session - survives reconnects!
        self.agentic_claude: Optional[AgenticClaude] = None

    def start(self):
        """Start the proxy server."""
        self.running = True

        # Set up control files
        os.makedirs(CONTROL_DIR, exist_ok=True)
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        # Remove any stale shutdown file
        if os.path.exists(SHUTDOWN_FILE):
            os.remove(SHUTDOWN_FILE)

        # Create TCP server socket
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(5)
        server.settimeout(1.0)
        threading.Thread(target=self._discovery_responder, daemon=True).start()

        print(f"Apple II Agent - Unified Proxy")
        print(f"Listening on {self.host}:{self.port}")
        print(f"Protocol: A2P (Apple II Protocol)")
        print(f"Claude API: {'Ready' if self.claude.client else 'Not configured'}")
        print(f"Agentic Mode: ON by default (/AGENT to toggle off)")
        lan = _lan_address()
        if lan:
            print(f"The Apple II finds this proxy by itself. If it can't: /SETIP {lan}")
        print(f"PID: {os.getpid()} (touch {SHUTDOWN_FILE} to stop)")
        print()
        print("Waiting for connections...")
        print()

        try:
            while self.running:
                # Check for shutdown file
                if os.path.exists(SHUTDOWN_FILE):
                    print("\nShutdown file detected, stopping...")
                    os.remove(SHUTDOWN_FILE)
                    break

                try:
                    client, addr = server.accept()
                    # Disable Nagle's algorithm for low-latency small packets
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    # Enable TCP keepalive to detect dead connections
                    client.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    # Handle each connection in a thread
                    # Pass proxy reference so session can access persistent agentic_claude
                    session = AppleIISession(client, addr, self.claude, self.mcp_call, proxy=self)
                    self.sessions[addr] = session
                    thread = threading.Thread(target=session.run, daemon=True)
                    thread.start()
                except socket.timeout:
                    continue

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            server.close()
            self.running = False
            # Clean up PID file
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)

    def _discovery_responder(self):
        """Answer the Apple II's boot-time broadcast (see DISCOVERY_PORT)."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, DISCOVERY_PORT))
        except OSError as e:
            print(f"Discovery: UDP {DISCOVERY_PORT} unavailable ({e}) - the Apple II will need /SETIP")
            return
        sock.settimeout(1.0)
        print(f"Discovery: answering on UDP {DISCOVERY_PORT}")
        with sock:
            while self.running:
                try:
                    data, addr = sock.recvfrom(64)
                except socket.timeout:
                    continue
                except OSError:
                    return
                if data.startswith(DISCOVERY_ASK):
                    try:
                        sock.sendto(DISCOVERY_ANSWER + bytes([self.port & 0xFF, self.port >> 8]), addr)
                        print(f"[Discovery] {addr[0]} asked - told it port {self.port}")
                    except OSError as e:
                        # macOS's Local Network privacy setting can block
                        # sends to LAN devices from apps it hasn't allowed
                        print(f"[Discovery] couldn't answer {addr[0]}: {e}. If this keeps happening, "
                              f"allow your terminal app under System Settings > Privacy & Security > "
                              f"Local Network, or type /SETIP <this Mac's address> on the Apple II")

    def stop(self):
        """Stop the server."""
        self.running = False
        for session in self.sessions.values():
            session.running = False


def run_test_mode():
    """Run in test mode with Bobbin emulator."""
    print("Test mode - Bobbin integration")
    print("This mode tests the proxy with the Bobbin emulator")
    print()
    print("Agentic mode is ON by default - Claude uses emulator for testing")
    print()

    # Use emulator bridge for MCP calls
    try:
        proxy = UnifiedProxy(mcp_call=emulator_mcp_call)
        proxy.start()
    except KeyboardInterrupt:
        print("\nTest mode ended")
    finally:
        # Clean up emulator on exit
        get_bridge().shutdown()


def main():
    parser = argparse.ArgumentParser(description='Apple II Agent Unified Proxy')
    parser.add_argument('--port', '-p', type=int, default=DEFAULT_PORT,
                        help=f'Port to listen on (default: {DEFAULT_PORT})')
    parser.add_argument('--host', '-H', default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--test', '-t', action='store_true',
                        help='Run in test mode with Bobbin emulator')
    args = parser.parse_args()

    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("Warning: ANTHROPIC_API_KEY not set")
        print("Responses will use fallback code generation")
        print()

    if args.test:
        run_test_mode()
    else:
        # Always use emulator bridge for agentic mode
        try:
            proxy = UnifiedProxy(args.host, args.port, mcp_call=emulator_mcp_call)
            proxy.start()
        finally:
            get_bridge().shutdown()


if __name__ == '__main__':
    main()
