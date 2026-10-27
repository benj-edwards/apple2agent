#!/usr/bin/env python3
"""
End-to-end test for Apple II Agent system.
Simulates an Apple II client connecting to the unified proxy.
"""

import sys
import os
import socket
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'proxy'))

from a2p_protocol import (
    A2PProtocol, PacketType, Packet,
    CAP_40_COL, CAP_80_COL
)


def test_proxy_connection():
    """Test connecting to the proxy and sending a chat message."""
    print("=== Apple II Agent E2E Test ===\n")

    proto = A2PProtocol()

    # Connect to proxy
    print("Connecting to proxy at localhost:6502...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(('localhost', 6502))
        print("Connected!\n")
    except ConnectionRefusedError:
        print("ERROR: Could not connect. Is the proxy running?")
        print("Start it with: python3 proxy/unified_proxy.py")
        return False
    except socket.timeout:
        print("ERROR: Connection timed out")
        return False

    try:
        # Send INIT packet
        print("Sending INIT packet (40-col mode)...")
        init_pkt = proto.encode_init(CAP_40_COL)
        sock.sendall(init_pkt)
        print(f"  Sent: {init_pkt.hex()}")

        # Wait for response
        time.sleep(0.5)

        # Send CHAT packet
        message = "HELLO CLAUDE"
        print(f"\nSending CHAT: '{message}'...")
        chat_pkt = proto.encode_chat(message)
        sock.sendall(chat_pkt)
        print(f"  Sent: {chat_pkt.hex()}")

        # Receive response
        print("\nWaiting for response...")
        sock.settimeout(30)  # Long timeout for API response

        response_text = ""
        while True:
            try:
                data = sock.recv(1024)
                if not data:
                    break

                print(f"  Received {len(data)} bytes: {data[:50].hex()}...")

                # Decode packets
                for packet in proto.decode_stream(data):
                    print(f"  Packet: {packet.ptype.name}, seq={packet.seq}")

                    if packet.ptype == PacketType.STATUS:
                        status = packet.data.decode('ascii', errors='replace')
                        print(f"    STATUS: {status}")

                    elif packet.ptype == PacketType.RESP:
                        is_final = packet.data[0] & 0x01
                        text = packet.data[1:].decode('ascii', errors='replace')
                        response_text += text
                        print(f"    RESP: {text[:50]}... (final={is_final})")

                        if is_final:
                            print("\n=== Full Response ===")
                            print(response_text)
                            print("=== End Response ===\n")
                            return True

                    elif packet.ptype == PacketType.ERR:
                        error = packet.data.decode('ascii', errors='replace')
                        print(f"    ERROR: {error}")
                        return False

                    elif packet.ptype == PacketType.ACK:
                        print(f"    ACK for seq {packet.data[0]}")

            except socket.timeout:
                print("  Timeout waiting for more data")
                break

        if response_text:
            print("\n=== Full Response ===")
            print(response_text)
            print("=== End Response ===\n")
            return True

        return False

    finally:
        sock.close()
        print("Connection closed.")


def test_code_request():
    """Test requesting BASIC code generation."""
    print("\n=== Code Generation Test ===\n")

    proto = A2PProtocol()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(('localhost', 6502))
        print("Connected!\n")
    except ConnectionRefusedError:
        print("ERROR: Could not connect")
        return False

    try:
        # Send INIT
        sock.sendall(proto.encode_init(CAP_40_COL))
        time.sleep(0.5)

        # Send code request
        message = "/CODE PRINT HELLO WORLD"
        print(f"Sending: '{message}'...")
        sock.sendall(proto.encode_chat(message))

        # Receive
        print("Waiting for code...")
        sock.settimeout(60)

        code_data = bytearray()
        code_total = 0

        while True:
            try:
                data = sock.recv(1024)
                if not data:
                    break

                for packet in proto.decode_stream(data):
                    print(f"  {packet.ptype.name}", end="")

                    if packet.ptype == PacketType.STATUS:
                        print(f": {packet.data.decode('ascii', errors='replace')}")

                    elif packet.ptype == PacketType.CODE:
                        # Parse offset, total, data
                        offset = packet.data[0] | (packet.data[1] << 8)
                        total = packet.data[2] | (packet.data[3] << 8)
                        chunk = packet.data[4:]

                        if len(chunk) == 0:
                            print(f": END (total={total} bytes)")
                            print("\n=== Code Received ===")
                            print(f"Total bytes: {len(code_data)}")
                            print(f"Hex: {code_data[:64].hex()}...")
                            return True
                        else:
                            code_data.extend(chunk)
                            print(f": offset={offset}, len={len(chunk)}")
                            code_total = total

                    elif packet.ptype == PacketType.RESP:
                        text = packet.data[1:].decode('ascii', errors='replace')
                        print(f": {text[:40]}")

                    elif packet.ptype == PacketType.ERR:
                        print(f": ERROR - {packet.data.decode()}")
                        return False

                    else:
                        print()

            except socket.timeout:
                break

        return len(code_data) > 0

    finally:
        sock.close()


if __name__ == '__main__':
    print("Testing proxy at localhost:6502\n")
    print("Make sure proxy is running: python3 proxy/unified_proxy.py\n")

    success = test_proxy_connection()
    print(f"\nChat test: {'PASSED' if success else 'FAILED'}")

    # Uncomment to test code generation (requires API key)
    # success = test_code_request()
    # print(f"Code test: {'PASSED' if success else 'FAILED'}")
