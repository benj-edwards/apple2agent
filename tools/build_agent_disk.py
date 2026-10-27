#!/usr/bin/env python3
"""
Build the agent boot disk in the way that boots on a real Apple IIe.

Start from a disk that real machine has booted - disks/base_jan19.dsk, the
January agent disk (ProDOS 1.9 + BASIC.SYSTEM) with the old agent files
removed - and add AGENT.SYSTEM with AppleCommander, the tool that disk was
made with. Nothing is written by hand: building ProDOS structures from
scratch (tools/make_agent_disk.py, with the ProDOS 2.4 kernel) gave disks
that Bobbin booted and the real //e crashed on at 2002-.

Then check what ProDOS will see: AGENT.SYSTEM is the first .SYSTEM file in
the directory (so it boots, not BASIC.SYSTEM) and reads back byte for byte.

Usage:
    python3 tools/build_agent_disk.py [output.dsk] [--test]

AppleCommander: tools/ac.jar or $AC_JAR.
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "disks", "base_jan19.dsk")
AGENT = os.path.join(ROOT, "build", "AGENT.SYSTEM")

# ProDOS block b of a track = these two sectors of a DOS-order image
BLOCK_SECTORS = [(0, 14), (13, 12), (11, 10), (9, 8), (7, 6), (5, 4), (3, 2), (1, 15)]


def find_ac_jar():
    for path in (os.environ.get("AC_JAR"), os.path.join(ROOT, "tools", "ac.jar")):
        if path and os.path.exists(path):
            return path
    sys.exit("AppleCommander not found: put ac.jar in tools/ or set AC_JAR")


def ac(jar, *args, stdin=None):
    r = subprocess.run(["java", "-jar", jar, *args], stdin=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"AppleCommander {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    return r.stdout


def block(img, n):
    t, b = divmod(n, 8)
    s1, s2 = BLOCK_SECTORS[b]
    return img[(t * 16 + s1) * 256:(t * 16 + s1 + 1) * 256] + img[(t * 16 + s2) * 256:(t * 16 + s2 + 1) * 256]


def directory(img):
    """Root directory entries in order: (name, storage type, file type, key block, eof)."""
    out, blk, first = [], 2, True
    while blk:
        d = block(img, blk)
        for i in range(1 if first else 0, 13):
            e = d[4 + i * 39:4 + (i + 1) * 39]
            if e[0] >> 4:
                out.append((e[1:1 + (e[0] & 15)].decode(), e[0] >> 4, e[0x10],
                            int.from_bytes(e[0x11:0x13], "little"), int.from_bytes(e[0x15:0x18], "little")))
        first = False
        blk = int.from_bytes(d[2:4], "little")
    return out


def read_file(img, storage, key, eof):
    if storage == 1:
        return block(img, key)[:eof]
    if storage != 2:
        raise ValueError("AGENT.SYSTEM should be a sapling file")
    idx = block(img, key)
    ptrs = [idx[i] | idx[256 + i] << 8 for i in range((eof + 511) // 512)]
    return b"".join(block(img, p) if p else bytes(512) for p in ptrs)[:eof]


def check(path, agent):
    img = open(path, "rb").read()
    entries = directory(img)
    systems = [e[0] for e in entries if e[2] == 0xFF and e[0].endswith(".SYSTEM")]
    if not systems or systems[0] != "AGENT.SYSTEM":
        sys.exit(f"ProDOS would boot {systems[0] if systems else 'nothing'}, not AGENT.SYSTEM: {systems}")
    name, storage, ftype, key, eof = next(e for e in entries if e[0] == "AGENT.SYSTEM")
    if read_file(img, storage, key, eof) != agent:
        sys.exit("AGENT.SYSTEM on the disk doesn't match build/AGENT.SYSTEM")
    print("   " + ", ".join(e[0] for e in entries) + " - AGENT.SYSTEM boots first and reads back exactly")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else os.path.join(ROOT, "disks", "agent_contiguous.dsk")
    if not os.path.exists(AGENT):
        sys.exit("build/AGENT.SYSTEM is missing: make agent")
    agent = open(AGENT, "rb").read()
    jar = find_ac_jar()

    tmp = out + ".tmp"
    shutil.copy(BASE, tmp)
    with open(AGENT, "rb") as f:
        ac(jar, "-p", tmp, "AGENT.SYSTEM", "SYS", "0x2000", stdin=f)
    check(tmp, agent)
    os.replace(tmp, out)
    print(f"   {out}")

    if "--test" in sys.argv:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import make_agent_disk
        if not make_agent_disk.test_boot(out):
            sys.exit("boot test FAILED")


if __name__ == "__main__":
    main()
