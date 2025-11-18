import socket
import struct
from utils.simulator import UnreliableChannel


# ============================================================
# ===================== PACKET FORMAT =========================
# ============================================================

_struct_header = struct.Struct("!B B H")
# ! = network byte order
# B = type (1 byte)
# B = seqnum (1 byte)
# H = checksum (2 bytes)

TYPE_DATA = 0
TYPE_ACK  = 1
TYPE_NAK  = 2


def compute_checksum(data: bytes) -> int:
    """Compute a 16-bit one's-complement checksum for `data`.

    The checksum is the one's-complement of the sum of all bytes
    truncated to 16 bits.

    Args:
        data: Bytes over which to compute the checksum.

    Returns:
        The 16-bit checksum as an integer.
    """

    total = 0
    for b in data:
        total = (total + b) & 0xFFFF
    return (~total) & 0xFFFF


def make_packet(pkt_type: int, seq: int, payload: bytes = b"") -> bytes:
    """
    Build unified rdt2.1 packet:
        type (1B)
        seqnum (1B)
        checksum (2B)
        payload (...)
    Checksum is computed over: type + seq + payload
    """
    to_checksum = bytes([pkt_type, seq]) + payload
    cs = compute_checksum(to_checksum)

    return _struct_header.pack(pkt_type, seq, cs) + payload


def decode_packet(raw: bytes):
    """
    Decode unified rdt2.1 packet.
    Returns:
        {
            "type": ...,
            "seq": 0/1,
            "checksum_ok": bool,
            "payload": bytes
        }
    """
    pkt_type, seq, recv_cs = _struct_header.unpack(raw[:4])
    payload = raw[4:]

    calc_cs = compute_checksum(bytes([pkt_type, seq]) + payload)

    return {
        "type": pkt_type,
        "seq": seq,
        "checksum_ok": (recv_cs == calc_cs),
        "payload": payload
    }


# ============================================================
# ===================== HELPERS ==============================
# ============================================================

def make_data(seq: int, data: bytes) -> bytes:
    """Build a DATA packet for sequence number `seq` containing `data`.

    Args:
        seq: Sequence number (0 or 1) for the alternating-bit protocol.
        data: Payload bytes.

    Returns:
        The serialized DATA packet bytes.
    """

    return make_packet(TYPE_DATA, seq, data)


def make_ack(seq: int) -> bytes:
    """Build an ACK packet for sequence number `seq`.

    Args:
        seq: Sequence number being acknowledged.

    Returns:
        The serialized ACK packet bytes.
    """

    return make_packet(TYPE_ACK, seq)


def make_nak(seq: int) -> bytes:
    """Build a NAK packet for sequence number `seq`.

    Args:
        seq: Sequence number being negatively acknowledged.

    Returns:
        The serialized NAK packet bytes.
    """

    return make_packet(TYPE_NAK, seq)


def is_ack(pkt: dict, expected_seq: int) -> bool:
    """Return True if `pkt` is an ACK for `expected_seq` with valid checksum.

    Args:
        pkt: Decoded-packet dictionary returned by `decode_packet`.
        expected_seq: Expected sequence number to match for ACKs.

    Returns:
        True when `pkt` is an ACK, checksum is valid and sequence matches.
    """

    return (
        pkt["type"] == TYPE_ACK and
        pkt["checksum_ok"] and
        pkt["seq"] == expected_seq
    )


def is_nak(pkt: dict, expected_seq: int) -> bool:
    """Return True if `pkt` is a NAK for `expected_seq` with valid checksum.

    Args:
        pkt: Decoded-packet dictionary returned by `decode_packet`.
        expected_seq: Expected sequence number to match for NAKs.

    Returns:
        True when `pkt` is a NAK, checksum is valid and sequence matches.
    """

    return (
        pkt["type"] == TYPE_NAK and
        pkt["checksum_ok"] and
        pkt["seq"] == expected_seq
    )


# ============================================================
# ======================= SENDER ==============================
# ============================================================


class RDT21Sender:
    def __init__(self, local_addr, remote_addr, channel):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.remote_addr = remote_addr
        self.channel = channel

        self.seq = 0  # alternating bit protocol (0 → 1 → 0 → 1 ...)
        """Initialize an RDT 2.1 sender.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            remote_addr: Remote UDP address tuple to send packets to.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

    def send(self, data: bytes):
        """Send `data` reliably using the RDT 2.1 alternating-bit protocol.

        This will repeatedly transmit the DATA packet for the current
        sequence number until a matching ACK is received, then toggle the
        sequence number.

        Args:
            data: Payload bytes to send.
        """

        pkt = make_data(self.seq, data)

        while True:
            self.channel.send(pkt, self.sock, self.remote_addr)

            msg, _ = self.sock.recvfrom(2048)
            info = decode_packet(msg)

            if not info["checksum_ok"]:
                continue

            if is_nak(info, self.seq):
                continue

            if info["type"] == TYPE_ACK and info["seq"] != self.seq:
                continue

            if info["type"] == TYPE_NAK and info["seq"] != self.seq:
                continue
            
            if is_ack(info, self.seq):
                self.seq = 1 - self.seq
                return
            
# ============================================================
# ======================= RECEIVER ============================
# ============================================================

class RDT21Receiver:
    def __init__(self, local_addr, app_deliver_callback, channel):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.app_deliver = app_deliver_callback
        self.channel = channel
        self.expected_seq = 0
        """Initialize an RDT 2.1 receiver.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            app_deliver_callback: Callable invoked with payload bytes when a
                valid DATA packet with expected sequence is received.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

    def loop(self):
        """Run the receiver loop forever for RDT 2.1.

        The loop receives incoming packets, verifies checksum and sequence
        number, delivers in-order payloads to the application, and replies
        with ACK/NAK according to the protocol.
        """

        while True:
            pkt, sender_addr = self.sock.recvfrom(4096)
            info = decode_packet(pkt)

            if not info["checksum_ok"]:
                self.channel.send(make_nak(self.expected_seq), self.sock, sender_addr)
                continue

            if info["type"] != TYPE_DATA:
                continue

            if info["seq"] == self.expected_seq:
                self.app_deliver(info["payload"])
                self.channel.send(make_ack(self.expected_seq), self.sock, sender_addr)
                self.expected_seq = 1 - self.expected_seq
                continue

            # If DATA has wrong seq (duplicate)
            # → do NOT deliver, but ACK the last correctly received seq
            # i.e., ACK the opposite of expected_seq
            last_seq = 1 - self.expected_seq
            self.channel.send(make_ack(last_seq), self.sock, sender_addr)
