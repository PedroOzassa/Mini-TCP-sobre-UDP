import threading
import time
import socket

from utils.simulator import UnreliableChannel
from fase1.rdt20 import RDT20Sender, RDT20Receiver
from fase1.rdt21 import RDT21Sender, RDT21Receiver, decode_packet, TYPE_DATA, TYPE_ACK, TYPE_NAK

# Utilities

# Gets a free socket adress on localhost
def free_udp_addr():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("localhost", 0))
    addr = s.getsockname()
    s.close()
    return addr

# Starts the reciever in a new thread
def start_receiver(receiver):
    t = threading.Thread(target=receiver.loop, daemon=True)
    t.start()
    return t

# Checks if every element in the list of sent messages is on the delivered list
def contains_all(sent, delivered):
    delivered_set = set(delivered)
    for msg in sent:
        if msg not in delivered_set:
            return False
    return True

# Wraps an UnreliableChannel and ensures that ONLY DATA packets are corrupted
# This wrapper was necessary because UnreliableChannel does not have the ability
# to distinguish between DATA, ACK, NAK or any type of packet 
class DataOnlyCorruptingChannel:
    def __init__(self, channel, corrupt_rate_for_data):
        self.base_channel = channel
        self.corrupt_rate_for_data = corrupt_rate_for_data

    def send(self, packet, dest_socket, dest_addr):
        info = decode_packet(packet)

        if info["type"] == TYPE_DATA:
            old_corrupt_rate = self.base_channel.corrupt_rate
            self.base_channel.corrupt_rate = self.corrupt_rate_for_data
            self.base_channel.send(packet, dest_socket, dest_addr)
            self.base_channel.corrupt_rate = old_corrupt_rate
        else:
            old_corrupt_rate = self.base_channel.corrupt_rate
            self.base_channel.corrupt_rate = 0.0
            self.base_channel.send(packet, dest_socket, dest_addr)
            self.base_channel.corrupt_rate = old_corrupt_rate
            
# Wraps an UnreliableChannel and ensures that ONLY ACK packets are corrupted
# This wrapper was necessary because UnreliableChannel does not have the ability
# to distinguish between DATA, ACK, NAK or any type of packet 
class ACKOnlyCorruptingChannel:
    def __init__(self, channel, corrupt_rate_for_ack):
        self.base_channel = channel
        self.corrupt_rate_for_ack = corrupt_rate_for_ack

    def send(self, packet, dest_socket, dest_addr):
        info = decode_packet(packet)
        if info["type"] == TYPE_ACK:
            old_corrupt_rate = self.base_channel.corrupt_rate
            self.base_channel.corrupt_rate = self.corrupt_rate_for_ack
            self.base_channel.send(packet, dest_socket, dest_addr)
            self.base_channel.corrupt_rate = old_corrupt_rate
        else:
            old_corrupt_rate = self.base_channel.corrupt_rate
            self.base_channel.corrupt_rate = 0.0
            self.base_channel.send(packet, dest_socket, dest_addr)
            self.base_channel.corrupt_rate = old_corrupt_rate


######################### RDT 2.0 TESTS #############################

# TEST 1. Transmitir uma sequência de 10 mensagens com canal perfeito

def test_rdt20_teste_1():
    
    # This simulates an upper layer app receiving the data
    delivered = []
    def app_deliver(data):
        delivered.append(data)

    # Setup for the channel, receiver(starts in a separate thread) and sender 
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.0,
        delay_range=(0,0)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT20Receiver(recv_addr, app_deliver, channel)
    sender = RDT20Sender(send_addr, recv_addr, channel)

    start_receiver(receiver)

    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender
    msgs = [f"msg_{i}".encode() for i in range(10)]
    
    for m in msgs:
        sender.send(m)

    time.sleep(1)

    # Asserts that:
    # 1. Every message was correctly delivered a single time, in the exact order it was sent
    assert delivered == msgs


# TEST 2. Introduzir corrupção artificial de bits (inverter bits aleatórios) em 30% dos pacotes

