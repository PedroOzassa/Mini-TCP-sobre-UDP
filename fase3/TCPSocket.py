import socket
import random
import time
import struct
from typing import Dict

FLAG_FIN = 0x01
FLAG_SYN = 0x02
FLAG_ACK = 0x10

# Header struct:
# src(2) | dst(2) | seq(4) | ack(4) | hdr_len(1) | flags(1) | window(2) | checksum(2) | urgent(2)
STRUCT_FMT = "!HHII B B H H H"
HEADER_SIZE = struct.calcsize(STRUCT_FMT)


def _ones_complement_checksum(data: bytes) -> int:
    """Compute simple 16-bit one's-complement checksum.

    Sums all bytes modulo 16 bits and returns one's complement.
    """
    total = 0
    for b in data:
        total = (total + b) & 0xFFFF
    return (~total) & 0xFFFF


def make_packet(
    src_port: int,
    dest_port: int,
    seq: int,
    ack: int,
    flags: int = 0,
    window: int = 0,
    urgent: int = 0,
    payload: bytes = b"",
) -> bytes:
    """
    Construct a packet according to the specified custom header format.
    Payload is appended at the end.
    """

    header_len = HEADER_SIZE

    # Build header with checksum=0 for calculation
    header_wo_checksum = struct.pack(
        STRUCT_FMT,
        src_port,
        dest_port,
        seq,
        ack,
        header_len,   # 1 byte
        flags,        # 1 byte
        window,       # 2 bytes
        0,            # checksum placeholder
        urgent        # 2 bytes
    )

    checksum = _ones_complement_checksum(header_wo_checksum + payload)

    # Final header with real checksum
    header = struct.pack(
        STRUCT_FMT,
        src_port,
        dest_port,
        seq,
        ack,
        header_len,
        flags,
        window,
        checksum,
        urgent
    )

    return header + payload


