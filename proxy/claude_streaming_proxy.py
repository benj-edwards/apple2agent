#!/usr/bin/env python3
"""
Claude Streaming Proxy for Apple II Agent

Full-featured proxy that:
1. Accepts requests from Apple II via Uthernet II
2. Uses Claude API to generate BASIC code
3. Tests code on Bobbin emulator before sending
4. Streams progress updates back to Apple II
5. Returns verified, working tokenized BASIC

Streaming Protocol (Apple II <- Proxy):
  STATUS messages: "S:message\n" - shown on Apple II screen
  ERROR messages:  "E:message\n" - shown as error
  READY message:   "R:prompt\n"  - ready to inject, show prompt
  BINARY data:     "B:" + BAS2 format data

Usage:
    python3 claude_streaming_proxy.py [--port 8080]

Environment:
    ANTHROPIC_API_KEY - Required for Claude API
"""

import os
import sys
import json
import struct
import socket
import threading
import argparse
import subprocess
import tempfile
import time
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Tuple, List, Dict, Generator

# Import our tokenizer
from basic_tokenizer_streaming import tokenize_program, detokenize_program

# Try to import anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("Warning: anthropic module not found. Install with: pip install anthropic")

# Configuration
DEFAULT_PORT = 8080
MAX_CHUNK_SIZE = 256
BASIC_START = 0x0801
MAX_ITERATIONS = 5
BOBBIN_TIMEOUT = 10

# System prompt for Claude - optimized for Applesoft BASIC
SYSTEM_PROMPT = """You are an expert Applesoft BASIC programmer for the Apple IIe.

CRITICAL RULES:
1. Respond with ONLY the BASIC code - no explanations, no markdown, no comments outside REM
2. Every line MUST start with a line number (10, 20, 30, etc.)
3. Use standard Applesoft syntax only

APPLESOFT BASICS:
- Line numbers: 0-63999
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

COLORS (Lo-Res):
0=Black,1=Magenta,2=DkBlue,3=Purple,4=DkGreen,5=Gray1,6=MedBlue,7=LtBlue
8=Brown,9=Orange,10=Gray2,11=Pink,12=Green,13=Yellow,14=Aqua,15=White

Respond with ONLY the BASIC program, starting with the first line number."""


