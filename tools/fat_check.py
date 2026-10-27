#!/usr/bin/env python3
"""
Check whether a file on a FAT16/FAT32 SD card is stored contiguously.

Floppy Emu-style adapters read a disk image as one unbroken run of clusters.
macOS gives no way to see cluster layout through the mounted volume, so this
reads the card's raw device (read-only) and walks the file's cluster chain.

Usage (raw devices of real cards belong to root, so usually with sudo):
    sudo python3 tools/fat_check.py /dev/rdisk4s1 "<folder>/Apple II Agent.dsk"
    sudo python3 tools/fat_check.py "/Volumes/<card>" "<folder>/Apple II Agent.dsk"

A mounted volume path is turned into its raw device with `diskutil info`.
Exit status: 0 contiguous, 1 fragmented, 2 error.
"""

import os
import plistlib
import struct
import subprocess
import sys


class FatError(Exception):
    pass


class Fat:
    def __init__(self, dev):
        self.fd = os.open(dev, os.O_RDONLY)
        self.cache = {}
        bs = self.read(0, 512)
        if bs[510:512] != b"\x55\xAA":
            raise FatError(f"{dev}: no FAT boot sector (is this the partition, e.g. /dev/rdisk4s1?)")
        self.bps = struct.unpack_from("<H", bs, 0x0B)[0]
        self.spc = bs[0x0D]
        reserved = struct.unpack_from("<H", bs, 0x0E)[0]
        nfats = bs[0x10]
        root_entries = struct.unpack_from("<H", bs, 0x11)[0]
        total = struct.unpack_from("<H", bs, 0x13)[0] or struct.unpack_from("<I", bs, 0x20)[0]
        fatsz = struct.unpack_from("<H", bs, 0x16)[0] or struct.unpack_from("<I", bs, 0x24)[0]
        root_secs = (root_entries * 32 + self.bps - 1) // self.bps
        self.fat_start = reserved * self.bps
        self.data_start = (reserved + nfats * fatsz + root_secs) * self.bps
        self.root_start = (reserved + nfats * fatsz) * self.bps
        self.root_size = root_entries * 32
        clusters = (total - (reserved + nfats * fatsz + root_secs)) // self.spc
        self.cluster_bytes = self.bps * self.spc
        self.fat32 = clusters >= 65525
        if clusters < 4085:
            raise FatError("FAT12 is not supported")
        self.root_cluster = struct.unpack_from("<I", bs, 0x2C)[0] if self.fat32 else None

    def read(self, offset, length):
        """Raw devices want sector-aligned reads."""
        out = bytearray()
        sec = 512
        start = offset - offset % sec
        end = offset + length
        pos = start
        while pos < end:
            if pos not in self.cache:
                self.cache[pos] = os.pread(self.fd, sec, pos)
            out += self.cache[pos]
            pos += sec
        return bytes(out[offset - start:offset - start + length])

    def next_cluster(self, c):
        if self.fat32:
            n = struct.unpack("<I", self.read(self.fat_start + c * 4, 4))[0] & 0x0FFFFFFF
            return None if n >= 0x0FFFFFF8 else n
        n = struct.unpack("<H", self.read(self.fat_start + c * 2, 2))[0]
        return None if n >= 0xFFF8 else n

    def chain(self, first):
        out, c = [], first
        while c is not None and c >= 2:
            out.append(c)
            if len(out) > 10_000_000:
                raise FatError("cluster chain loops")
            c = self.next_cluster(c)
        return out

    def dir_bytes(self, cluster):
        if cluster is None:                     # FAT16 fixed root
            return self.read(self.root_start, self.root_size)
        return b"".join(self.read(self.data_start + (c - 2) * self.cluster_bytes, self.cluster_bytes)
                        for c in self.chain(cluster))

    def entries(self, cluster):
        data, lfn = self.dir_bytes(cluster), {}
        for i in range(0, len(data), 32):
            e = data[i:i + 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5:
                lfn = {}
                continue
            if e[11] == 0x0F:                   # long-name piece
                chars = e[1:11] + e[14:26] + e[28:32]
                lfn[e[0] & 0x1F] = chars.decode("utf-16-le", "replace").split("\x00")[0].replace("￿", "")
                continue
            short = e[0:8].decode("latin-1").rstrip()
            ext = e[8:11].decode("latin-1").rstrip()
            name = "".join(lfn[k] for k in sorted(lfn)) if lfn else (short + ("." + ext if ext else ""))
            lfn = {}
            first = struct.unpack_from("<H", e, 0x1A)[0] | (struct.unpack_from("<H", e, 0x14)[0] << 16)
            yield name, bool(e[11] & 0x10), first, struct.unpack_from("<I", e, 0x1C)[0]

    def find(self, path):
        cluster = self.root_cluster
        parts = [p for p in path.split("/") if p]
        for depth, part in enumerate(parts):
            for name, is_dir, first, size in self.entries(cluster):
                if name.lower() == part.lower():
                    if depth == len(parts) - 1:
                        return first, size
                    if not is_dir:
                        raise FatError(f"{part} is not a folder")
                    cluster = first
                    break
            else:
                raise FatError(f"not found: {part}")


def raw_device(path):
    if path.startswith("/dev/"):
        return path.replace("/dev/disk", "/dev/rdisk")
    info = plistlib.loads(subprocess.run(["diskutil", "info", "-plist", path],
                                         capture_output=True, check=True).stdout)
    return "/dev/r" + info["DeviceIdentifier"]


def check(device_or_volume, path):
    dev = raw_device(device_or_volume)
    fat = Fat(dev)
    first, size = fat.find(path)
    clusters = fat.chain(first)
    need = (size + fat.cluster_bytes - 1) // fat.cluster_bytes
    runs, start = [], clusters[0] if clusters else None
    for a, b in zip(clusters, clusters[1:]):
        if b != a + 1:
            runs.append((start, a))
            start = b
    if clusters:
        runs.append((start, clusters[-1]))
    print(f"{path}: {size} bytes, {len(clusters)} clusters of {fat.cluster_bytes} bytes "
          f"({'FAT32' if fat.fat32 else 'FAT16'}, {dev})")
    if len(clusters) < need:
        print(f"  BROKEN: chain has {len(clusters)} clusters, the size needs {need}")
        return 1
    if len(runs) == 1:
        print(f"  CONTIGUOUS: clusters {runs[0][0]}-{runs[0][1]}")
        return 0
    print(f"  FRAGMENTED into {len(runs)} pieces:")
    offset = 0
    for a, b in runs:
        n = b - a + 1
        print(f"    file bytes {offset:7}-{offset + n * fat.cluster_bytes - 1:7}: clusters {a}-{b}")
        offset += n * fat.cluster_bytes
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(check(sys.argv[1], sys.argv[2]))
    except PermissionError:
        print(f"Can't read the raw device: run with sudo.\n  sudo python3 {' '.join(sys.argv)}")
        sys.exit(2)
    except FatError as e:
        print(f"error: {e}")
        sys.exit(2)
