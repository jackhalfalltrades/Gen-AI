"""
graph.py — LangGraph StateGraph for the interactive resume.

Why a graph instead of one LLM call
    A recruiter product needs *different paths*:
      - chat must be gated and judged
      - #skills / #experience should not go through the chat persona
        (they emit a structured inventory, not a conversational reply)

    START
      ├─ route=skills      → list_skills      → END
      ├─ route=experience  → list_experience  → END
      └─ route=chat        → input_guard
                               ├─ blocked → END  (polite redirect already appended)
                               └─ call_model ⇄ tools(search_profile)
                                               → evaluate_output → END

Conditional edges need an explicit path map. Without it the graph still
*runs* (the router returns a node name) but get_graph().draw_mermaid_png()
cannot see the edges — the README picture would be start → end only.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

import config
from evaluator import evaluate_output
from guardrails import input_guard
from experience import list_experience
from skills import list_skills
from tools import search_profile


# TwinState: shared graph state — messages, blocked, route.
class TwinState(TypedDict):
    """
    Shared state that every node reads/writes.

    messages: Annotated with add_messages so a node can return
              {"messages": [one_new_item]} and LangGraph *appends*
              instead of replacing the whole thread.
    blocked:  input_guard sets True when the turn is off-topic.
    route:    set by ask() — "chat" | "skills" | "experience".
    """

    messages: Annotated[list[BaseMessage], add_messages]
    blocked: bool
    route: str


# build_llm: wrap the configured chat client with the search_profile tool.
def build_llm(force_profile: bool = False):
    """
    Bind search_profile onto whatever provider config.get_chat_llm() returns.

    force_profile=True:
        Ask the provider to *must* call search_profile. That is how "Hi"
        still retrieves the resume instead of answering with a generic hello.
        Some providers (Ollama) do not support tool_choice — fall back to
        optional tools rather than crash the turn.
    """
    llm = config.get_chat_llm()
    if force_profile:
        try:
            return llm.bind_tools([search_profile], tool_choice="search_profile")
        except Exception:
            return llm.bind_tools([search_profile])
    return llm.bind_tools([search_profile])


# _chunk_text: pull visible tokens out of an AIMessageChunk.
def _chunk_text(chunk) -> str:
    """String tokens only — skip tool-call payloads and content-block noise."""
    content = getattr(chunk, "content", None)
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)
    return ""


# call_model: one LLM step; force retrieval on a fresh user turn.
async def call_model(state: TwinState) -> dict:
    """
    One model step. The graph comes back here after tools so the model
    can write the final answer with the ToolMessage sitting in state.

    We walk messages *backwards* to the latest HumanMessage. If we have
    not seen a ToolMessage since then, this is a fresh user turn → force
    retrieval. After tools run, we do *not* force again or we loop forever.
    """
    retrieved_this_turn = False
    for message in reversed(state["messages"]):
        if isinstance(message, ToolMessage):
            retrieved_this_turn = True
            break
        if isinstance(message, HumanMessage):
            break
    force = not retrieved_this_turn
    llm = build_llm(force_profile=force)
    writer = get_stream_writer()
    result = None
    async for chunk in llm.astream(state["messages"]):
        # First hop is usually tool_calls only — do not stream those.
        if not getattr(chunk, "tool_calls", None):
            piece = _chunk_text(chunk)
            if piece:
                writer(piece)
        result = chunk if result is None else result + chunk
    if result is None:
        return {}
    if result.tool_calls:
        print("GRAPH: call_model → tools", [tc["name"] for tc in result.tool_calls])
    else:
        print("GRAPH: call_model → evaluate_output")
    return {"messages": [result]}


# after_start: first router — skills / experience / chat.
def after_start(state: TwinState) -> str:
    """First router: channel click vs ordinary chat."""
    route = state.get("route") or "chat"
    if route == "skills":
        return "list_skills"
    if route == "experience":
        return "list_experience"
    return "input_guard"


# after_guard: blocked → END, else call_model.
def after_guard(state: TwinState) -> str:
    """Blocked turns already have the redirect AIMessage; skip the model."""
    return END if state.get("blocked") else "call_model"


# after_model: tool_calls → tools node, else evaluate_output.
def after_model(state: TwinState) -> str:
    """LangGraph helper: last AIMessage has tool_calls? → tools, else judge."""
    if tools_condition(state) == "tools":
        return "tools"
    return "evaluate_output"


# build_graph: register nodes + edges and compile the StateGraph.
def build_graph():
    """Compile the StateGraph. Path maps keep draw_mermaid_png() honest."""
    # ToolNode runs whatever tool_calls the last AIMessage requested.
    tools_node = ToolNode([search_profile])

    builder = StateGraph(TwinState)
    builder.add_node("input_guard", input_guard)
    builder.add_node("list_skills", list_skills)
    builder.add_node("list_experience", list_experience)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", tools_node)
    builder.add_node("evaluate_output", evaluate_output)

    builder.add_conditional_edges(
        START,
        after_start,
        {
            "list_skills": "list_skills",
            "list_experience": "list_experience",
            "input_guard": "input_guard",
        },
    )
    builder.add_edge("list_skills", END)
    builder.add_edge("list_experience", END)
    builder.add_conditional_edges(
        "input_guard",
        after_guard,
        {"call_model": "call_model", END: END},
    )
    builder.add_conditional_edges(
        "call_model",
        after_model,
        {"tools": "tools", "evaluate_output": "evaluate_output"},
    )
    # After tools, go back to the model so it can write prose from the hits.
    builder.add_edge("tools", "call_model")
    builder.add_edge("evaluate_output", END)

    return builder.compile()
