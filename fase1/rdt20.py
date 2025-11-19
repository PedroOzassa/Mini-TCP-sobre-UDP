import socket

from utils.packet import (
    TYPE_DATA,
    TYPE_ACK,
    TYPE_NAK,
    make_packet_20 as make_packet,
    decode_packet_20 as decode_packet,
    make_data_20 as make_data,
    make_ack_20 as make_ack,
    make_nak_20 as make_nak,
    is_ack_20 as is_ack,
    is_nak_20 as is_nak,
)


# packet helpers are provided by `utils.packet` and imported above


# helpers are provided by `utils.packet` and imported above

# ============================================================
# ======================= SENDER ==============================
# ============================================================


class RDT20Sender:
    def __init__(self, local_addr, remote_addr, channel):
        """Initialize an RDT 2.0 sender.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            remote_addr: Remote UDP address tuple to send packets to.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)

        self.remote_addr = remote_addr
        self.channel = channel

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
        """Initialize an RDT 2.0 receiver.

        Args:
            local_addr: Local UDP address tuple to bind to (host, port).
            app_deliver_callback: Callable invoked with payload bytes when a
                valid DATA packet is received.
            channel: Channel-like object exposing `send(packet, sock, addr)`.
        """

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.app_deliver = app_deliver_callback
        self.channel = channel

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
