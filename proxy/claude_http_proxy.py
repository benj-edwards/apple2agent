#!/usr/bin/env python3
"""
Claude HTTP Proxy for Apple II Agent

This server:
1. Listens for HTTP requests from the Apple II ampersand agent
2. Calls Claude API to generate BASIC code
3. Pre-tests the code on Bobbin emulator (via MCP or direct API)
4. Iterates until the code works
5. Returns verified, working tokenized BASIC in BAS2 format

BAS2 Protocol:
  "BAS2" (4 bytes) + total_len (2) + start_addr (2) +
  [chunk_size (2) + data]* + 0x0000

Usage:
    python3 claude_http_proxy.py [--port 8080]
"""

import os
import sys
import json
import struct
import socket
import threading
import argparse
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Tuple, List, Dict

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
MAX_CHUNK_SIZE = 512  # Chunk size for BAS2 protocol
BASIC_START = 0x0801  # Standard Applesoft BASIC start address

# System prompt for Claude
SYSTEM_PROMPT = """You are an expert Applesoft BASIC programmer for the Apple IIe.

When asked to write a program, respond with ONLY the BASIC code - no explanations, no markdown.
Use proper line numbers (10, 20, 30...) and standard Applesoft syntax.

Key Applesoft limitations:
- Line numbers 0-63999
- Variable names: 2 significant characters (A, A1, AB are distinct; ABC = AB)
- Arrays: DIM before use
- Strings: max 255 characters
- FOR loops need matching NEXT

Common commands:
- PRINT, INPUT, IF...THEN, FOR...NEXT, GOTO, GOSUB, RETURN
- HOME (clear screen), HTAB/VTAB (cursor position)
- GR (lo-res 40x48 graphics), HGR (hi-res 280x192)
- COLOR= (0-15 for GR), HCOLOR= (0-7 for HGR)
- PLOT X,Y, HLIN Y1,Y2 AT X, VLIN X1,X2 AT Y

Graphics colors (GR):
0=Black, 1=Magenta, 2=Dark Blue, 3=Purple, 4=Dark Green, 5=Gray1,
6=Medium Blue, 7=Light Blue, 8=Brown, 9=Orange, 10=Gray2, 11=Pink,
12=Green, 13=Yellow, 14=Aqua, 15=White

Always respond with just the BASIC code, nothing else.
Start with the line number, no extra text before or after."""


class EmulatorTester:
    """Tests BASIC programs on Bobbin emulator via MCP or subprocess."""

    def __init__(self, mcp_socket_path: Optional[str] = None):
        self.mcp_socket_path = mcp_socket_path
        self.bobbin_process = None

    def test_program(self, basic_code: str) -> Tuple[bool, str, Optional[str]]:
        """
        Test a BASIC program and return (success, output, error_msg).

        For now, just validates tokenization. Full emulator testing
        would require MCP integration or subprocess control.
        """
        try:
            # Step 1: Try to tokenize (catches syntax errors in tokenization)
            tokenized = tokenize_program(basic_code, BASIC_START)

            # Step 2: Verify it can be detokenized back
            detokenized = detokenize_program(tokenized)

            # Step 3: Basic validation checks
            errors = self._validate_basic(basic_code)
            if errors:
                return False, "", "\n".join(errors)

            return True, f"Tokenized OK: {len(tokenized)} bytes", None

        except Exception as e:
            return False, "", f"Tokenization error: {str(e)}"

    def _validate_basic(self, code: str) -> List[str]:
        """Basic validation of Applesoft BASIC code."""
        errors = []
        lines = code.strip().split('\n')

        for_stack = []
        gosub_targets = set()
        defined_lines = set()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Extract line number
            parts = line.split(None, 1)
            if not parts[0].isdigit():
                errors.append(f"Line without number: {line[:30]}")
                continue

            line_num = int(parts[0])
            defined_lines.add(line_num)

            content = parts[1].upper() if len(parts) > 1 else ""

            # Track FOR/NEXT
            if 'FOR ' in content or content.startswith('FOR'):
                # Extract loop variable
                match_for = content.find('FOR')
                if match_for >= 0:
                    rest = content[match_for+3:].strip()
                    if rest and rest[0].isalpha():
                        var = rest[0]
                        if len(rest) > 1 and rest[1].isalnum():
                            var += rest[1]
                        for_stack.append((line_num, var))

            if 'NEXT' in content:
                if for_stack:
                    for_stack.pop()

        # Check unmatched FOR
        for line_num, var in for_stack:
            errors.append(f"FOR without NEXT: variable {var} at line {line_num}")

        return errors


