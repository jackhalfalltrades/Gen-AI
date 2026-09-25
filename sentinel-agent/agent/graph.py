"""LangGraph for one investigation.

Why a graph, not a single LLM call:
  The model is bad at "always open the playbook first" and at pausing for a
  human. Nodes force those steps. The analyst is a second model that only
  writes notes back to the investigator — it never faces the operator.

Shape:
  START → route_kind → attach_runbook → call_investigator_model ⇄ tools
       call_investigator_model → call_analyst_model → call_investigator_model
       call_investigator_model → await_approval → END   (only after pass)

thread_id is the case_id. PostgresSaver keeps that thread across uvicorn restarts.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import interrupt
from psycopg_pool import ConnectionPool

import config
from agent.analyst import AnalystVerdict, call_analyst_model
from agent.context import build_system_prompts
from agent.router import route
from agent.runbooks import lookup_runbooks
from agent.tools import TOOLS

_graph = None
_pool = None
_saver = None


class InvestigationState(TypedDict):
    """One case. add_messages appends; it does not replace the thread."""

    messages: Annotated[list[BaseMessage], add_messages]
    kind: str | None
    approved: bool | None
    analyst_rounds: int
    analyst_verdict: str | None


def _alert_text(state: InvestigationState) -> str:
    """Last human line is the alert. Used by the router and playbook lookup."""
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content or ""
    return ""


def route_kind(state: InvestigationState) -> dict:
    """Pick incident vs security before any model runs.

    The client can send kind. If they omit it, keyword route() decides.
    That choice only changes the system prompt (policy), not the tools.
    """
    existing = (state.get("kind") or "").strip().lower()
    if existing in {"incident", "security"}:
        print(f"router: using client kind={existing}")
        return {"kind": existing}
    kind = route(_alert_text(state))
    print(f"router: {kind}")
    return {"kind": kind}


def attach_runbook(state: InvestigationState) -> dict:
    """Always inject a playbook. Not a tool, because the model skipped the tool.

    skills/*.md tell it which service/query to use (HikariPool, not Prometheus
    names). This node exists so that step cannot be optional.
    """
    playbook = lookup_runbooks(_alert_text(state))
    print(f"playbook:\n{playbook}\n")
    return {
        "messages": [
            SystemMessage(content="Follow this playbook for tool names and queries:\n\n" + playbook)
        ]
    }


def _build_llm(role: str = "investigator"):
    """Same factory, two bindings.

    investigator — bind_tools so it can call MCP.
    analyst — structured AnalystVerdict, no tools (it must not search).
    bind_tools / with_structured_output return a new runnable; they do not
    mutate the cached get_chat_llm() client.
    """
    llm = config.get_chat_llm()
    if role == "investigator":
        return llm.bind_tools(TOOLS)
    if role == "analyst":
        return llm.with_structured_output(AnalystVerdict)
    raise ValueError(f"unknown llm role {role!r}; use investigator or analyst")


def call_investigator_model(state: InvestigationState) -> dict:
    """Investigator turn: think, call a tool, or write ROOT_CAUSE.

    If it calls a tool, wipe analyst_verdict so a new fetch is reviewed again.
    Otherwise a leftover 'pass' would send a fresh draft straight to the human.
    """
    reply = _build_llm("investigator").invoke(
        [
            SystemMessage(content=build_system_prompts(state["kind"])["investigator"]),
            *state["messages"],
        ]
    )
    out: dict = {"messages": [reply], "kind": state["kind"]}
    if getattr(reply, "tool_calls", None):
        out["analyst_verdict"] = None
    return out


def await_approval(state: InvestigationState) -> dict:
    """Pause for the operator. The payload is the investigator's last AIMessage.

    Analyst notes are SystemMessages — they are not this content. Resume with
    Command(resume={"approved": bool}) from decide_case.
    """
    proposed = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, AIMessage)),
        "",
    )
    decision = interrupt({"root_cause": proposed, "kind": state["kind"]})
    approved = isinstance(decision, dict) and bool(decision.get("approved"))
    return {"approved": approved}


def _after_model(state: InvestigationState) -> str:
    """Where to go after the investigator speaks.

    tools            — it asked for MCP data
    await_approval   — analyst already said pass; this draft is for the human
    call_analyst_model — first draft, or more/hold came back and it wrote again
    """
    if tools_condition(state) == "tools":
        return "tools"
    if (state.get("analyst_verdict") or "").strip().lower() == "pass":
        return "await_approval"
    return "call_analyst_model"


def _build_graph(checkpointer: PostgresSaver):
    """Wire nodes. call_analyst_model → call_investigator_model always.

    The human only hangs off call_investigator_model after a pass.
    """
    builder = StateGraph(InvestigationState)
    builder.add_node("route_kind", route_kind)
    builder.add_node("attach_runbook", attach_runbook)
    builder.add_node("call_investigator_model", call_investigator_model)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_node("call_analyst_model", call_analyst_model)
    builder.add_node("await_approval", await_approval)
    builder.add_edge(START, "route_kind")
    builder.add_edge("route_kind", "attach_runbook")
    builder.add_edge("attach_runbook", "call_investigator_model")
    builder.add_conditional_edges(
        "call_investigator_model",
        _after_model,
        {
            "tools": "tools",
            "call_analyst_model": "call_analyst_model",
            "await_approval": "await_approval",
        },
    )
    builder.add_edge("tools", "call_investigator_model")
    builder.add_edge("call_analyst_model", "call_investigator_model")
    builder.add_edge("await_approval", END)
    return builder.compile(checkpointer=checkpointer)


def get_graph():
    """One compiled graph + Postgres checkpointer for this process.

    Built once. Restart uvicorn after you change edges or you will run the
    old graph. InMemorySaver died on --reload; that is why this is Postgres.
    """
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
