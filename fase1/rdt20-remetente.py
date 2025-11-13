"""
RDT 2.0 - Remetente (Sender)
Protocolo de Transferência de Dados Confiável com Detecção de Erros de Bits
Baseado em: Kurose & Ross - Redes de Computadores, 8ª edição, Seção 3.4.1

O remetente:
1. Aceita dados da aplicação
2. Cria pacotes com dados + checksum
3. Envia via UDP
4. Aguarda ACK/NAK do receptor
5. Se NAK: retransmite
6. Se ACK: aceita novos dados
"""

import socket
import hashlib
import struct
import time
import threading
from typing import Tuple, Optional

# ============================================================================
# CLASSE: Pacote RDT 2.0
# ============================================================================

class RDT20Packet:
    """
    Representa um pacote RDT 2.0 com a seguinte estrutura:
    - seq_num (1 byte): número de sequência (0 ou 1)
    - checksum (32 bytes): hash MD5 dos dados
    - data (variável): dados do aplicativo
    """
    
    SEQ_SIZE = 1
    CHECKSUM_SIZE = 32  # MD5 = 32 bytes (hexadecimal)
    HEADER_SIZE = SEQ_SIZE + CHECKSUM_SIZE
    MAX_DATA_SIZE = 1000  # Tamanho máximo dos dados
    
    def __init__(self, seq_num: int, data: bytes):
        """
        Inicializa um pacote RDT 2.0.
        
        Args:
            seq_num: Número de sequência (0 ou 1 para RDT 2.0)
            data: Dados a serem transmitidos
        """
        if len(data) > self.MAX_DATA_SIZE:
            raise ValueError(f"Dados excedem o tamanho máximo de {self.MAX_DATA_SIZE} bytes")
        
        self.seq_num = seq_num
        self.data = data
        self.checksum = self._calcular_checksum()
    
    def _calcular_checksum(self) -> str:
        """Calcula o checksum MD5 dos dados."""
        return hashlib.md5(self.data).hexdigest()
    
    def to_bytes(self) -> bytes:
        """Converte o pacote para bytes para transmissão."""
        header = struct.pack('B', self.seq_num)  # seq_num em 1 byte
        header += self.checksum.encode('ascii')  # checksum como string ASCII
        return header + self.data
    
    @staticmethod
    def from_bytes(packet_bytes: bytes) -> 'RDT20Packet':
        """Cria um pacote a partir de bytes recebidos."""
        seq_num = struct.unpack('B', packet_bytes[:1])[0]
        checksum = packet_bytes[1:33].decode('ascii')
        data = packet_bytes[33:]
        
        # Recria o pacote e valida
        pkt = RDT20Packet(seq_num, data)
        if pkt.checksum != checksum:
            raise ValueError("Erro de integridade: checksum não coincide")
        
        return pkt
    
    def verificar_integridade(self) -> bool:
        """Verifica se o pacote possui integridade (checksum válido)."""
        return self.checksum == hashlib.md5(self.data).hexdigest()
    
    def __repr__(self) -> str:
        return f"RDT20Packet(seq={self.seq_num}, data_len={len(self.data)}, checksum={self.checksum[:8]}...)"


# ============================================================================
# CLASSE: Remetente RDT 2.0
# ============================================================================

