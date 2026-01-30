#!/usr/bin/env python3
"""
Make Agent Disk - Create a contiguous, bootable agent disk

Creates a fresh ProDOS disk with files allocated contiguously,
verifies the structure, and optionally tests booting in the emulator.

Usage:
    python3 make_agent_disk.py [output.dsk] [--test]
"""

import sys
import os
import struct
import subprocess
import tempfile
import time

# Add parent dir for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SECTOR_SIZE = 256
SECTORS_PER_TRACK = 16
NUM_TRACKS = 35
BLOCK_SIZE = 512
NUM_BLOCKS = 280
DISK_SIZE = NUM_TRACKS * SECTORS_PER_TRACK * SECTOR_SIZE

# Sector interleave table for ProDOS in DOS-order disks
PRODOS_INTERLEAVE = [0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15]

# ProDOS file types
FILETYPE_BIN = 0x06
FILETYPE_BAS = 0xFC
FILETYPE_SYS = 0xFF


def read_block(disk_data, block_num, prodos_order=False):
    """Read a ProDOS block from a disk image."""
    if prodos_order:
        offset = block_num * BLOCK_SIZE
        return bytearray(disk_data[offset:offset + BLOCK_SIZE])
    else:
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


def write_block(disk_data, block_num, block, prodos_order=False):
    """Write a ProDOS block to a disk image."""
    if prodos_order:
        offset = block_num * BLOCK_SIZE
        disk_data[offset:offset + BLOCK_SIZE] = block
    else:
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


def copy_blocks(src_data, dst_data, start_block, end_block, prodos_order=False):
    """Copy a range of blocks from source to destination."""
    for block in range(start_block, end_block):
        block_data = read_block(src_data, block, prodos_order)
        write_block(dst_data, block, block_data, prodos_order)


def get_file_blocks(disk_data, prodos_name, prodos_order=False):
    """Get list of blocks used by a file."""
    prodos_name = prodos_name.upper()
    dir_block = 2

    while dir_block != 0:
        block = read_block(disk_data, dir_block, prodos_order)
        next_block = struct.unpack('<H', block[2:4])[0]
        offset = 4 + (0x27 if dir_block == 2 else 0)

        while offset + 0x27 <= BLOCK_SIZE:
            storage_type = block[offset] >> 4
            if storage_type > 0 and storage_type < 0x0F:
                name_len = block[offset] & 0x0F
                name = bytes(block[offset + 1:offset + 1 + name_len]).decode('ascii', errors='replace')

                if name == prodos_name:
                    key_block = struct.unpack('<H', block[offset + 0x11:offset + 0x13])[0]
                    file_size = struct.unpack('<I', block[offset + 0x15:offset + 0x18] + b'\x00')[0]
                    file_type = block[offset + 0x10]
                    aux_type = struct.unpack('<H', block[offset + 0x1F:offset + 0x21])[0]

                    blocks = []

                    if storage_type == 0x01:  # Seedling
                        blocks = [key_block]
                    elif storage_type == 0x02:  # Sapling
                        blocks = [key_block]
                        index_data = read_block(disk_data, key_block, prodos_order)
                        num_data_blocks = (file_size + BLOCK_SIZE - 1) // BLOCK_SIZE
                        for i in range(num_data_blocks):
                            data_block = index_data[i] | (index_data[256 + i] << 8)
                            blocks.append(data_block)

                    return {
                        'name': name,
                        'type': file_type,
                        'aux': aux_type,
                        'size': file_size,
                        'storage_type': storage_type,
                        'key_block': key_block,
                        'blocks': blocks
                    }

            offset += 0x27
        dir_block = next_block

    return None


