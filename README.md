# Mini-TCP-sobre-UDP
Projeto acadêmico baseado nas Seções 3.4 e 3.5 do livro *Redes de Computadores e a Internet* (Kurose & Ross), para ilustrar mecanismos simplificados do TCP (handshake e encerramento) sobre UDP.

## Requisitos
- Python 3.10+ instalado
- `pip` disponível

## Instalação de dependência de testes
Somente o `pytest` é necessário:

```bash
pip install pytest
```

## Como executar os testes com mensagens (prints)
Execute a partir da raiz do repositório para ver as mensagens:



```bash
pytest -s 
```

As flags `-s` permitem que os `print` apareçam (sequência SYN, SYN-ACK, ACK e FIN/ACK de encerramento).


