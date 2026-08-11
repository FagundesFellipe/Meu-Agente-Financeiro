"""Estratégias de trim (janela de turnos) para gerenciar contexto no LangGraph.

Dois usos, mesma lógica de contagem de turnos:

1. ``trim_messages_by_turns`` — cópia enxuta, não modifica o state.
   Use dentro de nós que passam mensagens para um LLM (ex.: roteador)
   para reduzir tokens sem perder mensagens no checkpoint.

2. ``create_trim_node`` — factory que devolve um nó do grafo. O nó retorna
   ``RemoveMessage`` para que o reducer ``add_messages`` apague as mensagens
   antigas do checkpoint de verdade, mantendo o ``MemorySaver`` limitado.

   Coloque no **final** do grafo (depois de ``finalize_response``) para que
   todos os nós anteriores vejam o estado completo e a limpeza aconteça só
   no fechamento da execução.

Regra de turno (idêntica nas duas funções):
    Um turno começa em cada ``HumanMessage`` e inclui tudo até a próxima
    ``HumanMessage`` (``AIMessage``, ``ToolMessage``, etc.). O turno é a
    unidade atómica — nunca cortamos no meio de uma interação.
"""

from collections.abc import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, RemoveMessage

from financial_agent.agent.state_graph import GraphState


def trim_messages_by_turns(
    messages: Sequence[BaseMessage], *, keep_turns: int = 3
) -> Sequence[BaseMessage]:
    """Devolve apenas os últimos ``keep_turns`` turnos, sem alterar o state.

    Args:
        messages: Lista de mensagens do state atual.
        keep_turns: Quantos turnos recentes preservar. Default: 3.

    Returns:
        Cópia enxuta da sequência ou a original se já couber no limite.
    """
    boundaries = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]

    if len(boundaries) <= keep_turns:
        return messages

    cutoff = boundaries[-keep_turns]
    return messages[cutoff:]


def create_trim_node(*, keep_turns: int = 5):
    """Cria um nó LangGraph que apaga turnos antigos do state.

    O nó retorna ``RemoveMessage`` — o reducer ``add_messages`` interpreta
    isso como comando de deleção e remove as mensagens do checkpoint.

    Args:
        keep_turns: Quantos turnos recentes manter no state.
                    Default alto (10) para preservar contexto de fluxos
                    multi-turno como correções e esclarecimentos.
    """

    async def trim_messages_node(state: GraphState) -> dict:
        messages: Sequence[BaseMessage] = state["messages"]

        boundaries = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]

        if len(boundaries) <= keep_turns:
            return {}

        cutoff = boundaries[-keep_turns]
        messages_to_remove = messages[:cutoff]

        return {
            "messages": [
                RemoveMessage(id=m.id) for m in messages_to_remove if m.id is not None
            ]
        }

    return trim_messages_node
