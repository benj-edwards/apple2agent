#!/usr/bin/env python3
"""
Make the agent diagnostic disk: the normal agent disk (same files in the same
blocks) plus DIAG.SYSTEM, listed first so ProDOS boots it.

DIAG.SYSTEM reads every block and compares it with checksums computed here,
then loads AGENT.SYSTEM the way ProDOS's launcher does and checks it, and
offers RETURN to start the agent. See asm/diag.s.

Usage:
    python3 tools/make_diag_disk.py [output.dsk]
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_agent_disk as m  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = b"DIAGTBL!"
ENTRY = 0x27


def checksum(data):
    """Same sum as diag.s: s1 += byte, s2 += s1, both mod 256."""
    s1 = s2 = 0
    for b in data:
        s1 = (s1 + b) & 0xFF
        s2 = (s2 + s1) & 0xFF
    return s1, s2


def build_base():
    """The normal agent disk, built exactly like make_agent_disk.py does."""
    template = bytearray(open(os.path.join(ROOT, "disks/ProDOS_2_4.dsk"), "rb").read())
    prodos, _ = m.extract_file(template, "PRODOS")
    basic, _ = m.extract_file(template, "BASIC.SYSTEM")
    agent = open(os.path.join(ROOT, "build/AGENT.SYSTEM"), "rb").read()
    disk = m.create_fresh_prodos_disk("AGENT")
    m.copy_blocks(template, disk, 0, 2)
    files = {"PRODOS": prodos, "AGENT.SYSTEM": agent, "BASIC.SYSTEM": basic}
    for name, aux in (("PRODOS", 0), ("AGENT.SYSTEM", 0x2000), ("BASIC.SYSTEM", 0x2000)):
        ok, _ = m.add_file_contiguous(disk, files[name], name, m.FILETYPE_SYS, aux)
        if not ok:
            sys.exit(f"could not add {name}")
    return disk, template, files


def move_entry_to_front(disk, name):
    """Make `name` the first file in the volume directory (ProDOS boots the first *.SYSTEM)."""
    vd = m.read_block(disk, 2)
    entries = [bytes(vd[4 + i * ENTRY:4 + (i + 1) * ENTRY]) for i in range(1, 13)]
    used = [e for e in entries if e[0] >> 4]
    target = [e for e in used if e[1:1 + (e[0] & 15)].decode() == name][0]
    order = [target] + [e for e in used if e is not target]
    order += [bytes(ENTRY)] * (12 - len(order))
    for i, e in enumerate(order, start=1):
        vd[4 + i * ENTRY:4 + (i + 1) * ENTRY] = e
    m.write_block(disk, 2, vd)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "disks/agent_diag.dsk")

    diag = bytearray(open(os.path.join(ROOT, "build/DIAG.SYSTEM"), "rb").read())
    disk, template, files = build_base()
    ok, blocks = m.add_file_contiguous(disk, bytes(diag), "DIAG.SYSTEM", m.FILETYPE_SYS, 0x2000)
    if not ok:
        sys.exit("could not add DIAG.SYSTEM")
    move_entry_to_front(disk, "DIAG.SYSTEM")

    # Checksums of every block as it is now; only DIAG.SYSTEM's own blocks
    # change when the table goes in, and those are skipped.
    sums = [checksum(m.read_block(disk, n)) for n in range(m.NUM_BLOCKS)]
    agent = files["AGENT.SYSTEM"]
    at = diag.index(MARKER) + len(MARKER)
    header = struct.pack("<HHH", blocks[0], blocks[-1], len(agent)) + bytes(checksum(agent))
    table = b"".join(bytes(s) for s in sums)
    diag[at:at + len(header) + len(table)] = header + table

    # Rewrite DIAG.SYSTEM's data blocks with the filled-in table
    info = m.get_file_blocks(disk, "DIAG.SYSTEM")
    for i, blk in enumerate(info["blocks"][1:]):
        chunk = bytes(diag[i * 512:(i + 1) * 512])
        m.write_block(disk, blk, chunk + bytes(512 - len(chunk)))

    files["DIAG.SYSTEM"] = bytes(diag)
    problems = m.verify_disk(disk, template, files)
    for p in problems:
        print("FAIL:", p)
    if problems:
        sys.exit(1)
    for n in range(m.NUM_BLOCKS):
        if not (blocks[0] <= n <= blocks[-1]) and checksum(m.read_block(disk, n)) != sums[n]:
            sys.exit(f"FAIL: block {n} changed after the table was made")

    with open(out, "wb") as f:
        f.write(disk)
    print(f"{out}: DIAG.SYSTEM blocks {blocks[0]}-{blocks[-1]} (first in the directory),",
          f"AGENT.SYSTEM {len(agent)} bytes sum {checksum(agent)[0]:02X}{checksum(agent)[1]:02X}")
    for f in m.list_files(disk):
        print(f"   {f['name']:15} blocks {f['blocks']:3}  {f['size']:6} bytes  key {f['key']}")


if __name__ == "__main__":
    main()