def decode_packet(packet_bytes: bytes) -> Dict:
    """
    Decode packet bytes into a dictionary with header fields and payload.
    """

    if len(packet_bytes) < HEADER_SIZE:
        raise ValueError("Packet too small to contain header")

    fields = struct.unpack(STRUCT_FMT, packet_bytes[:HEADER_SIZE])
    payload = packet_bytes[HEADER_SIZE:]

    # Verify checksum (compute with checksum field as 0)
    recv_checksum = fields[7]
    header_wo_checksum = struct.pack(
        STRUCT_FMT,
        fields[0],
        fields[1],
        fields[2],
        fields[3],
        fields[4],
        fields[5],
        fields[6],
        0,          # zeroed checksum for calculation
        fields[8],
    )
    calc_checksum = _ones_complement_checksum(header_wo_checksum + payload)
    checksum_ok = (recv_checksum == calc_checksum)

    result = {
        "src_port": fields[0],
        "dest_port": fields[1],
        "seq": fields[2],
        "ack": fields[3],
        "header_len": fields[4],
        "flags": fields[5],
        "window": fields[6],
        "checksum": recv_checksum,
        "checksum_ok": checksum_ok,
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
        # Bind state
        self._bound = False

    def connect(self, dest_address, timeout=5.0):
        """Inicia conexão com three-way handshake (SYN -> SYN-ACK -> ACK)."""
        # Bind local porta
        if not self._bound:
            try:
                self.udp_socket.bind(("127.0.0.1", self.port))
            except OSError:
                pass
            self._bound = True

        # Resolver destino para IPv4
        host, dport = dest_address
        try:
            host_ip = socket.gethostbyname(host)
        except Exception:
            host_ip = host
        self.peer_address = (host_ip, dport)

        # Enviar SYN
        self.state = 'SYN_SENT'
        syn_seq = self.seq_num
        try:
            print(f"[TCPSocket][CLIENT] -> SYN to {self.peer_address} seq={syn_seq}")
        except Exception:
            pass
        syn_pkt = make_packet(
            src_port=self.port,
            dest_port=dport,
            seq=syn_seq,
            ack=0,
            flags=FLAG_SYN,
            window=self.recv_window,
            urgent=0,
            payload=b""
        )
        start = time.time()
        resend_at = start
        self.udp_socket.settimeout(0.2)

        while time.time() - start < timeout:
            # Reenvia SYN periodicamente
            if time.time() >= resend_at:
                self.udp_socket.sendto(syn_pkt, self.peer_address)
                resend_at = time.time() + 0.5

            try:
                raw, addr = self.udp_socket.recvfrom(65535)
                if addr != self.peer_address:
                    continue
                pkt = decode_packet(raw)
                flags = pkt["flags"]
                if (flags & FLAG_SYN) and (flags & FLAG_ACK):
                    # Verificar ACK do nosso SYN
                    if pkt["ack"] == syn_seq + 1:
                        try:
                            print(f"[TCPSocket][CLIENT] <- SYN-ACK from {addr} seq={pkt['seq']} ack={pkt['ack']}")
                        except Exception:
                            pass
                        self.ack_num = pkt["seq"] + 1  # Próximo esperado do servidor
                        # Enviar ACK final
                        ack_pkt = make_packet(
                            src_port=self.port,
                            dest_port=dport,
                            seq=syn_seq + 1,  # Consumiu 1 pelo SYN
                            ack=self.ack_num,
                            flags=FLAG_ACK,
                            window=self.recv_window,
                            urgent=0,
                            payload=b""
                        )
                        try:
                            print(f"[TCPSocket][CLIENT] -> ACK to {self.peer_address} seq={syn_seq+1} ack={self.ack_num}")
                        except Exception:
                            pass
                        self.udp_socket.sendto(ack_pkt, self.peer_address)
                        self.seq_num = syn_seq + 1
                        self.state = 'ESTABLISHED'
                        try:
                            print(f"[TCPSocket][CLIENT] STATE=ESTABLISHED")
                        except Exception:
                            pass
                        return
            except (socket.timeout, OSError):
                # Em Windows, ICMP Port Unreachable pode gerar WSAECONNRESET (10054)
                # durante recvfrom em sockets UDP; ignore e continue aguardando.
                time.sleep(0.01)
                continue

        raise TimeoutError("Connection timeout during handshake")

    def listen(self):
        """Coloca socket em modo de escuta (bind na porta local)."""
        if not self._bound:
            try:
                self.udp_socket.bind(("127.0.0.1", self.port))
            except OSError:
                pass
            self._bound = True
        self.state = 'LISTEN'

    def accept(self, timeout=5.0):
        """Aceita conexão entrante (SYN -> responde SYN-ACK -> espera ACK)."""
        if self.state != 'LISTEN':
            raise RuntimeError("Socket is not listening")

        self.udp_socket.settimeout(0.2)
        start = time.time()
        client_syn_seq = None

        while time.time() - start < timeout:
            try:
                raw, addr = self.udp_socket.recvfrom(65535)
                pkt = decode_packet(raw)
                flags = pkt["flags"]

                if flags & FLAG_SYN:
                    # Primeiro passo: receber SYN
                    self.peer_address = addr
                    client_syn_seq = pkt["seq"]
                    try:
                        print(f"[TCPSocket][SERVER] <- SYN from {addr} seq={client_syn_seq}")
                    except Exception:
                        pass
                    self.ack_num = client_syn_seq + 1
                    # Enviar SYN-ACK
                    synack_pkt = make_packet(
                        src_port=self.port,
                        dest_port=pkt["src_port"],
                        seq=self.seq_num,
                        ack=self.ack_num,
                        flags=FLAG_SYN | FLAG_ACK,
                        window=self.recv_window,
                        urgent=0,
                        payload=b""
                    )
                    try:
                        print(f"[TCPSocket][SERVER] -> SYN-ACK to {addr} seq={self.seq_num} ack={self.ack_num}")
                    except Exception:
                        pass
                    self.udp_socket.sendto(synack_pkt, self.peer_address)
                    # Consumir 1 pelo SYN nosso
                    self.seq_num += 1

                elif (flags & FLAG_ACK) and self.peer_address and addr == self.peer_address:
                    # ACK final do cliente
                    # Verifica se ele está acusando nosso SYN corretamente
                    if pkt["ack"] == self.seq_num:
                        try:
                            print(f"[TCPSocket][SERVER] <- ACK from {addr} ack={pkt['ack']} (expected {self.seq_num})")
                        except Exception:
                            pass
                        self.state = 'ESTABLISHED'
                        try:
                            print(f"[TCPSocket][SERVER] STATE=ESTABLISHED")
                        except Exception:
                            pass
                        return self
            except (socket.timeout, OSError):
                time.sleep(0.01)
                continue

        raise TimeoutError("Accept timeout during handshake")

    def send(self, data):
        raise NotImplementedError("Data transfer disabled in Part 1 (handshake only)")

    def recv(self, buffer_size):
        raise NotImplementedError("Data transfer disabled in Part 1 (handshake only)")

    def close(self):
        """Fecha conexão com four-way handshake (FIN/ACK).

        Comportamentos suportados:
        - Ativo (inicia fechamento): envia FIN, espera ACK, espera FIN, envia ACK.
        - Passivo (recebe FIN primeiro): ao receber FIN, envia ACK e depois FIN, espera ACK final.

        A escolha do caminho é automática: se não tiver recebido FIN ainda, atua como ativo; caso um FIN chegue
        primeiro durante o processo, atua como passivo.
        """
        # Somente conexões estabelecidas podem fechar corretamente
        if self.state not in ("ESTABLISHED", "CLOSE_WAIT", "FIN_WAIT_1", "FIN_WAIT_2"):
            # Nada a fazer se já estiver fechado
            self.state = "CLOSED"
            try:
                self.udp_socket.close()
            except Exception:
                pass
            return

        self.udp_socket.settimeout(0.2)
        deadline = time.time() + 5.0

        def send_fin():
            pkt = make_packet(
                src_port=self.port,
                dest_port=self.peer_address[1],
                seq=self.seq_num,
                ack=self.ack_num,
                flags=FLAG_FIN,
                window=self.recv_window,
                urgent=0,
                payload=b"",
            )
            try:
                print(f"[TCPSocket] -> FIN to {self.peer_address} seq={self.seq_num}")
            except Exception:
                pass
            self.udp_socket.sendto(pkt, self.peer_address)

        def send_ack():
            pkt = make_packet(
                src_port=self.port,
                dest_port=self.peer_address[1],
                seq=self.seq_num,
                ack=self.ack_num,
                flags=FLAG_ACK,
                window=self.recv_window,
                urgent=0,
                payload=b"",
            )
            try:
                print(f"[TCPSocket] -> ACK to {self.peer_address} ack={self.ack_num}")
            except Exception:
                pass
            self.udp_socket.sendto(pkt, self.peer_address)

        # Se estamos em ESTABLISHED, tentamos fechar ativamente
        if self.state == "ESTABLISHED":
            # Envia FIN
            send_fin()
            self.state = "FIN_WAIT_1"
            fin_seq = self.seq_num
            self.seq_num += 1  # FIN consome 1

            got_ack_for_fin = False

            while time.time() < deadline:
                try:
                    raw, addr = self.udp_socket.recvfrom(65535)
                    if self.peer_address and addr != self.peer_address:
                        continue
                    pkt = decode_packet(raw)
                    flags = pkt["flags"]

                    # ACK do nosso FIN
                    if (flags & FLAG_ACK) and pkt["ack"] == self.seq_num:
                        got_ack_for_fin = True
                        if self.state == "FIN_WAIT_1":
                            self.state = "FIN_WAIT_2"
                        try:
                            print(f"[TCPSocket] <- ACK for our FIN from {addr} ack={pkt['ack']}")
                        except Exception:
                            pass
                        # continua aguardando FIN do peer
                        continue

                    # FIN do peer
                    if flags & FLAG_FIN:
                        # Acusa FIN do peer
                        try:
                            print(f"[TCPSocket] <- FIN from {addr} seq={pkt['seq']}")
                        except Exception:
                            pass
                        self.ack_num = pkt["seq"] + 1
                        send_ack()
                        # Estado TIME_WAIT simplificado
                        self.state = "TIME_WAIT"
                        time.sleep(0.2)
                        break
                except (socket.timeout, OSError):
                    continue

            # Encerrar recursos
            self.state = "CLOSED"
            try:
                self.udp_socket.close()
            except Exception:
                pass
            try:
                print("[TCPSocket] STATE=CLOSED")
            except Exception:
                pass
            return

        # Caminho passivo: já recebemos FIN antes (CLOSE_WAIT) ou vamos aguardá-lo agora
        # Estados possíveis aqui: CLOSE_WAIT (já recebemos FIN) ou FIN_WAIT_* (simultaneous close). Tratar CLOSE_WAIT.
        if self.state in ("CLOSE_WAIT", "ESTABLISHED"):
            got_fin = (self.state == "CLOSE_WAIT")
            if not got_fin:
                # Espera por FIN do peer
                while time.time() < deadline and not got_fin:
                    try:
                        raw, addr = self.udp_socket.recvfrom(65535)
                        if self.peer_address and addr != self.peer_address:
                            continue
                        pkt = decode_packet(raw)
                        flags = pkt["flags"]
                        if flags & FLAG_FIN:
                            try:
                                print(f"[TCPSocket] <- FIN from {addr} seq={pkt['seq']}")
                            except Exception:
                                pass
                            self.ack_num = pkt["seq"] + 1
                            # ACK imediato do FIN recebido
                            send_ack()
                            self.state = "CLOSE_WAIT"
                            got_fin = True
                            break
                    except (socket.timeout, OSError):
                        continue

            if not got_fin:
                # Timeout aguardando FIN
                try:
                    self.udp_socket.close()
                except Exception:
                    pass
                self.state = "CLOSED"
                return

            # Envia nosso FIN e espera ACK final
            send_fin()
            fin_seq = self.seq_num
            self.seq_num += 1
            self.state = "LAST_ACK"

            while time.time() < deadline:
                try:
                    raw, addr = self.udp_socket.recvfrom(65535)
                    if self.peer_address and addr != self.peer_address:
                        continue
                    pkt = decode_packet(raw)
                    flags = pkt["flags"]
                    if (flags & FLAG_ACK) and pkt["ack"] == self.seq_num:
                        try:
                            print(f"[TCPSocket] <- Final ACK from {addr} ack={pkt['ack']}")
                        except Exception:
                            pass
                        break
                except (socket.timeout, OSError):
                    continue

            # Fechar
            self.state = "CLOSED"
            try:
                self.udp_socket.close()
            except Exception:
                pass
            try:
                print("[TCPSocket] STATE=CLOSED")
            except Exception:
                pass
            return

    # Métodos auxiliares internos
    def _send_segment(self, flags, data=b''):
        """ Cria e envia segmento TCP """
        if not self.peer_address:
            raise RuntimeError("Peer address not set")
        pkt = make_packet(
            src_port=self.port,
            dest_port=self.peer_address[1],
            seq=self.seq_num,
            ack=self.ack_num,
            flags=flags,
            window=self.recv_window,
            urgent=0,
            payload=data or b""
        )
        self.udp_socket.sendto(pkt, self.peer_address)

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