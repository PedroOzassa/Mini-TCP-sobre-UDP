import socket
import threading

from utils.packet import (
    TYPE_DATA,
    TYPE_ACK,
    TYPE_NAK,
    make_data_21 as make_data,
    make_ack_21 as make_ack,
    make_nak_21 as make_nak,
    decode_packet_21 as decode_packet,
    is_ack_21 as is_ack,
    is_nak_21 as is_nak,
)


# packet helpers are provided by `utils.packet` (rdt2.1/3.0 variants)


# ============================================================
# ======================= SENDER ==============================
# ============================================================

class RDT30Sender:
    def __init__(self, local_addr, remote_addr, channel, timeout=2.0):
        """Initialize an RDT 3.0 sender with timeout-based retransmission.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            remote_addr: Remote UDP address tuple to send packets to.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
            timeout: Timeout interval (seconds) for retransmission (default 2.0).
        """

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

