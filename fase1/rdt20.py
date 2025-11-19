import socket
import struct
from utils.simulator import UnreliableChannel


# ============================================================
# ===================== PACKET FORMAT =========================
# ============================================================

_struct_header = struct.Struct("!BH")  
# ! = network byte order
# B = type (1 byte)
# H = checksum (2 bytes)

TYPE_DATA = 0
TYPE_ACK = 1
TYPE_NAK = 2


def compute_checksum(data: bytes) -> int:
    """Compute a 16-bit one's-complement checksum for `data`.

    The checksum is computed as the one's-complement of the
    sum of all bytes truncated to 16 bits.

    Args:
        data: Bytes over which to compute the checksum.

    Returns:
        The 16-bit checksum as an integer.
    """

    total = 0
    for b in data:
        total = (total + b) & 0xFFFF
    return (~total) & 0xFFFF


def make_packet(pkt_type: int, payload: bytes = b"") -> bytes:
    """
    Build unified packet: [type | checksum | payload]
    Checksum computed over: type byte + payload bytes
    """
    to_checksum = bytes([pkt_type]) + payload
    cs = compute_checksum(to_checksum)
    return _struct_header.pack(pkt_type, cs) + payload


def decode_packet(raw: bytes):
    """
    Decode unified packet.
    Returns:
        {
            "type": TYPE_DATA/TYPE_ACK/TYPE_NAK,
            "checksum_ok": bool,
            "payload": bytes
        }
    """
    
    pkt_type, recv_cs = _struct_header.unpack(raw[:_struct_header.size])
    payload = raw[_struct_header.size:]

    calc_cs = compute_checksum(bytes([pkt_type]) + payload)

    return {
        "type": pkt_type,
        "checksum_ok": (recv_cs == calc_cs),
        "payload": payload
    }


# ============================================================
# ===================== HELPERS ==============================
# ============================================================

def make_data(data: bytes) -> bytes:
    """Build a DATA packet containing `data` as payload.

    Args:
        data: Payload bytes to include in the DATA packet.

    Returns:
        The serialized packet bytes.
    """

    return make_packet(TYPE_DATA, data)


def make_ack() -> bytes:
    """Build an ACK packet with no payload.

    Returns:
        The serialized ACK packet bytes.
    """

    return make_packet(TYPE_ACK)


def make_nak() -> bytes:
    """Build a NAK packet with no payload.

    Returns:
        The serialized NAK packet bytes.
    """

    return make_packet(TYPE_NAK)


def is_ack(pkt: dict) -> bool:
    """Return True if `pkt` is a valid ACK packet.

    Args:
        pkt: Decoded-packet dictionary returned by `decode_packet`.

    Returns:
        True when `pkt` is an ACK and the checksum is valid.
    """

    return pkt["type"] == TYPE_ACK and pkt["checksum_ok"]


def is_nak(pkt: dict) -> bool:
    """Return True if `pkt` is a valid NAK packet.

    Args:
        pkt: Decoded-packet dictionary returned by `decode_packet`.

    Returns:
        True when `pkt` is a NAK and the checksum is valid.
    """

    return pkt["type"] == TYPE_NAK and pkt["checksum_ok"]


# ============================================================
# ======================= SENDER ==============================
# ============================================================


class RDT20Sender:
    def __init__(self, local_addr, remote_addr, channel):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.remote_addr = remote_addr
        self.channel = channel
        """Initialize an RDT 2.0 sender.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            remote_addr: Remote UDP address tuple to send packets to.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

    def send(self, data: bytes):
        """Send `data` reliably using the RDT 2.0 sender protocol.

        This will repeatedly transmit the DATA packet until a valid ACK
        (with correct checksum) is received from the receiver.

        Args:
            data: Payload bytes to send.
        """

        pkt = make_packet(TYPE_DATA, data)

        while True:
            self.channel.send(pkt, self.sock, self.remote_addr)

            msg, _ = self.sock.recvfrom(2048)
            info = decode_packet(msg)
            
            if not info["checksum_ok"]:
                continue
            
            if is_nak(info):
                continue
            
            if is_ack(info):
                return
                   
# ============================================================
# ======================= RECEIVER ============================
# ============================================================

class RDT20Receiver:
    def __init__(self, local_addr, app_deliver_callback, channel):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.app_deliver = app_deliver_callback
        self.channel = channel
        """Initialize an RDT 2.0 receiver.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            app_deliver_callback: Callable invoked with payload bytes when a
                valid DATA packet is received.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

    def loop(self):
        """Run the receiver loop forever.

        The loop receives incoming UDP packets, checks the checksum and
        packet type, and either delivers the payload to the application
        or sends a NAK/ACK back to the sender as appropriate.
        """

        while True:
            pkt, sender_addr = self.sock.recvfrom(4096)
            info = decode_packet(pkt)

            if not info["checksum_ok"]:
                self.channel.send(make_nak(), self.sock, sender_addr)
                continue

            if info["type"] != TYPE_DATA:
                continue

            self.app_deliver(info["payload"])
            self.channel.send(make_ack(), self.sock, sender_addr)
