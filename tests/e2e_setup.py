#!/usr/bin/env python3
"""
First-run setup, end to end - no API calls.

  1. Fresh disk, proxy on a non-default port: the agent finds it by broadcast,
     connects with no key pressed, and saves the address (CLAUDECONF).
  2. Reboot with discovery unavailable: the saved address is used.
  3. Proxy not running at boot: the agent says so; once the proxy starts,
     the next thing typed finds it and goes through.
  4. /SETIP and /PORT are saved to disk.

    .venv/bin/python tests/e2e_setup.py
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from apple2_mcp.control_socket import BobbinControlSocket  # noqa: E402
import make_agent_disk as m  # noqa: E402

WORK = "/tmp/a2setup"
SOCK = f"{WORK}/apple.sock"
PORT = 6598
DISCOVERY = PORT + 10000             # this test's own discovery channel (Bobbin + proxy)
DISK = f"{WORK}/agent.dsk"



def wait_until_listening(log_path, before, timeout=30):
    """Until the proxy (whose log had `before` starts) is up, discovery included."""
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(log_path) and open(log_path).read().count("Waiting for connections") > before:
            return
        time.sleep(0.1)
    raise TimeoutError(f"the proxy didn't start: see {log_path}")

def start_proxy(port=PORT):
    path = f"{WORK}/proxy.log"
    before = open(path).read().count("Waiting for connections") if os.path.exists(path) else 0
    log = open(path, "a")
    env = dict(os.environ, APPLE2_BRIDGE_DIR=WORK, APPLE2_PROXY_CONTROL_DIR=WORK,
               APPLE2_DISCOVERY_PORT=str(DISCOVERY))
    proc = subprocess.Popen([str(ROOT / ".venv/bin/python"), "-u", str(ROOT / "proxy/unified_proxy.py"),
                             "--port", str(port)],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            cwd=str(ROOT / "proxy"), env=env, start_new_session=True)
    wait_until_listening(path, before)
    return proc


def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=10)


def start_apple():
    if os.path.exists(SOCK):
        os.remove(SOCK)
    proc = subprocess.Popen([str(ROOT / "bobbin/src/bobbin"), "--simple", "--remain",
                             "--control-socket", SOCK, "-m", "enhanced", "--disk", DISK, "--uthernet2"],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True,
                            env=dict(os.environ, BOBBIN_U2_UDP_PORT=str(DISCOVERY)))
    sock = BobbinControlSocket(SOCK)
    for _ in range(100):
        if os.path.exists(SOCK) and sock.connect(timeout=1):
            break
        time.sleep(0.05)
    return proc, sock


def screen(sock):
    return "\n".join(line.rstrip() for line in sock.read_screen())


def wait_for(sock, text, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        if text in screen(sock):
            return True
        time.sleep(0.3)
    return False


def saved_config():
    """CLAUDECONF on the disk image: (ip, port) or None."""
    data, _ = m.extract_file(bytearray(open(DISK, "rb").read()), "CLAUDECONF")
    if not data or len(data) < 8 or data[7] != 0xA2:
        return None
    return ".".join(str(b) for b in data[:4]), data[4] | data[5] << 8


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    shutil.copy(ROOT / "disks/agent_contiguous.dsk", DISK)
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))

    proxy = apple = None
    try:
        # 1. Fresh disk finds the proxy by itself and remembers it
        proxy = start_proxy()
        apple, sock = start_apple()
        ok = wait_for(sock, "AGENT>", 60)
        check("fresh disk: finds the proxy on its port and goes straight to AGENT>",
              ok and "Connection from" in open(f"{WORK}/proxy.log").read(), screen(sock))
        stop(apple)
        apple = None
        check("fresh disk: saved the address it found", saved_config() == ("192.168.65.1", PORT), saved_config())

        # 2. Saved address works without discovery (the discovery port taken, nobody answers)
        stop(proxy)
        blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        blocker.bind(("0.0.0.0", DISCOVERY))
        try:
            proxy = start_proxy()
            apple, sock = start_apple()
            ok = wait_for(sock, "AGENT>", 60)
            check("reboot without discovery: connects with the saved address",
                  ok and open(f"{WORK}/proxy.log").read().count("Connection from") >= 2, screen(sock))
        finally:
            blocker.close()

        # 4. /SETIP and /PORT are saved (do this before the proxy-less boot)
        sock.inject_keys("/SETIP 192.168.65.1\r")
        time.sleep(2)
        sock.inject_keys("/PORT 6598\r")
        time.sleep(3)
        stop(apple)
        apple = None
        check("/SETIP + /PORT saved to disk", saved_config() == ("192.168.65.1", 6598), saved_config())

        # 3. No proxy at boot: helpful message; starting it later just works
        stop(proxy)
        proxy = None
        apple, sock = start_apple()
        ok = wait_for(sock, "PRESS ANY KEY", 90)
        sc = screen(sock)
        check("no proxy at boot: says how to start it", ok and "./PROXY.SH START" in sc, sc)
        sock.inject_keys("\r")
        wait_for(sock, "AGENT>", 10)
        proxy = start_proxy()
        sock.inject_keys("/VERSIONS\r")        # forwarded to the proxy, no Claude call
        ok = wait_for(sock, "PROGRAMS", 60)
        check("proxy started later: next message finds it and goes through", ok, screen(sock))
        stop(apple)
        apple = None
        check("...and the address it found is saved", saved_config() == ("192.168.65.1", PORT), saved_config())
    finally:
        stop(apple)
        stop(proxy)

    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
