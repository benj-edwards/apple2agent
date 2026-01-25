#!/usr/bin/env python3
"""
Native Apple II DOS 3.3 Disk Image Tools
Creates and manipulates .dsk disk images without external dependencies.
"""

import os
import struct
from typing import Optional, List, Tuple

# DOS 3.3 Constants
TRACKS = 35
SECTORS_PER_TRACK = 16
BYTES_PER_SECTOR = 256
DISK_SIZE = TRACKS * SECTORS_PER_TRACK * BYTES_PER_SECTOR  # 143360 bytes

# Track/Sector locations
VTOC_TRACK = 17
VTOC_SECTOR = 0
CATALOG_TRACK = 17
FIRST_CATALOG_SECTOR = 15

# File types
FILE_TYPE_TEXT = 0x00
FILE_TYPE_INTEGER_BASIC = 0x01
FILE_TYPE_APPLESOFT_BASIC = 0x02
FILE_TYPE_BINARY = 0x04
FILE_TYPE_RELOCATABLE = 0x08
FILE_TYPE_S_TYPE = 0x10
FILE_TYPE_A_TYPE = 0x20
FILE_TYPE_B_TYPE = 0x40

# Applesoft BASIC tokens
BASIC_TOKENS = {
    'END': 0x80, 'FOR': 0x81, 'NEXT': 0x82, 'DATA': 0x83, 'INPUT': 0x84,
    'DEL': 0x85, 'DIM': 0x86, 'READ': 0x87, 'GR': 0x88, 'TEXT': 0x89,
    'PR#': 0x8A, 'IN#': 0x8B, 'CALL': 0x8C, 'PLOT': 0x8D, 'HLIN': 0x8E,
    'VLIN': 0x8F, 'HGR2': 0x90, 'HGR': 0x91, 'HCOLOR=': 0x92, 'HPLOT': 0x93,
    'DRAW': 0x94, 'XDRAW': 0x95, 'HTAB': 0x96, 'HOME': 0x97, 'ROT=': 0x98,
    'SCALE=': 0x99, 'SHLOAD': 0x9A, 'TRACE': 0x9B, 'NOTRACE': 0x9C,
    'NORMAL': 0x9D, 'INVERSE': 0x9E, 'FLASH': 0x9F, 'COLOR=': 0xA0,
    'POP': 0xA1, 'VTAB': 0xA2, 'HIMEM:': 0xA3, 'LOMEM:': 0xA4, 'ONERR': 0xA5,
    'RESUME': 0xA6, 'RECALL': 0xA7, 'STORE': 0xA8, 'SPEED=': 0xA9, 'LET': 0xAA,
    'GOTO': 0xAB, 'RUN': 0xAC, 'IF': 0xAD, 'RESTORE': 0xAE, '&': 0xAF,
    'GOSUB': 0xB0, 'RETURN': 0xB1, 'REM': 0xB2, 'STOP': 0xB3, 'ON': 0xB4,
    'WAIT': 0xB5, 'LOAD': 0xB6, 'SAVE': 0xB7, 'DEF': 0xB8, 'POKE': 0xB9,
    'PRINT': 0xBA, 'CONT': 0xBB, 'LIST': 0xBC, 'CLEAR': 0xBD, 'GET': 0xBE,
    'NEW': 0xBF, 'TAB(': 0xC0, 'TO': 0xC1, 'FN': 0xC2, 'SPC(': 0xC3,
    'THEN': 0xC4, 'AT': 0xC5, 'NOT': 0xC6, 'STEP': 0xC7, '+': 0xC8,
    '-': 0xC9, '*': 0xCA, '/': 0xCB, '^': 0xCC, 'AND': 0xCD, 'OR': 0xCE,
    '>': 0xCF, '=': 0xD0, '<': 0xD1, 'SGN': 0xD2, 'INT': 0xD3, 'ABS': 0xD4,
    'USR': 0xD5, 'FRE': 0xD6, 'SCRN(': 0xD7, 'PDL': 0xD8, 'POS': 0xD9,
    'SQR': 0xDA, 'RND': 0xDB, 'LOG': 0xDC, 'EXP': 0xDD, 'COS': 0xDE,
    'SIN': 0xDF, 'TAN': 0xE0, 'ATN': 0xE1, 'PEEK': 0xE2, 'LEN': 0xE3,
    'STR$': 0xE4, 'VAL': 0xE5, 'ASC': 0xE6, 'CHR$': 0xE7, 'LEFT$': 0xE8,
    'RIGHT$': 0xE9, 'MID$': 0xEA
}

