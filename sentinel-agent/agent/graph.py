from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import interrupt
from psycopg_pool import ConnectionPool

import config
from agent.context import build_system_prompt
from agent.router import route
from agent.runbooks import lookup_runbooks
from agent.tools import TOOLS

_graph = None
_pool = None
_saver = None


class InvestigationState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    kind: str | None
    approved: bool | None


def _alert_text(state: InvestigationState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content or ""
    return ""


def route_kind(state: InvestigationState) -> dict:
    """Set kind if the client did not. You implement agent.router.route."""
    existing = (state.get("kind") or "").strip().lower()
    if existing in {"incident", "security"}:
        print(f"router: using client kind={existing}")
        return {"kind": existing}
    kind = route(_alert_text(state))
    print(f"router: {kind}")
    return {"kind": kind}


def attach_runbook(state: InvestigationState) -> dict:
    """Always load a playbook from the alert. Not a model choice."""
    playbook = lookup_runbooks(_alert_text(state))
    print(f"playbook:\n{playbook}\n")
    return {
        "messages": [
            SystemMessage(content="Follow this playbook for tool names and queries:\n\n" + playbook)
        ]
    }


def _build_llm():
    return config.get_chat_llm().bind_tools(TOOLS)


def call_model(state: InvestigationState) -> dict:
    reply = _build_llm().invoke(
        [SystemMessage(content=build_system_prompt(state["kind"])), *state["messages"]]
    )
    return {"messages": [reply], "kind": state["kind"]}


def await_approval(state: InvestigationState) -> dict:
    proposed = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, AIMessage)),
        "",
    )
    decision = interrupt({"root_cause": proposed, "kind": state["kind"]})
    approved = isinstance(decision, dict) and bool(decision.get("approved"))
    return {"approved": approved}


def _after_model(state: InvestigationState) -> str:
    if tools_condition(state) == "tools":
        return "tools"
    return "await_approval"


def _build_graph(checkpointer: PostgresSaver):
    builder = StateGraph(InvestigationState)
    builder.add_node("route_kind", route_kind)
    builder.add_node("attach_runbook", attach_runbook)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_node("await_approval", await_approval)
    builder.add_edge(START, "route_kind")
    builder.add_edge("route_kind", "attach_runbook")
    builder.add_edge("attach_runbook", "call_model")
    builder.add_conditional_edges(
        "call_model",
        _after_model,
        {"tools": "tools", "await_approval": "await_approval"},
    )
    builder.add_edge("tools", "call_model")
    builder.add_edge("await_approval", END)
    return builder.compile(checkpointer=checkpointer)


def get_graph():
    """Public entry: one compiled graph + Postgres checkpointer for this process."""
    global _graph, _pool, _saver
    if _graph is None:
        _pool = ConnectionPool(
            conninfo=config.DATABASE_URL,
            kwargs={"autocommit": True},
        )
        _saver = PostgresSaver(_pool)
        _saver.setup()
        _graph = _build_graph(_saver)
    return _graph
