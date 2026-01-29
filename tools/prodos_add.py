#!/usr/bin/env python3
"""
ProDOS Disk Tool - Add files to DOS-order disk images.
Handles .dsk/.do files which use DOS 3.3 sector interleaving.
"""

import sys
import struct
import os

SECTOR_SIZE = 256
SECTORS_PER_TRACK = 16
NUM_TRACKS = 35
BLOCK_SIZE = 512
NUM_BLOCKS = 280

# Sector interleave table for ProDOS in DOS-order disks (.dsk/.do)
PRODOS_INTERLEAVE = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15]

# Global flag for disk format
is_prodos_order = False

# ProDOS file types
FILETYPE_BIN = 0x06
FILETYPE_BAS = 0xFC
FILETYPE_SYS = 0xFF


def read_block(disk_data, block_num):
    """Read a ProDOS block from a disk image."""
    global is_prodos_order

    if is_prodos_order:
        # ProDOS order (.po) - blocks are sequential
        offset = block_num * BLOCK_SIZE
        return bytearray(disk_data[offset:offset + BLOCK_SIZE])
    else:
        # DOS order (.dsk/.do) - need interleaving
        track = block_num // 8
        block_in_track = block_num % 8

        sector1_logical = block_in_track * 2
        sector2_logical = block_in_track * 2 + 1

        sector1_physical = PRODOS_INTERLEAVE[sector1_logical]
        sector2_physical = PRODOS_INTERLEAVE[sector2_logical]

        offset1 = (track * SECTORS_PER_TRACK + sector1_physical) * SECTOR_SIZE
        offset2 = (track * SECTORS_PER_TRACK + sector2_physical) * SECTOR_SIZE

        block = bytearray(BLOCK_SIZE)
        block[0:256] = disk_data[offset1:offset1+256]
        block[256:512] = disk_data[offset2:offset2+256]

        return block


def write_block(disk_data, block_num, block):
    """Write a ProDOS block to a disk image."""
    global is_prodos_order

    if is_prodos_order:
        # ProDOS order (.po) - blocks are sequential
        offset = block_num * BLOCK_SIZE
        disk_data[offset:offset + BLOCK_SIZE] = block
    else:
        # DOS order (.dsk/.do) - need interleaving
        track = block_num // 8
        block_in_track = block_num % 8

        sector1_logical = block_in_track * 2
        sector2_logical = block_in_track * 2 + 1

        sector1_physical = PRODOS_INTERLEAVE[sector1_logical]
        sector2_physical = PRODOS_INTERLEAVE[sector2_logical]

        offset1 = (track * SECTORS_PER_TRACK + sector1_physical) * SECTOR_SIZE
        offset2 = (track * SECTORS_PER_TRACK + sector2_physical) * SECTOR_SIZE

        disk_data[offset1:offset1+256] = block[0:256]
        disk_data[offset2:offset2+256] = block[256:512]


def find_free_block(disk_data):
    """Find a free block in the bitmap."""
    # Get volume header to find bitmap location
    block2 = read_block(disk_data, 2)
    bitmap_block = struct.unpack('<H', block2[0x27:0x29])[0]

    bitmap = read_block(disk_data, bitmap_block)

    # Search for free block (bit set = free)
    for byte_idx in range(len(bitmap)):
        if bitmap[byte_idx] != 0:
            for bit_idx in range(8):
                if bitmap[byte_idx] & (1 << (7 - bit_idx)):
                    block = byte_idx * 8 + bit_idx
                    if block >= 7 and block < NUM_BLOCKS:
                        return block
    return None


def mark_block_used(disk_data, block_num):
    """Mark a block as used in the bitmap."""
    block2 = read_block(disk_data, 2)
    bitmap_block = struct.unpack('<H', block2[0x27:0x29])[0]

    bitmap = read_block(disk_data, bitmap_block)
    byte_idx = block_num // 8
    bit_idx = 7 - (block_num % 8)
    bitmap[byte_idx] &= ~(1 << bit_idx)

    write_block(disk_data, bitmap_block, bitmap)


def find_directory_slot(disk_data):
    """Find a free directory entry slot."""
    dir_block = 2
    while dir_block != 0:
        block = read_block(disk_data, dir_block)
        next_block = struct.unpack('<H', block[2:4])[0]

        offset = 4 + (0x27 if dir_block == 2 else 0)

        while offset + 0x27 <= BLOCK_SIZE:
            storage_type = block[offset] >> 4
            if storage_type == 0:
                return (dir_block, offset)
            offset += 0x27

        dir_block = next_block

    return None


