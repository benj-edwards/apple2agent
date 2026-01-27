#!/usr/bin/env python3
"""
A2P Protocol - Apple II Protocol for Claude Agent

Packet format:
  [A2][Type][Len:2][Seq][Data...][Checksum]

  - Magic: 'A2' (0x41 0x32) - identifies packet start
  - Type: Message type (1 byte)
  - Len: Data length (2 bytes, little-endian, excludes header/checksum)
  - Seq: Sequence number (1 byte, 0-255 wrapping)
  - Data: Variable length payload
  - Checksum: XOR of all bytes from Type through Data

Message Types:
  0x00 - INIT: Initialize, send capabilities
  0x01 - CHAT: User chat message
  0x02 - RESP: AI response chunk (streaming)
  0x03 - CODE: BASIC code chunk
  0x04 - STATUS: Status message
  0x05 - ACK: Acknowledgment
  0x06 - NACK: Request retransmit
  0x0F - ERR: Error message

Usage:
    from a2p_protocol import A2PProtocol, PacketType

    proto = A2PProtocol()

    # Encode a packet
    packet = proto.encode(PacketType.CHAT, b"Hello Claude")

    # Decode packets from stream
    for ptype, seq, data in proto.decode_stream(raw_bytes):
        print(f"Got {ptype.name}: {data}")
"""

import struct
from enum import IntEnum
from typing import Generator, Tuple, Optional, List
from dataclasses import dataclass


class PacketType(IntEnum):
    """A2P message types."""
    INIT = 0x00    # Initialize connection
    CHAT = 0x01    # User chat message
    RESP = 0x02    # AI response chunk
    CODE = 0x03    # BASIC code chunk
    STATUS = 0x04  # Status message
    ACK = 0x05     # Acknowledgment
    NACK = 0x06    # Request retransmit
    ERR = 0x0F     # Error message


# Capability flags for INIT packet
CAP_40_COL = 0x00      # 40-column display
CAP_80_COL = 0x01      # 80-column display
CAP_LOWERCASE = 0x02   # Supports lowercase
CAP_MOUSE = 0x04       # Has mouse card


# Protocol constants
MAGIC = b'A2'
HEADER_SIZE = 6        # A2 + Type + Len(2) + Seq
MAX_DATA_SIZE = 128    # Max payload per packet
MAX_RETRIES = 3        # Retransmit attempts
ACK_TIMEOUT = 2.0      # Seconds to wait for ACK


@dataclass
class Packet:
    """Decoded A2P packet."""
    ptype: PacketType
    seq: int
    data: bytes

    def __repr__(self):
        preview = self.data[:20].decode('ascii', errors='replace')
        if len(self.data) > 20:
            preview += '...'
        return f"Packet({self.ptype.name}, seq={self.seq}, len={len(self.data)}, data={preview!r})"


