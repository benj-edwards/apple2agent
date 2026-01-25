#!/usr/bin/env python3
"""
Remote Proxy - Command interface for Apple II Remote Shell
Listens for Apple II to connect and send READY,
then allows sending PEEK/POKE/CALL commands.

Usage:
    python3 remote_proxy.py [--host HOST] [--port PORT]

Protocol:
  Apple II -> Proxy: "READY\r\n"
  Proxy -> Apple II: "P xxxx\r\n" (PEEK) or "O xxxx,yy\r\n" (POKE) or "C xxxx\r\n" (CALL)
  Apple II -> Proxy: "OK xx\r\n" (PEEK result) or "OK\r\n" (POKE/CALL result)
"""

import socket
import threading
import sys
import json
import argparse
from datetime import datetime

DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 8080

# Safe memory regions (avoid $C000-$CFFF I/O space)
SAFE_REGIONS = [
    (0x0000, 0x00FF, "Zero Page"),
    (0x0100, 0x01FF, "Stack"),
    (0x0200, 0x02FF, "Input Buffer"),
    (0x0300, 0x03FF, "DOS Vectors / User"),
    (0x0400, 0x07FF, "Text Page 1"),
    (0x0800, 0x0BFF, "Text Page 2 / BASIC Start"),
    (0x2000, 0x3FFF, "HGR Page 1"),
    (0x4000, 0x5FFF, "HGR Page 2"),
    (0x6000, 0x95FF, "Free RAM / Program Area"),
    (0x9600, 0xBEFF, "DOS/ProDOS Area"),
    (0xBF00, 0xBFFF, "ProDOS Global Page"),
    (0xD000, 0xFFFF, "ROM"),
]

# Key memory locations
KEY_LOCATIONS = {
    0x0020: "WNDLFT - Window left",
    0x0021: "WNDWDTH - Window width",
    0x0022: "WNDTOP - Window top",
    0x0023: "WNDBTM - Window bottom",
    0x0024: "CH - Cursor horizontal",
    0x0025: "CV - Cursor vertical",
    0x0026: "GPTS - Graphics cursor",
    0x002B: "RPTS - Graphics cursor",
    0x0036: "CSWL - Output hook low",
    0x0037: "CSWH - Output hook high",
    0x0038: "KSWL - Input hook low",
    0x0039: "KSWH - Input hook high",
    0x0067: "TXTTAB - BASIC start low",
    0x0068: "TXTTAB - BASIC start high",
    0x0069: "VARTAB - Variables start low",
    0x006A: "VARTAB - Variables start high",
    0x006B: "ARYTAB - Arrays start low",
    0x006C: "ARYTAB - Arrays start high",
    0x006D: "STREND - String storage end low",
    0x006E: "STREND - String storage end high",
    0x0073: "HIMEM low",
    0x0074: "HIMEM high",
    0x00AF: "MEMSIZ - Top of memory low",
    0x00B0: "MEMSIZ - Top of memory high",
    0xBF00: "ProDOS MLI entry (4C = JMP)",
    0xBF98: "ProDOS machine ID",
    0xFBB3: "ROM ID byte",
    0xFBC0: "ROM secondary ID",
}

