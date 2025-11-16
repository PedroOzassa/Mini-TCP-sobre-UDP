import socket
import struct
from utils.simulator import UnreliableChannel


# ============================================================
# ===================== PACKET FORMAT ========================
# ============================================================

_struct_checksum = struct.Struct("!H")


def compute_checksum(data: bytes) -> int:
    """16-bit additive checksum (simple RDT-compliant version)."""
    total = 0
    for b in data:
        total = (total + b) & 0xFFFF
    return (~total) & 0xFFFF


def make_packet(data: bytes) -> bytes:
    """Data packet: [2-byte checksum | payload]."""
    cs = compute_checksum(data)
    return _struct_checksum.pack(cs) + data


def decode_packet(packet: bytes):
    """Return: { checksum_ok: bool, data: bytes }."""
    recv_cs, = _struct_checksum.unpack(packet[:2])
    payload = packet[2:]
    calc = compute_checksum(payload)
    return {
        "checksum_ok": (recv_cs == calc),
        "data": payload
    }


def make_ack() -> bytes:
    return b"ACK"


def make_nak() -> bytes:
    return b"NAK"


def is_ack(msg: bytes) -> bool:
    return msg == b"ACK"


def is_nak(msg: bytes) -> bool:
    return msg == b"NAK"


# ============================================================
# ======================= SENDER ==============================
# ============================================================

class RDT20Sender:
    """
    Reliable sender using rdt2.0 protocol.
    Assumptions:
      - Data packets may be corrupted/lost (via UnreliableChannel).
      - ACK/NAK are never corrupted or lost.
      - No sequence numbers in rdt2.0.
    """

    def __init__(self, local_addr, remote_addr, channel: UnreliableChannel):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.remote_addr = remote_addr
        self.channel = channel

    def send(self, data: bytes):
        """
        Implements:
            send data
            wait ACK/NAK
            if NAK → retransmit
            if ACK → return
        """
        pkt = make_packet(data)

        while True:
            # send unreliable DATA packet
            self.channel.send(pkt, self.sock, self.remote_addr)

            # wait for ACK or NAK (reliable)
            msg, _ = self.sock.recvfrom(2048)

            if is_ack(msg):
                return
            if is_nak(msg):
                continue  # retransmit


# ============================================================
# ======================= RECEIVER ============================
# ============================================================

class RDT20Receiver:
    """
    Reliable receiver using rdt2.0 protocol.
    Assumptions:
      - Incoming data packets may be corrupted.
      - ACK and NAK sent reliably over UDP.
      - No sequence numbers.
    """

    def __init__(self, local_addr, app_deliver_callback):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.app_deliver = app_deliver_callback

    def loop(self):
        """
        Blocking receive loop.
        Your test file should run this on a separate thread.
        """
        while True:
            pkt, sender_addr = self.sock.recvfrom(4096)

            info = decode_packet(pkt)

            if not info["checksum_ok"]:
                # corrupted → send NAK
                self.sock.sendto(make_nak(), sender_addr)
                continue

            # correct → deliver + send ACK
            self.app_deliver(info["data"])
            self.sock.sendto(make_ack(), sender_addr)
