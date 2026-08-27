"""Ferramentas determinísticas do agente financeiro.

Nenhuma delas é exposta ao LLM como tool-call: são funções Python chamadas
pelo nó do grafo depois da extração. Manter a aritmética, as datas e a
resolução de categoria fora do modelo é o que garante a regra do PRD de que
o LLM nunca calcula nem inventa dado financeiro.
"""

from financial_agent.agent.tools.amount_parser import (
    AmountParseError,
    parse_expense_amount,
)
from financial_agent.agent.tools.calendar import (
    DateResolutionError,
    resolve_occurred_at,
    user_now,
)
from financial_agent.agent.tools.get_category import (
    CategoryResolutionError,
    resolve_category,
)
from financial_agent.agent.tools.payment_method import normalize_payment_method

__all__ = [
    "AmountParseError",
    "CategoryResolutionError",
    "DateResolutionError",
    "normalize_payment_method",
    "parse_expense_amount",
    "resolve_category",
    "resolve_occurred_at",
    "user_now",
]
