#!/usr/bin/env python3
"""
Unit tests for A2P Protocol implementation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'proxy'))

import pytest
from a2p_protocol import (
    A2PProtocol, A2PConnection, PacketType, Packet,
    MAGIC, HEADER_SIZE, MAX_DATA_SIZE,
    CAP_40_COL, CAP_80_COL, CAP_LOWERCASE,
    create_code_packets, create_response_packets
)


class TestA2PProtocol:
    """Tests for the base protocol encoder/decoder."""

    def setup_method(self):
        """Create fresh protocol instance for each test."""
        self.proto = A2PProtocol()

    # === Encoding Tests ===

    def test_encode_magic(self):
        """Packets should start with 'A2' magic bytes."""
        packet = self.proto.encode(PacketType.INIT, b'')
        assert packet[:2] == MAGIC

    def test_encode_type(self):
        """Packet type should be at byte 2."""
        packet = self.proto.encode(PacketType.CHAT, b'')
        assert packet[2] == PacketType.CHAT

    def test_encode_length(self):
        """Data length should be little-endian at bytes 3-4."""
        data = b'Hello'
        packet = self.proto.encode(PacketType.CHAT, data)
        length = packet[3] | (packet[4] << 8)
        assert length == len(data)

    def test_encode_sequence(self):
        """Sequence number should increment."""
        p1 = self.proto.encode(PacketType.CHAT, b'')
        p2 = self.proto.encode(PacketType.CHAT, b'')
        assert p1[5] == 0
        assert p2[5] == 1

    def test_encode_sequence_wraps(self):
        """Sequence should wrap at 256."""
        self.proto.tx_seq = 255
        p1 = self.proto.encode(PacketType.CHAT, b'')
        p2 = self.proto.encode(PacketType.CHAT, b'')
        assert p1[5] == 255
        assert p2[5] == 0

    def test_encode_data(self):
        """Data should be included after header."""
        data = b'Test data'
        packet = self.proto.encode(PacketType.CHAT, data)
        assert packet[6:6+len(data)] == data

    def test_encode_checksum(self):
        """Checksum should be XOR of Type through Data."""
        data = b'Test'
        packet = self.proto.encode(PacketType.CHAT, data)
        # Calculate expected checksum
        body = packet[2:-1]  # Type + Len + Seq + Data
        expected = 0
        for b in body:
            expected ^= b
        assert packet[-1] == expected

    def test_encode_max_data(self):
        """Should accept data up to MAX_DATA_SIZE."""
        data = bytes(MAX_DATA_SIZE)
        packet = self.proto.encode(PacketType.CODE, data)
        assert len(packet) == HEADER_SIZE + MAX_DATA_SIZE + 1

    def test_encode_data_too_large(self):
        """Should raise error for oversized data."""
        data = bytes(MAX_DATA_SIZE + 1)
        with pytest.raises(ValueError):
            self.proto.encode(PacketType.CODE, data)

    # === Decoding Tests ===

    def test_decode_valid_packet(self):
        """Should decode a valid packet."""
        original = self.proto.encode(PacketType.CHAT, b'Hello')
        decoded = self.proto.decode_packet(original)
        assert decoded is not None
        assert decoded.ptype == PacketType.CHAT
        assert decoded.data == b'Hello'

    def test_decode_preserves_sequence(self):
        """Should preserve sequence number."""
        self.proto.tx_seq = 42
        original = self.proto.encode(PacketType.INIT, b'')
        decoded = self.proto.decode_packet(original)
        assert decoded.seq == 42

    def test_decode_invalid_magic(self):
        """Should reject packets with wrong magic."""
        packet = b'XX' + b'\x01\x00\x00\x00\x01'
        decoded = self.proto.decode_packet(packet)
        assert decoded is None

    def test_decode_truncated_header(self):
        """Should reject truncated packets."""
        packet = MAGIC + b'\x01\x05'  # Missing bytes
        decoded = self.proto.decode_packet(packet)
        assert decoded is None

    def test_decode_bad_checksum(self):
        """Should reject packets with bad checksum."""
        packet = self.proto.encode(PacketType.CHAT, b'Test')
        bad_packet = packet[:-1] + bytes([packet[-1] ^ 0xFF])
        decoded = self.proto.decode_packet(bad_packet)
        assert decoded is None

    def test_decode_unknown_type(self):
        """Should reject packets with unknown type."""
        # Manually craft packet with invalid type
        packet = MAGIC + bytes([0xFF, 0x00, 0x00, 0x00, 0xFF])
        decoded = self.proto.decode_packet(packet)
        assert decoded is None

    # === Stream Decoding Tests ===

    def test_stream_single_packet(self):
        """Should decode single packet from stream."""
        packet = self.proto.encode(PacketType.INIT, b'X')
        result = list(self.proto.decode_stream(packet))
        assert len(result) == 1
        assert result[0].ptype == PacketType.INIT

    def test_stream_multiple_packets(self):
        """Should decode multiple packets from stream."""
        p1 = self.proto.encode(PacketType.INIT, b'1')
        p2 = self.proto.encode(PacketType.CHAT, b'2')
        p3 = self.proto.encode(PacketType.RESP, b'3')

        result = list(self.proto.decode_stream(p1 + p2 + p3))
        assert len(result) == 3
        assert result[0].ptype == PacketType.INIT
        assert result[1].ptype == PacketType.CHAT
        assert result[2].ptype == PacketType.RESP

    def test_stream_fragmented(self):
        """Should handle fragmented data across calls."""
        packet = self.proto.encode(PacketType.CHAT, b'Hello World!')

        proto2 = A2PProtocol()

        # Feed first half
        result1 = list(proto2.decode_stream(packet[:5]))
        assert len(result1) == 0

        # Feed second half
        result2 = list(proto2.decode_stream(packet[5:]))
        assert len(result2) == 1
        assert result2[0].data == b'Hello World!'

    def test_stream_garbage_before_packet(self):
        """Should skip garbage before valid packet."""
        garbage = b'\x00\xFF\x00\xFF'
        packet = self.proto.encode(PacketType.INIT, b'X')

        result = list(self.proto.decode_stream(garbage + packet))
        assert len(result) == 1
        assert result[0].ptype == PacketType.INIT

    # === Convenience Method Tests ===

    def test_encode_init(self):
        """Should encode INIT with capabilities."""
        caps = CAP_80_COL | CAP_LOWERCASE
        packet = self.proto.encode_init(caps)
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.INIT
        assert decoded.data == bytes([caps])

    def test_encode_chat(self):
        """Should encode CHAT message in uppercase."""
        packet = self.proto.encode_chat("Hello World")
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.CHAT
        assert decoded.data == b'HELLO WORLD'

    def test_encode_response(self):
        """Should encode RESP with flags byte."""
        packet = self.proto.encode_response("Test", is_final=False)
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.RESP
        assert decoded.data[0] == 0x00  # Not final
        assert decoded.data[1:] == b'Test'

        packet2 = self.proto.encode_response("End", is_final=True)
        decoded2 = self.proto.decode_packet(packet2)
        assert decoded2.data[0] == 0x01  # Final

    def test_encode_code_chunk(self):
        """Should encode CODE chunk with offset/total header."""
        chunk = b'BASIC DATA'
        packet = self.proto.encode_code_chunk(chunk, offset=256, total=1024)
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.CODE

        # Parse header
        offset = decoded.data[0] | (decoded.data[1] << 8)
        total = decoded.data[2] | (decoded.data[3] << 8)
        assert offset == 256
        assert total == 1024
        assert decoded.data[4:] == chunk

    def test_encode_ack(self):
        """Should encode ACK with acknowledged sequence."""
        packet = self.proto.encode_ack(42)
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.ACK
        assert decoded.data[0] == 42

    def test_encode_nack(self):
        """Should encode NACK with requested sequence."""
        packet = self.proto.encode_nack(7)
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.NACK
        assert decoded.data[0] == 7

    def test_encode_status(self):
        """Should encode STATUS message."""
        packet = self.proto.encode_status("Processing...")
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.STATUS
        assert decoded.data == b'Processing...'

    def test_encode_error(self):
        """Should encode ERR message."""
        packet = self.proto.encode_error("Connection failed")
        decoded = self.proto.decode_packet(packet)
        assert decoded.ptype == PacketType.ERR
        assert decoded.data == b'Connection failed'

    # === Chunking Tests ===

    def test_chunk_small_data(self):
        """Small data should produce single chunk."""
        data = b'Small'
        chunks = self.proto.chunk_data(data)
        assert len(chunks) == 1
        assert chunks[0][0] == data
        assert chunks[0][1] == 0  # offset
        assert chunks[0][2] == len(data)  # total

    def test_chunk_large_data(self):
        """Large data should be split into chunks."""
        data = bytes(500)
        chunks = self.proto.chunk_data(data)
        assert len(chunks) > 1

        # Verify all data is covered
        reconstructed = b''
        for chunk, offset, total in chunks:
            assert total == 500
            reconstructed += chunk
        assert reconstructed == data

    def test_chunk_exact_boundary(self):
        """Data exactly at chunk size should work."""
        chunk_size = MAX_DATA_SIZE - 4  # Default chunk size
        data = bytes(chunk_size * 2)
        chunks = self.proto.chunk_data(data)
        assert len(chunks) == 2


class TestA2PConnection:
    """Tests for the connection handler with ACK/NACK."""

    def setup_method(self):
        """Create fresh connection for each test."""
        self.sent_packets = []
        self.conn = A2PConnection(lambda p: self.sent_packets.append(p))

    def test_send_packet(self):
        """Should send encoded packet."""
        self.conn.send_packet(PacketType.CHAT, b'Hello')
        assert len(self.sent_packets) == 1
        assert self.sent_packets[0][:2] == MAGIC

    def test_tracks_pending_acks(self):
        """Should track packets awaiting ACK."""
        seq = self.conn.send_packet(PacketType.CHAT, b'Test')
        assert seq in self.conn.pending_acks

    def test_ack_removes_pending(self):
        """Receiving ACK should remove from pending."""
        seq = self.conn.send_packet(PacketType.CHAT, b'Test')
        assert seq in self.conn.pending_acks

        ack_packet = Packet(PacketType.ACK, 0, bytes([seq]))
        self.conn.handle_received(ack_packet)
        assert seq not in self.conn.pending_acks

    def test_nack_triggers_retransmit(self):
        """Receiving NACK should retransmit packet."""
        seq = self.conn.send_packet(PacketType.CHAT, b'Test')
        initial_count = len(self.sent_packets)

        nack_packet = Packet(PacketType.NACK, 0, bytes([seq]))
        self.conn.handle_received(nack_packet)

        assert len(self.sent_packets) == initial_count + 1

    def test_sends_ack_for_received(self):
        """Should send ACK for received data packets."""
        packet = Packet(PacketType.CHAT, 5, b'Hello')
        self.conn.handle_received(packet)

        # Should have sent an ACK
        assert len(self.sent_packets) == 1
        decoded = self.conn.proto.decode_packet(self.sent_packets[0])
        assert decoded.ptype == PacketType.ACK
        assert decoded.data[0] == 5

    def test_ignores_duplicate_packet(self):
        """Should ignore duplicate packets (same seq)."""
        packet = Packet(PacketType.CHAT, 5, b'Hello')

        result1 = self.conn.handle_received(packet)
        result2 = self.conn.handle_received(packet)

        assert result1 is not None
        assert result2 is None  # Duplicate ignored

    def test_retransmit_pending(self):
        """Should retransmit all pending on timeout."""
        self.conn.send_packet(PacketType.CHAT, b'One')
        self.conn.send_packet(PacketType.CHAT, b'Two')
        initial_count = len(self.sent_packets)

        count = self.conn.retransmit_pending()

        assert count == 2
        assert len(self.sent_packets) == initial_count + 2


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_create_code_packets(self):
        """Should create packets for tokenized BASIC."""
        proto = A2PProtocol()
        tokenized = bytes(300)  # Fake BASIC program

        packets = create_code_packets(proto, tokenized)

        # Should have multiple data packets plus end marker
        assert len(packets) > 2

        # Last packet should signal end
        last = proto.decode_packet(packets[-1])
        assert last.ptype == PacketType.CODE
        # Empty chunk signals end
        chunk_data = last.data[4:]  # Skip offset/total header
        assert len(chunk_data) == 0

    def test_create_response_packets(self):
        """Should create packets for response text."""
        proto = A2PProtocol()
        text = "This is a test response " * 10  # Long text

        packets = create_response_packets(proto, text)

        assert len(packets) > 1

        # Verify final flag
        last = proto.decode_packet(packets[-1])
        assert last.data[0] == 0x01  # is_final

        # Verify all others are not final
        for pkt in packets[:-1]:
            decoded = proto.decode_packet(pkt)
            assert decoded.data[0] == 0x00


class TestRoundTrip:
    """Integration tests for encode/decode round trips."""

    def test_all_packet_types(self):
        """All packet types should round-trip correctly."""
        proto = A2PProtocol()

        test_cases = [
            (PacketType.INIT, bytes([CAP_80_COL])),
            (PacketType.CHAT, b'TEST MESSAGE'),
            (PacketType.RESP, b'\x01RESPONSE'),
            (PacketType.CODE, b'\x00\x00\x10\x00DATA'),
            (PacketType.STATUS, b'STATUS MSG'),
            (PacketType.ACK, bytes([42])),
            (PacketType.NACK, bytes([7])),
            (PacketType.ERR, b'ERROR'),
        ]

        for ptype, data in test_cases:
            encoded = proto.encode(ptype, data)
            decoded = proto.decode_packet(encoded)

            assert decoded is not None, f"Failed to decode {ptype.name}"
            assert decoded.ptype == ptype
            assert decoded.data == data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
