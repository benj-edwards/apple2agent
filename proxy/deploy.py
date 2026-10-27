#!/usr/bin/env python3
"""
Program building and memory layout for Apple II deploys.

One place decides where a program lives in memory and how it is launched.
The same Program object drives both the test emulator (emulator_bridge)
and the real Apple II (DEPLOY/LOAD/RUN packets), so what Claude tests is
exactly what the user gets.

Launch modes (must match asm/agent_deploy.s):

  RESIDENT  64K machines. Program in $0800-$5FFF, the agent stays put
            at $6000+. Instant launch and return.
  EXCHANGE  128K //e. Program may use $0800-$BEFF. Bytes are staged in
            aux memory, then swapped into place at launch while the
            agent waits in aux.
"""

import os
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from basic_tokenizer_streaming import tokenize_program

MODE_RESIDENT = 0
MODE_EXCHANGE = 1

RUN_BASIC = 0
RUN_BINARY = 1

PROGRAM_BOTTOM = 0x0800          # below: screen, page 3, stack
RESIDENT_TOP = 0x6000            # agent lives at $6000+ in RESIDENT mode
EXCHANGE_TOP = 0xBF00            # ProDOS global page at $BF00

HGR_PAGE1 = (0x2000, 0x4000)
HGR_PAGE2 = (0x4000, 0x6000)

NAME_MAX = 35                    # RUN descriptor is 48 bytes on the Apple II

# Applesoft tokens that imply hi-res pages
TOKEN_HGR = 0x91
TOKEN_HGR2 = 0x90


class BuildError(Exception):
    """Program can't be built or doesn't fit. Message is shown to Claude."""


@dataclass
class Program:
    kind: int                    # RUN_BASIC / RUN_BINARY
    name: str
    chunks: List[Tuple[int, bytes]]
    mode: int
    start: int                   # BASIC: TXTTAB, binary: entry point
    prgend: int = 0              # BASIC only
    lomem: int = 0
    himem: int = 0
    source_name: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(len(data) for _, data in self.chunks)

    @property
    def lo_page(self) -> int:
        return min(addr for addr, _ in self.chunks) >> 8

    @property
    def hi_page(self) -> int:
        end = max(addr + len(data) for addr, data in self.chunks)
        return (end + 0xFF) >> 8

    def descriptor(self) -> bytes:
        """RUN packet payload (layout = RD_* in agent_deploy.s)."""
        name = self.name.upper().encode('ascii', errors='replace')[:NAME_MAX]
        return (struct.pack('<BHHHHBBB', self.kind, self.start, self.prgend,
                            self.lomem, self.himem, self.mode,
                            self.lo_page, self.hi_page)
                + name + b'\x00')

    def summary(self) -> str:
        """One paragraph for Claude: where everything ended up."""
        mode = "EXCHANGE (128K)" if self.mode == MODE_EXCHANGE else "RESIDENT"
        if self.kind == RUN_BASIC:
            text = (f"BASIC '{self.name}': {self.size} bytes, program text "
                    f"${self.start:04X}-${self.prgend - 1:04X}, variables from "
                    f"${self.lomem:04X}, HIMEM ${self.himem:04X}, {mode} mode.")
        else:
            lo = min(a for a, _ in self.chunks)
            hi = max(a + len(d) for a, d in self.chunks)
            text = (f"Machine code '{self.name}': {self.size} bytes at "
                    f"${lo:04X}-${hi - 1:04X}, entry ${self.start:04X}, {mode} mode.")
        if self.notes:
            text += " " + " ".join(self.notes)
        return text


def _top(has_aux: bool) -> int:
    return EXCHANGE_TOP if has_aux else RESIDENT_TOP


def _mode(has_aux: bool) -> int:
    return MODE_EXCHANGE if has_aux else MODE_RESIDENT