# Reverse lookup for display
TOKEN_TO_KEYWORD = {v: k for k, v in BASIC_TOKENS.items()}


def ts_to_offset(track: int, sector: int) -> int:
    """Convert track/sector to byte offset in disk image."""
    return (track * SECTORS_PER_TRACK + sector) * BYTES_PER_SECTOR


def offset_to_ts(offset: int) -> Tuple[int, int]:
    """Convert byte offset to track/sector."""
    sector_num = offset // BYTES_PER_SECTOR
    track = sector_num // SECTORS_PER_TRACK
    sector = sector_num % SECTORS_PER_TRACK
    return track, sector


class DOS33Disk:
    """Native DOS 3.3 disk image handler."""

    def __init__(self, filename: Optional[str] = None):
        self.filename = filename
        if filename and os.path.exists(filename):
            with open(filename, 'rb') as f:
                self.data = bytearray(f.read())
        else:
            self.data = bytearray(DISK_SIZE)

    def read_sector(self, track: int, sector: int) -> bytes:
        """Read a single sector."""
        offset = ts_to_offset(track, sector)
        return bytes(self.data[offset:offset + BYTES_PER_SECTOR])

    def write_sector(self, track: int, sector: int, data: bytes):
        """Write a single sector."""
        if len(data) > BYTES_PER_SECTOR:
            raise ValueError(f"Sector data too large: {len(data)} > {BYTES_PER_SECTOR}")
        offset = ts_to_offset(track, sector)
        self.data[offset:offset + len(data)] = data
        # Pad with zeros if needed
        if len(data) < BYTES_PER_SECTOR:
            self.data[offset + len(data):offset + BYTES_PER_SECTOR] = bytes(BYTES_PER_SECTOR - len(data))

    def save(self, filename: Optional[str] = None):
        """Save disk image to file."""
        filename = filename or self.filename
        if not filename:
            raise ValueError("No filename specified")
        with open(filename, 'wb') as f:
            f.write(self.data)
        self.filename = filename

    def format(self, volume_num: int = 254, init_dos: bool = False):
        """Format disk with empty DOS 3.3 structure."""
        # Clear disk
        self.data = bytearray(DISK_SIZE)

        # Create VTOC (Volume Table of Contents) at Track 17, Sector 0
        vtoc = bytearray(BYTES_PER_SECTOR)
        vtoc[0x00] = 0x04  # Not used (should be 0 but DOS uses 4)
        vtoc[0x01] = CATALOG_TRACK  # Track of first catalog sector
        vtoc[0x02] = FIRST_CATALOG_SECTOR  # Sector of first catalog sector
        vtoc[0x03] = 0x03  # DOS version (3 = DOS 3.3)
        vtoc[0x06] = volume_num  # Volume number
        vtoc[0x27] = 122  # Max track/sector pairs in track/sector list
        vtoc[0x30] = 18  # Last track where sectors were allocated
        vtoc[0x31] = 1   # Direction of allocation (+1)
        vtoc[0x34] = TRACKS  # Number of tracks
        vtoc[0x35] = SECTORS_PER_TRACK  # Sectors per track
        vtoc[0x36] = BYTES_PER_SECTOR & 0xFF  # Bytes per sector (low)
        vtoc[0x37] = BYTES_PER_SECTOR >> 8     # Bytes per sector (high)

        # Free sector bitmap - mark all sectors as free except track 17
        for track in range(TRACKS):
            bitmap_offset = 0x38 + track * 4
            if track == 17:
                # Track 17 (DOS catalog) - mark sectors 0-15 as used
                vtoc[bitmap_offset:bitmap_offset + 4] = bytes([0x00, 0x00, 0x00, 0x00])
            else:
                # All sectors free (bits set = free)
                vtoc[bitmap_offset:bitmap_offset + 4] = bytes([0xFF, 0xFF, 0x00, 0x00])

        self.write_sector(VTOC_TRACK, VTOC_SECTOR, vtoc)

        # Create empty catalog sectors (linked list from sector 15 down to 1)
        for sector in range(FIRST_CATALOG_SECTOR, 0, -1):
            catalog = bytearray(BYTES_PER_SECTOR)
            catalog[0x00] = 0  # Not used
            if sector > 1:
                catalog[0x01] = CATALOG_TRACK  # Next catalog track
                catalog[0x02] = sector - 1      # Next catalog sector
            else:
                catalog[0x01] = 0  # No more catalog sectors
                catalog[0x02] = 0
            self.write_sector(CATALOG_TRACK, sector, catalog)

        return self

    def catalog(self) -> List[dict]:
        """Return list of files on disk."""
        files = []
        vtoc = self.read_sector(VTOC_TRACK, VTOC_SECTOR)
        cat_track = vtoc[0x01]
        cat_sector = vtoc[0x02]

        while cat_track != 0:
            cat_data = self.read_sector(cat_track, cat_sector)
            # Each catalog sector has 7 file entries starting at offset 0x0B
            for i in range(7):
                entry_offset = 0x0B + i * 0x23
                if entry_offset + 0x23 > BYTES_PER_SECTOR:
                    break

                ts_list_track = cat_data[entry_offset]
                if ts_list_track == 0x00:  # Empty entry
                    continue
                if ts_list_track == 0xFF:  # Deleted entry
                    continue

                ts_list_sector = cat_data[entry_offset + 0x01]
                file_type = cat_data[entry_offset + 0x02]

                # Extract filename (30 chars, high bit set, space padded)
                name_bytes = cat_data[entry_offset + 0x03:entry_offset + 0x03 + 30]
                filename = ''.join(chr(b & 0x7F) for b in name_bytes).rstrip()

                # File length in sectors
                length_sectors = cat_data[entry_offset + 0x21] | (cat_data[entry_offset + 0x22] << 8)

                file_type_char = 'T'  # Text
                if file_type & 0x02:
                    file_type_char = 'A'  # Applesoft
                elif file_type & 0x01:
                    file_type_char = 'I'  # Integer BASIC
                elif file_type & 0x04:
                    file_type_char = 'B'  # Binary

                locked = '*' if file_type & 0x80 else ' '

                files.append({
                    'name': filename,
                    'type': file_type_char,
                    'locked': file_type & 0x80 != 0,
                    'sectors': length_sectors,
                    'ts_track': ts_list_track,
                    'ts_sector': ts_list_sector,
                    'raw_type': file_type
                })

            # Next catalog sector
            cat_track = cat_data[0x01]
            cat_sector = cat_data[0x02]

        return files

    def allocate_sector(self) -> Tuple[int, int]:
        """Allocate a free sector from VTOC. Returns (track, sector)."""
        vtoc = bytearray(self.read_sector(VTOC_TRACK, VTOC_SECTOR))

        # Search for free sector (start from track 18, work outward)
        for track in list(range(18, TRACKS)) + list(range(16, -1, -1)):
            if track == 17:  # Skip catalog track
                continue
            bitmap_offset = 0x38 + track * 4
            bitmap = (vtoc[bitmap_offset] |
                     (vtoc[bitmap_offset + 1] << 8))

            for sector in range(SECTORS_PER_TRACK):
                if bitmap & (1 << sector):
                    # Found free sector - mark as used
                    bitmap &= ~(1 << sector)
                    vtoc[bitmap_offset] = bitmap & 0xFF
                    vtoc[bitmap_offset + 1] = (bitmap >> 8) & 0xFF
                    self.write_sector(VTOC_TRACK, VTOC_SECTOR, vtoc)
                    return (track, sector)

        raise IOError("Disk full - no free sectors")

    def add_catalog_entry(self, filename: str, file_type: int,
                          ts_track: int, ts_sector: int, sectors: int) -> bool:
        """Add a file entry to the catalog."""
        vtoc = self.read_sector(VTOC_TRACK, VTOC_SECTOR)
        cat_track = vtoc[0x01]
        cat_sector = vtoc[0x02]

        while cat_track != 0:
            cat_data = bytearray(self.read_sector(cat_track, cat_sector))

            for i in range(7):
                entry_offset = 0x0B + i * 0x23
                if cat_data[entry_offset] == 0x00 or cat_data[entry_offset] == 0xFF:
                    # Found empty slot
                    cat_data[entry_offset] = ts_track
                    cat_data[entry_offset + 0x01] = ts_sector
                    cat_data[entry_offset + 0x02] = file_type

                    # Filename (30 chars, high bit set, space padded)
                    name = filename.upper()[:30].ljust(30)
                    for j, c in enumerate(name):
                        cat_data[entry_offset + 0x03 + j] = ord(c) | 0x80

                    # File length in sectors
                    cat_data[entry_offset + 0x21] = sectors & 0xFF
                    cat_data[entry_offset + 0x22] = (sectors >> 8) & 0xFF

                    self.write_sector(cat_track, cat_sector, cat_data)
                    return True

            cat_track = cat_data[0x01]
            cat_sector = cat_data[0x02]

        raise IOError("Catalog full")

    def save_basic_program(self, filename: str, basic_text: str):
        """Tokenize and save an Applesoft BASIC program to disk."""
        # Tokenize the BASIC program
        tokenized = tokenize_basic(basic_text)

        # DOS 3.3 Applesoft files need a 2-byte length prefix
        program_len = len(tokenized)
        file_data = bytes([program_len & 0xFF, (program_len >> 8) & 0xFF]) + tokenized

        # Create track/sector list
        ts_track, ts_sector = self.allocate_sector()
        first_ts_track, first_ts_sector = ts_track, ts_sector

        ts_list = bytearray(BYTES_PER_SECTOR)
        ts_list[0x00] = 0  # No next T/S list
        ts_list[0x01] = 0
        ts_list[0x05] = 0  # Sector offset in file
        ts_list[0x06] = 0

        # Write data sectors
        data_offset = 0
        ts_list_offset = 0x0C
        sector_count = 0

        while data_offset < len(file_data):
            # Allocate data sector
            data_track, data_sector = self.allocate_sector()

            # Add to T/S list
            ts_list[ts_list_offset] = data_track
            ts_list[ts_list_offset + 1] = data_sector
            ts_list_offset += 2

            # Write data
            chunk = file_data[data_offset:data_offset + BYTES_PER_SECTOR]
            self.write_sector(data_track, data_sector, chunk)

            data_offset += BYTES_PER_SECTOR
            sector_count += 1

        # Write T/S list
        self.write_sector(ts_track, ts_sector, ts_list)
        sector_count += 1  # Include T/S list sector

        # Add catalog entry
        self.add_catalog_entry(filename, FILE_TYPE_APPLESOFT_BASIC,
                               first_ts_track, first_ts_sector, sector_count)

        return sector_count