class RDT20Remetente:
    """
    Implementação do lado remetente do protocolo RDT 2.0.
    
    Características:
    - Detecção de erros de bits via checksum MD5
    - Alternância de número de sequência (0/1)
    - Retransmissão automática em caso de NAK
    - Timeout para tratamento de ACK perdidos
    """
    
    def __init__(self, porta_remota: str, host_remoto: str = 'localhost', 
                 porta_local: int = 5005, timeout: float = 2.0):
        """
        Inicializa o remetente RDT 2.0.
        
        Args:
            porta_remota: Porta do receptor
            host_remoto: Endereço IP do receptor
            porta_local: Porta local para bindar o socket
            timeout: Timeout para recebimento de ACK/NAK (segundos)
        """
        self.host_remoto = host_remoto
        self.porta_remota = porta_remota
        self.porta_local = porta_local
        self.timeout = timeout
        
        # Estado do protocolo
        self.seq_num = 0  # Alternância entre 0 e 1
        self.esperando_ack = False
        self.pacote_enviado = None
        
        # Estatísticas
        self.pacotes_enviados = 0
        self.pacotes_retransmitidos = 0
        self.acks_recebidos = 0
        self.naks_recebidos = 0
        
        # Socket UDP
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(self.timeout)
        self.socket.bind(('', self.porta_local))
        
        print(f"[REMETENTE] Iniciado em porta {self.porta_local}")
        print(f"[REMETENTE] Receptor: {host_remoto}:{porta_remota}")
    
    def enviar_dados(self, dados: bytes) -> bool:
        """
        Envia dados para o receptor com protocolo RDT 2.0.
        
        Fluxo:
        1. Cria pacote com dados + checksum
        2. Envia via UDP
        3. Aguarda ACK (seq_num correto)
        4. Se NAK ou timeout: retransmite
        
        Args:
            dados: Dados a serem transmitidos
        
        Returns:
            True se dados foram entregues com sucesso, False caso contrário
        """
        if len(dados) > RDT20Packet.MAX_DATA_SIZE:
            print(f"[ERRO] Dados excedem tamanho máximo de {RDT20Packet.MAX_DATA_SIZE} bytes")
            return False
        
        # Cria pacote com número de sequência atual
        pacote = RDT20Packet(self.seq_num, dados)
        self.pacote_enviado = pacote
        self.esperando_ack = True
        
        max_tentativas = 3
        tentativa = 0
        
        while tentativa < max_tentativas and self.esperando_ack:
            tentativa += 1
            
            # Envia pacote
            pacote_bytes = pacote.to_bytes()
            try:
                self.socket.sendto(pacote_bytes, (self.host_remoto, self.porta_remota))
                self.pacotes_enviados += 1
                print(f"[ENVIO] {pacote} - Tentativa {tentativa}")
            except Exception as e:
                print(f"[ERRO] Falha ao enviar: {e}")
                return False
            
            # Aguarda ACK/NAK
            try:
                resposta, _ = self.socket.recvfrom(1024)
                
                # Processa resposta
                if resposta == b'ACK' or resposta.startswith(b'ACK'):
                    # Tenta extrair seq_num da resposta (formato: b'ACK0' ou b'ACK1')
                    try:
                        ack_seq = int(resposta.decode().split('ACK')[1])
                        if ack_seq == self.seq_num:
                            print(f"[ACK RECEBIDO] seq_num={self.seq_num}")
                            self.acks_recebidos += 1
                            self.esperando_ack = False
                            self.seq_num = 1 - self.seq_num  # Alterna 0 <-> 1
                            return True
                    except (IndexError, ValueError):
                        # Se for apenas 'ACK', assume que é para o seq_num atual
                        print(f"[ACK RECEBIDO] seq_num={self.seq_num}")
                        self.acks_recebidos += 1
                        self.esperando_ack = False
                        self.seq_num = 1 - self.seq_num  # Alterna 0 <-> 1
                        return True
                
                elif resposta == b'NAK' or resposta.startswith(b'NAK'):
                    print(f"[NAK RECEBIDO] Retransmitindo...")
                    self.naks_recebidos += 1
                    if tentativa < max_tentativas:
                        self.pacotes_retransmitidos += 1
                        time.sleep(0.1)  # Pequeno delay antes de retransmitir
                
            except socket.timeout:
                print(f"[TIMEOUT] ACK não recebido (tentativa {tentativa}/{max_tentativas})")
                if tentativa < max_tentativas:
                    self.pacotes_retransmitidos += 1
                    time.sleep(0.1)
        
        print(f"[ERRO] Falha na transmissão após {max_tentativas} tentativas")
        self.esperando_ack = False
        return False
    
    def processar_entrada_usuario(self):
        """
        Thread para processar entrada do usuário e enviar dados.
        Permite enviar múltiplos pacotes de forma contínua.
        """
        print("\n[INSTRUÇÕES] Digite os dados a serem transmitidos (ou 'sair' para encerrar):")
        
        while True:
            try:
                entrada = input(">>> ")
                
                if entrada.lower() == 'sair':
                    print("[REMETENTE] Encerrando...")
                    break
                
                if entrada.strip():
                    dados = entrada.encode('utf-8')
                    sucesso = self.enviar_dados(dados)
                    
                    if sucesso:
                        print(f"[SUCESSO] Dados transmitidos com sucesso!\n")
                    else:
                        print(f"[FALHA] Dados não foram transmitidos\n")
            
            except KeyboardInterrupt:
                print("\n[REMETENTE] Interrompido pelo usuário")
                break
            except Exception as e:
                print(f"[ERRO] {e}")
    
    def exibir_estatisticas(self):
        """Exibe estatísticas da transmissão."""
        print("\n" + "="*60)
        print("[ESTATÍSTICAS DO REMETENTE RDT 2.0]")
        print("="*60)
        print(f"Pacotes enviados:        {self.pacotes_enviados}")
        print(f"Pacotes retransmitidos:  {self.pacotes_retransmitidos}")
        print(f"ACKs recebidos:          {self.acks_recebidos}")
        print(f"NAKs recebidos:          {self.naks_recebidos}")
        print(f"Taxa de retransmissão:   {self.pacotes_retransmitidos / max(1, self.pacotes_enviados) * 100:.2f}%")
        print("="*60 + "\n")
    
    def fechar(self):
        """Fecha o socket e exibe estatísticas."""
        self.exibir_estatisticas()
        self.socket.close()
        print("[REMETENTE] Socket fechado")


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def main():
    """
    Função principal para testar o remetente RDT 2.0.
    """
    print("\n" + "="*60)
    print("RDT 2.0 - REMETENTE (com detecção de erros de bits)")
    print("Baseado em: Kurose & Ross, Seção 3.4.1")
    print("="*60)
    
    try:
        # Cria instância do remetente
        # Ajuste a porta e host conforme necessário
        remetente = RDT20Remetente(
            porta_remota=5006,      # Porta do receptor
            host_remoto='localhost',  # IP do receptor
            porta_local=5005,       # Porta local do remetente
            timeout=2.0             # Timeout para ACK/NAK
        )
        
        # Inicia processamento de entrada do usuário
        remetente.processar_entrada_usuario()
        
    except Exception as e:
        print(f"[ERRO FATAL] {e}")
    
    finally:
        remetente.fechar()


if __name__ == "__main__":
    main()