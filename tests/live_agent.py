#!/usr/bin/env python3
"""
Live end-to-end run: a real request to Claude, start to finish, on an
emulated Apple II - the same path a user takes.

Boots the agent disk in Bobbin, types the request at AGENT>, records the
screen as Claude works (progress, code, previews), waits for READY, runs the
program, saves screenshots, presses ESC and checks we're back at the agent.

Needs a proxy listening where the agent connects (by default the agent disk
points at 192.168.64.1:6502 = this Mac's port 6502; --port writes a
CLAUDECONF to a disk copy for another port). Each run costs a real request.

    .venv/bin/python tests/live_agent.py "make a breakout game in hi-res" --out /tmp/a2live
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from apple2_mcp.control_socket import BobbinControlSocket  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("request")
    ap.add_argument("--out", default="/tmp/a2live")
    ap.add_argument("--port", type=int, default=None,
                    help="proxy port (default 6502, or 6596 with --start-proxy)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds to wait for READY")
    ap.add_argument("--keys", default="", help="keys to send while the program runs (\\r, \\x1b ok)")
    ap.add_argument("--stop-after", type=float, default=None,
                    help="press ESC this many seconds in and check Claude stops cleanly")
    ap.add_argument("--start-proxy", action="store_true",
                    help="run this checkout's proxy on --port (own control dir; found by discovery)")
    ap.add_argument("--display", choices=("40", "40L", "80"), default="40")
    ap.add_argument("--then", action="append", default=[],
                    help="a follow-up request after the first program (repeatable)")
    ap.add_argument("--play", type=float, default=0,
                    help="seconds of random game keys once it runs, watching for crashes and freezes")
    args = ap.parse_args()
    if args.port is None:
        args.port = 6596 if args.start_proxy else 6502

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sock_path = "/tmp/a2live.sock"          # short: Unix socket path limit
    disk = out / "agent.dsk"
    shutil.copy(ROOT / "disks/agent_contiguous.dsk", disk)
    if args.port != 6502 or args.display != "40":
        conf = out / "CLAUDECONF"
        display = {"40": 0, "40L": 1, "80": 2}[args.display]
        # watchdog off: unthrottled Bobbin makes a real Claude think look like minutes of silence
        conf.write_bytes(bytes([192, 168, 64, 1, args.port & 0xFF, args.port >> 8, 1, 0xA2, display, 0]))
        subprocess.run([sys.executable, str(ROOT / "tools/prodos.py"), "add", str(disk), str(conf),
                        "CLAUDECONF", "BIN", "0300"], check=True, capture_output=True)

    proxy = None
    if args.start_proxy:
        env = dict(os.environ, APPLE2_BRIDGE_DIR="/tmp/a2live_bridge", APPLE2_PROXY_CONTROL_DIR=str(out),
                   APPLE2_DISCOVERY_PORT=str(args.port + 10000))   # its own discovery channel
        os.makedirs("/tmp/a2live_bridge", exist_ok=True)
        proxy = subprocess.Popen([str(ROOT / ".venv/bin/python"), "-u", str(ROOT / "proxy/unified_proxy.py"),
                                  "--port", str(args.port)], stdin=subprocess.DEVNULL,
                                 stdout=open(out / "proxy.log", "w"), stderr=subprocess.STDOUT,
                                 cwd=str(ROOT / "proxy"), env=env, start_new_session=True)
        t = time.time()                      # until it's listening, discovery included
        while "Waiting for connections" not in (out / "proxy.log").read_text() and time.time() - t < 30:
            time.sleep(0.1)

    if os.path.exists(sock_path):
        os.remove(sock_path)
    apple = subprocess.Popen([str(ROOT / "bobbin/src/bobbin"), "--simple", "--remain", "--control-socket",
                              sock_path, "-m", "enhanced", "--disk", str(disk), "--uthernet2"],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True,
                             env=dict(os.environ, BOBBIN_U2_UDP_PORT=str(args.port + 10000)))
    s = BobbinControlSocket(sock_path)
    for _ in range(100):
        if os.path.exists(sock_path) and s.connect(timeout=1):
            break
        time.sleep(0.05)

    log = open(out / "screens.txt", "w")
    last = [None]
    shots = [0]

    def screen():
        return "\n".join(l.rstrip() for l in s.read_screen())

    def record(tag=""):
        sc = screen()
        if sc != last[0]:
            log.write(f"\n===== {time.strftime('%H:%M:%S')} {tag}\n{sc}\n")
            log.flush()
            last[0] = sc
        return sc

    def shot(name):
        sw = s.get_softswitches()
        sw = sw.get("switches", sw)
        if sw.get("text"):
            return None
        shots[0] += 1
        ppm = out / f"{shots[0]:02d}_{name}.ppm"
        s.capture_hgr(str(ppm), page=2 if sw.get("page2") else 1, color=True)
        try:
            from PIL import Image
            png = ppm.with_suffix(".png")
            Image.open(ppm).save(png)
            ppm.unlink()
            return png
        except Exception:
            return ppm

    last_shot_frame = [None]

    def wait(text, timeout, tag):
        t = time.time()
        while time.time() - t < timeout:
            sc = record(tag)
            if text in sc:
                return True
            if not sw_text():
                f = frame()
                if f != last_shot_frame[0]:         # a new picture, not the same preview again
                    last_shot_frame[0] = f
                    shot(tag)
            time.sleep(1.0)
        return False

    def sw_text():
        sw = s.get_softswitches()
        return sw.get("switches", sw).get("text", True)

    def frame():
        """Something that changes when the picture does: the whole hi-res page
        (or the text screen), plus the text lines of a mixed screen."""
        sw = s.get_softswitches()
        sw = sw.get("switches", sw)
        if sw.get("text", True):
            return screen()
        if not sw.get("hires"):
            base = 0x0800 if sw.get("page2") else 0x0400
            return bytes(sum((s.peek(base + i, 256) for i in range(0, 0x400, 256)), [])) + screen().encode()
        tmp = out / "frame.ppm"
        s.capture_hgr(str(tmp), page=2 if sw.get("page2") else 1, color=False)
        return tmp.read_bytes() + (screen().encode() if sw.get("mixed") else b"")

    def play(seconds):
        """Random game keys (never ESC, Q or P); report crashes, exits, freezes."""
        import random
        rng = random.Random(6502)
        keys = ["\x08", "\x15", "\x0b", "\x0a", " ", " ", "A", "D", "W", "S", "Z", "X",
                "J", "K", "L", "I", "M", "1", "\r"]
        report = {"seconds": seconds, "ended": None, "longest_still_s": 0, "shots": []}
        t = time.time()
        last_change, last_frame, last_shot = time.time(), None, 0
        while time.time() - t < seconds:
            for _ in range(4):
                s.inject_keys(chr(ord(rng.choice(keys)) | 0x80))
                time.sleep(0.25)
            sc = record("playing")
            if "PROGRAM HIT A PROBLEM" in sc:
                report["ended"] = "crashed back to the agent: " + " / ".join(
                    l for l in sc.splitlines() if "BRK" in l or "ERROR" in l or "FIX" in l)
                break
            if "AGENT>" in sc:
                report["ended"] = "left on its own (no ESC sent)"
                break
            if any(l.startswith("?") and "ERROR" in l for l in sc.splitlines()):
                report["ended"] = "BASIC error: " + next(l for l in sc.splitlines() if "ERROR" in l)
                break
            f = frame()
            if f != last_frame:
                last_frame, last_change = f, time.time()
            still = time.time() - last_change
            report["longest_still_s"] = max(report["longest_still_s"], round(still))
            if time.time() - last_shot > 15:
                p = shot(f"play{int(time.time() - t):03d}")
                if p:
                    report["shots"].append(str(p))
                last_shot = time.time()
        report["pc"] = f"${s.get_cpu_state()['pc']:04X}"
        return report

    result = {"request": args.request}
    t0 = time.time()
    try:
        ok = wait("AGENT>", 90, "boot")       # connected boots go straight in
        s.inject_keys(args.request + "\r")
        if args.stop_after is not None:
            t_stop = time.time() + args.stop_after
            while time.time() < t_stop:
                record("working")
                time.sleep(1.0)
            s.inject_keys("\x1b")
            time.sleep(1.5)
            result["stopping_shown"] = "STOPPING" in record("esc")
            result["stopped"] = wait("STOPPED.", 120, "stopping")
            result["back_at_prompt"] = wait("READY", 30, "after stop")
            s.inject_keys("/VERSIONS\r")       # the session still works afterwards
            result["works_after"] = wait("PROGRAM", 60, "after stop")
            # ...and Claude takes the next request (the stopped one left the
            # conversation on a user turn)
            s.inject_keys("make a program that prints HELLO forever. esc quits\r")
            result["next_request_ok"] = wait("PRESS RETURN TO RUN", 600, "next request")
            print(result)                       # (stopping_shown can flash by too fast to catch)
            return 0 if all(result[k] for k in ("stopped", "works_after", "next_request_ok")) else 1
        def build_and_run(tag):
            r = {}
            t1 = time.time()
            r["ready"] = wait("PRESS RETURN TO RUN", args.timeout, f"{tag} working")   # status line
            r["ready_after_s"] = round(time.time() - t1)
            if not r["ready"]:
                return r
            s.inject_keys("\r")
            time.sleep(4)
            record(f"{tag} running")
            r["program_screen"] = str(shot(f"{tag}_running") or "text mode")
            for k in args.keys.encode().decode("unicode_escape"):
                s.inject_keys(chr(ord(k) | 0x80))      # the //e's own codes (LF = down arrow)
                time.sleep(0.15)
            time.sleep(2)
            record(f"{tag} after keys")
            shot(f"{tag}_after_keys")
            if args.play:
                r["play"] = play(args.play)
                if r["play"]["ended"]:
                    record(f"{tag} ended")
                    return r
            s.inject_keys("\x1b")
            r["esc_back"] = wait("WELCOME BACK", 15, f"{tag} esc")
            record(f"{tag} back")
            return r

        result["first"] = build_and_run("first")
        for i, follow_up in enumerate(args.then):
            if not result[list(result)[-1]].get("esc_back"):
                break
            s.inject_keys(follow_up + "\r")
            result[f"then{i + 1}"] = dict(request=follow_up, **build_and_run(f"then{i + 1}"))
    finally:
        apple.terminate()
        if proxy:
            proxy.terminate()
            try:
                proxy.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proxy.kill()
            # ...and Claude's test emulator, which a proxy that died hard leaves behind
            held = subprocess.run(["lsof", "-t", "/tmp/a2live_bridge/bobbin_bridge.sock"],
                                  capture_output=True, text=True).stdout.split()
            for pid in set(held):
                subprocess.run(["kill", pid])
        log.close()
    print(result)
    print(f"screens: {out / 'screens.txt'}")
    runs = [v for k, v in result.items() if isinstance(v, dict)]
    ok = len(runs) == 1 + len(args.then) and all(r.get("ready") and r.get("esc_back") for r in runs)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
