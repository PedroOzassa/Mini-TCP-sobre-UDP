import socket
import random
import time
import struct

FLAG_FIN = 0x01
FLAG_SYN = 0x02
FLAG_ACK = 0x10

# Header struct:
# src(2) | dst(2) | seq(4) | ack(4) | hdr_len(1) | flags(1) | window(2) | checksum(2) | urgent(2)
STRUCT_FMT = "!HHII B B H H H"
HEADER_SIZE = struct.calcsize(STRUCT_FMT)


def make_packet(
    src_port: int,
    dest_port: int,
    seq: int,
    ack: int,
    flags: int = 0,
    window: int = 0,
    checksum: int = 0,
    urgent: int = 0,
    payload: bytes = b"",
) -> bytes:
    """
    Construct a packet according to the specified custom header format.
    Payload is appended at the end.
    """

    header_len = HEADER_SIZE

    header = struct.pack(
        STRUCT_FMT,
        src_port,
        dest_port,
        seq,
        ack,
        header_len,   # 1 byte
        flags,        # 1 byte
        window,       # 2 bytes
        checksum,     # 2 bytes
        urgent        # 2 bytes
    )

    return header + payload


def decode_packet(packet_bytes: bytes) -> dict:
    """
    Decode packet bytes into a dictionary with header fields and payload.
    """

    if len(packet_bytes) < HEADER_SIZE:
        raise ValueError("Packet too small to contain header")

    fields = struct.unpack(STRUCT_FMT, packet_bytes[:HEADER_SIZE])
    payload = packet_bytes[HEADER_SIZE:]

    result = {
        "src_port": fields[0],
        "dest_port": fields[1],
        "seq": fields[2],
        "ack": fields[3],
        "header_len": fields[4],
        "flags": fields[5],
        "window": fields[6],
        "checksum": fields[7],
        "urgent": fields[8],
        "payload": payload,
    }

    return result

class SimpleTCPSocket:
    def __init__(self, port):
        """ Inicializa socket UDP subjacente e estruturas de dados """
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.port = port
        # Estados da conexão
        self.state = 'CLOSED'  # CLOSED, LISTEN, SYN_SENT, ESTABLISHED, etc.
        # Números de sequência e ACK
        self.seq_num = random.randint(0, 1000)  # ISN (Initial Sequence Number)
        self.ack_num = 0
        # Buffers
        self.send_buffer = []
        self.recv_buffer = []
        # Controle de fluxo
        self.recv_window = 4096  # bytes
        # Controle de tempo
        self.estimated_rtt = 1.0
        self.dev_rtt = 0.5
        # Dados do peer
        self.peer_address = None

    def connect(self, dest_address):
        """ Inicia conexão com three-way handshake """
        pass  # A implementar

    def listen(self):
        """ Coloca socket em modo de escuta """
        pass  # A implementar

    def accept(self):
        """ Aceita conexão entrante (completa handshake) """
        pass  # A implementar

    def send(self, data):
        """ Envia dados (pode bloquear se buffer cheio) """
        pass  # A implementar

    def recv(self, buffer_size):
        """ Recebe dados do buffer de recepção """
        pass  # A implementar

    def close(self):
        """ Fecha conexão (four-way handshake) """
        pass  # A implementar

    # Métodos auxiliares internos
    def _send_segment(self, flags, data=b''):
        """ Cria e envia segmento TCP """
        pass

    def _receive_loop(self):
        """ Thread que recebe segmentos UDP e processa """
        pass

    def _calculate_timeout(self):
        """ Calcula timeout baseado em RTT """
        return self.estimated_rtt + 4 * self.dev_rtt

    def _update_rtt(self, sample_rtt):
        """ Atualiza estimativa de RTT """
        self.estimated_rtt = 0.875 * self.estimated_rtt + 0.125 * sample_rtt
        self.dev_rtt = 0.75 * self.dev_rtt + 0.25 * abs(sample_rtt - self.estimated_rtt)