def _basic_hires_pages(tokens: bytes, start: int, source: str) -> set:
    """Which hi-res pages a tokenized program draws on (1, 2)."""
    pages = set()
    pos = 0
    while pos + 4 <= len(tokens):
        link = tokens[pos] | (tokens[pos + 1] << 8)
        if link == 0:
            break
        end = link - start
        content = tokens[pos + 4:end - 1]
        in_quote = False
        for b in content:
            if b == 0x22:
                in_quote = not in_quote
            elif not in_quote and b == TOKEN_HGR:
                pages.add(1)
            elif not in_quote and b == TOKEN_HGR2:
                pages.add(2)
        pos = end
    # Drawing on / showing page 2 by POKE (HPAG=230 or PAGE2 switch)
    flat = re.sub(r'\s+', '', source.upper())
    if re.search(r'POKE230,64', flat) or '-16299' in flat or '49237' in flat:
        pages.add(2)
    return pages


def build_basic(source: str, name: str, has_aux: bool,
                hires_pages: Optional[set] = None) -> Program:
    """Tokenize and place an Applesoft program around any hi-res pages."""
    if not re.search(r'^\s*\d+', source, re.MULTILINE):
        raise BuildError("No numbered lines found - Applesoft lines need line numbers.")
    try:
        probe = tokenize_program(source, 0x0801)
    except ValueError as e:
        raise BuildError(str(e))

    pages = hires_pages if hires_pages is not None else _basic_hires_pages(probe, 0x0801, source)
    top = _top(has_aux)

    # Free regions, lowest first, given the graphics pages in use
    used = []
    if 1 in pages:
        used.append(HGR_PAGE1)
    if 2 in pages:
        used.append(HGR_PAGE2)
    regions = []
    cursor = PROGRAM_BOTTOM
    for lo, hi in sorted(used):
        if lo > cursor:
            regions.append((cursor, min(lo, top)))
        cursor = max(cursor, hi)
    if cursor < top:
        regions.append((cursor, top))
    regions = [(lo, hi) for lo, hi in regions if hi > lo]

    # Program text goes in the first region it fits (+1 for the $00 that
    # must precede TXTTAB); variables and strings get the biggest region
    size = len(probe)
    for lo, hi in regions:
        if lo + 1 + size <= hi:
            txttab = lo + 1
            break
    else:
        room = max((hi - lo for lo, hi in regions), default=0)
        raise BuildError(
            f"Program is {size} bytes but the largest free block is {room} bytes "
            f"(hi-res pages {sorted(pages) or 'none'}, top ${top:04X}). Make it smaller.")

    tokens = tokenize_program(source, txttab)
    prgend = txttab + len(tokens)
    text_region = next(r for r in regions if r[0] < txttab <= r[1])
    after_text = (prgend, text_region[1])
    var_regions = [after_text] + [r for r in regions if r != text_region and r[0] >= prgend]
    lomem, himem = max(var_regions, key=lambda r: r[1] - r[0])

    program = Program(
        kind=RUN_BASIC, name=name,
        chunks=[(txttab - 1, b'\x00' + tokens)],
        mode=_mode(has_aux), start=txttab, prgend=prgend,
        lomem=lomem, himem=himem)
    if pages:
        program.notes.append(f"Hi-res page(s) {sorted(pages)} kept clear.")
    if himem - lomem < 2048:
        program.notes.append(f"WARNING: only {himem - lomem} bytes for variables/strings.")
    return program


_HIRES_ON_RE = re.compile(r'\$C057|\b(?:49239|-16297)\b', re.IGNORECASE)
_PAGE2_ON_RE = re.compile(r'\$C055|\b(?:49237|-16299)\b', re.IGNORECASE)


def _hires_overlap_note(data: bytes, load_addr: int, source: str) -> Optional[str]:
    """A hi-res program whose own bytes sit in a hi-res page draws over itself."""
    if not source or not _HIRES_ON_RE.search(source):
        return None
    hits = []
    pages = ((1, HGR_PAGE1), (2, HGR_PAGE2)) if _PAGE2_ON_RE.search(source) else ((1, HGR_PAGE1),)
    for n, (lo, hi) in pages:
        a, b = max(lo, load_addr), min(hi, load_addr + len(data))
        if a < b and any(data[a - load_addr:b - load_addr]):     # a .res gap is all zeros
            hits.append(f"page {n} (${lo:04X}-${hi - 1:04X})")
    if not hits:
        return None
    return ("WARNING: this program turns on hi-res, and its own code or data sit in hi-res "
            + " and ".join(hits) + ". Drawing on that page overwrites the program. Keep code "
            "and tables out of the pages you draw on (.org $6000 has room up to $BEFF; or skip "
            "a page with .res).")


