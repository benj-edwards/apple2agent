#!/usr/bin/env python3
"""
What the Apple II's screen shows - a fake proxy sends known text; no API.

  - the log: every row holds exactly one line that was sent (no leftovers
    from longer lines, no lines run together), across several page wraps
  - the input line: long input scrolls sideways intact, and clears once sent

    .venv/bin/python tests/e2e_display.py
"""

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "proxy"))
from apple2_mcp.control_socket import BobbinControlSocket  # noqa: E402
from a2p_protocol import A2PProtocol, PacketType  # noqa: E402

WORK = "/tmp/a2disp"
SOCK = f"{WORK}/apple.sock"
PORT = 6597
DISK = f"{WORK}/agent.dsk"


def lines_to_send():
    out = []
    for i in range(1, 48):
        if i % 3 == 1:
            out.append(f"LINE {i:02d} " + "LONG LONG LONG LONG LONG LONG"[:31])
        elif i % 3 == 2:
            out.append(f"LINE {i:02d} SHORT")
        else:
            out.append(f"LINE {i:02d} MEDIUM LENGTH TEXT")
    return out


class FakeProxy(threading.Thread):
    """Accepts the Apple II, answers its first CHAT with lines_to_send()."""

    def __init__(self):
        super().__init__(daemon=True)
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", PORT))
        self.srv.listen(2)
        self.chats = []

    def run(self):
        while True:                         # the agent reconnects after giving up
            try:
                conn, _ = self.srv.accept()
            except OSError:                 # closed at the end of the run
                return
            # each connection on its own thread: a stalled one stays open
            # while the watchdog's reconnect comes in
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def serve(self, conn):
        proto = A2PProtocol()
        while True:
            try:
                data = conn.recv(4096)
            except OSError:
                return
            if not data:
                return
            for pkt in proto.decode_stream(data):     # it buffers partial packets
                if pkt.ptype == PacketType.CHAT:
                    chat = pkt.data.decode("ascii", "replace")
                    self.chats.append(chat)
                    if chat.startswith("THE QUICK"):
                        for line in lines_to_send():
                            conn.sendall(proto.encode_response(line + "\n", is_final=False))
                            time.sleep(0.05)
                        conn.sendall(proto.encode_status("DONE"))
                    elif chat.startswith("PAGE"):
                        for line in ("OLD 1", "OLD 2", "OLD 3", "\f", "NEW 1", "NEW 2"):
                            conn.sendall(proto.encode_response(line if line == "\f" else line + "\n",
                                                               is_final=False))
                            time.sleep(0.05)
                        conn.sendall(proto.encode_status("DONE"))
                    elif chat.startswith("DAMAGED") or chat == "/RERUN":
                        # a small program; the first copy has one bad packet
                        send_program(conn, proto, damaged=chat.startswith("DAMAGED"))
                        conn.sendall(proto.encode_status("DONE"))
                    elif chat.startswith("STALL"):
                        conn.sendall(proto.encode_response("BEFORE THE STALL\n", is_final=False))
                        # ...then silence, with the connection left open
                    elif chat == "/RESYNC":
                        conn.sendall(proto.encode_response("RESYNCED\n", is_final=False))
                        conn.sendall(proto.encode_status("DONE"))
                    elif chat.startswith("HANG"):
                        conn.sendall(proto.encode_status("WORKING..."))   # ...and never DONE
                    elif chat == "/STOP":
                        pass                                              # pretend we're stuck
                    else:
                        conn.sendall(proto.encode_status("DONE"))


def send_program(conn, proto, damaged):
    """DEPLOY + LOADs + RUN of a tiny BASIC program, one LOAD's checksum broken if damaged."""
    import deploy
    prog = deploy.build_basic('10 PRINT "THE GOOD COPY"\n20 GOTO 20\n', "TINY", True)
    conn.sendall(proto.encode_deploy(1, 0))                 # aux (EXCHANGE), program
    addr, data = prog.chunks[0]
    for i, off in enumerate(range(0, len(data), 126)):
        pkt = bytearray(proto.encode_load(addr + off, data[off:off + 126]))
        if damaged and i == 0:
            pkt[-1] ^= 0xFF                                 # the checksum byte
        conn.sendall(bytes(pkt))
    conn.sendall(proto.encode_run(prog.descriptor()))


def make_disk(watchdog=0):
    """watchdog: the stall watchdog's seconds (0 = off; emulated seconds go by
    ~40x faster than real ones here)."""
    shutil.copy(ROOT / "disks/agent_contiguous.dsk", DISK)
    conf = f"{WORK}/CLAUDECONF"
    with open(conf, "wb") as f:
        f.write(bytes([192, 168, 64, 1, PORT & 0xFF, PORT >> 8, 1, 0xA2, 0, watchdog]))
    subprocess.run([sys.executable, str(ROOT / "tools/prodos.py"), "add", DISK, conf, "CLAUDECONF", "BIN", "0300"],
                   check=True, capture_output=True)


def main():
    ok = True
    for mode in ("40", "80", "watchdog"):
        print(f"--- {mode}" + (" columns" if mode != "watchdog" else " (a reply that stalls)"))
        ok = run(mode) and ok
    return 0 if ok else 1


