from __future__ import annotations

from deepeval.metrics import GEval, JsonCorrectnessMetric
from deepeval.metrics.g_eval import Rubric
from deepeval.models import OpenRouterModel
from deepeval.test_case import SingleTurnParams

from financial_agent.agent.state_graph import AddExpensesResult, ExpenseQuery


def build_json_correctness_metric() -> JsonCorrectnessMetric:
    """Métrica de schema: garante que o JSON respeita AddExpensesResult."""
    return JsonCorrectnessMetric(
        expected_schema=AddExpensesResult(expenses=[]),
        model=OpenRouterModel(),
        verbose_mode=True,
        async_mode=True,
        strict_mode=True,
    )


def build_report_json_correctness_metric() -> JsonCorrectnessMetric:
    """Métrica de schema: garante que o JSON respeita ExpenseQuery."""
    return JsonCorrectnessMetric(
        expected_schema=ExpenseQuery(operation="listar_gastos_fixos"),
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


def build_report_correctness_metrics() -> GEval:
    """Métrica baseada em LLM (GEval) para julgamento semântico da consulta de relatório."""
    criteria = (
        "Avalie se o JSON atual representa fielmente a consulta de relatório "
        "pedida pelo usuário, comparando campo a campo com o JSON esperado: "
        "operation, periods (symbol e day_hint), period_combination, category, "
        "payment_method, limit, pagination, unsupported e unsupported_reason. "
        "O campo category deve ser julgado por equivalência SEMÂNTICA com as "
        "palavras usadas pelo usuário, ignorando capitalização e acentuação. "
        "O campo unsupported_reason deve ser julgado por equivalência "
        "SEMÂNTICA (mesma razão de não suporte), nunca por comparação letra "
        "a letra. "
        "Considere erradas extrações que troquem a operação, inventem ou "
        "omitam períodos, troquem period_combination, meio de pagamento ou "
        "categoria de forma que altere o significado da consulta, ou que "
        "deixem de marcar unsupported quando o pedido está fora das cinco "
        "operações suportadas (ou marquem indevidamente quando está dentro)."
    )

    evaluation_steps = [
        "Leia a pergunta original e o JSON esperado, identificando operation, periods, period_combination, category, payment_method, limit, pagination e o par unsupported/unsupported_reason.",
        "Compare o JSON atual campo a campo com o esperado: a operação deve ser exatamente a mesma; os períodos devem ter os mesmos symbols e day_hints (quando specific_day); period_combination deve bater (merge vs compare).",
        "Verifique category e payment_method por equivalência semântica com o pedido do usuário, e confirme que limit/pagination só aparecem quando a operação é listar_gastos.",
        "Confirme que unsupported está correto: true somente para pedidos fora de total, comparar_periodos, listar_gastos, total_por_categoria e listar_gastos_fixos, com unsupported_reason semanticamente equivalente ao esperado.",
        "Penalize gravemente: operação errada, período inventado ou omitido, period_combination errado, e marcação incorreta de unsupported (em qualquer direção).",
    ]

    rubric = [
        Rubric(
            score_range=(0, 2),
            expected_outcome=(
                "Resposta incorreta: operação errada, período inventado ou "
                "omitido, period_combination errado, ou marcação incorreta de "
                "unsupported (em qualquer direção)."
            ),
        ),
        Rubric(
            score_range=(3, 5),
            expected_outcome=(
                "Resposta parcialmente correta, mas com filtros relevantes "
                "(category, payment_method, limit, pagination) divergindo do "
                "esperado, mesmo com a operação e os períodos corretos."
            ),
        ),
        Rubric(
            score_range=(6, 8),
            expected_outcome=(
                "Resposta majoritariamente correta: operação, períodos e "
                "period_combination corretos. Diferenças apenas textuais na "
                "redação de unsupported_reason não devem derrubar a nota "
                "para esta faixa, desde que o significado seja o mesmo."
            ),
        ),
        Rubric(
            score_range=(9, 10),
            expected_outcome=(
                "Resposta correta e completa: todos os campos relevantes "
                "batem com o esperado em significado (operação, períodos, "
                "combinação, filtros e tratamento de suporte)."
            ),
        ),
    ]

    return GEval(
        name="Report Query Field Correctness",
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
