from langchain.messages import HumanMessage

from financial_agent.agent.build_graph_workflow import graph as Graph
from financial_agent.agent.state_graph import AddExpensesResult, InputState


async def helper_agent_json(input: str) -> str:
    graph = Graph()
    result = await graph.ainvoke(
        InputState(
            channel="telegram",
            phone_number="5535912344321",
            messages=[HumanMessage(content=input)],
        ),
        config={"configurable": {"thread_id": f"{input}"}},
    )

    add_expenses_result = AddExpensesResult(
        expenses=result.get("extracted_expenses", []),
        needs_clarification=result.get("needs_clarification", False),
        clarification_message=result.get("clarification_message"),
    )

    return add_expenses_result.model_dump_json()
