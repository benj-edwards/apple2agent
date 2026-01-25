#!/usr/bin/env python3
"""
Agentic Apple II Proxy

"Claude Code for Apple IIe" - An autonomous coding system where Claude can:
1. Write BASIC programs
2. Inject them into Apple II memory
3. Run them and read screen output
4. Detect and fix errors automatically
5. Iterate until the program works

All without human intervention on the Apple II side.

Usage:
    python3 agentic_proxy.py "Write a program that prints the numbers 1 to 10"
    python3 agentic_proxy.py --interactive

Requires:
    - ANTHROPIC_API_KEY environment variable
    - Apple II with remote shell running (or Bobbin emulator)
"""

import os
import sys
import time
import json
import socket
import argparse
from typing import List, Dict, Optional, Tuple

# Import our components
from basic_tokenizer_streaming import tokenize_program, detokenize_program
from screen_reader import ScreenReader, LINE_ADDRESSES, SCREEN_WIDTH, apple2_char_to_ascii
from program_injector import ProgramInjector, PROGRAM_START
from run_trigger import RunTrigger, RUN_ENTRY, CURLINE
from error_parser import parse_errors, get_error_summary, get_fix_suggestion

# Try to import anthropic
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("Warning: anthropic module not found. Install with: pip install anthropic")

# Configuration
DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 8080
MAX_ATTEMPTS = 5
EXECUTION_TIMEOUT = 10.0  # seconds

# System prompt for Claude
SYSTEM_PROMPT = """You are an expert Applesoft BASIC programmer for the Apple IIe.

When asked to write a program, respond with ONLY the BASIC code - no explanations.
Use proper line numbers (10, 20, 30...) and standard Applesoft syntax.

Key Applesoft limitations:
- Line numbers 0-63999
- Variable names: 2 significant characters
- Arrays: DIM before use, max 32767 elements
- Strings: max 255 characters
- Numbers: max 1.7E38

Common commands:
- PRINT, INPUT, IF...THEN, FOR...NEXT, GOTO, GOSUB, RETURN
- HOME (clear screen), HTAB/VTAB (cursor position)
- GR (lo-res graphics), HGR (hi-res graphics)
- COLOR= (0-15), PLOT X,Y, HLIN Y1,Y2 AT X, VLIN

If there's an error, I'll show you the error message and screen.
Fix the error and provide the complete corrected program.

Always respond with just the BASIC code, nothing else."""