def tokenize_basic(source: str) -> bytes:
    """Tokenize Applesoft BASIC source code."""
    lines = source.strip().split('\n')
    output = bytearray()

    # Applesoft programs start at $0801
    address = 0x0801

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Parse line number
        parts = line.split(None, 1)
        if not parts:
            continue

        try:
            line_num = int(parts[0])
        except ValueError:
            continue

        line_text = parts[1] if len(parts) > 1 else ''

        # Tokenize the line
        tokenized_line = tokenize_line(line_text)

        # Calculate next line address
        line_length = 4 + len(tokenized_line) + 1  # ptr(2) + linenum(2) + tokens + null
        next_address = address + line_length

        # Write line: next_ptr (2 bytes) + line_num (2 bytes) + tokens + null
        output.append(next_address & 0xFF)
        output.append((next_address >> 8) & 0xFF)
        output.append(line_num & 0xFF)
        output.append((line_num >> 8) & 0xFF)
        output.extend(tokenized_line)
        output.append(0x00)  # Line terminator

        address = next_address

    # End of program marker (two zero bytes)
    output.append(0x00)
    output.append(0x00)

    return bytes(output)


def tokenize_line(line: str) -> bytes:
    """Tokenize a single BASIC line (without line number)."""
    output = bytearray()
    i = 0
    in_string = False
    in_rem = False

    while i < len(line):
        c = line[i]

        # Handle strings
        if c == '"':
            in_string = not in_string
            output.append(ord(c))
            i += 1
            continue

        if in_string or in_rem:
            output.append(ord(c))
            i += 1
            continue

        # Check for REM (rest of line is literal)
        if line[i:i+3].upper() == 'REM':
            output.append(BASIC_TOKENS['REM'])
            i += 3
            in_rem = True
            continue

        # Try to match keywords (longest first)
        matched = False
        for keyword in sorted(BASIC_TOKENS.keys(), key=len, reverse=True):
            if line[i:i+len(keyword)].upper() == keyword:
                output.append(BASIC_TOKENS[keyword])
                i += len(keyword)
                matched = True
                break

        if not matched:
            # Regular character
            output.append(ord(c.upper()) if c.isalpha() else ord(c))
            i += 1

    return bytes(output)


