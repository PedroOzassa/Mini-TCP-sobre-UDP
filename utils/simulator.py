import random
import threading


class UnreliableChannel:
    def __init__(self, loss_rate=0.1, corrupt_rate=0.1, delay_range=(0.01, 0.5)):
        """
        loss_rate: probabilidade de perda de pacote (0.0 a 1.0)
        corrupt_rate: probabilidade de corrupção (0.0 a 1.0)
        delay_range: tupla (min_delay, max_delay) em segundos
        """
        self.loss_rate = loss_rate
        self.corrupt_rate = corrupt_rate
        self.delay_range = delay_range

    def send(self, packet, dest_socket, dest_addr):
        """Envia pacote através do canal não confiável"""

        # Simular perda
        if random.random() < self.loss_rate:
            print("[SIMULADOR] Pacote perdido")
            return

        # Simular corrupção
        if random.random() < self.corrupt_rate:
            packet = self._corrupt_packet(packet)
            print("[SIMULADOR] Pacote corrompido")

        # Simular atraso e enviar
        delay = random.uniform(*self.delay_range)
        threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()

    def _corrupt_packet(self, packet):
        """Corrompe bits aleatórios do pacote"""
        packet_list = list(packet)
        num_corruptions = random.randint(1, 5)

        for _ in range(num_corruptions):
            idx = random.randint(0, len(packet_list) - 1)
            packet_list[idx] ^= 0xFF  # inverter todos os bits do byte

        return bytes(packet_list)
