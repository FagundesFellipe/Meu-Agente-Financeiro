"""Normalização do meio de pagamento para os valores aceitos pelo banco.

A coluna ``expense.payment_method`` tem CHECK restrito a
``pix | credit_card | debit_card | cash | not_informed``. O prompt já pede que
o LLM devolva um desses valores, mas este módulo aceita também as variações em
português — o modelo pode escorregar e o CHECK não perdoa.
"""

import re

from financial_agent.agent.state_graph import PaymentMethod

__all__ = ["normalize_payment_method"]

_ACCENTS = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")

_ALIASES: dict[str, PaymentMethod] = {
    "pix": "pix",
    "transferencia": "pix",
    "ted": "pix",
    "doc": "pix",
    "credit_card": "credit_card",
    "credito": "credit_card",
    "cartao de credito": "credit_card",
    "cartao credito": "credit_card",
    "no credito": "credit_card",
    "parcelado": "credit_card",
    "debit_card": "debit_card",
    "debito": "debit_card",
    "cartao de debito": "debit_card",
    "cartao debito": "debit_card",
    "no debito": "debit_card",
    "cash": "cash",
    "dinheiro": "cash",
    "especie": "cash",
    "em especie": "cash",
    "a vista": "cash",
    "not_informed": "not_informed",
}


def normalize_payment_method(hint: str | None) -> PaymentMethod:
    """Converte a sugestão do LLM em um valor aceito pelo CHECK da tabela.

    Args:
        hint: Meio de pagamento sugerido, em qualquer variação.

    Returns:
        Um dos valores canônicos. Quando o texto não é reconhecido,
        ``"not_informed"`` — nunca levantamos erro aqui, porque meio de
        pagamento é opcional e não deve bloquear o registro do gasto.
    """
    if not hint:
        return "not_informed"

    text = re.sub(r"\s+", " ", hint.strip().lower().translate(_ACCENTS))

    return _ALIASES.get(text, "not_informed")
