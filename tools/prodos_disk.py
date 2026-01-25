#!/usr/bin/env python3
"""
ProDOS Disk Image Tool

Create and manipulate ProDOS disk images for Apple II.
Supports adding binary files to a ProDOS disk.
"""

import sys
import struct
import os

BLOCK_SIZE = 512
BLOCKS_140K = 280
BLOCKS_800K = 1600

# ProDOS file types
FILETYPE_TXT = 0x04
FILETYPE_BIN = 0x06
FILETYPE_SYS = 0xFF
FILETYPE_BAS = 0xFC

# ProDOS access permissions
ACCESS_READ = 0x01
ACCESS_WRITE = 0x02
ACCESS_DESTROY = 0x80
ACCESS_RENAME = 0x40
ACCESS_FULL = 0xC3


class ProDOSDisk:
    """Manipulate ProDOS disk images."""

    def __init__(self, filename):
        self.filename = filename
        self.data = None
        self.block_count = 0

    def create(self, volume_name, blocks=BLOCKS_140K):
        """Create a new formatted ProDOS disk image."""
        self.block_count = blocks
        self.data = bytearray(BLOCK_SIZE * blocks)
        volume_name = volume_name[:15].upper()

        # Volume Directory Header (Block 2)
        vdh = self._get_block(2)

        # Previous/next block pointers
        vdh[0:2] = struct.pack('<H', 0)  # No previous
        vdh[2:4] = struct.pack('<H', 3)  # Next is block 3

        # Volume directory header entry
        # Storage type $F (volume header) | name length
        vdh[4] = 0xF0 | len(volume_name)

        # Volume name
        for i, c in enumerate(volume_name):
            vdh[5 + i] = ord(c)

        # Reserved (8 bytes)
        # Creation date/time (4 bytes at offset 0x1C)
        # Set to a reasonable date
        vdh[0x1C] = 0x21  # Day 1, month 1
        vdh[0x1D] = 0x32  # Year 2025-2000 = 25 << 1 = 50 = 0x32
        vdh[0x1E] = 0x00  # Minutes
        vdh[0x1F] = 0x0C  # Hour 12

        # Version, min version
        vdh[0x20] = 0x00
        vdh[0x21] = 0x00

        # Access
        vdh[0x22] = ACCESS_FULL

        # Entry length ($27 = 39 bytes)
        vdh[0x23] = 0x27

        # Entries per block ($0D = 13)
        vdh[0x24] = 0x0D

        # File count (0)
        vdh[0x25:0x27] = struct.pack('<H', 0)

        # Bitmap pointer (block 6)
        vdh[0x27:0x29] = struct.pack('<H', 6)

        # Total blocks
        vdh[0x29:0x2B] = struct.pack('<H', blocks)

        self._put_block(2, vdh)

        # Additional directory blocks (3, 4, 5)
        for block in range(3, 6):
            db = bytearray(BLOCK_SIZE)
            db[0:2] = struct.pack('<H', block - 1)  # Previous
            db[2:4] = struct.pack('<H', block + 1 if block < 5 else 0)  # Next
            self._put_block(block, db)

        # Volume bitmap (Block 6)
        bitmap = self._create_bitmap(blocks, used_blocks=[0, 1, 2, 3, 4, 5, 6])
        self._put_block(6, bitmap)

        self._save()
        print(f"Created ProDOS disk: {self.filename}")
        print(f"  Volume: {volume_name}")
        print(f"  Blocks: {blocks}")

    def load(self):
        """Load an existing disk image."""
        with open(self.filename, 'rb') as f:
            self.data = bytearray(f.read())
        self.block_count = len(self.data) // BLOCK_SIZE
        return True

    def _save(self):
        """Save the disk image."""
        with open(self.filename, 'wb') as f:
            f.write(self.data)

    def _get_block(self, block_num):
        """Get a block from the disk."""
        offset = block_num * BLOCK_SIZE
        return self.data[offset:offset + BLOCK_SIZE]

    def _put_block(self, block_num, data):
        """Write a block to the disk."""
        offset = block_num * BLOCK_SIZE
        self.data[offset:offset + BLOCK_SIZE] = data[:BLOCK_SIZE]

    def _create_bitmap(self, total_blocks, used_blocks):
        """Create a volume bitmap."""
        bitmap = bytearray(BLOCK_SIZE)

        # Initialize all blocks as free (1)
        for i in range(total_blocks // 8 + 1):
            if i < BLOCK_SIZE:
                bitmap[i] = 0xFF

        # Mark used blocks as used (0)
        for block in used_blocks:
            byte_idx = block // 8
            bit_idx = 7 - (block % 8)
            if byte_idx < BLOCK_SIZE:
                bitmap[byte_idx] &= ~(1 << bit_idx)

        return bitmap

    def _find_free_block(self):
        """Find a free block in the bitmap."""
        bitmap = self._get_block(6)

        # Start from block 7 (blocks 0-6 are system blocks)
        for byte_idx in range(len(bitmap)):
            if bitmap[byte_idx] != 0:
                for bit_idx in range(8):
                    if bitmap[byte_idx] & (1 << (7 - bit_idx)):
                        block = byte_idx * 8 + bit_idx
                        if block >= 7 and block < self.block_count:
                            return block
        return None

    def _mark_block_used(self, block):
        """Mark a block as used in the bitmap."""
        bitmap = self._get_block(6)
        byte_idx = block // 8
        bit_idx = 7 - (block % 8)
        bitmap[byte_idx] &= ~(1 << bit_idx)
        self._put_block(6, bitmap)

    def _find_directory_slot(self):
        """Find a free directory entry slot."""
        # Scan directory blocks (2-5)
        for dir_block in range(2, 6):
            block_data = self._get_block(dir_block)

            # Skip header/pointers (4 bytes)
            offset = 4

            # First block has volume header
            if dir_block == 2:
                offset = 4 + 0x27  # Skip volume header entry

            # Each entry is $27 (39) bytes
            while offset + 0x27 <= BLOCK_SIZE:
                storage_type = block_data[offset] >> 4
                if storage_type == 0:  # Empty slot
                    return (dir_block, offset)
                offset += 0x27

        return None

    def add_file(self, local_path, prodos_name, file_type=FILETYPE_BIN, aux_type=0x6000):
        """Add a file to the disk image."""
        if not self.data:
            self.load()

        # Read the local file
        with open(local_path, 'rb') as f:
            file_data = f.read()

        file_size = len(file_data)
        prodos_name = prodos_name[:15].upper()

        print(f"Adding file: {prodos_name}")
        print(f"  Size: {file_size} bytes")
        print(f"  Type: ${file_type:02X}, Aux: ${aux_type:04X}")

        # Calculate blocks needed
        blocks_needed = (file_size + BLOCK_SIZE - 1) // BLOCK_SIZE
        if blocks_needed == 0:
            blocks_needed = 1

        # For files up to 512 bytes, use seedling (1 block)
        # For larger files, we need an index block
        if blocks_needed == 1:
            storage_type = 0x10  # Seedling
            key_block = self._find_free_block()
            if key_block is None:
                print("  Error: No free blocks!")
                return False

            self._mark_block_used(key_block)

            # Write file data
            data_block = bytearray(BLOCK_SIZE)
            data_block[:file_size] = file_data
            self._put_block(key_block, data_block)

            blocks_used = 1

        elif blocks_needed <= 256:
            storage_type = 0x20  # Sapling (index block)

            # Allocate index block
            index_block = self._find_free_block()
            if index_block is None:
                print("  Error: No free blocks for index!")
                return False
            self._mark_block_used(index_block)

            index_data = bytearray(BLOCK_SIZE)
            key_block = index_block

            # Allocate and write data blocks
            offset = 0
            for i in range(blocks_needed):
                data_block_num = self._find_free_block()
                if data_block_num is None:
                    print("  Error: Not enough free blocks!")
                    return False
                self._mark_block_used(data_block_num)

                # Write block number to index (low byte, then high byte at +256)
                index_data[i] = data_block_num & 0xFF
                index_data[256 + i] = (data_block_num >> 8) & 0xFF

                # Write file data
                data_block = bytearray(BLOCK_SIZE)
                chunk = file_data[offset:offset + BLOCK_SIZE]
                data_block[:len(chunk)] = chunk
                self._put_block(data_block_num, data_block)
                offset += BLOCK_SIZE

            self._put_block(index_block, index_data)
            blocks_used = blocks_needed + 1  # +1 for index block

        else:
            print("  Error: File too large (needs tree structure)!")
            return False

        # Find a directory slot
        slot = self._find_directory_slot()
        if slot is None:
            print("  Error: No free directory slots!")
            return False

        dir_block, offset = slot

        # Create directory entry
        entry = bytearray(0x27)

        # Storage type (high nibble) | name length (low nibble)
        entry[0x00] = storage_type | len(prodos_name)

        # File name
        for i, c in enumerate(prodos_name):
            entry[0x01 + i] = ord(c)

        # File type
        entry[0x10] = file_type

        # Key block pointer
        entry[0x11] = key_block & 0xFF
        entry[0x12] = (key_block >> 8) & 0xFF

        # Blocks used
        entry[0x13] = blocks_used & 0xFF
        entry[0x14] = (blocks_used >> 8) & 0xFF

        # EOF (file size)
        entry[0x15] = file_size & 0xFF
        entry[0x16] = (file_size >> 8) & 0xFF
        entry[0x17] = (file_size >> 16) & 0xFF

        # Creation date/time
        entry[0x18] = 0x21  # Day 1, month 1
        entry[0x19] = 0x32  # Year 25
        entry[0x1A] = 0x00  # Minutes
        entry[0x1B] = 0x0C  # Hour 12

        # Version, min version
        entry[0x1C] = 0x00
        entry[0x1D] = 0x00

        # Access
        entry[0x1E] = ACCESS_FULL

        # Aux type (load address for BIN files)
        entry[0x1F] = aux_type & 0xFF
        entry[0x20] = (aux_type >> 8) & 0xFF

        # Modification date/time
        entry[0x21] = 0x21
        entry[0x22] = 0x32
        entry[0x23] = 0x00
        entry[0x24] = 0x0C

        # Header pointer (block 2 for volume directory)
        entry[0x25] = 0x02
        entry[0x26] = 0x00

        # Write entry to directory
        dir_data = self._get_block(dir_block)
        dir_data[offset:offset + 0x27] = entry
        self._put_block(dir_block, dir_data)

        # Update file count in volume header
        vdh = self._get_block(2)
        file_count = struct.unpack('<H', vdh[0x25:0x27])[0]
        file_count += 1
        vdh[0x25:0x27] = struct.pack('<H', file_count)
        self._put_block(2, vdh)

        self._save()
        print(f"  Added successfully to block {key_block}")
        return True

    def catalog(self):
        """List files on the disk."""
        if not self.data:
            self.load()

        # Read volume header
        vdh = self._get_block(2)
        name_len = vdh[4] & 0x0F
        vol_name = bytes(vdh[5:5 + name_len]).decode('ascii')
        file_count = struct.unpack('<H', vdh[0x25:0x27])[0]
        total_blocks = struct.unpack('<H', vdh[0x29:0x2B])[0]

        print(f"\n/{vol_name}")
        print(f"  {file_count} files, {total_blocks} blocks")
        print()
        print(" NAME           TYPE  BLOCKS  SIZE")
        print("-" * 40)

        # Scan directory blocks
        for dir_block in range(2, 6):
            block_data = self._get_block(dir_block)
            offset = 4 + (0x27 if dir_block == 2 else 0)

            while offset + 0x27 <= BLOCK_SIZE:
                storage_type = block_data[offset] >> 4
                if storage_type > 0 and storage_type < 0x0F:
                    name_len = block_data[offset] & 0x0F
                    name = bytes(block_data[offset + 1:offset + 1 + name_len]).decode('ascii')
                    ftype = block_data[offset + 0x10]
                    blocks = struct.unpack('<H', block_data[offset + 0x13:offset + 0x15])[0]
                    size = struct.unpack('<I', block_data[offset + 0x15:offset + 0x18] + b'\x00')[0]

                    type_str = {
                        0x04: 'TXT',
                        0x06: 'BIN',
                        0xFC: 'BAS',
                        0xFF: 'SYS'
                    }.get(ftype, f'${ftype:02X}')

                    print(f" {name:15s} {type_str:4s}  {blocks:5d}  {size:6d}")

                offset += 0x27

        print()


def main():
    if len(sys.argv) < 2:
        print("ProDOS Disk Tool")
        print("Usage:")
        print("  prodos_disk.py create <image.po> <volume_name> [blocks]")
        print("  prodos_disk.py add <image.po> <local_file> <prodos_name> [type] [aux]")
        print("  prodos_disk.py catalog <image.po>")
        print()
        print("File types: BIN=06 SYS=FF TXT=04 BAS=FC")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'create':
        if len(sys.argv) < 4:
            print("Usage: prodos_disk.py create <image.po> <volume_name> [blocks]")
            sys.exit(1)
        image = sys.argv[2]
        volume = sys.argv[3]
        blocks = int(sys.argv[4]) if len(sys.argv) > 4 else BLOCKS_140K
        disk = ProDOSDisk(image)
        disk.create(volume, blocks)

    elif cmd == 'add':
        if len(sys.argv) < 5:
            print("Usage: prodos_disk.py add <image.po> <local_file> <prodos_name> [type] [aux]")
            sys.exit(1)
        image = sys.argv[2]
        local_file = sys.argv[3]
        prodos_name = sys.argv[4]
        file_type = int(sys.argv[5], 16) if len(sys.argv) > 5 else FILETYPE_BIN
        aux_type = int(sys.argv[6], 16) if len(sys.argv) > 6 else 0x6000

        disk = ProDOSDisk(image)
        disk.add_file(local_file, prodos_name, file_type, aux_type)

    elif cmd == 'catalog' or cmd == 'cat':
        if len(sys.argv) < 3:
            print("Usage: prodos_disk.py catalog <image.po>")
            sys.exit(1)
        image = sys.argv[2]
        disk = ProDOSDisk(image)
        disk.catalog()

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