class A2PProtocol:
    """
    A2P Protocol encoder/decoder.

    Handles packet creation, parsing, sequencing, and checksums.
    """

    def __init__(self):
        self.tx_seq = 0          # Transmit sequence number
        self.rx_seq = 0          # Expected receive sequence
        self.rx_buffer = bytearray()  # Receive buffer for partial packets

    def reset(self):
        """Reset protocol state for new connection."""
        self.tx_seq = 0
        self.rx_seq = 0
        self.rx_buffer.clear()

    def _next_seq(self) -> int:
        """Get next sequence number."""
        seq = self.tx_seq
        self.tx_seq = (self.tx_seq + 1) & 0xFF
        return seq

    @staticmethod
    def _checksum(data: bytes) -> int:
        """Calculate XOR checksum."""
        result = 0
        for b in data:
            result ^= b
        return result

    def encode(self, ptype: PacketType, data: bytes = b'', seq: Optional[int] = None) -> bytes:
        """
        Encode a single A2P packet.

        Args:
            ptype: Packet type
            data: Payload data (max 128 bytes)
            seq: Optional sequence number (auto-assigned if None)

        Returns:
            Complete packet bytes
        """
        if len(data) > MAX_DATA_SIZE:
            raise ValueError(f"Data too large: {len(data)} > {MAX_DATA_SIZE}")

        if seq is None:
            seq = self._next_seq()

        # Build packet: A2 + Type + Len + Seq + Data + Checksum
        header = struct.pack('<2sBHB', MAGIC, ptype, len(data), seq)
        body = header[2:] + data  # Everything after magic for checksum
        checksum = self._checksum(body)

        return header + data + bytes([checksum])

    def encode_ack(self, seq: int) -> bytes:
        """Create ACK packet for given sequence number."""
        return self.encode(PacketType.ACK, bytes([seq]), seq=0)

    def encode_nack(self, seq: int) -> bytes:
        """Create NACK packet requesting retransmit of sequence."""
        return self.encode(PacketType.NACK, bytes([seq]), seq=0)

    def encode_init(self, capabilities: int = CAP_40_COL) -> bytes:
        """Create INIT packet with capability flags."""
        return self.encode(PacketType.INIT, bytes([capabilities]))

    def encode_chat(self, message: str) -> bytes:
        """Create CHAT packet with user message."""
        # Convert to uppercase and ASCII for Apple II
        data = message.upper().encode('ascii', errors='replace')
        return self.encode(PacketType.CHAT, data)

    def encode_response(self, text: str, is_final: bool = False) -> bytes:
        """
        Create RESP packet with response text.
        First byte is flags: 0x01 = final chunk
        """
        flags = 0x01 if is_final else 0x00
        data = bytes([flags]) + text.encode('ascii', errors='replace')
        return self.encode(PacketType.RESP, data)

    def encode_code_chunk(self, chunk: bytes, offset: int, total: int) -> bytes:
        """
        Create CODE packet with BASIC code chunk.
        Header: offset(2) + total(2) + chunk_data
        """
        header = struct.pack('<HH', offset, total)
        return self.encode(PacketType.CODE, header + chunk)

    def encode_status(self, message: str) -> bytes:
        """Create STATUS packet with status message."""
        data = message[:MAX_DATA_SIZE].encode('ascii', errors='replace')
        return self.encode(PacketType.STATUS, data)

    def encode_error(self, message: str) -> bytes:
        """Create ERR packet with error message."""
        data = message[:MAX_DATA_SIZE].encode('ascii', errors='replace')
        return self.encode(PacketType.ERR, data)

    def decode_packet(self, data: bytes) -> Optional[Packet]:
        """
        Decode a single complete packet.

        Args:
            data: Complete packet bytes

        Returns:
            Decoded Packet or None if invalid
        """
        if len(data) < HEADER_SIZE + 1:  # +1 for checksum
            return None

        # Check magic
        if data[:2] != MAGIC:
            return None

        # Parse header
        ptype_byte, data_len, seq = struct.unpack('<BHB', data[2:6])

        # Validate type
        try:
            ptype = PacketType(ptype_byte)
        except ValueError:
            return None

        # Check length
        expected_len = HEADER_SIZE + data_len + 1
        if len(data) < expected_len:
            return None

        # Extract payload and checksum
        payload = data[6:6+data_len]
        received_checksum = data[6+data_len]

        # Verify checksum (Type + Len + Seq + Data)
        body = data[2:6+data_len]
        calculated_checksum = self._checksum(body)

        if received_checksum != calculated_checksum:
            return None

        return Packet(ptype, seq, payload)

    def decode_stream(self, data: bytes) -> Generator[Packet, None, None]:
        """
        Decode packets from a byte stream.
        Handles partial packets by buffering.

        Args:
            data: Raw bytes from TCP

        Yields:
            Complete packets as they're parsed
        """
        self.rx_buffer.extend(data)

        while len(self.rx_buffer) >= HEADER_SIZE + 1:
            # Look for magic bytes
            magic_pos = self.rx_buffer.find(MAGIC)

            if magic_pos == -1:
                # No magic found, keep last byte (might be partial 'A')
                self.rx_buffer = self.rx_buffer[-1:]
                break

            if magic_pos > 0:
                # Discard garbage before magic
                del self.rx_buffer[:magic_pos]

            if len(self.rx_buffer) < HEADER_SIZE:
                break  # Need more data for header

            # Parse header to get length
            _, data_len, _ = struct.unpack('<BHB', bytes(self.rx_buffer[2:6]))
            packet_len = HEADER_SIZE + data_len + 1

            if len(self.rx_buffer) < packet_len:
                break  # Need more data for complete packet

            # Extract and decode packet
            packet_bytes = bytes(self.rx_buffer[:packet_len])
            packet = self.decode_packet(packet_bytes)

            # Remove packet from buffer
            del self.rx_buffer[:packet_len]

            if packet:
                yield packet
            # If decode failed, loop will find next magic

    def chunk_data(self, data: bytes, chunk_size: int = MAX_DATA_SIZE - 4) -> List[Tuple[bytes, int, int]]:
        """
        Split data into chunks for CODE packets.

        Args:
            data: Data to chunk (e.g., tokenized BASIC)
            chunk_size: Max bytes per chunk (default accounts for offset/total header)

        Returns:
            List of (chunk, offset, total) tuples
        """
        total = len(data)
        chunks = []
        offset = 0

        while offset < total:
            chunk = data[offset:offset + chunk_size]
            chunks.append((chunk, offset, total))
            offset += len(chunk)

        return chunks


