import sys
import os
import time
import socket
import threading

# Ensure repo root is on the path so imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.simulator import UnreliableChannel
from fase2.gbn import GBNSender, GBNReceiver
from fase1.rdt30 import RDT30Sender, RDT30Receiver

# Helpers

def free_udp_addr():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("localhost", 0))
    addr = s.getsockname()
    s.close()
    return addr


def start_receiver_loop(receiver):
    # RDT30Receiver uses .loop, GBNReceiver uses .start
    if hasattr(receiver, "loop"):
        t = threading.Thread(target=receiver.loop, daemon=True)
        t.start()
        return t
    if hasattr(receiver, "start"):
        receiver.start()
        return None
    return None


def test_efficiency_gbn_vs_rdt30_transfer_1mb():
    """Transfer 1MB using GBN (fase2) and RDT3.0 (stop-and-wait), compare time and channel utilization."""

    # Prepare 1MB of data split into 1024-byte chunks
    total_bytes = 1024 * 1024  # 1 MiB
    chunk_size = 1024
    qtt = total_bytes // chunk_size
    msgs = [b"x" * chunk_size for _ in range(qtt)]

    useful_bytes = total_bytes

    # --------------------------- GBN (fase2) ---------------------------
    delivered_gbn = []
    def app_deliver_gbn(data):
        delivered_gbn.append(data)

    # Perfect channel for baseline
    channel_gbn = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.0, delay_range=(0,0))

    # Wrap channel.send to count transmitted bytes
    total_sent_bytes_gbn = 0
    original_send_gbn = channel_gbn.send

    def counting_send_gbn(packet, dest_socket, dest_addr):
        nonlocal total_sent_bytes_gbn
        total_sent_bytes_gbn += len(packet)
        return original_send_gbn(packet, dest_socket, dest_addr)

    channel_gbn.send = counting_send_gbn

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver_gbn = GBNReceiver(recv_addr, app_deliver_gbn, channel_gbn)
    start_receiver_loop(receiver_gbn)

    # Use a larger window for GBN to show its advantage (if any)
    sender_gbn = GBNSender(send_addr, recv_addr, channel_gbn, N=32, timeout=1.0)

    start_t = time.time()
    for m in msgs:
        sender_gbn.send(m)
    end_t = time.time()

    # allow in-flight processing
    time.sleep(1)

    elapsed_gbn = end_t - start_t
    utilization_gbn = useful_bytes / total_sent_bytes_gbn if total_sent_bytes_gbn > 0 else 0
    throughput_gbn = useful_bytes / elapsed_gbn if elapsed_gbn > 0 else 0

    # Validate
    assert delivered_gbn == msgs

    print("\n=== GBN (fase2) Results ===")
    print(f"Elapsed time: {elapsed_gbn:.4f} s")
    print(f"Total bytes useful: {useful_bytes}")
    print(f"Total transmitted bytes: {total_sent_bytes_gbn}")
    print(f"Channel utilization (useful/total): {utilization_gbn:.4f}")
    print(f"Throughput (B/s): {throughput_gbn:.2f}")

    # ------------------------- RDT 3.0 (stop-and-wait) -------------------------
    delivered_rdt = []
    def app_deliver_rdt(data):
        delivered_rdt.append(data)

    channel_rdt = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.0, delay_range=(0,0))

    total_sent_bytes_rdt = 0
    original_send_rdt = channel_rdt.send

    def counting_send_rdt(packet, dest_socket, dest_addr):
        nonlocal total_sent_bytes_rdt
        total_sent_bytes_rdt += len(packet)
        return original_send_rdt(packet, dest_socket, dest_addr)

    channel_rdt.send = counting_send_rdt

    recv_addr2 = free_udp_addr()
    send_addr2 = free_udp_addr()

    receiver_rdt = RDT30Receiver(recv_addr2, app_deliver_rdt, channel_rdt)
    start_receiver_loop(receiver_rdt)

    sender_rdt = RDT30Sender(send_addr2, recv_addr2, channel_rdt, timeout=1.0)

    start_t2 = time.time()
    for m in msgs:
        sender_rdt.send(m)
    end_t2 = time.time()

    time.sleep(1)

    elapsed_rdt = end_t2 - start_t2
    utilization_rdt = useful_bytes / total_sent_bytes_rdt if total_sent_bytes_rdt > 0 else 0
    throughput_rdt = useful_bytes / elapsed_rdt if elapsed_rdt > 0 else 0

    # Validate
    assert delivered_rdt == msgs

    print("\n=== RDT 3.0 (stop-and-wait) Results ===")
    print(f"Elapsed time: {elapsed_rdt:.4f} s")
    print(f"Total bytes useful: {useful_bytes}")
    print(f"Total transmitted bytes: {total_sent_bytes_rdt}")
    print(f"Channel utilization (useful/total): {utilization_rdt:.4f}")
    print(f"Throughput (B/s): {throughput_rdt:.2f}")

    # Comparison summary
    print("\n=== Comparison Summary ===")
    print(f"GBN time: {elapsed_gbn:.4f}s vs RDT3.0 time: {elapsed_rdt:.4f}s")
    print(f"GBN utilization: {utilization_gbn:.4f} vs RDT3.0 utilization: {utilization_rdt:.4f}")
    print(f"GBN throughput: {throughput_gbn:.2f} B/s vs RDT3.0 throughput: {throughput_rdt:.2f} B/s")


