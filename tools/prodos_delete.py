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

# Sector interleave table for ProDOS in DOS-order disks
PRODOS_INTERLEAVE = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15]


def read_block(disk_data, block_num):
    """Read a ProDOS block from a DOS-order disk image."""
    track = block_num // 8
    block_in_track = block_num % 8

    sector1_logical = block_in_track * 2
    sector2_logical = block_in_track * 2 + 1

    sector1_physical = PRODOS_INTERLEAVE[sector1_logical]
    sector2_physical = PRODOS_INTERLEAVE[sector2_logical]

    offset1 = (track * SECTORS_PER_TRACK + sector1_physical) * SECTOR_SIZE
    offset2 = (track * SECTORS_PER_TRACK + sector2_physical) * SECTOR_SIZE

    # Block is sector1 first, then sector2
    block = bytearray(BLOCK_SIZE)
    block[0:256] = disk_data[offset1:offset1+256]
    block[256:512] = disk_data[offset2:offset2+256]

    return block


def write_block(disk_data, block_num, block):
    """Write a ProDOS block to a DOS-order disk image."""
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


def delete_file(disk_data, filename):
    """Delete a file from the disk by clearing its directory entry."""
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


def main():
    if len(sys.argv) < 2:
        print("ProDOS Delete Tool - Remove files from DOS-order disk images")
        print()
        print("Usage:")
        print("  prodos_delete.py <disk.dsk> list           - List files")
        print("  prodos_delete.py <disk.dsk> delete <name>  - Delete file")
        sys.exit(1)

    disk_file = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else 'list'

    if not os.path.exists(disk_file):
        print(f"Error: File not found: {disk_file}")
        sys.exit(1)

    with open(disk_file, 'rb') as f:
        disk_data = bytearray(f.read())

    if len(disk_data) != 143360:
        print(f"Error: Invalid disk size: {len(disk_data)} (expected 143360)")
        sys.exit(1)

    if command == 'list':
        list_files(disk_data)

    elif command == 'delete':
        if len(sys.argv) < 4:
            print("Usage: prodos_delete.py <disk.dsk> delete <filename>")
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
