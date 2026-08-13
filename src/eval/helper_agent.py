import json

from langchain.messages import HumanMessage

from financial_agent.agent.build_graph_workflow import graph as Graph
from financial_agent.agent.state_graph import InputState


async def helper_agent_json(input: str) -> str:
    graph = Graph()
    result = await graph.ainvoke(
        InputState(
            channel="telegram",
            phone_number="5535912344321",
            messages=[HumanMessage(content=input)],
        ),
        config={"configurable": {"thread_id": "eval_test"}},
    )

    extracted = result.get("extracted_expenses", [])

    return json.dumps(
        [expense.model_dump(mode="json") for expense in extracted],
        ensure_ascii=False,
    )


async def helper_agent_string(input: str) -> str:
    graph = Graph()
    result = await graph.ainvoke(
        InputState(
            channel="telegram",
            phone_number="5535912344321",
            messages=[HumanMessage(content=input)],
        ),
        config={"configurable": {"thread_id": "eval_test"}},
    )

    return result["response_text"]
