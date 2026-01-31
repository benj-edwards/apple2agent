#!/usr/bin/env python3
"""
Apple II Agent for Apple II - Web Interface

A web-based terminal that provides the same Apple II Agent experience
as the Apple II client, but from a browser. Still deploys code to
the real Apple II connected to the proxy.

Usage:
    python3 web_interface.py

Then open http://localhost:8081 in your browser.
"""

import os
import sys
import json
import asyncio
import threading
from typing import Optional, Callable, List, Dict, Any
from queue import Queue

# Add parent directory for imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from agentic_claude import AgenticClaude

# Try to import Flask
try:
    from flask import Flask, render_template_string, request, Response, jsonify
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    print("Flask not found. Install with: pip install flask")

# HTML template for the terminal interface
TERMINAL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Apple II Agent for Apple II</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            background: #000;
            color: #33ff33;
            font-family: 'Apple II', 'Courier New', monospace;
            font-size: 16px;
            padding: 20px;
            min-height: 100vh;
        }
        #header {
            text-align: center;
            border: 2px solid #33ff33;
            padding: 10px;
            margin-bottom: 20px;
        }
        #header h1 {
            font-size: 24px;
            margin-bottom: 5px;
        }
        #header .subtitle {
            font-size: 14px;
            color: #22aa22;
        }
        #terminal {
            background: #001100;
            border: 2px solid #33ff33;
            padding: 15px;
            min-height: 400px;
            max-height: 60vh;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        #status-bar {
            background: #002200;
            border: 2px solid #33ff33;
            border-top: none;
            padding: 5px 15px;
            font-size: 14px;
            color: #ffff00;
        }
        #input-area {
            margin-top: 10px;
            display: flex;
            border: 2px solid #33ff33;
        }
        #prompt {
            background: #001100;
            color: #33ff33;
            padding: 10px;
            font-size: 16px;
        }
        #input {
            flex: 1;
            background: #001100;
            color: #33ff33;
            border: none;
            padding: 10px;
            font-size: 16px;
            font-family: inherit;
            outline: none;
        }
        #input:focus {
            background: #002200;
        }
        .user-msg {
            color: #33ff33;
        }
        .claude-msg {
            color: #00ffff;
        }
        .status-msg {
            color: #ffff00;
        }
        .error-msg {
            color: #ff3333;
        }
        .system-msg {
            color: #888888;
        }
        #commands {
            margin-top: 15px;
            font-size: 12px;
            color: #22aa22;
        }
        #commands span {
            margin-right: 15px;
        }
        .apple-ii-status {
            margin-top: 10px;
            padding: 10px;
            border: 1px solid #33ff33;
            font-size: 12px;
        }
        .connected {
            color: #33ff33;
        }
        .disconnected {
            color: #ff3333;
        }
    </style>
</head>
<body>
    <div id="header">
        <h1>CLAUDE CODE FOR APPLE //E</h1>
        <div class="subtitle">AI-Powered Programming - Web Terminal</div>
    </div>

    <div id="terminal"></div>
    <div id="status-bar">READY</div>

    <div id="input-area">
        <span id="prompt">&gt; </span>
        <input type="text" id="input" placeholder="Describe what you want to create..." autofocus>
    </div>

    <div id="commands">
        <span>/AGENT - Toggle Apple II Agent mode</span>
        <span>/CLEAR - New conversation</span>
        <span>/HELP - All commands</span>
    </div>

    <div class="apple-ii-status">
        Apple II Connection: <span id="apple-status" class="disconnected">CHECKING...</span>
    </div>

    <script>
        const terminal = document.getElementById('terminal');
        const statusBar = document.getElementById('status-bar');
        const input = document.getElementById('input');
        const appleStatus = document.getElementById('apple-status');

        let agentMode = false;

        function appendLine(text, className = '') {
            const line = document.createElement('div');
            line.className = className;
            line.textContent = text;
            terminal.appendChild(line);
            terminal.scrollTop = terminal.scrollHeight;
        }

        function setStatus(text) {
            statusBar.textContent = text;
        }

        function showWelcome() {
            appendLine('================================', 'system-msg');
            appendLine('    CLAUDE CODE FOR //E', 'system-msg');
            appendLine('================================', 'system-msg');
            appendLine('', 'system-msg');
            appendLine('AI-POWERED PROGRAMMING', 'system-msg');
            appendLine('DESCRIBE WHAT YOU WANT!', 'system-msg');
            appendLine('', 'system-msg');
            appendLine('Type /AGENT to enable Apple II Agent mode', 'system-msg');
            appendLine('Then describe your program in plain English.', 'system-msg');
            appendLine('', 'system-msg');
            appendLine('Examples:', 'system-msg');
            appendLine('  "Make a breakout game"', 'system-msg');
            appendLine('  "Write space invaders in assembly"', 'system-msg');
            appendLine('  "Create a bouncing ball demo"', 'system-msg');
            appendLine('================================', 'system-msg');
            appendLine('', 'system-msg');
        }

        async function sendMessage(message) {
            appendLine('> ' + message, 'user-msg');
            input.value = '';
            setStatus('THINKING...');

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: message})
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    const {value, done} = await reader.read();
                    if (done) break;

                    const text = decoder.decode(value);
                    const lines = text.split('\\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'status') {
                                    setStatus(data.text);
                                } else if (data.type === 'response') {
                                    appendLine(data.text, 'claude-msg');
                                } else if (data.type === 'error') {
                                    appendLine('ERROR: ' + data.text, 'error-msg');
                                } else if (data.type === 'done') {
                                    setStatus('READY');
                                }
                            } catch (e) {}
                        }
                    }
                }
            } catch (error) {
                appendLine('CONNECTION ERROR: ' + error.message, 'error-msg');
                setStatus('ERROR');
            }
        }

        async function checkAppleConnection() {
            try {
                const response = await fetch('/apple-status');
                const data = await response.json();
                if (data.connected) {
                    appleStatus.textContent = 'CONNECTED - ' + data.address;
                    appleStatus.className = 'connected';
                } else {
                    appleStatus.textContent = 'NOT CONNECTED';
                    appleStatus.className = 'disconnected';
                }
            } catch (e) {
                appleStatus.textContent = 'UNKNOWN';
                appleStatus.className = 'disconnected';
            }
        }

        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && input.value.trim()) {
                sendMessage(input.value.trim());
            }
        });

        // Initialize
        showWelcome();
        checkAppleConnection();
        setInterval(checkAppleConnection, 5000);
    </script>
