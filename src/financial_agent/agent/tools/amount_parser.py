"""Validação determinística do valor estruturado pelo LLM para ``Decimal``.

O LLM já normaliza o valor em algarismos (vírgula ou ponto como separador
decimal, sem texto por extenso, sem símbolo de moeda). Este módulo apenas:

    1. extrai o token numérico (safety net para ruído residual como "R$");
    2. desambigua `.`/`,` (problema de locale, não de linguagem natural);
    3. valida que há um único valor e que ele é positivo;
    4. quantiza em 2 casas decimais.

Interpretação semântica ("duzentos reais", "8 e 50", "3x de 50") é
responsabilidade do LLM, não deste módulo.
"""

import re
from decimal import Decimal, InvalidOperation

__all__ = ["AmountParseError", "parse_amount"]


class AmountParseError(ValueError):
    """O valor informado não pôde ser convertido com segurança."""


_NUMERIC = re.compile(r"\d[\d.,]*")


def _parse_numeric(token: str) -> Decimal:
    """Converte um token numérico respeitando as convenções pt-BR e en-US."""
    has_comma = "," in token
    has_dot = "." in token

    if has_comma and has_dot:
        # O separador decimal é o que aparece por último.
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif has_comma:
        token = token.replace(",", ".")
    elif has_dot:
        # "1.234" é milhar; "12.90" é decimal. Decide pelo tamanho do sufixo.
        head, _, tail = token.rpartition(".")
        if len(tail) == 3 and head:
            token = token.replace(".", "")

    try:
        return Decimal(token)
    except InvalidOperation as exc:
        raise AmountParseError(f"Valor numérico inválido: {token!r}") from exc


def parse_amount(raw: str) -> Decimal:
    """Converte o valor estruturado pelo LLM em ``Decimal`` positivo com 2 casas.

    Args:
        raw: Valor em algarismos (``ExtractedExpense.amount_raw``). Resíduos
            como "R$" ou espaços são tolerados como safety net.

    Returns:
        Valor decimal quantizado em duas casas.

    Raises:
        AmountParseError: Se o texto não contiver um valor único e inequívoco.
            O chamador deve transformar isso em um pedido de esclarecimento.
    """
    if not raw or not raw.strip():
        raise AmountParseError("Valor vazio")

    text = raw.strip()

    # Sinal negativo: rejeita antes que vire positivo silenciosamente.
    if re.search(r"-\s*\d", text):
        raise AmountParseError(f"Valor negativo não é aceito: {raw!r}")

    numeric_tokens = _NUMERIC.findall(text)
    if len(numeric_tokens) > 1:
        raise AmountParseError(f"Mais de um valor numérico em {raw!r}")

    if not numeric_tokens:
        raise AmountParseError(f"Não foi possível interpretar o valor: {raw!r}")

    value = _parse_numeric(numeric_tokens[0])

    if value <= 0:
        raise AmountParseError(f"Valor precisa ser maior que zero: {raw!r}")

    return value.quantize(Decimal("0.01"))