def extract_file(disk_data, prodos_name, prodos_order=False):
    """Extract a file's contents from disk."""
    info = get_file_blocks(disk_data, prodos_name, prodos_order)
    if not info:
        return None, None

    if info['storage_type'] == 0x01:  # Seedling
        data = read_block(disk_data, info['key_block'], prodos_order)[:info['size']]
    elif info['storage_type'] == 0x02:  # Sapling
        index_data = read_block(disk_data, info['key_block'], prodos_order)
        data = bytearray()
        remaining = info['size']
        i = 0
        while remaining > 0:
            data_block = index_data[i] | (index_data[256 + i] << 8)
            chunk_size = min(BLOCK_SIZE, remaining)
            data.extend(read_block(disk_data, data_block, prodos_order)[:chunk_size])
            remaining -= chunk_size
            i += 1
    else:
        return None, None

    return bytes(data), info


def create_fresh_prodos_disk(volume_name="AGENT"):
    """Create a fresh formatted ProDOS disk."""
    disk_data = bytearray(DISK_SIZE)
    volume_name = volume_name[:15].upper()

    # Block 0 and 1 are boot blocks - leave empty for now (will copy from template)

    # Block 2: Volume Directory Header
    vdh = bytearray(BLOCK_SIZE)
    vdh[0:2] = struct.pack('<H', 0)  # No previous
    vdh[2:4] = struct.pack('<H', 3)  # Next block
    vdh[4] = 0xF0 | len(volume_name)  # Storage type | name length
    for i, c in enumerate(volume_name):
        vdh[5 + i] = ord(c)
    vdh[0x1C:0x20] = bytes([0x21, 0x32, 0x00, 0x0C])  # Creation date
    vdh[0x20] = 0x00  # Version
    vdh[0x21] = 0x00  # Min version
    vdh[0x22] = 0xC3  # Access
    vdh[0x23] = 0x27  # Entry length
    vdh[0x24] = 0x0D  # Entries per block
    vdh[0x25:0x27] = struct.pack('<H', 0)  # File count
    vdh[0x27:0x29] = struct.pack('<H', 6)  # Bitmap block
    vdh[0x29:0x2B] = struct.pack('<H', NUM_BLOCKS)  # Total blocks
    write_block(disk_data, 2, vdh)

    # Blocks 3-5: Additional directory blocks
    for block in range(3, 6):
        db = bytearray(BLOCK_SIZE)
        db[0:2] = struct.pack('<H', block - 1)
        db[2:4] = struct.pack('<H', block + 1 if block < 5 else 0)
        write_block(disk_data, block, db)

    # Block 6: Volume bitmap
    bitmap = bytearray(BLOCK_SIZE)
    for i in range(NUM_BLOCKS // 8 + 1):
        if i < BLOCK_SIZE:
            bitmap[i] = 0xFF
    # Mark blocks 0-6 as used
    for block in range(7):
        byte_idx = block // 8
        bit_idx = 7 - (block % 8)
        bitmap[byte_idx] &= ~(1 << bit_idx)
    write_block(disk_data, 6, bitmap)

    return disk_data


def add_file_contiguous(disk_data, file_data, prodos_name, file_type, aux_type, prodos_order=False):
    """Add a file to disk, allocating blocks contiguously."""
    file_size = len(file_data)
    prodos_name = prodos_name[:15].upper()

    # Calculate blocks needed
    blocks_needed = (file_size + BLOCK_SIZE - 1) // BLOCK_SIZE
    if blocks_needed == 0:
        blocks_needed = 1

    # Find contiguous free blocks
    block2 = read_block(disk_data, 2, prodos_order)
    bitmap_block = struct.unpack('<H', block2[0x27:0x29])[0]
    bitmap = read_block(disk_data, bitmap_block, prodos_order)

    # Find first run of contiguous free blocks
    start_block = None
    run_length = 0

    # Need +1 for index block if sapling
    total_blocks_needed = blocks_needed + (1 if blocks_needed > 1 else 0)

    for block in range(7, NUM_BLOCKS):
        byte_idx = block // 8
        bit_idx = 7 - (block % 8)
        if bitmap[byte_idx] & (1 << bit_idx):  # Free
            if start_block is None:
                start_block = block
            run_length += 1
            if run_length >= total_blocks_needed:
                break
        else:
            start_block = None
            run_length = 0

    if run_length < total_blocks_needed:
        print(f"  Error: Cannot find {total_blocks_needed} contiguous blocks!")
        return False, []

    # Allocate blocks
    allocated = []
    for i in range(total_blocks_needed):
        block = start_block + i
        byte_idx = block // 8
        bit_idx = 7 - (block % 8)
        bitmap[byte_idx] &= ~(1 << bit_idx)
        allocated.append(block)

    write_block(disk_data, bitmap_block, bitmap, prodos_order)

    # Write file data
    if blocks_needed == 1:
        # Seedling
        storage_type = 0x10
        key_block = allocated[0]
        data_block = bytearray(BLOCK_SIZE)
        data_block[:file_size] = file_data
        write_block(disk_data, key_block, data_block, prodos_order)
        blocks_used = 1
    else:
        # Sapling
        storage_type = 0x20
        key_block = allocated[0]
        index_data = bytearray(BLOCK_SIZE)

        for i in range(blocks_needed):
            data_block_num = allocated[1 + i]
            index_data[i] = data_block_num & 0xFF
            index_data[256 + i] = (data_block_num >> 8) & 0xFF

            data_block = bytearray(BLOCK_SIZE)
            offset = i * BLOCK_SIZE
            chunk = file_data[offset:offset + BLOCK_SIZE]
            data_block[:len(chunk)] = chunk
            write_block(disk_data, data_block_num, data_block, prodos_order)

        write_block(disk_data, key_block, index_data, prodos_order)
        blocks_used = blocks_needed + 1

    # Find directory slot
    dir_block = 2
    slot = None
    while dir_block != 0:
        block = read_block(disk_data, dir_block, prodos_order)
        next_block = struct.unpack('<H', block[2:4])[0]
        offset = 4 + (0x27 if dir_block == 2 else 0)

        while offset + 0x27 <= BLOCK_SIZE:
            if (block[offset] >> 4) == 0:
                slot = (dir_block, offset)
                break
            offset += 0x27

        if slot:
            break
        dir_block = next_block

    if slot is None:
        print("  Error: No free directory slots!")
        return False, []

    dir_block_num, offset = slot

    # Create directory entry
    dir_block = read_block(disk_data, dir_block_num, prodos_order)
    entry = dir_block[offset:offset + 0x27]

    entry[0x00] = storage_type | len(prodos_name)
    for i, c in enumerate(prodos_name):
        entry[0x01 + i] = ord(c)
    for i in range(len(prodos_name), 15):
        entry[0x01 + i] = 0

    entry[0x10] = file_type
    entry[0x11] = key_block & 0xFF
    entry[0x12] = (key_block >> 8) & 0xFF
    entry[0x13] = blocks_used & 0xFF
    entry[0x14] = (blocks_used >> 8) & 0xFF
    entry[0x15] = file_size & 0xFF
    entry[0x16] = (file_size >> 8) & 0xFF
    entry[0x17] = (file_size >> 16) & 0xFF
    entry[0x18:0x1C] = bytes([0x21, 0x32, 0x00, 0x0C])
    entry[0x1C] = 0x00
    entry[0x1D] = 0x00
    entry[0x1E] = 0xC3
    entry[0x1F] = aux_type & 0xFF
    entry[0x20] = (aux_type >> 8) & 0xFF
    entry[0x21:0x25] = bytes([0x21, 0x32, 0x00, 0x0C])
    entry[0x25] = 0x02
    entry[0x26] = 0x00

    dir_block[offset:offset + 0x27] = entry
    write_block(disk_data, dir_block_num, dir_block, prodos_order)

    # Update file count
    block2 = read_block(disk_data, 2, prodos_order)
    file_count = struct.unpack('<H', block2[0x25:0x27])[0]
    file_count += 1
    block2[0x25:0x27] = struct.pack('<H', file_count)
    write_block(disk_data, 2, block2, prodos_order)

    return True, allocated


def verify_contiguous(disk_data, prodos_name, prodos_order=False):
    """Verify that a file's blocks are contiguous."""
    info = get_file_blocks(disk_data, prodos_name, prodos_order)
    if not info:
        return False, "File not found"

    blocks = info['blocks']
    if len(blocks) <= 1:
        return True, "Single block"

    # Check if blocks are sequential
    for i in range(len(blocks) - 1):
        if blocks[i+1] != blocks[i] + 1:
            return False, f"Gap at blocks {blocks[i]} -> {blocks[i+1]}"

    return True, f"Contiguous: blocks {blocks[0]}-{blocks[-1]}"


def list_files(disk_data, prodos_order=False):
    """List files on disk with their block allocation."""
    files = []
    dir_block = 2

    while dir_block != 0:
        block = read_block(disk_data, dir_block, prodos_order)
        next_block = struct.unpack('<H', block[2:4])[0]
        offset = 4 + (0x27 if dir_block == 2 else 0)

        while offset + 0x27 <= BLOCK_SIZE:
            storage_type = block[offset] >> 4
            if storage_type > 0 and storage_type < 0x0F:
                name_len = block[offset] & 0x0F
                name = bytes(block[offset + 1:offset + 1 + name_len]).decode('ascii', errors='replace')
                key_block = struct.unpack('<H', block[offset + 0x11:offset + 0x13])[0]
                blocks_used = struct.unpack('<H', block[offset + 0x13:offset + 0x15])[0]
                file_size = struct.unpack('<I', block[offset + 0x15:offset + 0x18] + b'\x00')[0]
                file_type = block[offset + 0x10]

                files.append({
                    'name': name,
                    'type': file_type,
                    'size': file_size,
                    'blocks': blocks_used,
                    'key': key_block,
                    'storage': storage_type
                })

            offset += 0x27
        dir_block = next_block

    return files


def test_boot(disk_path, timeout=10):
    """Test booting the disk in Bobbin emulator."""
    bobbin_path = os.path.join(os.path.dirname(__file__), '..', 'bobbin', 'src', 'bobbin')
    socket_path = '/tmp/bobbin_test.sock'

    if not os.path.exists(bobbin_path):
        print(f"  Bobbin not found at {bobbin_path}")
        return False

    # Remove old socket
    if os.path.exists(socket_path):
        os.remove(socket_path)

    # Start emulator
    proc = subprocess.Popen([
        bobbin_path, '--simple', '--remain',
        '--control-socket', socket_path,
        '-m', 'enhanced',
        '--disk', disk_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for boot
    time.sleep(3)

    try:
        # Connect to control socket
        import socket
        import json

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)

        connected = False
        for _ in range(20):
            try:
                sock.connect(socket_path)
                connected = True
                break
            except:
                time.sleep(0.25)

        if not connected:
            print("  Failed to connect to emulator")
            proc.kill()
            return False

        # Read screen
        sock.send(b'{"cmd":"screen"}\n')
        response = b''
        while b'\n' not in response:
            response += sock.recv(4096)

        data = json.loads(response.decode())
        lines = data.get('lines', [])

        # Check for ProDOS or BASIC prompt
        screen_text = '\n'.join(lines)

        if 'UNABLE' in screen_text or 'ERROR' in screen_text:
            print("  Boot failed - disk error")
            sock.send(b'{"cmd":"quit"}\n')
            sock.close()
            proc.wait(timeout=5)
            return False

        if ']' in screen_text or 'PRODOS' in screen_text.upper() or 'BASIC' in screen_text.upper():
            print("  Boot successful!")
            sock.send(b'{"cmd":"quit"}\n')
            sock.close()
            proc.wait(timeout=5)
            return True

        print("  Boot result unclear")
        print(f"  Screen: {screen_text[:200]}")
        sock.send(b'{"cmd":"quit"}\n')
        sock.close()
        proc.wait(timeout=5)
        return True

    except Exception as e:
        print(f"  Boot test error: {e}")
        proc.kill()
        return False


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)

    # Parse args
    output_path = os.path.join(project_dir, 'disks', 'agent_contiguous.dsk')
    test_boot_flag = False

    for arg in sys.argv[1:]:
        if arg == '--test':
            test_boot_flag = True
        elif arg == '--help':
            print(__doc__)
            sys.exit(0)
        else:
            output_path = arg

    # Source files - use ProDOS 2.4 master for boot blocks and system files
    template_disk = os.path.join(project_dir, 'disks', 'ProDOS_2_4.dsk')
    agent_bin = os.path.join(project_dir, 'build', 'AGENT.BIN')

    print("=" * 60)
    print("Make Agent Disk - Contiguous Allocation")
    print("=" * 60)

    # Check requirements
    if not os.path.exists(template_disk):
        print(f"Error: Template disk not found: {template_disk}")
        sys.exit(1)

    if not os.path.exists(agent_bin):
        print(f"Error: Agent binary not found: {agent_bin}")
        print("Run 'make agent' first")
        sys.exit(1)

    # Load template disk
    print(f"\n1. Loading template disk: {template_disk}")
    with open(template_disk, 'rb') as f:
        template_data = bytearray(f.read())

    # Extract system files from template
    print("\n2. Extracting system files...")
    prodos_data, prodos_info = extract_file(template_data, "PRODOS")
    if prodos_data:
        print(f"   PRODOS: {len(prodos_data)} bytes")
    else:
        print("   Error: Could not extract PRODOS")
        sys.exit(1)

    basic_data, basic_info = extract_file(template_data, "BASIC.SYSTEM")
    if basic_data:
        print(f"   BASIC.SYSTEM: {len(basic_data)} bytes")
    else:
        print("   Error: Could not extract BASIC.SYSTEM")
        sys.exit(1)

    # Load agent binary
    with open(agent_bin, 'rb') as f:
        agent_data = f.read()
    print(f"   AGENT.BIN: {len(agent_data)} bytes")

    # Create fresh disk
    print("\n3. Creating fresh ProDOS disk...")
    disk_data = create_fresh_prodos_disk("AGENT")

    # Copy boot blocks from template
    print("   Copying boot blocks...")
    copy_blocks(template_data, disk_data, 0, 2)

    # Add files in order (contiguous allocation)
    print("\n4. Adding files with contiguous allocation...")

    success, blocks = add_file_contiguous(disk_data, prodos_data, "PRODOS", FILETYPE_SYS, 0x0000)
    print(f"   PRODOS: blocks {blocks[0]}-{blocks[-1] if blocks else 'N/A'}")

    success, blocks = add_file_contiguous(disk_data, basic_data, "BASIC.SYSTEM", FILETYPE_SYS, 0x2000)
    print(f"   BASIC.SYSTEM: blocks {blocks[0]}-{blocks[-1] if blocks else 'N/A'}")

    success, blocks = add_file_contiguous(disk_data, agent_data, "AGENT.BIN", FILETYPE_BIN, 0x6000)
    print(f"   AGENT.BIN: blocks {blocks[0]}-{blocks[-1] if blocks else 'N/A'}")

    # Verify contiguous allocation
    print("\n5. Verifying contiguous allocation...")
    for name in ["PRODOS", "BASIC.SYSTEM", "AGENT.BIN"]:
        ok, msg = verify_contiguous(disk_data, name)
        status = "OK" if ok else "FAIL"
        print(f"   {name}: {status} - {msg}")

    # List files
    print("\n6. Disk catalog:")
    files = list_files(disk_data)
    print("   NAME            TYPE  BLOCKS  SIZE     KEY")
    print("   " + "-" * 50)
    for f in files:
        type_names = {0x06: 'BIN', 0xFC: 'BAS', 0xFF: 'SYS'}
        type_str = type_names.get(f['type'], f"${f['type']:02X}")
        print(f"   {f['name']:15} {type_str:4}  {f['blocks']:5}  {f['size']:7}  {f['key']}")

    # Save disk
    print(f"\n7. Saving disk: {output_path}")
    with open(output_path, 'wb') as f:
        f.write(disk_data)
    print(f"   Created {len(disk_data)} byte disk image")

    # Test boot if requested
    if test_boot_flag:
        print("\n8. Testing boot in emulator...")
        if test_boot(output_path):
            print("   Boot test PASSED")
        else:
            print("   Boot test FAILED")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
