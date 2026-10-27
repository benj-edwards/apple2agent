#!/usr/bin/env python3
"""
Copy a disk image to a FAT SD card for a Floppy Emu-style adapter.

These adapters read an image as one unbroken run of clusters from where the
file starts. A fragmented file (or one the adapter remembers at an old
location) gives the Apple II the right data up to the first break and zeros
after it: ProDOS boots, then a .SYSTEM file "loads" as all zeros and the
machine drops into the monitor at 2002- (BRK at $2000).

So: push the allocator past scattered free gaps with a temporary filler,
allocate the whole image in one go, write it in one call (no ._ AppleDouble
file), verify the bytes, remove the filler, then check the cluster chain
with tools/fat_check.py (needs read access to the raw device: sudo).

Usage:
    python3 tools/copy_to_card.py disks/agent_contiguous.dsk "/Volumes/<card>/<folder>/Apple II Agent.dsk"

After copying, choose the image again in the adapter's menu so it looks the
file up afresh.
"""

import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fat_check  # noqa: E402

MAX_FILLER = 64 * 2**20


def volume_root(path):
    path = os.path.abspath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def copy_contiguous(src, dest):
    data = open(src, "rb").read()
    root = volume_root(dest)
    filler = os.path.join(root, "zz_contig_filler.tmp")
    st = os.statvfs(root)
    free = st.f_bavail * st.f_frsize
    if free < 2 * len(data):
        raise SystemExit(f"only {free} bytes free on {root}")
    filler_bytes = min(MAX_FILLER, (free - 2 * len(data)) // 2)

    if os.path.exists(dest):
        os.remove(dest)
    os.sync()

    try:
        with open(filler, "wb") as f:
            f.write(bytes(filler_bytes))
            f.flush()
            os.fsync(f.fileno())
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.ftruncate(fd, len(data))     # one allocation for the whole file
            os.fsync(fd)
            if os.pwrite(fd, data, 0) != len(data):
                raise OSError("short write")
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(filler):
            os.remove(filler)
        os.sync()

    if open(dest, "rb").read() != data:
        raise SystemExit(f"verify FAILED: {dest} does not match {src}")
    print(f"copied {len(data)} bytes to {dest} (bytes verified)")

    rel = os.path.relpath(dest, root)
    try:
        status = fat_check.check(root, rel)
    except PermissionError:
        print("Contiguity not checked (the card's raw device needs root). To check:\n"
              f"  sudo python3 {shlex.quote(os.path.abspath(fat_check.__file__))} {shlex.quote(root)} {shlex.quote(rel)}")
        return
    if status != 0:
        raise SystemExit("the image is NOT contiguous - the adapter will read it wrong")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    copy_contiguous(sys.argv[1], sys.argv[2])