class A2PConnection:
    """
    Higher-level connection handler with ACK/NACK and retransmission.

    Wraps A2PProtocol with reliable delivery.
    """

    def __init__(self, send_func, max_retries: int = MAX_RETRIES):
        """
        Args:
            send_func: Callable that sends bytes to the connection
            max_retries: Max retransmission attempts
        """
        self.proto = A2PProtocol()
        self.send = send_func
        self.max_retries = max_retries
        self.pending_acks = {}  # seq -> (packet, retries)
        self.last_rx_seq = -1

    def reset(self):
        """Reset connection state."""
        self.proto.reset()
        self.pending_acks.clear()
        self.last_rx_seq = -1

    def send_packet(self, ptype: PacketType, data: bytes = b'') -> int:
        """
        Send a packet and track for potential retransmission.

        Returns:
            Sequence number of sent packet
        """
        packet = self.proto.encode(ptype, data)
        seq = self.proto.tx_seq - 1  # Was just incremented

        # Track packets that need ACK (not ACK/NACK themselves)
        if ptype not in (PacketType.ACK, PacketType.NACK):
            self.pending_acks[seq] = (packet, 0)

        self.send(packet)
        return seq

    def send_with_ack(self, ptype: PacketType, data: bytes = b'',
                       timeout: float = ACK_TIMEOUT) -> bool:
        """
        Send packet and wait for ACK (blocking).

        Note: Actual implementation needs async/threading.
        This is a simplified synchronous version.

        Returns:
            True if ACKed, False if failed
        """
        seq = self.send_packet(ptype, data)
        # In real implementation, would wait for ACK here
        return True  # Placeholder

    def handle_received(self, packet: Packet) -> Optional[Packet]:
        """
        Handle a received packet, sending ACK/NACK as needed.

        Returns:
            The packet if it should be processed, None if it was a control packet
        """
        if packet.ptype == PacketType.ACK:
            # Remove from pending
            ack_seq = packet.data[0] if packet.data else 0
            self.pending_acks.pop(ack_seq, None)
            return None

        if packet.ptype == PacketType.NACK:
            # Retransmit requested packet
            nack_seq = packet.data[0] if packet.data else 0
            if nack_seq in self.pending_acks:
                pkt, retries = self.pending_acks[nack_seq]
                if retries < self.max_retries:
                    self.pending_acks[nack_seq] = (pkt, retries + 1)
                    self.send(pkt)
            return None

        # Regular packet - send ACK
        self.send(self.proto.encode_ack(packet.seq))

        # Check for duplicate
        if packet.seq == self.last_rx_seq:
            return None  # Already processed

        self.last_rx_seq = packet.seq
        return packet

    def retransmit_pending(self) -> int:
        """
        Retransmit any pending unACKed packets.
        Call periodically on timeout.

        Returns:
            Number of packets retransmitted
        """
        count = 0
        failed = []

        for seq, (packet, retries) in self.pending_acks.items():
            if retries < self.max_retries:
                self.pending_acks[seq] = (packet, retries + 1)
                self.send(packet)
                count += 1
            else:
                failed.append(seq)

        # Remove failed packets
        for seq in failed:
            del self.pending_acks[seq]

        return count