def create_game_disk(output_path: str, games: List[Tuple[str, str]]) -> str:
    """
    Create a DOS 3.3 disk with BASIC games.

    Args:
        output_path: Path for output .dsk file
        games: List of (filename, basic_source) tuples

    Returns:
        Path to created disk image
    """
    disk = DOS33Disk()
    disk.format(volume_num=254)

    for filename, source in games:
        disk.save_basic_program(filename, source)

    disk.save(output_path)
    return output_path


# Command-line interface
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: disktools.py <command> [args...]")
        print("Commands:")
        print("  create <output.dsk>              - Create blank formatted disk")
        print("  catalog <disk.dsk>               - List files on disk")
        print("  save <disk.dsk> <file.bas> [name] - Save BASIC program to disk")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'create':
        if len(sys.argv) < 3:
            print("Usage: disktools.py create <output.dsk>")
            sys.exit(1)
        disk = DOS33Disk()
        disk.format()
        disk.save(sys.argv[2])
        print(f"Created blank DOS 3.3 disk: {sys.argv[2]}")

    elif cmd == 'catalog':
        if len(sys.argv) < 3:
            print("Usage: disktools.py catalog <disk.dsk>")
            sys.exit(1)
        disk = DOS33Disk(sys.argv[2])
        files = disk.catalog()
        print(f"\nDISK VOLUME 254\n")
        for f in files:
            lock = '*' if f['locked'] else ' '
            print(f"{lock}{f['type']} {f['sectors']:03d} {f['name']}")
        print(f"\n{len(files)} FILES")

    elif cmd == 'save':
        if len(sys.argv) < 4:
            print("Usage: disktools.py save <disk.dsk> <file.bas> [name]")
            sys.exit(1)
        disk_path = sys.argv[2]
        bas_path = sys.argv[3]
        name = sys.argv[4] if len(sys.argv) > 4 else os.path.splitext(os.path.basename(bas_path))[0]

        with open(bas_path, 'r') as f:
            source = f.read()

        if os.path.exists(disk_path):
            disk = DOS33Disk(disk_path)
        else:
            disk = DOS33Disk()
            disk.format()

        sectors = disk.save_basic_program(name, source)
        disk.save(disk_path)
        print(f"Saved {name} ({sectors} sectors) to {disk_path}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
