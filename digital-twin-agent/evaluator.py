"""
evaluator.py — LLM judge on the *final* answer, plus a swap.

This is not a second input gate. The question already passed input_guard.
We score the assistant text against the ToolMessage evidence.

    ok     → leave the answer alone (return {})
    not ok → append SAFE_FALLBACK (add_messages will make it the latest)

We do *not* ask the same model to "try again and be honest." A failed
judge becomes a fixed sentence so a recruiter never sees a hallucinated
title like "Lead Engineer at Target" when the resume said something else.
"""

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

import config
from guardrails import last_user_text

SAFE_FALLBACK = (
    "I don't have a reliable, resume-grounded answer for that. "
    "Please ask about a specific role, company, skill, or project "
    "from Chandra Peravelli's work history."
)


# OutputVerdict: judge score. evaluate_output only branches on `ok`.
class OutputVerdict(BaseModel):
    """Structured judge score. ok is the only field evaluate_output branches on."""

    grounded: bool = Field(
        description="True if claims are supported by tool/resume evidence or the model correctly says it does not know."
    )
    on_topic: bool = Field(description="True if the reply stays on Chandra's professional background.")
    professional: bool = Field(description="True if the tone is suitable for recruiters.")
    ok: bool = Field(description="True only if grounded, on_topic, and professional.")
    reason: str = Field(description="Short reason.")


# _last_final_answer: last AIMessage that is not a tool-call stub.
def _last_final_answer(messages: list[BaseMessage]) -> str:
    """Last AIMessage that is not a tool-call stub."""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            return message.content or ""
    return ""


# _tool_evidence: up to two recent ToolMessages for the judge to compare.
def _tool_evidence(messages: list[BaseMessage]) -> str:
    """
    Up to the two most recent ToolMessages (4k chars each).

    That is the resume text the model was allowed to use. The judge
    compares the answer against this, not against the whole PDF.
    """
    chunks: list[str] = []
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.content:
            chunks.append(str(message.content)[:4000])
        if len(chunks) >= 2:
            break
    return "\n---\n".join(reversed(chunks)) or "(no tool results this turn)"


# check_output: LLM OutputVerdict against question + tool evidence.
async def check_output(question: str, answer: str, evidence: str) -> OutputVerdict:
    """Ask the configured LLM whether this answer is grounded and on-topic."""
    llm = config.get_chat_llm().with_structured_output(OutputVerdict)
    try:
        return await llm.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You evaluate answers from Chandra Peravelli's interactive resume.\n"
                        "Greetings and 'tell me about yourself' ask for a professional summary "
                        "and are on topic.\n"
                        "A paraphrase of resume facts is grounded. PASS if companies, titles, "
                        "and skills in the answer appear in the evidence, even if wording differs.\n"
                        "FAIL grounded only if the answer names an employer, title, date, or skill "
                        "that is not in the evidence at all.\n"
                        "If evidence is present and the answer stays within it, set ok true."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Evidence from resume tools / prior retrieval:\n{evidence}\n\n"
                        f"Answer to evaluate:\n{answer}"
                    ),
                },
            ]
        )
    except Exception as exc:
        # Fail closed: if the judge dies, do not ship the unchecked answer.
        print("EVALUATOR: failed, treating as not ok:", exc)
        return OutputVerdict(
            grounded=False,
            on_topic=False,
            professional=False,
            ok=False,
            reason="evaluator_error",
        )


# evaluate_output: graph node — keep the answer or swap in SAFE_FALLBACK.
async def evaluate_output(state: dict) -> dict:
    """LangGraph node: judge the last final AIMessage; replace if it fails."""
    messages: list[BaseMessage] = state["messages"]
    answer = _last_final_answer(messages)
    question = last_user_text(messages)
    evidence = _tool_evidence(messages)
    verdict = await check_output(question, answer, evidence)
    print(
        f"EVALUATOR: ok={verdict.ok} grounded={verdict.grounded} "
        f"on_topic={verdict.on_topic} — {verdict.reason}"
    )
    if verdict.ok:
        return {}
    return {"messages": [AIMessage(content=SAFE_FALLBACK)]}
