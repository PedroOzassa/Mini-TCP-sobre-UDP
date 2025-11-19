import socket
import struct
import threading
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
    total = 0
    for b in data:
        total = (total + b) & 0xFFFF
    return (~total) & 0xFFFF


def make_packet(pkt_type: int, seq: int, payload: bytes = b"") -> bytes:
    """
    Build unified rdt3.0 packet:
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
    Decode unified rdt3.0 packet.
    Returns:
        {
            "type": ...,
            "seq": int, # Incrementing sequence
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
    return make_packet(TYPE_DATA, seq, data)


def make_ack(seq: int) -> bytes:
    return make_packet(TYPE_ACK, seq)


def make_nak(seq: int) -> bytes:
    return make_packet(TYPE_NAK, seq)


def is_ack(pkt: dict, expected_seq: int) -> bool:
    return (
        pkt["type"] == TYPE_ACK and
        pkt["checksum_ok"] and
        pkt["seq"] == expected_seq
    )


def is_nak(pkt: dict, expected_seq: int) -> bool:
    return (
        pkt["type"] == TYPE_NAK and
        pkt["checksum_ok"] and
        pkt["seq"] == expected_seq
    )

# ============================================================
# ======================= SENDER ==============================
# ============================================================

class RDT30Sender:
    def __init__(self, local_addr, remote_addr, channel, timeout=2.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.remote_addr = remote_addr
        self.channel = channel

        self.seq = 0 
        
        self.timeout = timeout
        self._timer = None
        self._timeout_event = threading.Event()
        
    def _start_timer(self):
        self._timeout_event.clear()
        self._timer = threading.Timer(self.timeout, self._timer_expired)
        self._timer.start()

    def _stop_timer(self):
        if self._timer:
            self._timer.cancel()
        self._timeout_event.set()

    def _timer_expired(self):
        self._timeout_event.set()

    def send(self, data: bytes):
        pkt = make_data(self.seq, data)

        while True:
            self.channel.send(pkt, self.sock, self.remote_addr)
            
            self._start_timer()

            while True:
                if self._timeout_event.is_set():
                    break

                self.sock.settimeout(0.1)
                try:
                    msg, _ = self.sock.recvfrom(2048)
                except socket.timeout:
                    continue

                info = decode_packet(msg)

                if not info["checksum_ok"]:
                    continue

                if is_nak(info, self.seq):
                    continue

                if info["type"] == TYPE_ACK and info["seq"] != self.seq:
                    continue

                if is_ack(info, self.seq):
                    self._stop_timer()
                    
                    # Seqnum needed to be changed to account for the possibility
                    # of extreme delay, much more than the timeout window in the
                    # Sender. The old 0/1 alternating bit could cause problems
                    # if there was enough time for two complete packages to pass
                    # through the channel, leaving a stale ACK with a "correct" 
                    # seqnum still in travel, causing a possible packet loss.
                    self.seq = (self.seq + 1) & 0xFF
                    return

# ============================================================
# ======================= RECEIVER ============================
# ============================================================

class RDT30Receiver:
    def __init__(self, local_addr, app_deliver_callback, channel):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.app_deliver = app_deliver_callback
        self.channel = channel
        self.expected_seq = 0

    def loop(self):
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
                
                # Seqnum needed to be changed to account for the possibility
                # of extreme delay, much more than the timeout window in the
                # Sender. The old 0/1 alternating bit could cause problems
                # if there was enough time for two complete packages to pass
                # through the channel, leaving a stale ACK with a "correct" 
                # seqnum still in travel, causing a possible packet loss.
                self.expected_seq = (self.expected_seq + 1) & 0xFF
            else:
                last_seq = (self.expected_seq - 1) & 0xFF
                self.channel.send(make_ack(last_seq), self.sock, sender_addr)