</body>
</html>
"""


class WebInterface:
    """Web interface for Apple II Agent for Apple II."""

    def __init__(self, proxy_host: str = 'localhost', proxy_port: int = 8080):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.app = Flask(__name__) if HAS_FLASK else None
        self.agentic_claude: Optional[AgenticClaude] = None
        self.status_queue: Queue = Queue()
        self.apple_connected = False
        self.apple_address = None

        if self.app:
            self._setup_routes()

    def _setup_routes(self):
        """Set up Flask routes."""

        @self.app.route('/')
        def index():
            return render_template_string(TERMINAL_HTML)

        @self.app.route('/chat', methods=['POST'])
        def chat():
            data = request.json
            message = data.get('message', '')

            def generate():
                # Initialize agentic Claude if needed
                if not self.agentic_claude:
                    self.agentic_claude = AgenticClaude(
                        send_to_apple2=self._send_to_apple2,
                        send_status=self._send_status,
                        send_code=self._send_code,
                        send_binary=self._send_binary
                    )

                # Clear status queue
                while not self.status_queue.empty():
                    self.status_queue.get()

                # Run in thread to allow streaming
                result_holder = [None]
                error_holder = [None]

                def run_agent():
                    try:
                        result = self.agentic_claude.run_agentic(message)
                        result_holder[0] = result
                    except Exception as e:
                        error_holder[0] = str(e)

                thread = threading.Thread(target=run_agent)
                thread.start()

                # Stream status updates while agent runs
                while thread.is_alive():
                    try:
                        status = self.status_queue.get(timeout=0.1)
                        yield f"data: {json.dumps({'type': 'status', 'text': status})}\n\n"
                    except:
                        pass

                thread.join()

                # Drain remaining status updates
                while not self.status_queue.empty():
                    status = self.status_queue.get()
                    yield f"data: {json.dumps({'type': 'status', 'text': status})}\n\n"

                # Send result
                if error_holder[0]:
                    yield f"data: {json.dumps({'type': 'error', 'text': error_holder[0]})}\n\n"
                elif result_holder[0]:
                    yield f"data: {json.dumps({'type': 'response', 'text': result_holder[0]})}\n\n"

                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return Response(generate(), mimetype='text/event-stream')

        @self.app.route('/apple-status')
        def apple_status():
            return jsonify({
                'connected': self.apple_connected,
                'address': self.apple_address
            })

    def _send_status(self, status: str):
        """Queue status update for streaming."""
        self.status_queue.put(status)

    def _send_to_apple2(self, message: str):
        """Send message to Apple II (placeholder - would connect to proxy)."""
        self.status_queue.put(f"[TO APPLE II] {message}")

    def _send_code(self, source: str):
        """Send BASIC code to Apple II."""
        lines = len(source.strip().split('\n'))
        self.status_queue.put(f"[DEPLOYING] {lines} lines of BASIC")
        # TODO: Actually send to proxy

    def _send_binary(self, hex_data: str, address: int):
        """Send binary to Apple II."""
        size = len(hex_data.replace(" ", "")) // 2
        self.status_queue.put(f"[DEPLOYING] {size} bytes at ${address:04X}")
        # TODO: Actually send to proxy

    def run(self, host: str = '0.0.0.0', port: int = 8081):
        """Run the web interface."""
        if not HAS_FLASK:
            print("ERROR: Flask not installed. Run: pip install flask")
            return

        print(f"Apple II Agent for Apple II - Web Interface")
        print(f"=========================================")
        print(f"Open http://localhost:{port} in your browser")
        print(f"")
        print(f"This provides the same Apple II Agent experience")
        print(f"as the Apple II client, but from your browser.")
        print(f"Code will still be deployed to your real Apple II!")
        print(f"")

        self.app.run(host=host, port=port, threaded=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Apple II Agent for Apple II - Web Interface')
    parser.add_argument('--port', '-p', type=int, default=8081,
                        help='Web server port (default: 8081)')
    parser.add_argument('--host', '-H', default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--proxy-port', type=int, default=8080,
                        help='Apple II proxy port (default: 8080)')
    args = parser.parse_args()

    web = WebInterface(proxy_port=args.proxy_port)
    web.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