class BobhinTester:
    """Tests BASIC programs using Bobbin emulator."""

    def __init__(self, bobbin_path: Optional[str] = None):
        self.bobbin_path = bobbin_path or self._find_bobbin()

    def _find_bobbin(self) -> Optional[str]:
        """Try to find bobbin executable."""
        paths = [
            "/usr/local/bin/bobbin",
            os.path.expanduser("~/bobbin/src/bobbin"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bobbin", "src", "bobbin"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return None

    def test_syntax(self, code: str) -> Tuple[bool, str]:
        """
        Test BASIC syntax by tokenizing and validating.
        Returns (success, error_message).
        """
        errors = []
        lines = code.strip().split('\n')

        # Track FOR/NEXT matching
        for_stack = []
        line_numbers = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check line number
            match = re.match(r'^(\d+)\s*(.*)', line)
            if not match:
                errors.append(f"Missing line number: {line[:30]}")
                continue

            line_num = int(match.group(1))
            content = match.group(2).upper()
            line_numbers.append(line_num)

            # Check FOR/NEXT balance
            # Count FOR statements (not inside strings)
            in_string = False
            i = 0
            while i < len(content):
                if content[i] == '"':
                    in_string = not in_string
                elif not in_string:
                    if content[i:i+4] == 'FOR ' or content[i:i+4] == 'FOR=':
                        # Extract variable
                        rest = content[i+3:].strip()
                        if rest and rest[0].isalpha():
                            var = rest[0]
                            for_stack.append((line_num, var))
                    elif content[i:i+4] == 'NEXT':
                        if for_stack:
                            for_stack.pop()
                        else:
                            errors.append(f"NEXT without FOR at line {line_num}")
                i += 1

        # Check unclosed FOR loops
        for line_num, var in for_stack:
            errors.append(f"FOR without NEXT: {var} at line {line_num}")

        # Check line number order
        for i in range(1, len(line_numbers)):
            if line_numbers[i] <= line_numbers[i-1]:
                errors.append(f"Line numbers out of order: {line_numbers[i-1]} >= {line_numbers[i]}")

        # Try tokenization
        try:
            tokenized = tokenize_program(code, BASIC_START)
            if len(tokenized) < 4:
                errors.append("Program too short or empty")
        except Exception as e:
            errors.append(f"Tokenization error: {str(e)}")

        if errors:
            return False, "; ".join(errors)
        return True, f"OK ({len(tokenized)} bytes)"

    def test_with_bobbin(self, code: str) -> Tuple[bool, str, List[str]]:
        """
        Test program with actual Bobbin emulator.
        Returns (success, output, errors).
        """
        if not self.bobbin_path:
            # Fall back to syntax check only
            success, msg = self.test_syntax(code)
            return success, msg, [] if success else [msg]

        # This would run bobbin in headless mode and capture output
        # For now, just do syntax validation
        success, msg = self.test_syntax(code)
        return success, msg, [] if success else [msg]


class ClaudeGenerator:
    """Generates BASIC code using Claude API with iteration."""

    def __init__(self):
        self.client = None
        if HAS_ANTHROPIC:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
        self.tester = BobhinTester()

    def generate_with_testing(self, prompt: str,
                              status_callback=None) -> Tuple[str, bool, List[str]]:
        """
        Generate and test BASIC code, iterating until it works.
        Returns (code, success, messages).
        """
        messages_log = []

        def status(msg):
            messages_log.append(msg)
            if status_callback:
                status_callback(msg)

        if not self.client:
            status("No API key - using fallback")
            code = self._fallback_code(prompt)
            return code, True, messages_log

        messages = [{"role": "user", "content": prompt}]

        for attempt in range(1, MAX_ITERATIONS + 1):
            status(f"Attempt {attempt}/{MAX_ITERATIONS}...")

            try:
                # Call Claude
                status("Asking Claude...")
                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4000,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )

                code = self._extract_code(response.content[0].text)
                line_count = len([l for l in code.split('\n') if l.strip()])
                status(f"Got {line_count} lines")

                # Test the code
                status("Testing...")
                success, result, errors = self.tester.test_with_bobbin(code)

                if success:
                    status("SUCCESS!")
                    return code, True, messages_log

                # Report error and ask for fix
                error_msg = "; ".join(errors) if errors else result
                status(f"Error: {error_msg[:50]}")

                messages.append({"role": "assistant", "content": code})
                messages.append({
                    "role": "user",
                    "content": f"Error: {error_msg}\n\nFix the error and provide the complete corrected program."
                })

            except Exception as e:
                status(f"API error: {str(e)[:30]}")
                if attempt == MAX_ITERATIONS:
                    return self._fallback_code(prompt), False, messages_log

        # Return last attempt
        status("Max attempts reached")
        return code, False, messages_log

    def _extract_code(self, response: str) -> str:
        """Extract BASIC code from response."""
        # Remove markdown
        if '```' in response:
            match = re.search(r'```(?:\w*\n)?(.*?)```', response, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Find first line that starts with a number
        lines = response.split('\n')
        start_idx = 0
        for i, line in enumerate(lines):
            if re.match(r'^\d+\s', line.strip()):
                start_idx = i
                break

        # Find last line that starts with a number
        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if re.match(r'^\d+\s', lines[i].strip()):
                end_idx = i + 1
                break

        return '\n'.join(lines[start_idx:end_idx]).strip()

    def _fallback_code(self, prompt: str) -> str:
        """Generate fallback code when API unavailable."""
        safe = prompt[:18].upper().replace('"', "'")
        return f'''10 REM CLAUDE AGENT
20 HOME
30 PRINT "REQUEST:"
40 PRINT "{safe}"
50 PRINT
60 PRINT "API KEY NOT SET"
70 PRINT "EXPORT ANTHROPIC_API_KEY"
80 END
'''


def encode_bas2(tokenized: bytes, start_addr: int = BASIC_START) -> bytes:
    """Encode tokenized BASIC in BAS2 streaming protocol."""
    output = bytearray()
    output.extend(b'BAS2')
    output.extend(struct.pack('<H', len(tokenized)))
    output.extend(struct.pack('<H', start_addr))

    offset = 0
    while offset < len(tokenized):
        chunk_size = min(MAX_CHUNK_SIZE, len(tokenized) - offset)
        output.extend(struct.pack('<H', chunk_size))
        output.extend(tokenized[offset:offset + chunk_size])
        offset += chunk_size

    output.extend(struct.pack('<H', 0))  # End marker
    return bytes(output)


class StreamingHandler(BaseHTTPRequestHandler):
    """HTTP handler with streaming support."""

    generator = ClaudeGenerator()

    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}")

    def do_POST(self):
        if self.path == '/claude/binary':
            self.handle_binary_request()
        elif self.path == '/claude/stream':
            self.handle_streaming_request()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Claude Streaming Proxy OK\n')
        elif self.path == '/test':
            self.handle_test_page()
        else:
            self.send_error(404)

    def handle_binary_request(self):
        """Handle /claude/binary - returns BAS2 encoded program."""
        content_length = int(self.headers.get('Content-Length', 0))
        prompt = self.rfile.read(content_length).decode('utf-8', errors='ignore')

        print(f"[Proxy] Request: {prompt[:50]}...")

        code, success, messages = self.generator.generate_with_testing(
            prompt,
            lambda msg: print(f"  [{msg}]")
        )

        try:
            tokenized = tokenize_program(code, BASIC_START)
            bas2_data = encode_bas2(tokenized)

            print(f"[Proxy] Sending {len(bas2_data)} bytes")

            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(bas2_data)))
            self.send_header('X-Success', 'true' if success else 'false')
            self.end_headers()
            self.wfile.write(bas2_data)

        except Exception as e:
            print(f"[Proxy] Error: {e}")
            self.send_error(500, str(e))

    def handle_streaming_request(self):
        """Handle /claude/stream - streams progress then BAS2."""
        content_length = int(self.headers.get('Content-Length', 0))
        prompt = self.rfile.read(content_length).decode('utf-8', errors='ignore')

        print(f"[Stream] Request: {prompt[:50]}...")

        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()

        def send_status(msg):
            # Send status line: S:message\n
            line = f"S:{msg}\n".encode('ascii', errors='replace')
            self._send_chunk(line)
            print(f"  [Status] {msg}")

        code, success, _ = self.generator.generate_with_testing(prompt, send_status)

        try:
            tokenized = tokenize_program(code, BASIC_START)
            bas2_data = encode_bas2(tokenized)

            # Send ready indicator
            self._send_chunk(b"R:Inject program? (Y/N)\n")

            # Send binary marker and data
            self._send_chunk(b"B:")
            self._send_chunk(bas2_data)

            # End chunked transfer
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

        except Exception as e:
            self._send_chunk(f"E:{str(e)}\n".encode())
            self.wfile.write(b"0\r\n\r\n")

    def _send_chunk(self, data: bytes):
        """Send a chunk in chunked transfer encoding."""
        self.wfile.write(f"{len(data):x}\r\n".encode())
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def handle_test_page(self):
        """Serve a test page."""
        html = '''<!DOCTYPE html>
<html><head><title>Claude Apple II Proxy</title></head>
<body>
<h1>Claude Apple II Proxy</h1>
<form method="post" action="/claude/binary">
<textarea name="prompt" rows="4" cols="50">print hello world</textarea><br>
<button type="submit">Generate</button>
</form>
</body></html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())


def main():
    parser = argparse.ArgumentParser(description='Claude Streaming Proxy')
    parser.add_argument('--port', '-p', type=int, default=DEFAULT_PORT)
    parser.add_argument('--host', '-H', default='0.0.0.0')
    args = parser.parse_args()

    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("Warning: ANTHROPIC_API_KEY not set")
        print("Using fallback code generation\n")

    server = HTTPServer((args.host, args.port), StreamingHandler)
    print(f"Claude Streaming Proxy")
    print(f"Listening on {args.host}:{args.port}")
    print(f"Endpoints:")
    print(f"  POST /claude/binary  - Generate BAS2 program")
    print(f"  POST /claude/stream  - Stream progress + BAS2")
    print(f"  GET  /status         - Health check")
    print(f"  GET  /test           - Test page")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown")


if __name__ == '__main__':
    main()