class SimpleProxy:
    """Simple synchronous proxy for Apple II remote shell."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self) -> bool:
        """Connect to Apple II remote shell."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(5)
            self._wait_ready()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Close connection."""
        if self.sock:
            self.sock.close()
            self.sock = None

    def _wait_ready(self):
        """Wait for READY prompt."""
        data = b''
        while b'READY' not in data:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk

    def _send_cmd(self, cmd: str) -> str:
        """Send command and get response."""
        self.sock.send((cmd + '\r\n').encode())
        data = b''
        while b'\n' not in data:
            data += self.sock.recv(1024)
        return data.decode().strip()

    def peek(self, addr: int) -> Optional[int]:
        """Read a byte from memory."""
        self._wait_ready()
        resp = self._send_cmd(f'P {addr:04X}')
        if resp.startswith('OK '):
            return int(resp[3:5], 16)
        return None

    def poke(self, addr: int, value: int) -> bool:
        """Write a byte to memory."""
        self._wait_ready()
        resp = self._send_cmd(f'O {addr:04X} {value:02X}')
        return resp.startswith('OK')

    def call(self, addr: int) -> bool:
        """Call a subroutine."""
        self._wait_ready()
        resp = self._send_cmd(f'C {addr:04X}')
        return resp.startswith('OK')

    def wait_response(self, timeout: float = 1.0):
        """Wait for any pending response (placeholder for compatibility)."""
        pass


class AgenticProxy:
    """Main agentic proxy for autonomous Apple II coding."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.proxy = SimpleProxy(host, port)
        self.client = None
        if HAS_ANTHROPIC:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)

    def connect(self) -> bool:
        """Connect to Apple II."""
        return self.proxy.connect()

    def disconnect(self):
        """Disconnect from Apple II."""
        self.proxy.disconnect()

    def read_screen(self) -> List[str]:
        """Read the Apple II text screen."""
        lines = []
        for line_num in range(24):
            addr = LINE_ADDRESSES[line_num]
            line_bytes = []
            for col in range(SCREEN_WIDTH):
                val = self.proxy.peek(addr + col)
                if val is None:
                    return None
                line_bytes.append(val)
            line = ''.join(apple2_char_to_ascii(b) for b in line_bytes)
            lines.append(line)
        return lines

    def inject_program(self, source: str) -> Dict:
        """Inject a BASIC program into Apple II memory."""
        injector = ProgramInjector(self.proxy)
        return injector.inject_basic(source)

    def run_program(self) -> bool:
        """Run the current BASIC program."""
        trigger = RunTrigger(self.proxy)
        return trigger.run_program()

    def wait_for_completion(self, timeout: float = EXECUTION_TIMEOUT) -> bool:
        """Wait for program to finish."""
        trigger = RunTrigger(self.proxy)
        return trigger.wait_for_completion(timeout)

    def ask_claude(self, messages: List[Dict]) -> str:
        """Ask Claude to write or fix code."""
        if not self.client:
            raise RuntimeError("Anthropic client not initialized. Set ANTHROPIC_API_KEY.")

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        return response.content[0].text

    def extract_basic_code(self, response: str) -> str:
        """Extract BASIC code from Claude's response."""
        # Remove markdown code blocks if present
        if '```' in response:
            # Find code between ```basic or ``` markers
            import re
            match = re.search(r'```(?:basic|BASIC)?\n?(.*?)```', response, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Otherwise assume entire response is code
        return response.strip()

    def run_agentic(self, request: str, max_attempts: int = MAX_ATTEMPTS) -> Dict:
        """Run the agentic coding loop.

        Args:
            request: User's coding request
            max_attempts: Maximum fix attempts

        Returns:
            Dict with results:
                success: bool
                code: final BASIC code
                output: screen output
                attempts: number of attempts
                errors: list of any remaining errors
        """
        if not self.client:
            return {
                'success': False,
                'error': 'Claude API not configured. Set ANTHROPIC_API_KEY.',
                'attempts': 0,
            }

        messages = [{"role": "user", "content": request}]
        last_code = None
        last_errors = []

        for attempt in range(1, max_attempts + 1):
            print(f"\n=== Attempt {attempt}/{max_attempts} ===")

            # Ask Claude to write/fix code
            print("Asking Claude...")
            try:
                response = self.ask_claude(messages)
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Claude API error: {e}',
                    'attempts': attempt,
                }

            code = self.extract_basic_code(response)
            last_code = code
            print(f"Got {len(code.split(chr(10)))} lines of BASIC")

            # Inject the program
            print("Injecting program...")
            result = self.inject_program(code)
            if not result.get('success'):
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": f"Injection failed: {result.get('error')}. Please fix."
                })
                continue

            print(f"Injected {result['bytes_written']} bytes in {result['time_taken']:.1f}s")

            # Run the program
            print("Running program...")
            if not self.run_program():
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": "RUN failed. Please check the code."
                })
                continue

            # Wait for completion
            print("Waiting for completion...")
            time.sleep(1)  # Give program time to execute
            # self.wait_for_completion()  # Polling may not work well

            # Read screen
            print("Reading screen...")
            screen = self.read_screen()
            if screen is None:
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": "Could not read screen. Please check the code."
                })
                continue

            screen_text = '\n'.join(screen)

            # Check for errors
            errors = parse_errors(screen)
            last_errors = errors

            if not errors:
                print("SUCCESS! No errors detected.")
                return {
                    'success': True,
                    'code': code,
                    'output': screen_text,
                    'attempts': attempt,
                    'errors': [],
                }

            # Report errors and ask Claude to fix
            print(f"Found {len(errors)} error(s):")
            print(get_error_summary(errors))

            error_detail = get_error_summary(errors)
            for err in errors:
                error_detail += f"\nSuggestion: {get_fix_suggestion(err)}"

            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"""The program has errors:

{error_detail}

Screen output:
{screen_text}

Please fix the errors and provide the complete corrected program."""
            })

        # Max attempts reached
        return {
            'success': False,
            'code': last_code,
            'errors': last_errors,
            'attempts': max_attempts,
            'error': 'Max attempts reached',
        }


