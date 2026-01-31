"""Proxy control for Apple II Agent.

Controls the unified proxy server that bridges Apple II to Claude API.
"""

import os
import subprocess
import time
from pathlib import Path

CONTROL_DIR = '/tmp/claude'
PID_FILE = f'{CONTROL_DIR}/proxy.pid'
SHUTDOWN_FILE = f'{CONTROL_DIR}/proxy_shutdown'
LOG_FILE = f'{CONTROL_DIR}/proxy.log'

# Find proxy script relative to this module
PROXY_DIR = Path(__file__).parent.parent.parent / "proxy"
PROXY_SCRIPT = PROXY_DIR / "unified_proxy.py"


def get_pid() -> int | None:
    """Get the running proxy PID from PID file, or None."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            pass
    return None


def is_running() -> bool:
    """Check if proxy is running."""
    pid = get_pid()
    if pid:
        # Check if process actually exists
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            # Process doesn't exist, clean up stale PID file
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
    return False


def status() -> dict:
    """Get proxy status."""
    pid = get_pid()
    running = is_running()
    return {
        "running": running,
        "pid": pid if running else None,
        "log_file": LOG_FILE if running else None
    }


def start(host: str = '0.0.0.0', port: int = 8080) -> dict:
    """Start the proxy server."""
    if is_running():
        return {"success": False, "error": "Proxy is already running", "pid": get_pid()}

    # Ensure control directory exists
    os.makedirs(CONTROL_DIR, exist_ok=True)

    # Clean up stale files
    for f in [SHUTDOWN_FILE, PID_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    # Check if proxy script exists
    if not PROXY_SCRIPT.exists():
        return {"success": False, "error": f"Proxy script not found: {PROXY_SCRIPT}"}

    # Start proxy in background with unbuffered output
    with open(LOG_FILE, 'w') as log:
        proc = subprocess.Popen(
            ['python3', '-u', str(PROXY_SCRIPT), '--host', host, '--port', str(port)],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(PROXY_DIR)
        )

    # Wait for PID file to appear
    for _ in range(50):
        time.sleep(0.1)
        if os.path.exists(PID_FILE):
            pid = get_pid()
            return {"success": True, "pid": pid, "port": port, "log_file": LOG_FILE}

    return {"success": False, "error": "Proxy failed to start (no PID file)"}


def stop() -> dict:
    """Stop the proxy server."""
    pid = get_pid()
    if not pid:
        return {"success": True, "message": "Proxy is not running"}

    # Create shutdown file
    os.makedirs(CONTROL_DIR, exist_ok=True)
    with open(SHUTDOWN_FILE, 'w') as f:
        f.write('shutdown')

    # Wait for PID file to disappear
    for _ in range(50):
        time.sleep(0.1)
        if not os.path.exists(PID_FILE):
            # Clean up shutdown file
            if os.path.exists(SHUTDOWN_FILE):
                try:
                    os.remove(SHUTDOWN_FILE)
                except OSError:
                    pass
            return {"success": True, "message": "Proxy stopped"}

    # Try harder - remove PID file
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
    if os.path.exists(SHUTDOWN_FILE):
        try:
            os.remove(SHUTDOWN_FILE)
        except OSError:
            pass

    return {"success": True, "message": "Proxy stopped (forced cleanup)"}


def get_log(lines: int = 50) -> str:
    """Get recent proxy log lines."""
    if not os.path.exists(LOG_FILE):
        return "No log file found"

    try:
        with open(LOG_FILE, 'r') as f:
            all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    except OSError as e:
        return f"Error reading log: {e}"
