from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from deepeval.metrics import GEval, JsonCorrectnessMetric
from deepeval.metrics.g_eval import Rubric
from deepeval.models import OpenRouterModel
from deepeval.test_case import SingleTurnParams

from financial_agent.agent.state_graph import AddExpensesResult, ExtractedExpense


def build_json_correctness_metric() -> JsonCorrectnessMetric:
    """Métrica de schema: garante que o JSON respeita AddExpensesResult."""
    return JsonCorrectnessMetric(
        expected_schema=AddExpensesResult(expenses=[]),
        model=OpenRouterModel(),
        verbose_mode=True,
        async_mode=True,
        strict_mode=True,
    )


def build_correctness_metrics() -> GEval:
    """Métrica baseada em LLM (GEval) para julgamento semântico da resposta."""
    criteria = (
        "Avalie se o JSON atual representa fielmente cada gasto citado na "
        "mensagem do usuário, comparando campo a campo com o JSON esperado. "
        "Considere corretas extrações que preservem o significado financeiro "
        "do gasto (o que foi comprado, quanto, em quantas vezes, como foi "
        "pago e em qual categoria). "
        "O campo description deve ser julgado por equivalência SEMÂNTICA, "
        "nunca por comparação letra a letra: ignore completamente "
        "capitalização, acentuação, espaçamento, ordem de palavras e "
        "escolha de sinônimos ou paráfrases (ex.: 'uber', 'Uber' e 'corrida "
        "de aplicativo' descrevem o mesmo gasto e são igualmente corretos). "
        "Só penalize description se o significado do que foi comprado "
        "mudar de fato. "
        "O campo date_hint NUNCA deve influenciar a nota, em nenhuma "
        "direção: ignore-o por completo ao comparar os gastos, mesmo que "
        "os valores de data_hint sejam diferentes ou que um esteja "
        "presente e o outro null. "
        "Considere erradas extrações que omitam gastos da "
        "mensagem, inventem gastos inexistentes, troquem valores, "
        "parcelas, meios de pagamento ou categorias de forma que altere o "
        "significado do registro, ou que falhem em sinalizar ambiguidade "
        "quando ela existe."
    )

    evaluation_steps = [
        "Leia a mensagem original e o JSON esperado, listando cada gasto e seus atributos, exceto date_hint.",
        "Compare cada gasto do JSON atual com o correspondente no esperado, na ordem da mensagem: descrição (equivalência semântica, ignorando forma textual), valor (após normalizar separadores e remover R$), parcelas e amount_is_total, horário (HH:MM), meio de pagamento e categoria.",
        "Ignore completamente o campo date_hint na comparação e na nota final — divergências nesse campo não contam a favor nem contra.",
        "Confirme que nenhum gasto foi omitido nem inventado; trate como equivalentes variações de espaçamento, capitalização, acentuação, ordem de palavras e sinônimos/parafraseamento na descrição.",
        "Verifique a ambiguidade: itens claros vão em 'expenses' e os ambíguos acionam needs_clarification=true com pergunta específica. Mensagens claras devem ter needs_clarification=false.",
        "Penalize gravemente: valor numérico errado, inversão de amount_is_total, troca de categoria que mude o domínio do gasto e omissão de um gasto.",
    ]

    rubric = [
        Rubric(
            score_range=(0, 2),
            expected_outcome=(
                "Resposta incorreta: erros graves como valor numérico errado, "
                "inversão de amount_is_total, troca de categoria que mude o "
                "domínio do gasto, omissão de um gasto ou fabricação de gastos "
                "inexistentes."
            ),
        ),
        Rubric(
            score_range=(3, 5),
            expected_outcome=(
                "Resposta parcialmente correta, mas com omissões relevantes ou "
                "campos importantes (parcelas, meio de pagamento) divergindo "
                "do esperado. Divergências em date_hint nunca justificam essa "
                "faixa."
            ),
        ),
        Rubric(
            score_range=(6, 8),
            expected_outcome=(
                "Resposta majoritariamente correta: estrutura, valor, parcelas, "
                "categoria e tratamento de ambiguidade corretos. Diferenças "
                "apenas textuais/semânticas em description (capitalização, "
                "espaçamento, acentuação, ordem de palavras, sinônimos) e "
                "quaisquer diferenças em date_hint **não devem derrubar a "
                "nota para esta faixa** — mantenha aqui enquanto o "
                "significado financeiro estiver preservado."
            ),
        ),
        Rubric(
            score_range=(9, 10),
            expected_outcome=(
                "Resposta correta e completa: todos os campos relevantes "
                "batem com o esperado em significado (descrição "
                "semanticamente equivalente, valor, parcelas, pagamento e "
                "categoria). O campo date_hint é ignorado e não impede essa "
                "nota."
            ),
        ),
    ]

    return GEval(
        name="Field Correctness",
        criteria=criteria,
        evaluation_steps=evaluation_steps,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        rubric=rubric,
        threshold=0.7,
        model=OpenRouterModel(),
        async_mode=True,
        verbose_mode=True,
    )
