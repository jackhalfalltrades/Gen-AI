"""
ask.py — the only function Gradio (and the CLI) should call.

ask_stream() is the live path: LangGraph astream + custom token writer
from call_model. Gradio yields each partial so the recruiter sees text
as it arrives. ask() just collects the last chunk for the CLI.

The graph is cached on first use. Restart app.py after graph.py changes.
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from context import build_system_prompt
from graph import build_graph
from memory import CompactSession

# Compiled once per process. Compiling on every question would rebuild
# the StateGraph and lose nothing functionally, but it is wasted work.
_graph = None


# get_graph: compile the StateGraph once per process.
def get_graph():
    """Lazy singleton so `import ask` does not talk to the LLM provider yet."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ask_stream: yield growing answer text as the graph produces it.
async def ask_stream(question: str, session: CompactSession, route: str = "chat"):
    """
    One graph pass, token-by-token for chat.

    custom  — call_model writes visible tokens after retrieval
    values  — full state after each node (used for session.replace)

    Skills / experience / guard redirects have no token stream; we yield
    the finished bubble once. If the evaluator swaps in a fallback, the
    last yield replaces the streamed draft.
    """
    if route == "chat":
        await session.add(HumanMessage(content=question))

    streamed = ""
    last_state = None
    async for mode, data in get_graph().astream(
        {"messages": session.get_messages(), "route": route},
        stream_mode=["custom", "values"],
    ):
        if mode == "custom" and isinstance(data, str) and data:
            streamed += data
            yield streamed
        elif mode == "values":
            last_state = data

    if last_state is None:
        if streamed:
            yield streamed
        return

    await session.replace(last_state["messages"])
    final = last_state["messages"][-1].content
    if not isinstance(final, str):
        final = str(final or "")
    if final and final != streamed:
        yield final


# ask: collect ask_stream — CLI / anything that wants one string.
async def ask(question: str, session: CompactSession, route: str = "chat") -> str:
    """
    Run one graph pass and return the final assistant text.

    route:
        "chat"       — input_guard → call_model ⇄ tools → evaluate_output
        "skills"     — list_skills → END
        "experience" — list_experience → END
    """
    answer = ""
    async for part in ask_stream(question, session, route=route):
        answer = part
    return answer


# run_and_print: smoke-test helper — prints answer, latency, window size.
async def run_and_print(question: str, session: CompactSession) -> None:
    """CLI helper used by `uv run python ask.py` to smoke-test two turns."""
    t0 = time.perf_counter()
    answer = await ask(question, session)
    latency_ms = (time.perf_counter() - t0) * 1000
    print(f"Q: {question}")
    print(f"Answer: {answer}")
    print(f"Latency: {latency_ms:.0f}ms")
    print(f"Messages in session: {len(session.get_messages())}")
    print("---")


# _main: CLI smoke test — two questions on one CompactSession.
async def _main() -> None:
    """CLI entry: two sequential questions on one CompactSession."""
    session = CompactSession(build_system_prompt())
    await run_and_print("What company does Chandra work at currently?", session)
    await run_and_print("What is his role there?", session)


if __name__ == "__main__":
    asyncio.run(_main())