def test_rdt20_teste_2():
    
    # This simulates an upper layer app receiving the data
    delivered = []

    def app_deliver(data):
        delivered.append(data)

    # Wrapper made for rdt20.decode_packet to count every time a corrupted packet appears
    import fase1.rdt20 as rdt20
    
    original_decode = rdt20.decode_packet
    
    corrupted_count = 0
    
    def decode_wrapper(packet):
        nonlocal corrupted_count
        info = original_decode(packet)
        if not info["checksum_ok"]:
            corrupted_count += 1
        return info

    rdt20.decode_packet = decode_wrapper 

    # Setup for the channel, receiver(starts in a separate thread) and sender 
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.3,
        delay_range=(0,0)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT20Receiver(recv_addr, app_deliver, channel)
    sender = RDT20Sender(send_addr, recv_addr, channel)

    start_receiver(receiver)

    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender
    msgs = [f"data_{i}".encode() for i in range(100)]
    for m in msgs:
        sender.send(m)

    time.sleep(1)

    # Asserts that:
    # 1. All messages were delivered at least once
    # 2. There were more messages delivered than sent (Correct because of the duplication in rdt 2.0)
    # 3. A corruption happened at least once
    assert contains_all(msgs, delivered)
    assert len(delivered) >= 100
    assert corrupted_count > 0


# TEST 3. Verificar se todas as mensagens chegam corretamente ao destino    

def test_rdt20_teste_3():
    
    # This simulates an upper layer app receiving the data
    delivered = []
    def app_deliver(data):
        delivered.append(data)
        
    # Setup for the channel, receiver(starts in a separate thread) and sender 
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.3,
        delay_range=(0,0)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT20Receiver(recv_addr, app_deliver, channel)
    sender = RDT20Sender(send_addr, recv_addr, channel)

    start_receiver(receiver)
    
    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender
    msgs = [f"packet_{i}".encode() for i in range(100)]

    for m in msgs:
        sender.send(m)

    time.sleep(1)

    # Asserts that:
    # 1. All messages were delivered at least once even with corruption
    assert contains_all(msgs, delivered)


# TEST 4. Registrar quantas retransmissões ocorreram

def test_rdt20_teste_4():
    
    # This simulates an upper layer app receiving the data
    delivered = []
    def app_deliver(data):
        delivered.append(data)

    # Setup for the channel, receiver(starts in a separate thread) and sender 
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.5,
        delay_range=(0,0)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT20Receiver(recv_addr, app_deliver, channel)
    sender = RDT20Sender(send_addr, recv_addr, channel)

    start_receiver(receiver)

    # Wrapper made for channel.send to count every time a transmission is made
    transmissions = 0
    original_send = channel.send

    def send_wrapper(packet, dest_socket, dest_addr):
        nonlocal transmissions
        transmissions += 1
        return original_send(packet, dest_socket, dest_addr)

    channel.send = send_wrapper
    
    
    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender
    
    msgs = [f"msg_{i}".encode() for i in range(100)]

    for m in msgs:
        sender.send(m)

    time.sleep(1.0)
    
    # Prints the number of retransmissions and then asserts that:
    # 1. All messages were delivered at least once
    # 2. There were more messages delivered than sent (Correct because of the duplication in rdt 2.0)
    # 3. A retransmission happened at least once
    print("Retransmissions:", transmissions - 100)

    assert contains_all(msgs, delivered)
    assert len(delivered) >= 100
    assert transmissions > 100
    
    
    
######################### RDT 2.1 TESTS #############################

# TEST 1. Corromper 20% dos pacotes DATA

def test_rdt21_test_1():
    
    # This simulates an upper layer app receiving the data
    delivered = []
    def app_deliver(data):
        delivered.append(data)
    
    # Setup for the channel, receiver(starts in a separate thread) and sender
    # Wrapper made for UnreliableChannel that distinguishes between packet types
    channel = DataOnlyCorruptingChannel(
        UnreliableChannel(loss_rate=0,delay_range=(0,0)),
        corrupt_rate_for_data=0.2
        )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT21Receiver(recv_addr, app_deliver, channel)
    sender = RDT21Sender(send_addr, recv_addr, channel)
    
    start_receiver(receiver)
    
    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender
    msgs = [f"msg_{i}".encode() for i in range(100)]
    for m in msgs:
        sender.send(m)

    time.sleep(1)
    
    # Asserts that:
    # 1. Every message was correctly delivered a single time, in the exact order it was sent
    assert delivered == msgs