# Utility functions for common operations

def create_code_packets(proto: A2PProtocol, tokenized: bytes) -> List[bytes]:
    """
    Create all CODE packets for a tokenized BASIC program.

    Args:
        proto: Protocol instance
        tokenized: Tokenized BASIC program bytes

    Returns:
        List of encoded packets
    """
    packets = []
    chunks = proto.chunk_data(tokenized)

    for chunk, offset, total in chunks:
        packet = proto.encode_code_chunk(chunk, offset, total)
        packets.append(packet)

    # Final empty packet signals end
    packets.append(proto.encode_code_chunk(b'', len(tokenized), len(tokenized)))

    return packets


def create_response_packets(proto: A2PProtocol, text: str,
                            chunk_size: int = MAX_DATA_SIZE - 1) -> List[bytes]:
    """
    Create RESP packets for a complete response, chunked appropriately.

    Args:
        proto: Protocol instance
        text: Full response text
        chunk_size: Max text per packet (accounts for flags byte)

    Returns:
        List of encoded packets
    """
    packets = []
    offset = 0

    while offset < len(text):
        chunk = text[offset:offset + chunk_size]
        is_final = (offset + chunk_size >= len(text))
        packet = proto.encode_response(chunk, is_final)
        packets.append(packet)
        offset += chunk_size

    return packets


# Test
if __name__ == '__main__':
    proto = A2PProtocol()

    # Test encoding
    print("=== Encoding Tests ===")

    init_pkt = proto.encode_init(CAP_80_COL | CAP_LOWERCASE)
    print(f"INIT: {init_pkt.hex()}")

    chat_pkt = proto.encode_chat("Hello Claude!")
    print(f"CHAT: {chat_pkt.hex()}")

    resp_pkt = proto.encode_response("Here is your program:", is_final=False)
    print(f"RESP: {resp_pkt.hex()}")

    ack_pkt = proto.encode_ack(5)
    print(f"ACK: {ack_pkt.hex()}")

    # Test decoding
    print("\n=== Decoding Tests ===")

    proto2 = A2PProtocol()
    for pkt in [init_pkt, chat_pkt, resp_pkt, ack_pkt]:
        decoded = proto2.decode_packet(pkt)
        print(f"Decoded: {decoded}")

    # Test stream decoding
    print("\n=== Stream Decoding ===")

    # Simulate fragmented data
    all_data = init_pkt + chat_pkt + resp_pkt

    proto3 = A2PProtocol()
    chunk1 = all_data[:5]   # Partial first packet
    chunk2 = all_data[5:25] # Rest of first, partial second
    chunk3 = all_data[25:]  # Rest

    print(f"Chunk 1 ({len(chunk1)} bytes):")
    for p in proto3.decode_stream(chunk1):
        print(f"  {p}")

    print(f"Chunk 2 ({len(chunk2)} bytes):")
    for p in proto3.decode_stream(chunk2):
        print(f"  {p}")

    print(f"Chunk 3 ({len(chunk3)} bytes):")
    for p in proto3.decode_stream(chunk3):
        print(f"  {p}")

    # Test chunking
    print("\n=== Code Chunking ===")

    fake_basic = bytes(range(256)) + bytes(range(128))
    chunks = proto.chunk_data(fake_basic)
    print(f"Split {len(fake_basic)} bytes into {len(chunks)} chunks:")
    for chunk, offset, total in chunks:
        print(f"  offset={offset}, len={len(chunk)}, total={total}")
