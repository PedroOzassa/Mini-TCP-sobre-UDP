import threading
import time
import socket
import pytest

from utils.simulator import UnreliableChannel
from fase1.rdt20 import RDT20Sender, RDT20Receiver


# ==========================
# Utilities
# ==========================

def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


def run_receiver(receiver: RDT20Receiver):
    """Run the receiver loop in a thread."""
    receiver.loop()


# ==========================
#     TEST 1 — PERFECT CHANNEL
# ==========================

def test_rdt20_perfect_channel():
    delivered = []
    def app_deliver(data):
        delivered.append(data)

    # No loss, no corruption, near-zero delay
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.0,
        delay_range=(0.001, 0.002)
    )

    recv_port = free_udp_port()
    send_port = free_udp_port()

    receiver = RDT20Receiver(("127.0.0.1", recv_port), app_deliver)
    sender = RDT20Sender(("127.0.0.1", send_port), ("127.0.0.1", recv_port), channel)

    # Run receiver in thread
    t = threading.Thread(target=run_receiver, args=(receiver,), daemon=True)
    t.start()

    # Send 10 messages
    msgs = [f"msg_{i}".encode() for i in range(10)]
    for m in msgs:
        sender.send(m)

    time.sleep(1.0)  # allow delivery

    assert len(delivered) == 10
    assert delivered == msgs


# ==========================
#     TEST 2-4 — CORRUPTION, RETRANSMISSION, DELIVERY VALIDATION
# ==========================

def test_rdt20_corrupted_channel():
    delivered = []
    def app_deliver(data):
        delivered.append(data)

    # 30% corruption, no loss
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.3,
        delay_range=(0.001, 0.003)
    )

    recv_port = free_udp_port()
    send_port = free_udp_port()

    receiver = RDT20Receiver(("127.0.0.1", recv_port), app_deliver)
    sender = RDT20Sender(("127.0.0.1", send_port), ("127.0.0.1", recv_port), channel)

    t = threading.Thread(target=run_receiver, args=(receiver,), daemon=True)
    t.start()

    msgs = [f"message_{i}".encode() for i in range(10)]

    retransmissions = 0

    # Patch the sender to count retransmissions externally
    original_send = channel.send

    def send_wrapper(packet, dest_socket, dest_addr):
        nonlocal retransmissions
        # If packet is resent, it means first attempt failed → increment external counter
        # We detect retransmission when sender sends a packet whose checksum payload
        # has already been sent before for the same message. But easier: wrap sender loop.
        original_send(packet, dest_socket, dest_addr)

    channel.send = send_wrapper

    # Send messages and internally detect retransmissions
    for m in msgs:
        # Wrap sender send to count retransmissions from NAK loop
        count_before = getattr(sender, "retransmissions", 0)
        sender.send(m)
        count_after = getattr(sender, "retransmissions", 0)
        retransmissions += (count_after - count_before)

    time.sleep(1.0)

    # Verify all messages delivered correctly
    assert len(delivered) == 10
    assert delivered == msgs

    # Ensure retransmissions occurred (likely > 0 due to 30% corruption)
    assert retransmissions > 0