def build_binary(data: bytes, load_addr: int, entry: Optional[int], name: str,
                 has_aux: bool, source: str = "") -> Program:
    """Place a machine-code image."""
    top = _top(has_aux)
    end = load_addr + len(data)
    if not data:
        raise BuildError("Assembled program is empty.")
    if load_addr < PROGRAM_BOTTOM:
        raise BuildError(f"Load address ${load_addr:04X} is below $0800 "
                         "(text screen, page 3 and the stack live there).")
    if end > top:
        raise BuildError(
            f"Program ends at ${end - 1:04X} but must end below ${top:04X} "
            f"({'EXCHANGE' if has_aux else 'RESIDENT'} mode).")
    entry = load_addr if entry is None else entry
    if not load_addr <= entry < end:
        raise BuildError(f"Entry ${entry:04X} is outside the program.")
    program = Program(kind=RUN_BINARY, name=name, chunks=[(load_addr, bytes(data))],
                      mode=_mode(has_aux), start=entry)
    note = _hires_overlap_note(data, load_addr, source)
    if note:
        program.notes.append(note)
    return program


_ORG_RE = re.compile(r'^\s*\.org\s+\$?([0-9A-Fa-f]+)', re.MULTILINE)


def assemble(source: str, workdir: str, basename: str) -> Tuple[bytes, int, dict, str]:
    """Assemble ca65 source to a flat binary.

    The load address is the first .org (default $0800). Returns
    (binary, load_addr, labels, listing_path). Raises BuildError with
    the assembler's own messages on failure.
    """
    m = _ORG_RE.search(source)
    load_addr = int(m.group(1), 16) if m else PROGRAM_BOTTOM
    if not m:
        source = f".org ${load_addr:04X}\n" + source

    os.makedirs(workdir, exist_ok=True)
    asm_path = os.path.join(workdir, basename + ".s")
    obj_path = os.path.join(workdir, basename + ".o")
    bin_path = os.path.join(workdir, basename + ".bin")
    lst_path = os.path.join(workdir, basename + ".lst")
    lbl_path = os.path.join(workdir, basename + ".lbl")
    with open(asm_path, "w") as f:
        f.write(source)

    with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as cfg:
        cfg.write(f"""MEMORY {{
    ZP:  start = $0000, size = $0100, type = rw, file = "";
    RAM: start = ${load_addr:04X}, size = ${EXCHANGE_TOP - load_addr:04X}, file = %O;
}}
SEGMENTS {{
    ZEROPAGE: load = ZP,  type = zp,  optional = yes;
    CODE:     load = RAM, type = rw;
    RODATA:   load = RAM, type = rw,  optional = yes;
    DATA:     load = RAM, type = rw,  optional = yes;
    BSS:      load = RAM, type = bss, optional = yes, define = yes;
}}
""")
        cfg_path = cfg.name
    try:
        r = subprocess.run(["ca65", "-g", "--cpu", "65C02", "-l", lst_path,
                            "-o", obj_path, asm_path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise BuildError("ca65 errors:\n" + _short_errors(r.stderr, asm_path))
        r = subprocess.run(["ld65", "-C", cfg_path, "-Ln", lbl_path,
                            "-o", bin_path, obj_path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise BuildError("ld65 errors:\n" + _short_errors(r.stderr, asm_path))
    except FileNotFoundError:
        raise BuildError("ca65/ld65 not found - install the cc65 toolchain.")
    finally:
        os.unlink(cfg_path)

    with open(bin_path, "rb") as f:
        binary = f.read()
    labels = {}
    if os.path.exists(lbl_path):
        for line in open(lbl_path):
            parts = line.split()
            if len(parts) == 3 and parts[0] == "al":
                labels[parts[2].lstrip('.')] = int(parts[1], 16)
    return binary, load_addr, labels, lst_path


def _short_errors(stderr: str, asm_path: str) -> str:
    lines = [l.replace(asm_path, "line") for l in stderr.strip().splitlines()]
    return "\n".join(lines[:25])