def add_file(disk_data, file_data, prodos_name, file_type, aux_type):
    """Add a file to the disk."""
    file_size = len(file_data)
    prodos_name = prodos_name[:15].upper()

    print(f"Adding file: {prodos_name}")
    print(f"  Size: {file_size} bytes")
    print(f"  Type: ${file_type:02X}, Aux: ${aux_type:04X}")

    # Calculate blocks needed
    blocks_needed = (file_size + BLOCK_SIZE - 1) // BLOCK_SIZE
    if blocks_needed == 0:
        blocks_needed = 1

    if blocks_needed == 1:
        # Seedling file (single data block)
        storage_type = 0x10
        key_block = find_free_block(disk_data)
        if key_block is None:
            print("  Error: No free blocks!")
            return False
        mark_block_used(disk_data, key_block)

        data_block = bytearray(BLOCK_SIZE)
        data_block[:file_size] = file_data
        write_block(disk_data, key_block, data_block)
        blocks_used = 1

    elif blocks_needed <= 256:
        # Sapling file (index block + data blocks)
        storage_type = 0x20

        index_block = find_free_block(disk_data)
        if index_block is None:
            print("  Error: No free blocks!")
            return False
        mark_block_used(disk_data, index_block)

        index_data = bytearray(BLOCK_SIZE)
        key_block = index_block

        offset = 0
        for i in range(blocks_needed):
            data_block_num = find_free_block(disk_data)
            if data_block_num is None:
                print("  Error: Not enough free blocks!")
                return False
            mark_block_used(disk_data, data_block_num)

            index_data[i] = data_block_num & 0xFF
            index_data[256 + i] = (data_block_num >> 8) & 0xFF

            data_block = bytearray(BLOCK_SIZE)
            chunk = file_data[offset:offset + BLOCK_SIZE]
            data_block[:len(chunk)] = chunk
            write_block(disk_data, data_block_num, data_block)
            offset += BLOCK_SIZE

        write_block(disk_data, index_block, index_data)
        blocks_used = blocks_needed + 1
    else:
        print("  Error: File too large!")
        return False

    # Find directory slot
    slot = find_directory_slot(disk_data)
    if slot is None:
        print("  Error: No free directory slots!")
        return False

    dir_block_num, offset = slot

    # Create directory entry
    entry = bytearray(0x27)
    entry[0x00] = storage_type | len(prodos_name)

    for i, c in enumerate(prodos_name):
        entry[0x01 + i] = ord(c)

    entry[0x10] = file_type
    entry[0x11] = key_block & 0xFF
    entry[0x12] = (key_block >> 8) & 0xFF
    entry[0x13] = blocks_used & 0xFF
    entry[0x14] = (blocks_used >> 8) & 0xFF
    entry[0x15] = file_size & 0xFF
    entry[0x16] = (file_size >> 8) & 0xFF
    entry[0x17] = (file_size >> 16) & 0xFF

    # Date/time
    entry[0x18] = 0x21
    entry[0x19] = 0x32
    entry[0x1A] = 0x00
    entry[0x1B] = 0x0C

    entry[0x1C] = 0x00
    entry[0x1D] = 0x00
    entry[0x1E] = 0xC3

    entry[0x1F] = aux_type & 0xFF
    entry[0x20] = (aux_type >> 8) & 0xFF

    entry[0x21] = 0x21
    entry[0x22] = 0x32
    entry[0x23] = 0x00
    entry[0x24] = 0x0C

    entry[0x25] = 0x02
    entry[0x26] = 0x00

    # Write entry to directory
    dir_block = read_block(disk_data, dir_block_num)
    dir_block[offset:offset + 0x27] = entry
    write_block(disk_data, dir_block_num, dir_block)

    # Update file count
    block2 = read_block(disk_data, 2)
    file_count = struct.unpack('<H', block2[0x25:0x27])[0]
    file_count += 1
    block2[0x25:0x27] = struct.pack('<H', file_count)
    write_block(disk_data, 2, block2)

    print(f"  Added successfully to block {key_block}")
    return True


def detect_disk_format(disk_file):
    """Detect disk format based on extension and content."""
    global is_prodos_order
    ext = os.path.splitext(disk_file)[1].lower()

    if ext == '.po':
        is_prodos_order = True
        print(f"Detected ProDOS-order disk (.po)")
    else:
        is_prodos_order = False
        print(f"Detected DOS-order disk (.dsk/.do)")


def main():
    global is_prodos_order

    if len(sys.argv) < 5:
        print("ProDOS Add File Tool")
        print()
        print("Usage: prodos_add.py <disk.dsk|disk.po> <local_file> <prodos_name> <type> [aux]")
        print()
        print("Supports both DOS-order (.dsk/.do) and ProDOS-order (.po) disk images")
        print("File types: BIN=06 BAS=FC SYS=FF")
        print("Aux type: load address for BIN, $0801 for BAS")
        sys.exit(1)

    disk_file = sys.argv[1]
    local_file = sys.argv[2]
    prodos_name = sys.argv[3]
    file_type = int(sys.argv[4], 16)
    aux_type = int(sys.argv[5], 16) if len(sys.argv) > 5 else 0x0000

    if not os.path.exists(disk_file):
        print(f"Error: Disk file not found: {disk_file}")
        sys.exit(1)

    if not os.path.exists(local_file):
        print(f"Error: Local file not found: {local_file}")
        sys.exit(1)

    # Detect disk format from extension
    detect_disk_format(disk_file)

    with open(disk_file, 'rb') as f:
        disk_data = bytearray(f.read())

    with open(local_file, 'rb') as f:
        file_data = f.read()

    if add_file(disk_data, file_data, prodos_name, file_type, aux_type):
        with open(disk_file, 'wb') as f:
            f.write(disk_data)
        print(f"Saved changes to {disk_file}")


if __name__ == "__main__":
    main()
