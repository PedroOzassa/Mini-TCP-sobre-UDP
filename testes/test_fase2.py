import time
import threading
import pytest
from utils.simulator import UnreliableChannel
from fase2.gbn import GBNSender, GBNReceiver, make_ack  # adjust import paths


# ---------------------------------------------------------
# Helper: allocate free ports
# ---------------------------------------------------------
import socket
def free_udp_addr():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    addr = s.getsockname()
    s.close()
    return addr


# ---------------------------------------------------------
# Helper: start receiver thread (same as your previous tests)
# ---------------------------------------------------------
def start_receiver(receiver):
    receiver.start()
    time.sleep(0.1)  # give time for thread to start


# ---------------------------------------------------------
# Main Test: basic GBN operation under good conditions
# ---------------------------------------------------------
def test_gbn_basic():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.0,
        delay_range=(0.01, 0.02)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = GBNReceiver(recv_addr, app_deliver, channel)
    sender   = GBNSender(send_addr, recv_addr, channel, timeout=0.2, N=5)

    start_receiver(receiver)

    msgs = [f"msg_{i}".encode() for i in range(10)]

    for m in msgs:
        sender.send(m)

    time.sleep(0.5)

    assert delivered == msgs


# ---------------------------------------------------------
# Test: GBN under heavy loss + corruption + delay
# ---------------------------------------------------------
def test_gbn_unreliable_conditions():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    channel = UnreliableChannel(
        loss_rate=0.3,
        corrupt_rate=0.25,
        delay_range=(0.05, 0.2)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = GBNReceiver(recv_addr, app_deliver, channel)
    sender   = GBNSender(send_addr, recv_addr, channel, timeout=0.1, N=5)

    start_receiver(receiver)

    msgs = [f"data_{i}".encode() for i in range(20)]

    # Wrap channel.send to count all transmissions
    transmissions = 0
    original_send = channel.send

    def send_wrapper(packet, dest_socket, dest_addr):
        nonlocal transmissions
        transmissions += 1
        return original_send(packet, dest_socket, dest_addr)

    channel.send = send_wrapper

    for m in msgs:
        sender.send(m)

    time.sleep(1.5)

    assert delivered == msgs
    assert transmissions > len(msgs)   # retransmissions happened


# ---------------------------------------------------------
# Test: GBN cumulative ACK behavior
# ---------------------------------------------------------
def test_gbn_cumulative_ack():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    # zero loss & corruption so we can check ordering precisely
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.0,
        delay_range=(0.01, 0.03)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = GBNReceiver(recv_addr, app_deliver, channel)
    sender   = GBNSender(send_addr, recv_addr, channel, timeout=0.2, N=4)

    start_receiver(receiver)

    msgs = [f"X{i}".encode() for i in range(6)]

    for m in msgs:
        sender.send(m)

    time.sleep(0.5)

    assert delivered == msgs  # correct order guaranteed


# ---------------------------------------------------------
# Test: large number of packets to ensure 32-bit wrap is fine
# ---------------------------------------------------------
def test_gbn_sequence_wrap():
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    channel = UnreliableChannel(
        loss_rate=0.1,
        corrupt_rate=0.1,
        delay_range=(0.03, 0.1)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = GBNReceiver(recv_addr, app_deliver, channel)
    sender   = GBNSender(send_addr, recv_addr, channel, timeout=0.15, N=5)

    start_receiver(receiver)

    # Sequence numbers must wrap correctly past 255 and beyond
    msgs = [f"packet_{i}".encode() for i in range(300)]

    for m in msgs:
        print(m)
        sender.send(m)

    time.sleep(3)

    assert delivered == msgs
