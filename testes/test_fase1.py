import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

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
    """Return an unused UDP port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    _, port = s.getsockname()
    s.close()
    return port


def start_receiver(receiver: RDT20Receiver):
    """Run receiver loop in a background thread."""
    t = threading.Thread(target=receiver.loop, daemon=True)
    t.start()
    return t


# ============================================================================
# TEST 1 — PERFECT CHANNEL (no corruption, no loss)
# ============================================================================

def test_rdt20_perfect_channel():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.0,
        delay_range=(0.001, 0.003)
    )

    recv_port = free_udp_port()
    send_port = free_udp_port()

    receiver = RDT20Receiver(("127.0.0.1", recv_port), app_deliver)
    sender = RDT20Sender(("127.0.0.1", send_port), ("127.0.0.1", recv_port), channel)

    start_receiver(receiver)

    msgs = [f"msg_{i}".encode() for i in range(10)]
    for m in msgs:
        sender.send(m)

    time.sleep(0.5)

    assert delivered == msgs
    assert len(delivered) == 10


# ============================================================================
# TEST 2 — CORRUPTION ONLY (30% corruption)
# ============================================================================

def test_rdt20_corruption_only():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.3,
        delay_range=(0.001, 0.003)
    )

    recv_port = free_udp_port()
    send_port = free_udp_port()

    receiver = RDT20Receiver(("127.0.0.1", recv_port), app_deliver)
    sender = RDT20Sender(("127.0.0.1", send_port), ("127.0.0.1", recv_port), channel)

    start_receiver(receiver)

    msgs = [f"data_{i}".encode() for i in range(10)]
    for m in msgs:
        sender.send(m)

    time.sleep(1.0)

    assert delivered == msgs
    assert len(delivered) == 10


# ============================================================================
# TEST 3 — VERIFY DELIVERY CORRECTNESS
# ============================================================================

def test_rdt20_delivery_correctness():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    # Moderate corruption to challenge delivery
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.25,
        delay_range=(0.001, 0.005)
    )

    recv_port = free_udp_port()
    send_port = free_udp_port()

    receiver = RDT20Receiver(("127.0.0.1", recv_port), app_deliver)
    sender = RDT20Sender(("127.0.0.1", send_port), ("127.0.0.1", recv_port), channel)

    start_receiver(receiver)

    msgs = [f"packet_{i}".encode() for i in range(10)]

    for m in msgs:
        sender.send(m)

    time.sleep(1.2)

    assert delivered == msgs
    assert len(delivered) == 10


# ============================================================================
# TEST 4 — COUNT RETRANSMISSIONS
# ============================================================================

def test_rdt20_retransmission_count():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    # High corruption to guarantee retransmissions
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.3,
        delay_range=(0.001, 0.008)
    )

    recv_port = free_udp_port()
    send_port = free_udp_port()

    receiver = RDT20Receiver(("127.0.0.1", recv_port), app_deliver)
    sender = RDT20Sender(("127.0.0.1", send_port), ("127.0.0.1", recv_port), channel)

    start_receiver(receiver)

    # Count retransmissions by wrapping channel.send
    retransmissions = 0
    original_send = channel.send

    def send_wrapper(packet, dest_socket, dest_addr):
        nonlocal retransmissions
        # Every time RDT20Sender sends the same data again → retransmission
        retransmissions += 1
        return original_send(packet, dest_socket, dest_addr)

    channel.send = send_wrapper

    msgs = [f"msg_{i}".encode() for i in range(10)]

    for m in msgs:
        sender.send(m)

    time.sleep(1.0)

    assert delivered == msgs
    assert len(delivered) == 10
    assert retransmissions > 10   # must be > number of original sends
