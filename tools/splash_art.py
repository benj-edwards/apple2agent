#!/usr/bin/env python3
"""
Splash screen art for the Apple II Agent, drawn the way hi-res can show it.

The canvas is 140 x 192 color cells (each cell = 2 screen pixels), in the six
HGR colors: K black, W white, G green, V violet, O orange, B blue. A cell of
green or violet lights the odd or even pixel of its pair with the palette bit
clear; orange and blue do the same with it set; white lights both. Each 7-pixel
byte has one palette bit (chosen by majority), so the two color groups only
meet cleanly at byte boundaries - the same limit an artist had in 1980.

    python3 tools/splash_art.py            # writes build/splash/<option>.hgr (8192 bytes)
"""

import math
import os
import random
import sys

W, H = 140, 192
GROUP1 = {"O", "B"}             # palette bit set
EVEN = {"V", "B"}               # lit on the even pixel of the pair
ODD = {"G", "O"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "splash")

FONT = {
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ####"],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "#   #", "##  #", "# # #", "#  ##", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "# # #", "# # #", "# # #", " # # "],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": ["#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": ["  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "],
    ".": ["     ", "     ", "     ", "     ", "     ", "     ", "  #  "],
    "-": ["     ", "     ", "     ", " ### ", "     ", "     ", "     "],
    ">": ["#    ", " #   ", "  #  ", "   # ", "  #  ", " #   ", "#    "],
    "]": [" ### ", "   # ", "   # ", "   # ", "   # ", "   # ", " ### "],
    " ": ["     "] * 7,
}

VERSION = "2.1"
CREDIT = "2026 BX FOUNDRY"


