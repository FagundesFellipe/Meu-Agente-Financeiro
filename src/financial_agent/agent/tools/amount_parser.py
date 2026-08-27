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

__all__ = ["AmountParseError", "parse_expense_amount"]


class AmountParseError(ValueError):
    """O valor informado não pôde ser convertido com segurança."""


_NUMERIC_AMOUNT_FRAGMENT_PATTERN = re.compile(r"\d[\d.,]*")


def _parse_numeric(numeric_amount_text_extracted: str) -> Decimal:
    """Converte um token numérico respeitando as convenções pt-BR e en-US."""
    has_comma = "," in numeric_amount_text_extracted
    has_dot = "." in numeric_amount_text_extracted

    if has_comma and has_dot:
        if numeric_amount_text_extracted.rfind(
            ","
        ) > numeric_amount_text_extracted.rfind("."):
            numeric_amount_text_extracted = numeric_amount_text_extracted.replace(
                ".", ""
            ).replace(",", ".")
        else:
            numeric_amount_text_extracted = numeric_amount_text_extracted.replace(
                ",", ""
            )
    elif has_comma:
        numeric_amount_text_extracted = numeric_amount_text_extracted.replace(",", ".")
    elif has_dot:
        head, _, tail = numeric_amount_text_extracted.rpartition(".")
        if len(tail) == 3 and head:
            numeric_amount_text_extracted = numeric_amount_text_extracted.replace(
                ".", ""
            )

    try:
        return Decimal(numeric_amount_text_extracted)
    except InvalidOperation as exc:
        raise AmountParseError(
            f"Valor numérico inválido: {numeric_amount_text_extracted!r}"
        ) from exc


def parse_expense_amount(raw: str) -> Decimal:
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

    normalized_amount_text = raw.strip()

    # Sinal negativo: rejeita antes que vire positivo silenciosamente.
    if re.search(r"-\s*\d", normalized_amount_text):
        raise AmountParseError(f"Valor negativo não é aceito: {raw!r}")

    numeric_amount_matches = _NUMERIC_AMOUNT_FRAGMENT_PATTERN.findall(
        normalized_amount_text
    )
    if len(numeric_amount_matches) > 1:
        raise AmountParseError(f"Mais de um valor numérico em {raw!r}")

    if not numeric_amount_matches:
        raise AmountParseError(f"Não foi possível interpretar o valor: {raw!r}")

    decimal_amount = _parse_numeric(numeric_amount_matches[0])

    if decimal_amount <= 0:
        raise AmountParseError(f"Valor precisa ser maior que zero: {raw!r}")

    return decimal_amount.quantize(Decimal("0.01"))
