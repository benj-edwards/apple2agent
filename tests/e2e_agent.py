#!/usr/bin/env python3
"""
End-to-end regression for deploy / launch / return - no API calls.

Boots the real AGENT.SYSTEM disk in Bobbin (Uthernet II), starts the proxy,
and drives the Apple II through its control socket: /SEND programs from
programs/, run them, and come back every possible way.

    .venv/bin/python tests/e2e_agent.py

Needs: build/ + disks/agent_contiguous.dsk (make disk), port 6599 free.
It boots a copy of the disk whose CLAUDECONF points the agent at 6599, so a
proxy you have running on 6502 is never touched.
Runs outside any sandbox that blocks Unix sockets or local listening.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from apple2_mcp.control_socket import BobbinControlSocket  # noqa: E402

WORK = "/tmp/a2e2e"                 # short: Unix socket paths max out at 104 chars
SOCK = f"{WORK}/apple.sock"
PORT = int(os.environ.get("E2E_PORT", "6599"))
DISCOVERY = PORT + 10000             # this test's own discovery channel (Bobbin + proxy)
# E2E_REAL_SPEED=1: run the Apple II at a real 1 MHz (Bobbin --simple is
# otherwise unthrottled) to see the times a real machine will take
REAL_SPEED = os.environ.get("E2E_REAL_SPEED") == "1"
SLOW = 8 if REAL_SPEED else 1
DISK = f"{WORK}/agent.dsk"


def make_disk():
    """The agent disk plus a CLAUDECONF: proxy 192.168.64.1 (Bobbin's localhost) on PORT."""
    shutil.copy(os.environ.get("E2E_DISK", ROOT / "disks/agent_contiguous.dsk"), DISK)
    conf = f"{WORK}/CLAUDECONF"
    display = {"40": 0, "40L": 1, "80": 2}[os.environ.get("E2E_DISPLAY", "40")]
    with open(conf, "wb") as f:     # IP, port (LE), model (Opus), magic, display, watchdog
        # watchdog off: Bobbin runs unthrottled here, so 20 emulated seconds of
        # silence pass in half a real second (e2e_display tests the watchdog)
        f.write(bytes([192, 168, 64, 1, PORT & 0xFF, PORT >> 8, 1, 0xA2, display, 0]))
    subprocess.run([sys.executable, str(ROOT / "tools/prodos.py"), "add", DISK, conf, "CLAUDECONF", "BIN", "0300"],
                   check=True, capture_output=True)



def wait_until_listening(log_path, before, timeout=30):
    """Until the proxy (whose log had `before` starts) is up, discovery included."""
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(log_path) and open(log_path).read().count("Waiting for connections") > before:
            return
        time.sleep(0.1)
    raise TimeoutError(f"the proxy didn't start: see {log_path}")

def start_proxy():
    path = f"{WORK}/proxy.log"
    before = open(path).read().count("Waiting for connections") if os.path.exists(path) else 0
    log = open(path, "a")                    # main() clears it once
    env = dict(os.environ, APPLE2_BRIDGE_DIR=WORK, APPLE2_PROXY_CONTROL_DIR=WORK,
               APPLE2_DISCOVERY_PORT=str(DISCOVERY))
    proc = subprocess.Popen([str(ROOT / ".venv/bin/python"), "-u", str(ROOT / "proxy/unified_proxy.py"),
                             "--port", str(PORT)],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            cwd=str(ROOT / "proxy"), env=env, start_new_session=True)
    wait_until_listening(path, before)
    return proc


def start_apple():
    if os.path.exists(SOCK):
        os.remove(SOCK)
    proc = subprocess.Popen([str(ROOT / "bobbin/src/bobbin"), "--simple", "--remain",
                             "--control-socket", SOCK, "-m", "enhanced",
                             "--disk", DISK, "--uthernet2"] + (["--no-turbo"] if REAL_SPEED else []),
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True,
                            env=dict(os.environ, BOBBIN_U2_UDP_PORT=str(DISCOVERY)))
    sock = BobbinControlSocket(SOCK)
    for _ in range(50):
        time.sleep(0.2)
        if os.path.exists(SOCK) and sock.connect(timeout=1):
            break
    return proc, sock


def screen(sock):
    return "\n".join(line.rstrip() for line in sock.read_screen())


def wait_for(sock, text, timeout=30):
    timeout *= SLOW
    start = time.time()
    while time.time() - start < timeout:
        if text in screen(sock):
            return screen(sock)
        time.sleep(0.3)
    raise TimeoutError(f"never saw {text!r}:\n{screen(sock)}")


def nap(seconds):
    time.sleep(seconds * (3 if REAL_SPEED else 1))


def switches(sock):
    sw = sock.get_softswitches()
    return sw.get("switches", sw)


def main():
    os.makedirs(WORK, exist_ok=True)
    if os.path.exists(f"{WORK}/proxy.log"):
        os.remove(f"{WORK}/proxy.log")
    make_disk()
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))

    def typed(text):
        sock.inject_keys(text + "\r")

    def send_and_run(name):
        typed("/CLEAR")
        nap(0.5)
        typed(f"/SEND {name}")
        wait_for(sock, "IS READY", 60)
        sock.inject_keys("\r")

    proxy = start_proxy()
    apple, sock = start_apple()
    try:
        # A connected boot goes straight to AGENT> - no key needed
        wait_for(sock, "AGENT>", 60)
        log = open(f"{WORK}/proxy.log").read()
        check("boot broadcast found the proxy (discovery) and went straight in",
              "[Discovery]" in log and f"told it port {PORT}" in log, log[-600:])

        send_and_run("TESTHGR.BAS")
        nap(3)
        sw = switches(sock)
        check("HGR program shows hi-res", sw.get("hires") and not sw.get("text"), sw)
        sock.inject_keys("\x1b")
        nap(2.5)
        check("ESC -> & returns to the agent", "WELCOME BACK" in screen(sock), screen(sock))

        typed("/RUN")
        nap(3)
        check("/RUN replays", switches(sock).get("hires"), switches(sock))
        sock.inject_keys("\x1b")
        nap(2.5)
        check("back after /RUN", "WELCOME BACK" in screen(sock), screen(sock))

        send_and_run("TESTML.S")
        nap(2.5)
        pc = sock.get_cpu_state()["pc"]
        check("machine code runs at $4000", 0x4000 <= pc < 0x4100, hex(pc))
        sock.reset(cold=False)
        nap(2.5)
        check("Ctrl-Reset returns", "WELCOME BACK" in screen(sock), screen(sock))

        # /RUN gives machine code that changed itself above $6000 a fresh copy
        send_and_run("HIGHML.S")
        nap(2)
        first = sock.read_screen()[0][:1]
        sock.inject_keys(" ")
        wait_for(sock, "WELCOME BACK", 30)
        typed("/RUN")
        nap(5)
        second = sock.read_screen()[0][:1]
        check("/RUN gives self-modifying code above $6000 a fresh copy",
              first == "1" and second == "1", (first, second, screen(sock)))
        sock.inject_keys(" ")
        wait_for(sock, "WELCOME BACK", 30)

        for i in range(3):
            typed("/CLEAR")
            nap(0.5)
            start = time.time()
            typed("/SEND BIGTEST.BAS")
            try:
                wait_for(sock, "IS READY", 60)
                check(f"28K deploy #{i + 1} ({time.time() - start:.1f}s)", True)
            except TimeoutError as e:
                check(f"28K deploy #{i + 1}", False, e)
                break
            if i < 2:
                sock.inject_keys("\x1b")
                nap(0.8)
        sock.inject_keys("\r")
        nap(4)
        check("28K program runs past $6000 to its end", "MADE IT TO THE END" in screen(sock), screen(sock))
        sock.inject_keys("\x1b")
        nap(3)
        check("back from the 28K program", "WELCOME BACK" in screen(sock), screen(sock))

        send_and_run("CRASHTST.S")
        nap(3)
        sc = screen(sock)
        check("BRK crash comes back with FIX", "PROGRAM HIT A PROBLEM" in sc and "BRK AT $0905" in sc, sc)
        sock.inject_keys("\x7f" * 60)
        nap(0.5)

        send_and_run("ERRTEST.BAS")
        nap(3)
        check("BASIC error stops at ]", "?UNDEF'D STATEMENT ERROR" in screen(sock), screen(sock))
        sock.inject_keys("\x1b")
        nap(2.5)
        sc = screen(sock)
        check("ESC at ] returns with FIX", "PROGRAM HIT A PROBLEM" in sc and "STATEMENT ERROR" in sc, sc)
        sock.inject_keys("\x7f" * 60)
        nap(0.5)

        # INPUT and GET go through the agent's keyboard hook too
        send_and_run("INPUTTST.BAS")
        nap(2)
        typed("ADA")
        nap(1)
        sock.inject_keys("Q")
        nap(1)
        rows = [r.rstrip() for r in sock.read_screen()]
        check("INPUT and GET in a program get the keys, with nothing left behind",
              rows[:3] == ["NAME? ADA", "HELLO ADA", "KEY Q"], "\n".join(rows))
        sock.inject_keys("\x1b")
        nap(2.5)
        check("...and ESC in the program's own GET is the program's", "WELCOME BACK" in screen(sock),
              screen(sock))

        # A program that only ever INPUTs (GETLN eats ESC) still has a way out
        send_and_run("INPUTESC.BAS")
        nap(2)
        typed("HELLO")
        nap(1)
        ok = "YOU SAID HELLO" in screen(sock)
        sock.inject_keys("\x1b")
        nap(2.5)
        check("ESC at a program's INPUT prompt comes back to the agent",
              ok and "WELCOME BACK" in screen(sock), screen(sock))

        # /EXIT: a working ] prompt
        typed("/EXIT")
        nap(1.5)
        typed("PRINT 6*7")
        nap(1)
        rows = [r.rstrip() for r in sock.read_screen()]
        check("/EXIT gives a ] prompt that runs BASIC", "]PRINT 6*7" in rows and "42" in rows and
              "}" not in screen(sock), "\n".join(rows))
        typed("&")
        nap(2.5)
        check("& goes back to the agent", "WELCOME BACK" in screen(sock), screen(sock))

        proxy.terminate()
        proxy.wait()
        nap(1)
        proxy = start_proxy()
        typed("/CLEAR")
        nap(0.4)
        typed("/VERSIONS")
        try:
            wait_for(sock, "PROGRAMS", 30)
            check("reconnects after a proxy restart", True)
        except TimeoutError as e:
            check("reconnects after a proxy restart", False, e)

        # 80 columns: the agent draws 80, programs get plain 40, and back
        def wide():
            rows = sock.read_screen()
            return switches(sock).get("80col") and len(rows[0]) == 80
        typed("/DISPLAY 80")
        try:
            wait_for(sock, "80 MIXED CASE", 30)
            check("/DISPLAY 80 switches to 80 columns", wide(), screen(sock))
        except TimeoutError as e:
            check("/DISPLAY 80 switches to 80 columns", False, e)
        send_and_run("TESTHGR.BAS")
        nap(3)
        sw = switches(sock)
        check("80 columns: the program gets plain hi-res", sw.get("hires") and not sw.get("80col"), sw)
        sock.inject_keys("\x1b")
        nap(2.5)
        check("80 columns: back in 80 columns", "WELCOME BACK" in screen(sock) and wide(), screen(sock))
        send_and_run("ERRTEST.BAS")
        nap(3)
        check("80 columns: the program's ] prompt is 40 columns",
              "?UNDEF'D STATEMENT ERROR" in screen(sock) and not switches(sock).get("80col"), screen(sock))
        sock.inject_keys("\x1b")
        nap(2.5)
        sc = screen(sock)
        check("80 columns: ESC at ] comes back with FIX",
              "PROGRAM HIT A PROBLEM" in sc and "FIX:" in sc and wide(), sc)
        sock.inject_keys("\x7f" * 80)
        nap(0.5)
        typed("/EXIT")
        nap(1.5)
        check("80 columns: /EXIT leaves plain 40 columns at ]",
              not switches(sock).get("80col") and "APPLESOFT BASIC" in screen(sock), screen(sock))
        typed("&")
        nap(2.5)
        check("80 columns: & comes back in 80 columns", "WELCOME BACK" in screen(sock) and wide(), screen(sock))
        sock.reset(cold=True)
        try:
            gone = time.time()
            while "AGENT>" in screen(sock) and time.time() - gone < 10:
                time.sleep(0.1)
            wait_for(sock, "AGENT>", 60)
            check("80 columns: the setting survives a reboot", wide(), screen(sock))
        except TimeoutError as e:
            check("80 columns: the setting survives a reboot", False, e)
    finally:
        apple.terminate()
        proxy.terminate()

    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
