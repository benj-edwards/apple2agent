#!/usr/bin/env python3
"""Control script for the Apple II Agent proxy server."""

import os
import sys
import time
import subprocess

CONTROL_DIR = '/tmp/claude'
PID_FILE = f'{CONTROL_DIR}/proxy.pid'
SHUTDOWN_FILE = f'{CONTROL_DIR}/proxy_shutdown'
PROXY_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unified_proxy.py')


def get_pid():
    """Get the running proxy PID from PID file, or None."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            pass
    return None


def status():
    """Show proxy status."""
    pid = get_pid()
    if pid:
        print(f"Proxy is running (PID: {pid})")
        return True
    else:
        print("Proxy is not running")
        return False


def stop():
    """Stop the proxy gracefully using shutdown file."""
    pid = get_pid()
    if not pid:
        print("Proxy is not running")
        # Clean up any stale files
        if os.path.exists(SHUTDOWN_FILE):
            os.remove(SHUTDOWN_FILE)
        return True

    print(f"Stopping proxy (PID: {pid})...")
    os.makedirs(CONTROL_DIR, exist_ok=True)

    # Create shutdown file - proxy checks for this and exits gracefully
    with open(SHUTDOWN_FILE, 'w') as f:
        f.write('shutdown')

    # Wait for PID file to disappear (proxy removes it on exit)
    for _ in range(50):
        time.sleep(0.1)
        if not os.path.exists(PID_FILE):
            print("Proxy stopped")
            # Clean up shutdown file if still there
            if os.path.exists(SHUTDOWN_FILE):
                os.remove(SHUTDOWN_FILE)
            return True

    # If still running after 5 seconds, PID file may be stale
    print("Proxy did not respond - removing stale PID file")
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    if os.path.exists(SHUTDOWN_FILE):
        os.remove(SHUTDOWN_FILE)
    return True


def start():
    """Start the proxy in background."""
    if get_pid():
        print("Proxy is already running")
        return False

    print("Starting proxy...")
    os.makedirs(CONTROL_DIR, exist_ok=True)

    # Start in background with unbuffered output
    log_file = f'{CONTROL_DIR}/proxy.log'
    with open(log_file, 'w') as log:
        subprocess.Popen(
            [sys.executable, '-u', PROXY_SCRIPT],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )

    # Wait for it to start
    for _ in range(30):
        time.sleep(0.1)
        if get_pid():
            pid = get_pid()
            print(f"Proxy started (PID: {pid})")
            print(f"Log: {log_file}")
            return True

    print("Proxy failed to start. Check log:")
    print(f"  cat {log_file}")
    return False


def restart():
    """Restart the proxy."""
    stop()
    time.sleep(0.5)
    return start()


def main():
    if len(sys.argv) < 2:
        print("Usage: proxyctl.py [start|stop|restart|status]")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'start':
        success = start()
    elif cmd == 'stop':
        success = stop()
    elif cmd == 'restart':
        success = restart()
    elif cmd == 'status':
        success = status()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: proxyctl.py [start|stop|restart|status]")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