class Canvas:
    def __init__(self, bg="K"):
        self.px = [[bg] * W for _ in range(H)]

    def set(self, x, y, c):
        if 0 <= x < W and 0 <= y < H and c:
            self.px[y][x] = c

    def get(self, x, y):
        return self.px[y][x] if 0 <= x < W and 0 <= y < H else "K"

    def rect(self, x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, c)

    def frame(self, x0, y0, x1, y1, c, t=1):
        self.rect(x0, y0, x1, y0 + t - 1, c)
        self.rect(x0, y1 - t + 1, x1, y1, c)
        self.rect(x0, y0, x0 + t - 1, y1, c)
        self.rect(x1 - t + 1, y0, x1, y1, c)

    def line(self, x0, y0, x1, y1, c):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.set(x0, y0, c)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def text(self, x, y, s, color, sx=1, sy=1, gap=1):
        """color: a color letter, or f(font_row, font_col, cell_y) -> letter."""
        for ch in s:
            glyph = FONT[ch]
            for r, row in enumerate(glyph):
                for col, bit in enumerate(row):
                    if bit != "#":
                        continue
                    for yy in range(sy):
                        for xx in range(sx):
                            cy = y + r * sy + yy
                            c = color(r, col, cy) if callable(color) else color
                            self.set(x + col * sx + xx, cy, c)
            x += (5 + gap) * sx

    @staticmethod
    def text_width(s, sx=1, gap=1):
        return len(s) * (5 + gap) * sx - gap * sx

    def shadowed(self, x, y, s, color, shadow, sx, sy, dx=1, dy=1, gap=1):
        self.text(x + dx, y + dy, s, shadow, sx, sy, gap)
        self.text(x, y, s, color, sx, sy, gap)

    def credits(self, y=181, color="W", box=False):
        """'2026 BX FOUNDRY' at the left, 'V2.1' at the right of the bottom line."""
        ver = "V" + VERSION
        if box:
            self.rect(0, y - 3, W - 1, H - 1, "K")
        self.text(6, y, CREDIT, color)
        self.text(W - 6 - self.text_width(ver), y, ver, color)

    def to_hgr(self):
        mem = bytearray(8192)
        for y in range(H):
            base = (y & 7) * 0x400 + ((y >> 3) & 7) * 0x80 + (y >> 6) * 0x28
            for b in range(40):
                cells = [self.px[y][(7 * b + i) // 2] for i in range(7)]
                g1 = sum(c in GROUP1 for c in cells)
                g0 = sum(c in ("G", "V") for c in cells)
                byte = 0x80 if g1 > g0 else 0
                for i in range(7):
                    x = 7 * b + i
                    c = self.px[y][x // 2]
                    if c == "W" or (c in EVEN and x % 2 == 0) or (c in ODD and x % 2 == 1):
                        byte |= 1 << i
                mem[base + b] = byte
        return bytes(mem)


def stars(cv, n, seed, colors=("W",), y0=0, y1=H - 1, avoid=lambda x, y: False):
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.randrange(W), rng.randrange(y0, y1 + 1)
        if not avoid(x, y) and cv.get(x, y) == "K":
            cv.set(x, y, rng.choice(colors))


# ---------------------------------------------------------------- the options

def option_rainbow():
    """A: rainbow-striped APPLE II, a big white AGENT with the block cursor."""
    cv = Canvas()
    stars(cv, 70, 1977, ("W", "W", "B", "V"), 0, 170)
    bands = ["G", "G", "O", "O", "V", "V", "B"]

    def stripe(r, col, cy):                 # bands follow the font rows: one color per row pair
        return bands[min(r, 6)]
    t1 = "APPLE II"
    sx, sy = 2, 3
    x1 = (W - Canvas.text_width(t1, sx)) // 2
    cv.text(x1 + 1, 28 + 2, t1, "B", sx, sy)       # shadow
    cv.text(x1, 28, t1, stripe, sx, sy)
    t2 = "AGENT"
    sx2, sy2 = 4, 6
    x2 = (W - Canvas.text_width(t2, sx2) - 6 * sx2) // 2
    cv.text(x2 + 2, 66 + 3, t2, "V", sx2, sy2)
    cv.text(x2, 66, t2, "W", sx2, sy2)
    cx = x2 + Canvas.text_width(t2, sx2) + 2 * sx2  # the Apple II's block cursor
    cv.rect(cx, 66, cx + 5 * sx2 - 1, 66 + 7 * sy2 - 1, "W")
    for i, c in enumerate(["G", "O", "V", "B"]):    # a striped rule under the title
        cv.rect(14, 124 + i * 3, W - 15, 125 + i * 3, c)
    tag = "TALK TO YOUR APPLE II"
    cv.text((W - Canvas.text_width(tag)) // 2, 148, tag, "O")
    cv.credits()
    return cv


def option_monitor():
    """B: an Apple II and its monitor; the green screen shows the agent."""
    cv = Canvas()
    # monitor
    cv.rect(26, 8, 113, 92, "W")
    cv.rect(30, 12, 109, 86, "K")
    cv.frame(32, 14, 107, 84, "G")
    cv.rect(60, 93, 79, 98, "W")                    # neck
    # screen contents (green phosphor)
    lines = ["]RUN AGENT", "", "APPLE II AGENT", "", "AGENT> MAKE A", "GAME"]
    for i, s in enumerate(lines):
        cv.text(36, 18 + i * 10, s, "G")
    cv.rect(36 + Canvas.text_width("GAME") + 2, 68, 36 + Canvas.text_width("GAME") + 6, 74, "G")
    # computer case + keyboard
    cv.rect(18, 102, 121, 122, "W")
    cv.rect(22, 105, 117, 119, "K")
    for row in range(3):
        for k in range(14 - row):
            kx = 25 + row * 2 + k * 6
            cv.rect(kx, 107 + row * 4, kx + 3, 108 + row * 4, "W")
    cv.rect(40, 119, 99, 119, "W")                  # space bar
    cv.rect(18, 123, 121, 126, "O")                 # the base
    title = "APPLE II AGENT"
    cv.shadowed((W - Canvas.text_width(title, 1)) // 2, 140, title, "W", "O", 1, 3)
    tag = "AI CODING AGENT"
    cv.text((W - Canvas.text_width(tag)) // 2, 164, tag, "B")
    cv.credits()
    return cv


def option_synthwave():
    """C: a striped sunset sun over a perspective grid, the title in the sky."""
    cv = Canvas()
    horizon = 118
    stars(cv, 60, 6502, ("W", "B"), 0, 70)
    cx, cy, r = 70, 92, 34                          # the sun: orange, gaps widening downward
    for y in range(cy - r, horizon):
        half = int(math.sqrt(max(0, r * r - (y - cy) ** 2)))
        depth = y - (cy - 6)
        if depth > 0 and (depth // 4) % 2 == 1 and (depth % 4) < 1 + depth // 10:
            continue
        cv.rect(cx - half, y, cx + half, y, "O" if y < cy + 8 else "V")
    cv.rect(0, horizon, W - 1, horizon, "W")
    # perspective floor: horizontal lines bunching toward the horizon...
    y = horizon
    step = 2.0
    while y < 172:
        y += step
        step *= 1.35
        cv.rect(0, int(y), W - 1, int(y), "V")
    # ...and lines fanning out from the vanishing point
    for k in range(-10, 11):
        cv.line(cx, horizon, cx + k * 22, 172, "V")
    cv.rect(0, 173, W - 1, H - 1, "K")
    t1, t2 = "APPLE II", "AGENT"
    cv.shadowed((W - Canvas.text_width(t1, 2)) // 2, 8, t1, "W", "B", 2, 3, 1, 2)
    cv.shadowed((W - Canvas.text_width(t2, 3)) // 2, 34, t2, "W", "V", 3, 3, 1, 2)
    cv.credits(181)
    return cv


def option_circuit():
    """D: a big 6502 chip with circuit-board traces, the title above."""
    cv = Canvas()
    title = "APPLE II AGENT"
    cv.shadowed((W - Canvas.text_width(title, 1)) // 2, 10, title, "W", "B", 1, 3)
    x0, y0, x1, y1 = 40, 52, 99, 150                # the chip
    rng = random.Random(1975)
    for i in range(10):                             # pins + traces on both sides
        py = y0 + 6 + i * 9
        cv.rect(x0 - 5, py, x0 - 1, py + 2, "W")
        cv.rect(x1 + 1, py, x1 + 5, py + 2, "W")
        lx = rng.randrange(6, 26)
        cv.rect(lx, py + 1, x0 - 6, py + 1, "G")
        cv.rect(lx - 1, py, lx + 1, py + 2, "O")    # a via
        rx = rng.randrange(W - 26, W - 6)
        cv.rect(x1 + 6, py + 1, rx, py + 1, "G")
        cv.rect(rx - 1, py, rx + 1, py + 2, "O")
        if i % 3 == 0:                              # some traces turn
            cv.rect(lx, py + 1, lx, min(py + 9 * rng.randrange(1, 3), 170), "G")
    cv.rect(x0, y0, x1, y1, "W")
    cv.rect(x0 + 2, y0 + 2, x1 - 2, y1 - 2, "K")
    cv.rect(66, y0, 73, y0 + 3, "K")                # the notch
    cv.text((x0 + x1) // 2 - Canvas.text_width("6502", 2) // 2, 80, "6502", "W", 2, 3)
    cv.text((x0 + x1) // 2 - Canvas.text_width("AGENT") // 2, 112, "AGENT", "O")
    cv.text((x0 + x1) // 2 - Canvas.text_width("1 MHZ") // 2, 126, "1 MHZ", "V")
    cv.credits()
    return cv


OPTIONS = {
    "a_rainbow": option_rainbow,
    "b_monitor": option_monitor,
    "c_synthwave": option_synthwave,
    "d_circuit": option_circuit,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, make in OPTIONS.items():
        data = make().to_hgr()
        assert len(data) == 8192
        with open(os.path.join(OUT, name + ".hgr"), "wb") as f:
            f.write(data)
        print(os.path.join(OUT, name + ".hgr"))


if __name__ == "__main__":
    sys.exit(main())
