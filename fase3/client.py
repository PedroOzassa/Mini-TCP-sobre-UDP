"""
Cliente Parte 1: apenas o three-way handshake.

Etapas:
1) client = SimpleTCPSocket(9000)
2) client.connect(('localhost', 8000))
"""

import time
from TCPSocket import SimpleTCPSocket


def main():
    client = SimpleTCPSocket(9000)
    try:
        print("[CLIENT] Conectando ao servidor em localhost:8000...")
        client.connect(("localhost", 8000), timeout=5.0)
        print("[CLIENT] Conexão estabelecida (ESTABLISHED)")
        time.sleep(0.5)
    except Exception as e:
        print(f"[CLIENT] Erro: {e}")
    finally:
        try:
            client.udp_socket.close()
        except:
            pass


if __name__ == "__main__":
    main()