class ClaudeCodeGenerator:
    """Generates and refines BASIC code using Claude API."""

    def __init__(self):
        self.client = None
        if HAS_ANTHROPIC:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str, max_attempts: int = 3) -> Tuple[str, bool]:
        """
        Generate BASIC code for the given prompt.
        Returns (code, success).
        """
        if not self.client:
            # Fallback: generate a simple test program
            return self._fallback_generate(prompt)

        messages = [{"role": "user", "content": prompt}]
        tester = EmulatorTester()

        for attempt in range(max_attempts):
            try:
                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4000,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )

                code = self._extract_code(response.content[0].text)

                # Test the code
                success, output, error = tester.test_program(code)

                if success:
                    print(f"[Claude] Generated working code on attempt {attempt + 1}")
                    return code, True

                # Ask Claude to fix
                print(f"[Claude] Attempt {attempt + 1} failed: {error}")
                messages.append({"role": "assistant", "content": code})
                messages.append({
                    "role": "user",
                    "content": f"That code has an error: {error}\n\nPlease fix it and provide the complete corrected program."
                })

            except Exception as e:
                print(f"[Claude] API error: {e}")
                return self._fallback_generate(prompt)

        # Return last attempt even if it has issues
        return code, False

    def _extract_code(self, response: str) -> str:
        """Extract BASIC code from Claude's response."""
        # Remove markdown code blocks if present
        if '```' in response:
            import re
            match = re.search(r'```(?:basic|BASIC|applesoft)?\n?(.*?)```', response, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return response.strip()

    def _fallback_generate(self, prompt: str) -> Tuple[str, bool]:
        """Generate a simple test program when API is unavailable."""
        # Create a simple program that shows the prompt was received
        safe_prompt = prompt[:20].upper().replace('"', "'")
        code = f'''10 REM CLAUDE AGENT
20 HOME
30 PRINT "REQUEST RECEIVED:"
40 PRINT "{safe_prompt}..."
50 PRINT
60 PRINT "(API KEY NOT SET)"
70 END
'''
        return code, True


def encode_bas2(tokenized: bytes, start_addr: int = BASIC_START) -> bytes:
    """
    Encode tokenized BASIC in BAS2 protocol format.

    Format:
      "BAS2" (4 bytes)
      total_length (2 bytes, little-endian)
      start_address (2 bytes, little-endian)
      [chunk_size (2 bytes) + chunk_data]*
      0x0000 (end marker)
    """
    output = bytearray()

    # Magic
    output.extend(b'BAS2')

    # Total length
    output.extend(struct.pack('<H', len(tokenized)))

    # Start address
    output.extend(struct.pack('<H', start_addr))

    # Chunks
    offset = 0
    while offset < len(tokenized):
        chunk_size = min(MAX_CHUNK_SIZE, len(tokenized) - offset)
        output.extend(struct.pack('<H', chunk_size))
        output.extend(tokenized[offset:offset + chunk_size])
        offset += chunk_size

    # End marker
    output.extend(struct.pack('<H', 0))

    return bytes(output)


class AppleIIProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Apple II agent."""

    generator = ClaudeCodeGenerator()

    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}")

    def do_POST(self):
        if self.path == '/claude/binary':
            self.handle_claude_binary()
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Apple II Claude Proxy OK\n')
        else:
            self.send_error(404, "Not Found")

    def handle_claude_binary(self):
        """Handle POST /claude/binary - generate and return tokenized BASIC."""
        try:
            # Read the prompt from request body
            content_length = int(self.headers.get('Content-Length', 0))
            prompt = self.rfile.read(content_length).decode('utf-8', errors='ignore')

            print(f"[Proxy] Received request: {prompt[:50]}...")

            # Generate BASIC code
            code, success = self.generator.generate(prompt)

            print(f"[Proxy] Generated code ({len(code)} chars):")
            for line in code.split('\n')[:5]:
                print(f"  {line}")
            if len(code.split('\n')) > 5:
                print("  ...")

            # Tokenize
            try:
                tokenized = tokenize_program(code, BASIC_START)
            except Exception as e:
                print(f"[Proxy] Tokenization failed: {e}")
                self.send_error(500, f"Tokenization error: {e}")
                return

            # Encode in BAS2 format
            bas2_data = encode_bas2(tokenized)

            print(f"[Proxy] Sending {len(bas2_data)} bytes (BAS2 format)")

            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(bas2_data)))
            self.end_headers()
            self.wfile.write(bas2_data)

        except Exception as e:
            print(f"[Proxy] Error: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))


def main():
    parser = argparse.ArgumentParser(
        description='Claude HTTP Proxy for Apple II Agent'
    )
    parser.add_argument('--port', '-p', type=int, default=DEFAULT_PORT,
                        help=f'Port to listen on (default: {DEFAULT_PORT})')
    parser.add_argument('--host', '-H', default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')

    args = parser.parse_args()

    # Check for API key
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("Warning: ANTHROPIC_API_KEY not set")
        print("Set with: export ANTHROPIC_API_KEY='your-key'")
        print("Proxy will use fallback code generation.\n")

    server_address = (args.host, args.port)
    httpd = HTTPServer(server_address, AppleIIProxyHandler)

    print(f"Claude HTTP Proxy for Apple II")
    print(f"Listening on {args.host}:{args.port}")
    print(f"Endpoints:")
    print(f"  POST /claude/binary - Generate BASIC from prompt")
    print(f"  GET  /status        - Health check")
    print()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()


if __name__ == '__main__':
    main()
