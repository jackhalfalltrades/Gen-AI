"""Reviewer agent. No MCP tools. Votes on the investigator's draft.

Why it exists: the investigator will skip a playbook step (promo without
discount_bps) or treat empty search_logs as a fact. This node reads the
thread and writes a SystemMessage only the investigator sees.

It never goes to await_approval. pass means "tell the investigator to
submit ROOT_CAUSE to the operator," not "I accept the case."
"""

from typing import Literal

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from agent.context import build_system_prompts, format_analyst_note

# Two reviews max. Without this, more/hold can bounce forever and eval hangs.
MAX_ROUNDS = 2


class AnalystVerdict(BaseModel):
    """Structured vote. with_structured_output fills this — no VERDICT: parsing."""

    verdict: Literal["more", "hold", "pass"] = Field(
        description="more = fetch again, hold = rewrite the draft, pass = investigator may submit"
    )
    ask: str | None = Field(
        default=None,
        description="Exact tool call when verdict is more. Empty for hold or pass.",
    )
    reason: str = Field(description="Short reason citing tool results already in the thread.")


def call_analyst_model(state: dict) -> dict:
    """One analyst pass. Always returns to call_investigator_model with a note.

    Fallback pass: if LangChain does not return AnalystVerdict, do not loop
    and do not invent an ask — let the investigator submit. A thrown invoke
    still fails the node (no silent hang).

    Loop cap: after MAX_ROUNDS, coerce more/hold to pass so a human still
    sees a draft.
    """
    rounds = int(state.get("analyst_rounds") or 0) + 1
    # Late import: graph.py imports call_analyst_model from this file.
    from agent.graph import _build_llm

    reply = _build_llm("analyst").invoke(
        [
            SystemMessage(
                content=build_system_prompts(state.get("kind") or "incident")["analyst"]
            ),
            *state["messages"],
        ]
    )
    if not isinstance(reply, AnalystVerdict):
        reply = AnalystVerdict(verdict="pass", reason="analyst returned no structured verdict")
    if rounds >= MAX_ROUNDS and reply.verdict in {"more", "hold"}:
        reply = AnalystVerdict(
            verdict="pass",
            reason="loop cap; submit the current ROOT_CAUSE to the operator",
        )
    print(f"analyst: verdict={reply.verdict} round={rounds} ask={reply.ask}\n{reply.reason}\n")
    return {
        "analyst_rounds": rounds,
        "analyst_verdict": reply.verdict,
        "messages": [
            SystemMessage(
                content=format_analyst_note(reply.verdict, reply.reason, ask=reply.ask)
            )
        ],
    }
