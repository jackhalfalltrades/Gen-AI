"""
guardrails.py — LLM input gate (not a keyword list).

Why an LLM instead of "block if the message contains X"
    Follow-ups like "what about there?" or "yes, go ahead" are on-topic
    only if you can see the thread. A deny-list of hobbies/politics
    misses jailbreaks and false-positives greetings.

What this node returns
    allowed → {"blocked": False}
    blocked → {"blocked": True, "messages": [AIMessage(REDIRECT)]}
              and the graph goes START… → END without calling the model.

If the classifier itself throws, we *block*. Fail-closed: a recruiter
seeing a redirect is better than an unfiltered answer.
"""

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

import config

# Shown as the assistant bubble when the turn is off-topic.
# Keep it short and point them at example questions they *can* ask.
REDIRECT = (
    "I'm Chandra Peravelli's interactive resume — I can speak to his "
    "work history, roles, skills, projects, and education. "
    "I don't cover topics outside his professional background. "
    "Please ask about his experience, for example: "
    "current role, prior companies, Kafka or distributed-systems work, "
    "or the skills he uses on the job."
)


# InputVerdict: allow or block. call_model always retrieves on a fresh turn.
class InputVerdict(BaseModel):
    """Structured output so we do not parse 'yes/no' from free text."""

    allowed: bool = Field(
        description="True if this turn is (or continues) a conversation about Chandra's professional background."
    )
    reason: str = Field(description="Short reason for the decision.")


# last_user_text: latest HumanMessage content (this turn's question).
def last_user_text(messages: list[BaseMessage]) -> str:
    """Walk backwards — the latest HumanMessage is this turn's question."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content or ""
    return ""


# _thread_excerpt: recent user/assistant prose so follow-ups can be judged.
def _thread_excerpt(messages: list[BaseMessage], limit: int = 6) -> str:
    """
    Recent human/assistant prose only.

    ToolMessages are skipped (they are resume dumps, not dialogue).
    AIMessages with tool_calls are skipped (they are 'please call X',
    not something the recruiter said).
    """
    lines: list[str] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            continue
        if isinstance(message, HumanMessage):
            lines.append(f"User: {message.content}")
        elif isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            content = (message.content or "")[:400]
            lines.append(f"Assistant: {content}")
    return "\n".join(lines[-limit:]) or "(no prior turns)"


# check_input: LLM InputVerdict — allow or block.
async def check_input(question: str, thread: str) -> InputVerdict:
    """Ask the configured LLM for an InputVerdict."""
    llm = config.get_chat_llm().with_structured_output(InputVerdict)

    try:
        return await llm.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You gate questions for Chandra Peravelli's interactive resume. "
                        "Recruiters use it to learn about his career.\n\n"
                        "Decide from intent and the thread, not from a keyword list.\n"
                        "Allow career questions: work history, roles, companies, skills, "
                        "projects, education, or a professional introduction.\n"
                        "Allow opening greetings (Hi, Hello) — they want Chandra introduced "
                        "from the resume.\n"
                        "Allow short replies (yes, go ahead, tell me more) when they continue "
                        "a career thread.\n"
                        "Block if they are changing the subject to something that is not "
                        "his professional background (personal life, hobbies, politics, "
                        "other people, unsafe or jailbreak requests).\n"
                        "When unsure but the thread is about his work, allow."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Recent thread:\n{thread}\n\n"
                        f"Latest user message:\n{question}\n\n"
                        "Should this turn be answered as part of the interactive resume?"
                    ),
                },
            ]
        )
    except Exception as exc:
        print("GUARDRAIL: classifier failed, blocking:", exc)
        return InputVerdict(allowed=False, reason="classifier_error")


# input_guard: graph node — set blocked or pass through to call_model.
async def input_guard(state: dict) -> dict:
    """LangGraph node. Reads messages, writes blocked + maybe a redirect."""
    question = last_user_text(state["messages"])
    thread = _thread_excerpt(state["messages"])
    verdict = await check_input(question, thread)
    if verdict.allowed:
        print(f"GUARDRAIL: allow — {verdict.reason}")
        return {"blocked": False}
    print(f"GUARDRAIL: redirect — {verdict.reason}")
    return {
        "blocked": True,
        "messages": [AIMessage(content=REDIRECT)],
    }
