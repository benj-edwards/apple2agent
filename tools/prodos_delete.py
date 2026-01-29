#!/usr/bin/env python3
"""
ProDOS Disk Tool - Delete files from DOS-order disk images.
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


def list_files(disk_data):
    """List all files on the disk."""
    block2 = read_block(disk_data, 2)

    # Parse volume header
    vol_storage = block2[4]
    vol_name_len = vol_storage & 0x0F
    vol_name = bytes(block2[5:5+vol_name_len]).decode('ascii', errors='replace')

    print(f"Volume: /{vol_name}")
    print("-" * 50)

    files = []

    # Scan directory blocks
    dir_block = 2
    while dir_block != 0:
        block = read_block(disk_data, dir_block)
        next_block = struct.unpack('<H', block[2:4])[0]

        # Start offset depends on block
        offset = 4 + (0x27 if dir_block == 2 else 0)  # Skip volume header in block 2

        while offset + 0x27 <= BLOCK_SIZE:
            storage_type = block[offset] >> 4
            name_len = block[offset] & 0x0F

            if storage_type > 0 and storage_type < 0x0F and name_len > 0:
                name = bytes(block[offset+1:offset+1+name_len]).decode('ascii', errors='replace')
                ftype = block[offset + 0x10]

                type_names = {0x04: 'TXT', 0x06: 'BIN', 0xFC: 'BAS', 0xFF: 'SYS'}
                type_str = type_names.get(ftype, f'${ftype:02X}')

                files.append({
                    'name': name,
                    'type': type_str,
                    'storage': storage_type,
                    'block': dir_block,
                    'offset': offset
                })
                print(f"  {name:15s} {type_str:4s}")

            offset += 0x27

        dir_block = next_block

    return files


def mark_block_free(disk_data, block_num):
    """Mark a block as free in the bitmap."""
    block2 = read_block(disk_data, 2)
    bitmap_block = struct.unpack('<H', block2[0x27:0x29])[0]

    bitmap = read_block(disk_data, bitmap_block)
    byte_idx = block_num // 8
    bit_idx = 7 - (block_num % 8)
    bitmap[byte_idx] |= (1 << bit_idx)  # Set bit = free

    write_block(disk_data, bitmap_block, bitmap)


def free_file_blocks(disk_data, storage_type, key_block):
    """Free all blocks used by a file."""
    if storage_type == 0x1:  # Seedling - single data block
        mark_block_free(disk_data, key_block)
        return 1

    elif storage_type == 0x2:  # Sapling - index + data blocks
        index = read_block(disk_data, key_block)
        freed = 0
        for i in range(256):
            data_block = index[i]
            if data_block != 0:
                mark_block_free(disk_data, data_block)
                freed += 1
        mark_block_free(disk_data, key_block)  # Free index block
        return freed + 1

    elif storage_type == 0x3:  # Tree - master index + subindex + data
        master = read_block(disk_data, key_block)
        freed = 0
        for i in range(256):
            sub_block = master[i]
            if sub_block != 0:
                subindex = read_block(disk_data, sub_block)
                for j in range(256):
                    data_block = subindex[j]
                    if data_block != 0:
                        mark_block_free(disk_data, data_block)
                        freed += 1
                mark_block_free(disk_data, sub_block)
                freed += 1
        mark_block_free(disk_data, key_block)
        return freed + 1

    return 0


def delete_file(disk_data, filename):
    """Delete a file from the disk by clearing its directory entry and freeing blocks."""
    filename = filename.upper()

    # Find the file
    dir_block = 2
    while dir_block != 0:
        block = read_block(disk_data, dir_block)
        next_block = struct.unpack('<H', block[2:4])[0]

        offset = 4 + (0x27 if dir_block == 2 else 0)

        while offset + 0x27 <= BLOCK_SIZE:
            storage_type = block[offset] >> 4
            name_len = block[offset] & 0x0F

            if storage_type > 0 and storage_type < 0x0F and name_len > 0:
                name = bytes(block[offset+1:offset+1+name_len]).decode('ascii', errors='replace')

                if name.upper() == filename:
                    print(f"Found {name} at block {dir_block}, offset {offset}")

                    # Get key block for freeing
                    key_block = struct.unpack('<H', block[offset+0x11:offset+0x13])[0]

                    # Free the file's blocks
                    blocks_freed = free_file_blocks(disk_data, storage_type, key_block)
                    print(f"  Freed {blocks_freed} blocks")

                    # Clear the storage type (marks entry as deleted)
                    block[offset] = 0x00

                    # Write the modified block back
                    write_block(disk_data, dir_block, block)

                    # Update file count in volume header
                    block2 = read_block(disk_data, 2)
                    file_count = struct.unpack('<H', block2[0x25:0x27])[0]
                    if file_count > 0:
                        file_count -= 1
                        block2[0x25:0x27] = struct.pack('<H', file_count)
                        write_block(disk_data, 2, block2)

                    print(f"Deleted {name}")
                    return True

            offset += 0x27

        dir_block = next_block

    print(f"File not found: {filename}")
    return False


def detect_disk_format(disk_file):
    """Detect disk format based on extension."""
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

    if len(sys.argv) < 2:
        print("ProDOS Delete Tool - Remove files from disk images")
        print()
        print("Supports both DOS-order (.dsk/.do) and ProDOS-order (.po) disk images")
        print()
        print("Usage:")
        print("  prodos_delete.py <disk.dsk|disk.po> list           - List files")
        print("  prodos_delete.py <disk.dsk|disk.po> delete <name>  - Delete file")
        sys.exit(1)

    disk_file = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else 'list'

    if not os.path.exists(disk_file):
        print(f"Error: File not found: {disk_file}")
        sys.exit(1)

    # Detect disk format from extension
    detect_disk_format(disk_file)

    with open(disk_file, 'rb') as f:
        disk_data = bytearray(f.read())

    if len(disk_data) != 143360:
        print(f"Error: Invalid disk size: {len(disk_data)} (expected 143360)")
        sys.exit(1)

    if command == 'list':
        list_files(disk_data)

    elif command == 'delete':
        if len(sys.argv) < 4:
            print("Usage: prodos_delete.py <disk.dsk|disk.po> delete <filename>")
            sys.exit(1)

        filename = sys.argv[3]
        if delete_file(disk_data, filename):
            with open(disk_file, 'wb') as f:
                f.write(disk_data)
            print(f"Saved changes to {disk_file}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
