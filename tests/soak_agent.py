#!/usr/bin/env python3
"""
Soak test: many deploy / run / return cycles in one session - no API calls.

Catches what a single pass can't: memory slowly corrupted, the connection
wearing out, deploys getting slower. Each cycle sends a workspace program
with /SEND, runs it, comes back (ESC, Ctrl-Reset or a crash), and checks the
agent still answers.

    .venv/bin/python tests/soak_agent.py [cycles]
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e2e_agent as e  # noqa: E402  (reuses its proxy, disk and Bobbin setup)


PROGRAMS = [
    ("TESTHGR.BAS", "esc"),
    ("TESTML.S", "reset"),
    ("BIGTEST.BAS", "esc"),
    ("TIMES.BAS", "esc"),
    ("CRASHTST.S", "crash"),
]


def main():
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    os.makedirs(e.WORK, exist_ok=True)
    e.make_disk()
    rng = random.Random(6502)
    proxy = e.start_proxy()
    apple, sock = e.start_apple()
    failures, times = [], []
    try:
        e.wait_for(sock, "AGENT>", 60)
        for i in range(cycles):
            name, back = rng.choice(PROGRAMS)
            sock.inject_keys("/CLEAR\r")
            time.sleep(0.4)
            if rng.random() < 0.3:                      # some long typing, then erase it
                junk = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789") for _ in range(rng.randint(40, 120)))
                sock.inject_keys(junk)
                time.sleep(0.3)
                sock.inject_keys("\x7f" * len(junk))
                time.sleep(0.3)
            t = time.time()
            sock.inject_keys(f"/SEND {name}\r")
            try:
                e.wait_for(sock, "IS READY", 60)
            except TimeoutError as ex:
                failures.append(f"cycle {i}: {name} never READY\n{ex}")
                break
            times.append(time.time() - t)
            sock.inject_keys("\r")
            time.sleep(3)
            if back == "esc":
                sock.inject_keys("\x1b")
                if name == "TIMES.BAS":
                    time.sleep(0.5)
                    sock.inject_keys("\x1b")
            elif back == "reset":
                sock.reset(cold=False)
            try:
                e.wait_for(sock, "AGENT>", 20)
                sc = e.screen(sock)
                if back == "crash":
                    ok = "PROGRAM HIT A PROBLEM" in sc
                    sock.inject_keys("\x7f" * 60)       # don't send the FIX: prefill
                    time.sleep(0.4)
                else:
                    ok = "WELCOME BACK" in sc
                if not ok:
                    failures.append(f"cycle {i}: {name} came back wrong:\n{sc}")
            except TimeoutError as ex:
                failures.append(f"cycle {i}: {name} never came back ({back})\n{ex}")
                break
            print(f"cycle {i + 1:2}/{cycles}: {name:12} {back:5} ready in {times[-1]:.1f}s", flush=True)

        sock.inject_keys("/CLEAR\r")
        time.sleep(0.4)
        sock.inject_keys("/VERSIONS\r")
        try:
            e.wait_for(sock, "PROGRAMS", 30)
        except TimeoutError as ex:
            failures.append(f"agent stopped answering at the end\n{ex}")
    finally:
        apple.terminate()
        proxy.terminate()

    if times:
        first, last = times[:5], times[-5:]
        print(f"\nREADY times: first {sum(first) / len(first):.1f}s, last {sum(last) / len(last):.1f}s, max {max(times):.1f}s")
    for f in failures:
        print("FAIL", f)
    print(f"{len(times)} cycles, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