def test_gbn_loss_10_percent():
    """Simular perda de 10% no canal, verificar entrega e contar retransmissões (GBN)."""

    # Application delivery collector
    delivered = []
    def app_deliver(data):
        delivered.append(data)

    # Channel with 10% loss
    channel = UnreliableChannel(loss_rate=0.10, corrupt_rate=0.0, delay_range=(0,0))

    # Count transmissions
    transmissions = 0
    original_send = channel.send

    def counting_send(packet, dest_socket, dest_addr):
        nonlocal transmissions
        transmissions += 1
        return original_send(packet, dest_socket, dest_addr)

    channel.send = counting_send

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = GBNReceiver(recv_addr, app_deliver, channel)
    start_receiver_loop(receiver)

    sender = GBNSender(send_addr, recv_addr, channel, N=8, timeout=0.5)

    # Send a moderate number of small messages
    qtt = 100
    msgs = [f"msg_{i}".encode() for i in range(qtt)]

    for m in msgs:
        sender.send(m)

    # allow processing
    time.sleep(1)

    # Verify all messages were delivered at least once
    delivered_set = set(delivered)
    for m in msgs:
        assert m in delivered_set

    # There should be retransmissions when loss occurs
    assert transmissions > qtt

    print("\nGBN Loss Test: transmissions:", transmissions, "sent:", qtt, "retransmissions:", transmissions - qtt)


def test_gbn_window_size_analysis():
    """Vary window size N = [1,5,10,20] and measure elapsed time, throughput and channel utilization.

    Note: Uses a smaller total size (256 KiB) to keep test runtime reasonable. Increase `total_bytes`
    to 1MiB if you want a longer, more accurate benchmark.
    """

    Ns = [1, 5, 10, 20]
    total_bytes = 256 * 1024  # 256 KiB (change to 1024*1024 for 1 MiB)
    chunk_size = 1024
    qtt = total_bytes // chunk_size
    msgs = [b"x" * chunk_size for _ in range(qtt)]

    results = []

    for N in Ns:
        delivered = []
        def app_deliver(data):
            delivered.append(data)

        channel = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.0, delay_range=(0,0))

        total_sent = 0
        original_send = channel.send

        def counting_send(packet, dest_socket, dest_addr):
            nonlocal total_sent
            total_sent += len(packet)
            return original_send(packet, dest_socket, dest_addr)

        channel.send = counting_send

        recv_addr = free_udp_addr()
        send_addr = free_udp_addr()

        receiver = GBNReceiver(recv_addr, app_deliver, channel)
        start_receiver_loop(receiver)

        sender = GBNSender(send_addr, recv_addr, channel, N=N, timeout=1.0)

        start_t = time.time()
        for m in msgs:
            sender.send(m)
        end_t = time.time()

        # allow receiver to process last packets
        time.sleep(0.5)

        elapsed = end_t - start_t
        throughput = total_bytes / elapsed if elapsed > 0 else 0
        utilization = total_bytes / total_sent if total_sent > 0 else 0

        # Validation: all messages delivered in order
        assert delivered == msgs

        results.append((N, elapsed, throughput, utilization, total_sent))

        print(f"\nN={N}: elapsed={elapsed:.4f}s, throughput={throughput:.2f} B/s, utilization={utilization:.4f}, transmitted={total_sent}")

    print("\n=== Window Size Benchmark Summary ===")
    for N, elapsed, throughput, utilization, total_sent in results:
        print(f"N={N}: time={elapsed:.4f}s, throughput={throughput:.2f} B/s, utilization={utilization:.4f}, transmitted={total_sent}")
