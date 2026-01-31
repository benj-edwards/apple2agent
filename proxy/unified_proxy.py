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
import socket
import select
import threading
import argparse
import time
import re
from typing import Optional, Callable, Dict

# Force unbuffered output for logging
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

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
    CAP_40_COL, CAP_80_COL, CAP_LOWERCASE,
    create_code_packets, create_response_packets,
    MAX_DATA_SIZE
)
from basic_tokenizer_streaming import tokenize_program, detokenize_program
from agentic_claude import AgenticClaude, get_agentic_claude
from emulator_bridge import mcp_call as emulator_mcp_call, get_bridge

# Try to import anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("Warning: anthropic module not found. Install with: pip install anthropic")


# Configuration
DEFAULT_PORT = 8080
BASIC_START = 0x0801
MAX_ITERATIONS = 5
RECV_TIMEOUT = 1.0
CONNECTION_TIMEOUT = 300  # 5 minutes idle timeout
RECONNECT_BACKOFF = [2, 4, 8, 16, 30]  # Exponential backoff seconds

# Model selection (matches agent CONFIG_MODEL values)
MODEL_SONNET = 0
MODEL_OPUS = 1
MODEL_HAIKU = 2

# Use aliases that Anthropic maintains - won't break with new releases
MODEL_IDS = {
    MODEL_SONNET: "claude-sonnet-4-20250514",
    MODEL_OPUS: "claude-opus-4-20250514",
    MODEL_HAIKU: "claude-haiku-4-20250514",
}

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
                    max_tokens=4000,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )

                code = self._extract_code(response.content[0].text)
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
                        custom_prompt: Optional[str] = None) -> None:
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
                max_tokens=500,  # Keep responses short for 40-col display
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                buffer = ""
                for text in stream.text_stream:
                    buffer += text.upper()
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

    def __init__(self, sock: socket.socket, addr: tuple, claude: ClaudeClient,
                 mcp_call: Optional[Callable] = None):
        self.sock = sock
        self.addr = addr
        self.claude = claude
        self.proto = A2PProtocol()
        self.running = True
        self.capabilities = CAP_40_COL
        self.columns = 40
        self.model = MODEL_SONNET  # Default model
        self.custom_prompt = None  # Custom system prompt
        self.agentic_mode = True  # DEFAULT ON - agentic software development
        self.mcp_call = mcp_call  # Function to call MCP tools (for emulator)
        self.agentic_claude: Optional[AgenticClaude] = None
        self.max_turns = 20  # Max agentic turns
        self.keep_history = True  # Keep conversation history between messages

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

                    # Debug: show raw data received
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
        elif packet.ptype == PacketType.ACK:
            pass  # Handled by connection layer
        elif packet.ptype == PacketType.NACK:
            pass  # Would trigger retransmit

    def _handle_init(self, packet: Packet):
        """Handle INIT packet."""
        if packet.data:
            self.capabilities = packet.data[0]
            self.columns = 80 if (self.capabilities & CAP_80_COL) else 40

            # Read model selection (byte 1) if present
            if len(packet.data) > 1:
                self.model = packet.data[1]
                if self.model not in MODEL_IDS:
                    self.model = MODEL_SONNET  # Default if invalid

            model_name = MODEL_NAMES.get(self.model, "Sonnet")
            print(f"[Session] Capabilities: {self.capabilities:#x}, columns={self.columns}, model={model_name}")

        # Send welcome status with model name
        model_name = MODEL_NAMES.get(self.model, "Sonnet")
        self._send_status(f"CONNECTED - {model_name.upper()}")

        # Initialize agentic Claude if agentic mode is on by default
        if self.agentic_mode and not self.agentic_claude:
            # Use a no-op status function to avoid overwhelming Apple II
            # Status updates crash the Apple II when sent rapidly
            def noop_status(msg): pass
            self.agentic_claude = AgenticClaude(
                send_to_apple2=self._send_response,
                send_status=noop_status,  # Disabled - crashes Apple II
                send_code=self._send_basic_code,
                mcp_call=self.mcp_call,
                send_binary=self._send_binary_code
            )
            print(f"[Session] Agentic Claude initialized (status disabled)")

    def _handle_chat(self, packet: Packet):
        """Handle CHAT packet - user message."""
        message = packet.data.decode('ascii', errors='replace').strip()
        print(f"[Session] Chat: {message}")

        # Check for special commands
        if message.startswith('/'):
            self._handle_command(message)
            return

        # Route based on mode
        if self.agentic_mode:
            # Use agentic loop with tools
            self._agentic_response(message)
        elif any(kw in message.upper() for kw in ['WRITE', 'PROGRAM', 'CODE', 'BASIC', 'MAKE']):
            # Check if requesting code
            self._generate_code(message)
        else:
            self._chat_response(message)

    def _handle_command(self, cmd: str):
        """Handle slash commands."""
        parts = cmd[1:].split(maxsplit=1)
        command = parts[0].upper()

        if command == 'HELP':
            self._send_response(
                "/HELP - SHOW COMMANDS\n"
                "/AGENT - TOGGLE APPLE II AGENT MODE\n"
                "/MODEL S|O|H - SET MODEL\n"
                "/SUSPEND - DROP TO BASIC\n"
                "/CODE <DESC> - GENERATE BASIC\n"
                "/CHAT <MSG> - CHAT WITH CLAUDE\n"
                "/TURNS <N> - SET MAX AGENT TURNS\n"
                "/HISTORY - TOGGLE MEMORY\n"
                "/CLEAR - CLEAR CONVERSATION\n"
                "/PROMPT <TEXT> - SET PROMPT\n"
                "/IP - SHOW CONNECTION INFO"
            )
        elif command == 'SUSPEND':
            self._handle_suspend()
        elif command == 'AGENT':
            self._toggle_agentic_mode()
        elif command == 'TURNS':
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                    if 1 <= n <= 100:
                        self.max_turns = n
                        self._send_response(f"MAX TURNS SET TO {n}")
                    else:
                        self._send_response("TURNS MUST BE 1-100")
                except ValueError:
                    self._send_response("USAGE: /TURNS <NUMBER>")
            else:
                self._send_response(f"MAX TURNS: {self.max_turns}")
        elif command == 'HISTORY':
            self.keep_history = not self.keep_history
            if self.keep_history:
                self._send_response("HISTORY ON - REMEMBERING CONVERSATION")
            else:
                self._send_response("HISTORY OFF - EACH MESSAGE IS FRESH")
                if self.agentic_claude:
                    self.agentic_claude.clear_conversation()
        elif command == 'CLEAR':
            if self.agentic_claude:
                self.agentic_claude.clear_conversation()
            self._send_response("CONVERSATION CLEARED")
        elif command == 'CODE':
            desc = parts[1] if len(parts) > 1 else "simple hello world"
            self._generate_code(desc)
        elif command == 'CHAT':
            msg = parts[1] if len(parts) > 1 else "hello"
            self._chat_response(msg)
        elif command == 'PROMPT':
            if len(parts) > 1:
                self.custom_prompt = parts[1]
                self._send_response(f"PROMPT SET: {parts[1][:30]}...")
                print(f"[Session] Custom prompt: {self.custom_prompt}")
            else:
                self.custom_prompt = None
                self._send_response("PROMPT CLEARED - USING DEFAULT")
                print("[Session] Custom prompt cleared")
        elif command == 'IP':
            self._send_response(f"CONNECTED FROM {self.addr[0]}")
        elif command == 'MODEL':
            if len(parts) > 1:
                m = parts[1].upper()
                if m in ('S', 'SONNET'):
                    self.model = MODEL_SONNET
                    self._send_response("MODEL: SONNET")
                elif m in ('O', 'OPUS'):
                    self.model = MODEL_OPUS
                    self._send_response("MODEL: OPUS")
                elif m in ('H', 'HAIKU'):
                    self.model = MODEL_HAIKU
                    self._send_response("MODEL: HAIKU")
                else:
                    self._send_response("USAGE: /MODEL S|O|H\n(SONNET/OPUS/HAIKU)")
            else:
                model_name = MODEL_NAMES.get(self.model, "SONNET")
                self._send_response(f"MODEL: {model_name.upper()}\nUSE /MODEL S|O|H TO CHANGE")
        else:
            self._send_response(f"UNKNOWN: {command}\nTYPE /HELP")

    def _generate_code(self, prompt: str):
        """Generate and send BASIC code."""
        def status(msg):
            self._send_status(msg)

        # Generate code using selected model
        code = self.claude.generate(prompt, status, model=self.model)

        try:
            # Tokenize
            tokenized = tokenize_program(code, BASIC_START)
            self._send_status(f"CODE: {len(tokenized)} BYTES")

            # Send code packets
            packets = create_code_packets(self.proto, tokenized)
            for packet in packets:
                self._send(packet)
                time.sleep(0.01)  # Small delay between packets

            self._send_status("CODE LOADED - TYPE RUN")

        except Exception as e:
            self._send_error(f"TOKENIZE ERROR: {str(e)[:40]}")

    def _chat_response(self, message: str):
        """Send streaming chat response."""
        def send_chunk(text: str, is_final: bool):
            packet = self.proto.encode_response(text, is_final)
            self._send(packet)

        def status(msg):
            self._send_status(msg)

        self.claude.stream_response(message, send_chunk, status,
                                    model=self.model, custom_prompt=self.custom_prompt)

    def _send(self, packet: bytes):
        """Send raw packet with throttling for Apple II."""
        import time
        try:
            self.sock.sendall(packet)
            print(f"[Session] -> sent {len(packet)} bytes: {packet[:20].hex()}...")
            time.sleep(0.2)  # Throttle ALL sends - Apple II needs time to process
        except (BrokenPipeError, ConnectionResetError) as e:
            print(f"[Session] Send error: {e}")
            self.running = False

    def _send_status(self, message: str):
        """Send status message."""
        packet = self.proto.encode_status(message[:MAX_DATA_SIZE])
        self._send(packet)

    def _send_error(self, message: str):
        """Send error message."""
        packet = self.proto.encode_error(message[:MAX_DATA_SIZE])
        self._send(packet)

    def _send_response(self, text: str):
        """Send complete response."""
        packets = create_response_packets(self.proto, text)
        for packet in packets:
            self._send(packet)

    def _handle_suspend(self):
        """Handle /SUSPEND - drop to BASIC prompt."""
        self._send_status("SUSPENDING...")
        # Send suspend command - Apple II client will drop to BASIC
        # The connection stays open, context preserved
        suspend_msg = (
            "\n"
            "================================\n"
            "   APPLE II AGENT SUSPENDED\n"
            "================================\n"
            "\n"
            "YOUR PROGRAM IS LOADED!\n"
            "TYPE: RUN\n"
            "\n"
            "TO RESUME APPLE II AGENT:\n"
            "  CTRL-C CTRL-C  OR\n"
            "  CALL 24576     (CALL $6000)\n"
            "\n"
            "================================\n"
        )
        self._send_response(suspend_msg)
        # Send special suspend packet (type 0x10)
        suspend_packet = self.proto.encode_suspend()
        self._send(suspend_packet)
        print(f"[Session] Suspended to BASIC")

    def _toggle_agentic_mode(self):
        """Toggle agentic mode on/off."""
        self.agentic_mode = not self.agentic_mode

        if self.agentic_mode:
            # Initialize agentic Claude if needed
            if not self.agentic_claude:
                self.agentic_claude = AgenticClaude(
                    send_to_apple2=self._send_response,
                    send_status=self._send_status,
                    send_code=self._send_basic_code,
                    mcp_call=self.mcp_call,
                    send_binary=self._send_binary_code
                )
            welcome = (
                "================================\n"
                "    APPLE II AGENT FOR //E\n"
                "================================\n"
                "\n"
                "AI-POWERED PROGRAMMING\n"
                "DESCRIBE WHAT YOU WANT!\n"
                "\n"
                "/SUSPEND - RUN YOUR PROGRAM\n"
                "/CLEAR   - NEW CONVERSATION\n"
                "/HELP    - ALL COMMANDS\n"
                "================================\n"
            )
            self._send_response(welcome)
            self._send_status("APPLE II AGENT READY")
            print(f"[Session] Apple II Agent mode enabled")
        else:
            self._send_response("APPLE II AGENT OFF\nBACK TO NORMAL CHAT")
            self._send_status("CHAT MODE")
            print(f"[Session] Apple II Agent mode disabled")

    def _agentic_response(self, message: str):
        """Handle message in agentic mode."""
        if not self.agentic_claude:
            self._send_error("AGENTIC MODE NOT INITIALIZED")
            return

        # Clear history if not keeping it
        if not self.keep_history:
            self.agentic_claude.clear_conversation()

        # Get model ID
        model_id = MODEL_IDS.get(self.model, MODEL_IDS[MODEL_SONNET])

        try:
            # Prepend custom prompt/context if set
            if self.custom_prompt:
                message = f"[CONTEXT: {self.custom_prompt}]\n\n{message}"

            # Run the agentic loop
            response = self.agentic_claude.run_agentic(
                message,
                model=model_id,
                max_turns=self.max_turns
            )
            # Send final response to Apple II
            self._send_response(response)
        except Exception as e:
            self._send_error(f"AGENT ERROR: {str(e)[:50]}")

    def _send_basic_code(self, source: str):
        """Send BASIC code to Apple II (used by agentic mode)."""
        try:
            # Tokenize
            tokenized = tokenize_program(source, BASIC_START)
            self._send_status(f"CODE: {len(tokenized)} BYTES")

            # Send code packets
            packets = create_code_packets(self.proto, tokenized)
            for packet in packets:
                self._send(packet)
                time.sleep(0.01)

            self._send_status("CODE LOADED - TYPE RUN")
        except Exception as e:
            self._send_error(f"CODE ERROR: {str(e)[:40]}")

    def _send_binary_code(self, hex_data: str, load_address: int = 0x6000):
        """Send machine code to Apple II (used by agentic mode)."""
        try:
            # Convert hex string to bytes
            hex_clean = hex_data.replace(" ", "").replace("\n", "")
            binary = bytes.fromhex(hex_clean)
            size = len(binary)

            self._send_status(f"BINARY: {size} BYTES @ ${load_address:04X}")

            # Send binary packets (similar to code packets but with address)
            chunk_size = MAX_DATA_SIZE - 4  # Leave room for address header
            offset = 0
            while offset < size:
                chunk = binary[offset:offset + chunk_size]
                packet = self.proto.encode_binary(chunk, load_address + offset, size)
                self._send(packet)
                time.sleep(0.01)
                offset += len(chunk)

            self._send_status(f"READY - CALL {load_address}")
        except Exception as e:
            self._send_error(f"BINARY ERROR: {str(e)[:40]}")


CONTROL_DIR = '/tmp/claude'
PID_FILE = f'{CONTROL_DIR}/proxy.pid'
SHUTDOWN_FILE = f'{CONTROL_DIR}/proxy_shutdown'


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

        print(f"Apple II Agent - Unified Proxy")
        print(f"Listening on {self.host}:{self.port}")
        print(f"Protocol: A2P (Apple II Protocol)")
        print(f"Claude API: {'Ready' if self.claude.client else 'Not configured'}")
        print(f"Agentic Mode: ON by default (/AGENT to toggle off)")
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
                    # Handle each connection in a thread
                    session = AppleIISession(client, addr, self.claude, self.mcp_call)
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
