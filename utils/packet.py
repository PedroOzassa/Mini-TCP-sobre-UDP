import struct
from typing import Dict


# Packet types (shared)
TYPE_DATA = 0
TYPE_ACK = 1
TYPE_NAK = 2


def compute_checksum(data: bytes) -> int:
    """Compute a 16-bit one's-complement checksum for `data`.

    The checksum is the one's-complement of the sum of all bytes
    truncated to 16 bits.
    """

    total = 0
    for b in data:
        total = (total + b) & 0xFFFF
    return (~total) & 0xFFFF


# -------------------- RDT 2.0 (no sequence number) --------------------
_struct_header_20 = struct.Struct("!BH")


def make_packet_20(pkt_type: int, payload: bytes = b"") -> bytes:
    """Build a RDT 2.0 packet: [type(1B) | checksum(2B) | payload]."""

    to_checksum = bytes([pkt_type]) + payload
    cs = compute_checksum(to_checksum)
    return _struct_header_20.pack(pkt_type, cs) + payload


def decode_packet_20(raw: bytes) -> Dict:
    """Decode a RDT 2.0 packet and return a dict with type/checksum/payload."""

    pkt_type, recv_cs = _struct_header_20.unpack(raw[: _struct_header_20.size])
    payload = raw[_struct_header_20.size :]
    calc_cs = compute_checksum(bytes([pkt_type]) + payload)

    return {
        "type": pkt_type,
        "checksum_ok": (recv_cs == calc_cs),
        "payload": payload,
    }


def make_data_20(data: bytes) -> bytes:
    return make_packet_20(TYPE_DATA, data)


def make_ack_20() -> bytes:
    return make_packet_20(TYPE_ACK)


def make_nak_20() -> bytes:
    return make_packet_20(TYPE_NAK)


def is_ack_20(pkt: Dict) -> bool:
    return pkt["type"] == TYPE_ACK and pkt["checksum_ok"]


def is_nak_20(pkt: Dict) -> bool:
    return pkt["type"] == TYPE_NAK and pkt["checksum_ok"]


# -------------------- RDT 2.1 / 3.0 (with seq number) --------------------
_struct_header_21 = struct.Struct("!BBH")


def make_packet_21(pkt_type: int, seq: int, payload: bytes = b"") -> bytes:
    """Build a RDT 2.1/3.0 packet: [type(1B) | seq(1B) | checksum(2B) | payload]."""

    to_checksum = bytes([pkt_type, seq]) + payload
    cs = compute_checksum(to_checksum)
    return _struct_header_21.pack(pkt_type, seq, cs) + payload


def decode_packet_21(raw: bytes) -> Dict:
    """Decode a RDT 2.1/3.0 packet and return a dict with type/seq/checksum/payload."""

    pkt_type, seq, recv_cs = _struct_header_21.unpack(raw[: _struct_header_21.size])
    payload = raw[_struct_header_21.size :]
    calc_cs = compute_checksum(bytes([pkt_type, seq]) + payload)

    return {
        "type": pkt_type,
        "seq": seq,
        "checksum_ok": (recv_cs == calc_cs),
        "payload": payload,
    }


def make_data_21(seq: int, data: bytes) -> bytes:
    return make_packet_21(TYPE_DATA, seq, data)


def make_ack_21(seq: int) -> bytes:
    return make_packet_21(TYPE_ACK, seq)


def make_nak_21(seq: int) -> bytes:
    return make_packet_21(TYPE_NAK, seq)


def is_ack_21(pkt: Dict, expected_seq: int) -> bool:
    return (
        pkt["type"] == TYPE_ACK and pkt["checksum_ok"] and pkt["seq"] == expected_seq
    )


def is_nak_21(pkt: Dict, expected_seq: int) -> bool:
    return (
        pkt["type"] == TYPE_NAK and pkt["checksum_ok"] and pkt["seq"] == expected_seq
    )
