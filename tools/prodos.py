#!/usr/bin/env python3
"""
ProDOS Disk Tool - Unified interface for ProDOS disk images
No Java required!

Usage:
    prodos.py list <disk>                              - List files
    prodos.py add <disk> <file> <name> [type] [addr]   - Add file
    prodos.py del <disk> <name>                        - Delete file

Types: BIN (default), SYS, BAS, TXT
Addr: hex load address for BIN files (default: 0000)
"""

import sys
import os
import subprocess

def run_tool(script, args):
    """Run one of the existing tools."""
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(tool_dir, script)
    result = subprocess.run(
        ['python3', script_path] + args,
        capture_output=True,
        text=True
    )
    print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    return result.returncode

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    disk = sys.argv[2]

    if cmd == 'list' or cmd == 'ls':
        run_tool('prodos_delete.py', [disk, 'list'])

    elif cmd == 'add':
        if len(sys.argv) < 5:
            print("Usage: prodos.py add <disk> <file> <name> [type] [addr]")
            sys.exit(1)

        local_file = sys.argv[3]
        prodos_name = sys.argv[4]

        # Default type and address
        file_type = '06'  # BIN
        aux_type = '0000'

        if len(sys.argv) > 5:
            type_arg = sys.argv[5].upper()
            type_map = {'BIN': '06', 'SYS': 'FF', 'BAS': 'FC', 'TXT': '04'}
            file_type = type_map.get(type_arg, type_arg)

        if len(sys.argv) > 6:
            aux_type = sys.argv[6]

        run_tool('prodos_add.py', [disk, local_file, prodos_name, file_type, aux_type])

    elif cmd == 'del' or cmd == 'rm':
        if len(sys.argv) < 4:
            print("Usage: prodos.py del <disk> <name>")
            sys.exit(1)
        name = sys.argv[3]
        run_tool('prodos_delete.py', [disk, 'delete', name])

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == '__main__':
    main()