def main():
    parser = argparse.ArgumentParser(
        description='Agentic Apple II Proxy - Claude Code for Apple IIe'
    )
    parser.add_argument('request', nargs='?',
                        help='Coding request for Claude')
    parser.add_argument('--host', default=DEFAULT_HOST,
                        help=f'Remote shell host (default: {DEFAULT_HOST})')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help=f'Remote shell port (default: {DEFAULT_PORT})')
    parser.add_argument('--max-attempts', type=int, default=MAX_ATTEMPTS,
                        help=f'Maximum fix attempts (default: {MAX_ATTEMPTS})')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive mode')
    parser.add_argument('--test', action='store_true',
                        help='Test connection only')

    args = parser.parse_args()

    # Check for API key
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("Warning: ANTHROPIC_API_KEY not set")
        if not args.test:
            print("Set with: export ANTHROPIC_API_KEY='your-key'")

    # Create proxy
    agent = AgenticProxy(args.host, args.port)

    # Connect
    print(f"Connecting to {args.host}:{args.port}...")
    if not agent.connect():
        print("Failed to connect to Apple II")
        sys.exit(1)
    print("Connected!")

    if args.test:
        print("\nTest mode - reading screen...")
        screen = agent.read_screen()
        if screen:
            print("+" + "-" * 40 + "+")
            for line in screen:
                print("|" + line + "|")
            print("+" + "-" * 40 + "+")
        else:
            print("Failed to read screen")
        agent.disconnect()
        sys.exit(0)

    try:
        if args.interactive:
            # Interactive mode
            print("\nAgentic Apple II - Interactive Mode")
            print("Type your coding requests. 'quit' to exit.\n")

            while True:
                try:
                    request = input("Request: ").strip()
                except EOFError:
                    break

                if not request:
                    continue
                if request.lower() in ('quit', 'exit', 'q'):
                    break

                result = agent.run_agentic(request, args.max_attempts)

                print("\n" + "=" * 50)
                if result['success']:
                    print("SUCCESS!")
                    print(f"Attempts: {result['attempts']}")
                    print("\nFinal code:")
                    print(result['code'])
                    print("\nOutput:")
                    print(result['output'][:500])
                else:
                    print("FAILED")
                    print(f"Error: {result.get('error')}")
                    print(f"Attempts: {result['attempts']}")
                    if result.get('code'):
                        print("\nLast code:")
                        print(result['code'])
                print("=" * 50 + "\n")

        elif args.request:
            # Single request mode
            result = agent.run_agentic(args.request, args.max_attempts)

            print("\n" + "=" * 50)
            print(f"Result: {'SUCCESS' if result['success'] else 'FAILED'}")
            print(f"Attempts: {result['attempts']}")

            if result['success']:
                print("\nFinal code:")
                print(result['code'])
                print("\nOutput:")
                print(result['output'])
            else:
                print(f"\nError: {result.get('error')}")
                if result.get('code'):
                    print("\nLast code:")
                    print(result['code'])

        else:
            print("\nUsage:")
            print("  agentic_proxy.py 'Write a hello world program'")
            print("  agentic_proxy.py --interactive")
            print("  agentic_proxy.py --test")

    finally:
        agent.disconnect()


if __name__ == '__main__':
    main()