# TEST 2. Corromper 20% dos ACKs

def test_rdt21_test_2():
    
    # This simulates an upper layer app receiving the data
    delivered = []
    def app_deliver(data):
        delivered.append(data)
        
    # Setup for the channel, receiver(starts in a separate thread) and sender
    # Wrapper made for UnreliableChannel that distinguishes between packet types
    channel = ACKOnlyCorruptingChannel(
        UnreliableChannel(loss_rate=0, delay_range=(0,0)),
        corrupt_rate_for_ack=0.2
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT21Receiver(recv_addr, app_deliver, channel)
    sender = RDT21Sender(send_addr, recv_addr, channel)
    
    start_receiver(receiver)
    
    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender    
    msgs = [f"msg_{i}".encode() for i in range(100)]
    for m in msgs:
        sender.send(m)

    time.sleep(1)
    
    # Asserts that:
    # 1. Every message was correctly delivered a single time, in the exact order it was sent
    assert delivered == msgs
    
    
# TEST 3. Verificar se não há duplicação de dados na aplicação receptora

def test_rdt21_test_3():
    
    # This simulates an upper layer app receiving the data
    delivered = []
    def app_deliver(data):
        delivered.append(data)
    
    # Setup for the channel, receiver(starts in a separate thread) and sender
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.3,
        delay_range=(0,0)
    )
    
    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT21Receiver(recv_addr, app_deliver, channel)
    sender = RDT21Sender(send_addr, recv_addr, channel)
    
    start_receiver(receiver)
    
    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender
    msgs = [f"msg_{i}".encode() for i in range(100)]
    for m in msgs:
        sender.send(m)

    time.sleep(1)
    
    # Asserts that:
    # 1. Every message was correctly delivered a single time,
    # in the exact order it was sent with NO duplicates
    assert delivered == msgs


# TEST 4. Medir overhead (quantos bytes extras por mensagem útil)

def test_rdt21_test_4():
    
    # This simulates an upper layer app receiving the data
    delivered = []
    def app_deliver(data):
        delivered.append(data)
        
    # Setup for the channel, receiver(starts in a separate thread) and sender 
    channel = UnreliableChannel(
        loss_rate=0.0,
        corrupt_rate=0.5,
        delay_range=(0,0)
    )

    recv_addr = free_udp_addr()
    send_addr = free_udp_addr()

    receiver = RDT21Receiver(recv_addr, app_deliver, channel)
    sender = RDT21Sender(send_addr, recv_addr, channel)

    start_receiver(receiver)
    
    # Wrapper made for channel.send that counts the number of
    # header bytes, payload bytes and total bytes in a packet, 
    # and adds it a counter(includes all retransmissions of data)
    total_sent_bytes = 0
    total_header_bytes = 0
    total_payload_bytes = 0

    original_send = channel.send

    def counting_send(packet, dest_socket, dest_addr):
        nonlocal total_sent_bytes, total_header_bytes, total_payload_bytes

        raw_len = len(packet)
        total_sent_bytes += raw_len

        total_header_bytes += 4

        total_payload_bytes += (raw_len - 4)

        return original_send(packet, dest_socket, dest_addr)

    channel.send = counting_send
    
    # Makes a message with a number (ex:msg_1),
    # then converts it to bytes and puts it an a list.
    # The list is then sent via the sender
    msgs = [f"msg_{i}".encode() for i in range(100)]
    for m in msgs:
        sender.send(m)
        
    time.sleep(1)
    
    # Computes the overhead
    assert delivered == msgs
    
    useful_bytes = sum(len(m) for m in msgs)

    overhead_bytes = total_sent_bytes - useful_bytes

    print("\n=== RDT 2.1 OVERHEAD REPORT ===")
    print(f"Total useful payload bytes: {useful_bytes}")
    print(f"Total transmitted bytes: {total_sent_bytes}")
    print(f"Overhead bytes: {overhead_bytes}")
    print(f"Overhead(extra bytes per data message): {overhead_bytes/100}")
    print(f"Header bytes alone: {total_header_bytes}")
    print(f"Payload bytes (incl. retransmissions): {total_payload_bytes}")
    print("================================\n")