def run(mode):
    global PORT
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    make_disk(watchdog=2 if mode == "watchdog" else 0)
    proxy = FakeProxy()
    proxy.start()
    apple = subprocess.Popen([str(ROOT / "bobbin/src/bobbin"), "--simple", "--remain", "--control-socket", SOCK,
                              "-m", "enhanced", "--disk", DISK, "--uthernet2"],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True,
                             env=dict(os.environ, BOBBIN_U2_UDP_PORT=str(PORT + 10000)))  # no discovery answers
    s = BobbinControlSocket(SOCK)
    for _ in range(100):
        if os.path.exists(SOCK) and s.connect(timeout=1):
            break
        time.sleep(0.05)
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))

    def rows():
        return [l.rstrip() for l in s.read_screen()]

    def wait_for(text, timeout=60):
        t = time.time()
        while time.time() - t < timeout:
            if any(text in r for r in rows()):
                return True
            time.sleep(0.3)
        return False

    try:
        ok = wait_for("AGENT>", 60)
        check("boots to AGENT> with the fake proxy", ok, "\n".join(rows()))
        if mode == "watchdog":
            s.inject_keys("STALL\r")
            ok = wait_for("RESYNCED", 90)
            check("a reply that goes silent: the watchdog reconnects and asks for /RESYNC",
                  ok and "/RESYNC" in proxy.chats, "\n".join(rows()) + f"\nchats: {proxy.chats}")
            time.sleep(2)
            check("...and the wait ends normally", any(r.startswith("AGENT>") for r in rows()) and
                  not any("CONNECTION LOST" in r for r in rows()), "\n".join(rows()))
            print(f"{sum(results)}/{len(results)} passed")
            return all(results)
        if mode == "80":
            s.inject_keys("/DISPLAY 80\r")
            time.sleep(4)
            check("80 columns: rows are 80 wide and the screen is clean",
                  len(s.read_screen()[0]) == 80 and all(
                      all(c == " " or c.isprintable() for c in r) for r in rows()) and
                  not any("@ @" in r for r in rows()), "\n".join(rows()))

        # Input line: a long request scrolls sideways intact; the line holds
        # 239 characters (a ] line's worth), the rest beeps
        typed = ("THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG AND THEN 0123456789 ABCDEFG " * 4)[:250]
        kept = typed[:239]
        for ch in typed:
            s.inject_keys(ch)
            time.sleep(0.02)
        time.sleep(1)
        inp = [r for r in rows() if r.startswith("AGENT>")]
        shown = inp[0][len("AGENT>"):].strip() if inp else ""
        check("long input scrolls sideways intact", bool(shown) and kept.rstrip().endswith(shown) and
              "  " not in shown, f"input row: {inp}")

        s.inject_keys("\r")
        ok = wait_for("LINE 47", 60)
        time.sleep(3)
        sc = rows()
        check("all lines arrive", ok, "\n".join(sc))
        sent = set(lines_to_send())
        log = [r.strip() for r in sc[1:21] if r.strip()]
        bad = [r for r in log if r.startswith("LINE") and r not in sent]
        check("every log row is exactly one line that was sent", not bad and log,
              "bad rows:\n" + "\n".join(bad) + "\n--- screen:\n" + "\n".join(sc))
        nums = [int(r[5:7]) for r in log if r.startswith("LINE") and r in sent]
        check("log rows are in order", nums == sorted(nums) and nums and nums[-1] == 47, nums)
        inp = [r for r in sc if r.startswith("AGENT>")]
        check("input line is cleared after sending", inp and inp[-1].strip() == "AGENT>", f"input row: {inp}")
        check("the proxy got the whole 239-character message", kept.strip() in [c.strip() for c in proxy.chats],
              proxy.chats)

        # ESC while waiting: first asks the proxy to stop, second stops waiting
        s.inject_keys("HANG ON\r")
        time.sleep(3)
        s.inject_keys("\x1b")
        time.sleep(2)
        check("ESC while waiting sends /STOP", "/STOP" in proxy.chats, proxy.chats)
        check("...and says so", any("STOPPING CLAUDE" in r for r in rows()), "\n".join(rows()))
        s.inject_keys("\x1b")
        ok = wait_for("STOPPED WAITING", 10)
        check("ESC again gives up waiting", ok, "\n".join(rows()))
        s.inject_keys("AFTER\r")
        time.sleep(3)
        check("the prompt works again afterwards", proxy.chats[-1] == "AFTER", proxy.chats)
        s.inject_keys("PAGE\r")
        wait_for("NEW 2", 20)
        time.sleep(1)
        log = [r.rstrip() for r in rows()[1:21]]
        check("a form feed starts a fresh page of the log", log[:3] == ["NEW 1", "NEW 2", ""] and
              not any(r.startswith("OLD") for r in log), "\n".join(rows()))
        s.inject_keys("DAMAGED\r")
        ok = wait_for("PRESS RETURN TO RUN", 30)
        check("a deploy with a bad packet isn't run: a fresh copy comes, then READY",
              ok and "/RERUN" in proxy.chats, "\n".join(rows()) + f"\nchats: {proxy.chats[-4:]}")
        s.inject_keys("\r")
        ok = wait_for("THE GOOD COPY", 15)
        check("...and the fresh copy is the one that runs", ok, "\n".join(rows()))
        s.inject_keys("\x1b")                  # ESC at the program's ] / loop: back to the agent
        wait_for("AGENT>", 15)
        s.reset(cold=False)                     # (the program loops: Ctrl-Reset comes home too)
        wait_for("WELCOME BACK", 15)
        s.inject_keys("make it Faster\r")
        time.sleep(3)
        want = "make it Faster" if mode == "80" else "MAKE IT FASTER"
        check(f"a request goes as typed on a mixed-case screen, uppercase on 40U ({want!r})",
              proxy.chats[-1] == want, proxy.chats[-3:])
    finally:
        apple.terminate()
        proxy.srv.close()

    print(f"{sum(results)}/{len(results)} passed")
    return all(results)


if __name__ == "__main__":
    sys.exit(main())
