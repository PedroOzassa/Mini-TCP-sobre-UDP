"""
Servidor Parte 1: apenas o three-way handshake.

Etapas:
1) server = SimpleTCPSocket(8000)
2) server.listen()
3) conn = server.accept()
"""

from TCPSocket import SimpleTCPSocket


def main():
    server = SimpleTCPSocket(8000)
    try:
        print("[SERVER] Escutando na porta 8000...")
        server.listen()
        conn = server.accept(timeout=10.0)
        if conn and conn.state == 'ESTABLISHED':
            print("[SERVER] Conexão estabelecida (ESTABLISHED)")
    except Exception as e:
        print(f"[SERVER] Erro: {e}")
    finally:
        try:
            server.udp_socket.close()
        except:
            pass


if __name__ == "__main__":
    main()