class RemoteProxy:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.client = None
        self.connected = False
        self.response = None
        self.response_event = threading.Event()

    def start_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(1)
        print(f"Remote Proxy listening on {self.host}:{self.port}")
        print("Waiting for Apple II to connect...")

        while True:
            self.client, addr = server.accept()
            print(f"Connected from {addr}")
            self.connected = True

            # Start receiver thread
            recv_thread = threading.Thread(target=self.receive_loop)
            recv_thread.daemon = True
            recv_thread.start()

            # Process commands
            self.command_loop()

            self.connected = False
            self.client.close()
            print("Disconnected. Waiting for reconnect...")

    def receive_loop(self):
        buffer = b''
        while self.connected:
            try:
                data = self.client.recv(1024)
                if not data:
                    self.connected = False
                    break
                buffer += data

                # Process complete lines
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    line = line.strip().decode('ascii', errors='ignore')

                    if line == 'READY':
                        print("[READY]")
                        self.response = 'READY'
                        self.response_event.set()
                    elif line.startswith('OK'):
                        self.response = line
                        self.response_event.set()
            except Exception as e:
                print(f"Receive error: {e}")
                self.connected = False
                break

    def wait_response(self, timeout=5.0):
        self.response_event.clear()
        if self.response_event.wait(timeout):
            return self.response
        return None

    def send_command(self, cmd):
        if not self.connected or not self.client:
            print("Not connected!")
            return None
        try:
            self.client.send((cmd + '\r\n').encode('ascii'))
            return self.wait_response()
        except Exception as e:
            print(f"Send error: {e}")
            return None

    def peek(self, addr):
        cmd = f"P {addr:04X}"
        resp = self.send_command(cmd)
        if resp and resp.startswith('OK '):
            return int(resp[3:5], 16)
        return None

    def poke(self, addr, val):
        cmd = f"O {addr:04X},{val:02X}"
        resp = self.send_command(cmd)
        return resp == 'OK'

    def call(self, addr):
        cmd = f"C {addr:04X}"
        resp = self.send_command(cmd)
        return resp == 'OK'

    def scan_memory(self):
        """Safely scan memory and build a system map."""
        print("\n" + "="*60)
        print("APPLE II MEMORY SCAN")
        print("="*60)

        memory_map = {
            'timestamp': datetime.now().isoformat(),
            'key_values': {},
            'analysis': {},
            'regions': {},
        }

        # Read key locations first
        print("\nReading key memory locations...")
        for addr, desc in KEY_LOCATIONS.items():
            val = self.peek(addr)
            if val is not None:
                memory_map['key_values'][f"${addr:04X}"] = {
                    'value': val,
                    'hex': f"${val:02X}",
                    'description': desc
                }
                # Wait for READY between commands
                self.wait_response(5)
            else:
                print(f"  Failed to read ${addr:04X}")
                return None

        # Analyze what we found
        print("\nAnalyzing system state...")
        kv = memory_map['key_values']

        # BASIC program location
        if '$0067' in kv and '$0068' in kv:
            txttab = kv['$0067']['value'] + (kv['$0068']['value'] << 8)
            memory_map['analysis']['basic_start'] = f"${txttab:04X}"

        # BASIC variables
        if '$0069' in kv and '$006A' in kv:
            vartab = kv['$0069']['value'] + (kv['$006A']['value'] << 8)
            memory_map['analysis']['variables_start'] = f"${vartab:04X}"

        # HIMEM
        if '$0073' in kv and '$0074' in kv:
            himem = kv['$0073']['value'] + (kv['$0074']['value'] << 8)
            memory_map['analysis']['himem'] = f"${himem:04X}"

        # ROM identification
        if '$FBB3' in kv:
            rom_id = kv['$FBB3']['value']
            if rom_id == 0x06:
                memory_map['analysis']['machine'] = "Apple II+ or IIe"
            elif rom_id == 0xEA:
                memory_map['analysis']['machine'] = "Apple IIe"
            elif rom_id == 0x00:
                memory_map['analysis']['machine'] = "Apple IIc"
            elif rom_id == 0xE0:
                memory_map['analysis']['machine'] = "Apple IIe Enhanced"
            else:
                memory_map['analysis']['machine'] = f"Unknown (${rom_id:02X})"

        # ProDOS check
        if '$BF00' in kv:
            if kv['$BF00']['value'] == 0x4C:  # JMP instruction
                memory_map['analysis']['prodos'] = "ProDOS present"
            else:
                memory_map['analysis']['prodos'] = "ProDOS not active"

        # Sample some memory regions for content analysis
        print("\nSampling memory regions...")
        for start, end, name in SAFE_REGIONS[:6]:  # First 6 regions only for speed
            sample = []
            sample_addr = start
            # Read 16 bytes from start of region
            for i in range(16):
                val = self.peek(sample_addr + i)
                if val is not None:
                    sample.append(val)
                    self.wait_response(2)
                else:
                    break
            memory_map['regions'][name] = {
                'start': f"${start:04X}",
                'end': f"${end:04X}",
                'sample': ' '.join(f'{b:02X}' for b in sample)
            }
            print(f"  {name}: ${start:04X}-${end:04X}")

        # Print summary
        print("\n" + "-"*60)
        print("SYSTEM SUMMARY")
        print("-"*60)
        for key, val in memory_map['analysis'].items():
            print(f"  {key}: {val}")

        print("\n" + "-"*60)
        print("KEY MEMORY VALUES")
        print("-"*60)
        for addr, info in sorted(memory_map['key_values'].items()):
            print(f"  {addr} = {info['hex']:>4}  {info['description']}")

        # Save to file
        filename = f"memory_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(memory_map, f, indent=2)
        print(f"\nMemory map saved to: {filename}")

        return memory_map

    def quick_scan(self):
        """Quick scan of essential locations only."""
        print("\nQuick system scan...")

        essentials = [
            (0x0067, 0x0068, "BASIC Start"),
            (0x0073, 0x0074, "HIMEM"),
            (0xFBB3, None, "ROM ID"),
            (0xBF00, None, "ProDOS"),
        ]

        for item in essentials:
            if len(item) == 3 and item[1] is not None:
                lo, hi, name = item
                val_lo = self.peek(lo)
                self.wait_response(2)
                val_hi = self.peek(hi)
                self.wait_response(2)
                if val_lo is not None and val_hi is not None:
                    addr = val_lo + (val_hi << 8)
                    print(f"  {name}: ${addr:04X}")
            else:
                addr, _, name = item
                val = self.peek(addr)
                self.wait_response(2)
                if val is not None:
                    print(f"  {name}: ${val:02X}")

        print()

    def command_loop(self):
        print("\nCommands:")
        print("  P <addr>       - PEEK address (hex)")
        print("  O <addr> <val> - POKE value to address (hex)")
        print("  C <addr>       - CALL address (hex)")
        print("  D <addr> <len> - Dump memory (hex)")
        print("  L <addr> <bytes...> - Load bytes to address")
        print("  SCAN           - Full memory scan (safe, saves to JSON)")
        print("  QS             - Quick scan (essential locations only)")
        print("  Q              - Quit (disconnect Apple II)")
        print("  X              - Exit proxy")
        print()

        # Wait for initial READY
        print("Waiting for READY...")
        resp = self.wait_response(30)
        if resp != 'READY':
            print("Timeout waiting for READY")
            return

        while self.connected:
            try:
                cmd = input("> ").strip().upper()
                if not cmd:
                    continue

                parts = cmd.split()
                op = parts[0]

                if op == 'P' and len(parts) >= 2:
                    addr = int(parts[1], 16)
                    val = self.peek(addr)
                    if val is not None:
                        print(f"${addr:04X} = ${val:02X} ({val})")
                    else:
                        print("No response")

                elif op == 'O' and len(parts) >= 3:
                    addr = int(parts[1], 16)
                    val = int(parts[2], 16)
                    if self.poke(addr, val):
                        print("OK")
                    else:
                        print("Failed")

                elif op == 'C' and len(parts) >= 2:
                    addr = int(parts[1], 16)
                    if self.call(addr):
                        print("OK")
                    else:
                        print("Failed")

                elif op == 'D' and len(parts) >= 3:
                    addr = int(parts[1], 16)
                    length = int(parts[2], 16)
                    print(f"Dumping ${length:X} bytes from ${addr:04X}:")
                    for i in range(length):
                        val = self.peek(addr + i)
                        if val is None:
                            print("\nRead failed")
                            break
                        if i % 16 == 0:
                            print(f"\n${addr+i:04X}: ", end='')
                        print(f"{val:02X} ", end='')
                    print()

                elif op == 'L' and len(parts) >= 3:
                    addr = int(parts[1], 16)
                    bytes_to_load = [int(b, 16) for b in parts[2:]]
                    print(f"Loading {len(bytes_to_load)} bytes to ${addr:04X}...")
                    for i, b in enumerate(bytes_to_load):
                        if not self.poke(addr + i, b):
                            print(f"Failed at offset {i}")
                            break
                    else:
                        print("OK")

                elif op == 'SCAN':
                    self.scan_memory()

                elif op == 'QS':
                    self.quick_scan()

                elif op == 'Q':
                    self.send_command("Q")
                    break

                elif op == 'X':
                    self.send_command("Q")
                    sys.exit(0)

                else:
                    print("Unknown command")

                # Wait for next READY
                resp = self.wait_response(10)
                if resp != 'READY':
                    print("Lost connection (no READY)")
                    break

            except ValueError as e:
                print(f"Invalid input: {e}")
            except EOFError:
                break
            except KeyboardInterrupt:
                break

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Remote Shell Proxy - Command interface for Apple II'
    )
    parser.add_argument(
        '--host', '-H',
        default=DEFAULT_HOST,
        help=f'Host to bind to (default: {DEFAULT_HOST})'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=DEFAULT_PORT,
        help=f'Port to listen on (default: {DEFAULT_PORT})'
    )

    args = parser.parse_args()

    proxy = RemoteProxy(args.host, args.port)
    proxy.start_server()
