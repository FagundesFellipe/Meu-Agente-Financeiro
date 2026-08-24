""""""

from financial_agent.agent.state_graph import GraphState


def view_expenses_report_predefined(graphState: GraphState):
    """
    Identificar e executuar SQL querys pré definidas para obter dados dos gastos.

    Exemplos:
        Quanto gastei ontem? -- dia completo -- valor total e 3 maiores
        gastos (configurado de forma fácil, não hardcode, ou seja,
        o agente retornará todos os dados, e a visualização aparecerá
        apenas 3, porém devo poder mudar de forma fácil para 4 ou 5).
        Quanto gastei de comida ontem? -- Categoria + dia completo
        valor total e 3 maiores gastos (configurado de forma fácil,
        não hardcode, ou seja, o agente retornará todos os dados,
        e a visualização aparecerá apenas 3, porém devo poder mudar
        de forma fácil para 4 ou 5).
        Qual foi o meu maior gasto? - apresentar maior gasto do mês
        até o dia atual + maior gasto da semana.
        Quanto gastei mês passado? -- Total mês + categoria de maior gasto.
    """
