import socket

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


# helpers are provided by `utils.packet` (imported at module top)


# ============================================================
# ======================= SENDER ==============================
# ============================================================


class RDT21Sender:
    def __init__(self, local_addr, remote_addr, channel):
        """Initialize an RDT 2.1 sender.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            remote_addr: Remote UDP address tuple to send packets to.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.remote_addr = remote_addr
        self.channel = channel

        self.seq = 0

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
        """Initialize an RDT 2.1 receiver.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            app_deliver_callback: Callable invoked with payload bytes when a
                valid DATA packet with expected sequence is received.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.app_deliver = app_deliver_callback
        self.channel = channel
        self.expected_seq = 0

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
            else:
                last_seq = 1 - self.expected_seq
                self.channel.send(make_ack(last_seq), self.sock, sender_addr)
