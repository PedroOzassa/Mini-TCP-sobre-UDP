import threading
import time
import sys
import os

# Adicionar diretorio da fase3 ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../fase3")

from TCPSocket import SimpleTCPSocket


def test_handshake_basico():
    print("\nTCP Simples (fase3) TESTE 1. Estabelecimento de conexão (three-way handshake)")

    # Servidor
    server = SimpleTCPSocket(8000)
    server_state = {"established": False}

    def server_thread():
        print("Servidor: escutando em 127.0.0.1:8000")
        server.listen()
        conn = server.accept(timeout=5.0)
        assert conn is not None
        assert conn.state == 'ESTABLISHED'
        server_state["established"] = True
        print("Servidor: conexão aceita (ESTABLISHED)")

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()

    # Pequeno atraso para garantir que o servidor escutou
    time.sleep(0.2)

    # Cliente
    client = SimpleTCPSocket(9000)
    start_t = time.time()
    client.connect(('localhost', 8000), timeout=5.0)
    end_t = time.time()
    assert client.state == 'ESTABLISHED'

    t.join(timeout=5.0)

    elapsed = end_t - start_t
    print(f"Cliente: ESTABLISHED em {elapsed:.4f} s")
    print(f"Servidor ESTABLISHED? {server_state['established']}")
    

def test_encerramento_conexao():
    print("\nTCP Simples (fase3) TESTE 2. Encerramento de conexão (four-way handshake)")

    # Servidor aceita conexão e então fecha de forma passiva ao receber FIN
    server = SimpleTCPSocket(8000)

    server_ready = {"ok": False}

    def server_thread():
        print("Servidor: escutando em 127.0.0.1:8000")
        server.listen()
        conn = server.accept(timeout=5.0)
        assert conn is not None and conn.state == 'ESTABLISHED'
        server_ready["ok"] = True
        # Passivo: aguarda FIN do cliente e realiza ACK -> FIN -> espera ACK final
        conn.close()
        assert conn.state == 'CLOSED'
        print("Servidor: conexão encerrada (CLOSED)")

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()

    time.sleep(0.2)

    # Cliente conecta e inicia fechamento (ativo)
    client = SimpleTCPSocket(9000)
    client.connect(("localhost", 8000), timeout=5.0)
    assert client.state == 'ESTABLISHED'

    # Espera o servidor sinalizar que está pronto
    start_wait = time.time()
    while not server_ready["ok"] and (time.time() - start_wait) < 2.0:
        time.sleep(0.05)

    print("Cliente: iniciando fechamento (FIN)")
    client.close()
    assert client.state == 'CLOSED'
    print("Cliente: conexão encerrada (CLOSED)")

    t.join(timeout=5.0)

