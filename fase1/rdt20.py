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
    
    pkt_type, recv_cs = _struct_header.unpack(raw[:3])
    payload = raw[3:]

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
    return make_packet(TYPE_DATA, data)


def make_ack() -> bytes:
    return make_packet(TYPE_ACK)


def make_nak() -> bytes:
    return make_packet(TYPE_NAK)


def is_ack(pkt: dict) -> bool:
    return pkt["type"] == TYPE_ACK and pkt["checksum_ok"]


def is_nak(pkt: dict) -> bool:
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

    def send(self, data: bytes):
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

    def loop(self):
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
