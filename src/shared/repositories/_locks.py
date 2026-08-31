"""Advisory locks de transação, compartilhados entre os repositórios.

Um advisory lock serializa operações concorrentes que precisam checar-e-inserir
dentro da mesma transação — é o que impede que dois workers processando a mesma
mensagem criem linhas duplicadas.

A chave é derivada de ``namespace:key`` para que repositórios diferentes nunca
colidam entre si mesmo usando o mesmo identificador de origem.
"""

import hashlib

__all__ = ["ADVISORY_TRANSACTION_LOCK", "advisory_lock_key"]

ADVISORY_TRANSACTION_LOCK = "SELECT pg_advisory_xact_lock(%s)"


def advisory_lock_key(namespace: str, key: str) -> int:
    """Gera uma chave de lock determinística via SHA-256 para o namespace.

    Produz um inteiro signed 64-bit a partir dos primeiros 8 bytes do hash,
    compatível com ``pg_advisory_xact_lock(bigint)``.
    """
    payload = f"{namespace}:{key}".encode()
    return int.from_bytes(
        hashlib.sha256(payload).digest()[:8],
        byteorder="big",
        signed=True,
    )
