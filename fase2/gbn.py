import socket
import struct
import threading

# ============================================================
# ===================== PACKET FORMAT =========================
# ============================================================

_struct_header = struct.Struct("!B I H")
# ! = network byte order
# B = type (1 byte)
# I = seqnum (4 bytes, unsigned)
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
    Unified GBN packet format:
        type (1B)
        seqnum (4B)
        checksum (2B)
        payload (...)
    Checksum is computed over: type + seq(4B) + payload
    """
    seq_bytes = seq.to_bytes(4)

    to_checksum = bytes([pkt_type]) + seq_bytes + payload
    cs = compute_checksum(to_checksum)

    return _struct_header.pack(pkt_type, seq, cs) + payload



def decode_packet(raw: bytes):
    pkt_type, seq, recv_cs = _struct_header.unpack(raw[:_struct_header.size])
    payload = raw[_struct_header.size:]

    seq_bytes = seq.to_bytes(4)
    calc_cs = compute_checksum(bytes([pkt_type]) + seq_bytes + payload)

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

def is_ack(pkt: dict, base: int, nextseqnum: int) -> bool:
    if pkt["type"] != TYPE_ACK:
        return False
    
    if not pkt["checksum_ok"]:
        return False

    return base <= pkt["seq"] < nextseqnum


# ============================================================
# ======================= SENDER ==============================
# ============================================================

class GBNSender:
    def __init__(self, local_addr, remote_addr, channel, N=4, timeout=2.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.remote_addr = remote_addr
        self.channel = channel

        # Sliding-window state
        self.base = 0
        self.nextseqnum = 0
        self.N = N

        # Store sent but unACKed packets: seq -> bytes
        self.send_buffer = {}

        # Timer infra
        self.timeout = timeout
        self._timer = None
        self._timeout_event = threading.Event()

    # ---------------------------------------------------------------------

    def _start_timer(self):
        # Only start for base packet
        self._timeout_event.clear()
        self._timer = threading.Timer(self.timeout, self._timer_expired)
        self._timer.start()

    def _stop_timer(self):
        if self._timer:
            self._timer.cancel()
        self._timeout_event.set()

    def _timer_expired(self):
        self._timeout_event.set()

    # ---------------------------------------------------------------------

    def send(self, data: bytes):
        """
        Application wants to send a single new message.
        Implement sliding-window logic.
        """

        # Wait while window is full
        while (self.nextseqnum - self.base) >= self.N:
            self._handle_incoming()   # process ACKs while waiting

        seq = self.nextseqnum & 0xFFFFFFFF
        pkt = make_data(seq, data)

        # Store it
        self.send_buffer[seq] = pkt

        # Send it
        self.channel.send(pkt, self.sock, self.remote_addr)

        # If sending base packet, start timer
        if self.base == self.nextseqnum:
            self._start_timer()

        self.nextseqnum += 1

        # After sending, process ACKs until the message is accepted
        while seq in self.send_buffer:
            # Either process ACKs or timeout
            if self._timeout_event.is_set():
                self._timeout_event.clear()
                self._on_timeout()
                continue

            self._handle_incoming()

    # ---------------------------------------------------------------------

    def _handle_incoming(self):
        self.sock.settimeout(0.05)
        try:
            raw, _ = self.sock.recvfrom(2048)
        except socket.timeout:
            return

        pkt = decode_packet(raw)
        if not pkt["checksum_ok"]:
            return

        # Use your logic
        if not is_ack(pkt, self.base, self.nextseqnum):
            return

        ack = pkt["seq"]

        # Slide window: base = ack + 1
        old_base = self.base
        self.base = ack + 1

        # Remove acknowledged packets
        for s in list(self.send_buffer.keys()):
            if self.base > s:        # acknowledged falls below new base
                del self.send_buffer[s]

        # Timer logic
        if self.base == self.nextseqnum:
            self._stop_timer()
        else:
            self._stop_timer()
            self._start_timer()


    # ---------------------------------------------------------------------

    def _on_timeout(self):
        """Timeout: retransmit all packets in the window."""
        # Retransmit packets base .. nextseqnum-1
        for s in sorted(self.send_buffer.keys()):
            self.channel.send(self.send_buffer[s], self.sock, self.remote_addr)

        # Restart timer
        self._stop_timer()
        self._start_timer()

    # ---------------------------------------------------------------------


class GBNReceiver:
    def __init__(self, local_addr, app_deliver, channel):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.app_deliver = app_deliver
        self.channel = channel

        # Next in-order packet expected
        self.expectedseqnum = 0

    def start(self):
        # Same style as your RDT20/21/30 receivers
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            raw, addr = self.sock.recvfrom(2048)
            pkt = decode_packet(raw)

            # Corrupted → send dup ACK for last good
            if not pkt["checksum_ok"]:
                last_good = (self.expectedseqnum - 1) & 0xFFFFFFFF
                ack = make_ack(last_good)
                self.channel.send(ack, self.sock, addr)
                continue

            # Not data → ignore silently
            if pkt["type"] != TYPE_DATA:
                continue

            seq = pkt["seq"]

            # Correct in-order packet
            if seq == self.expectedseqnum:
                # deliver to app
                self.app_deliver(pkt["payload"])

                # ACK(expectedseqnum)
                ack = make_ack(self.expectedseqnum)
                self.channel.send(ack, self.sock, addr)

                # advance expected sequence number
                self.expectedseqnum = (self.expectedseqnum + 1) & 0xFFFFFFFF
                continue

            # Out-of-order packet → send duplicate ACK for last good
            last_good = (self.expectedseqnum - 1) & 0xFFFFFFFF
            ack = make_ack(last_good)
            self.channel.send(ack, self.sock, addr)
