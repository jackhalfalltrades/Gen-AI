"""
experience.py — the #experience channel.

Same idea as skills.py: own graph node, own structured schema, own
formatter. Chat was a bad place to ask for "a good summary of my
professional experience" — the persona path wandered and the evaluator
sometimes rejected a fine overview.

Flow
    1. RAG over roles / companies / dates / accomplishments.
    2. ExperienceSummary: 2–3 sentence overview + roles newest first.
    3. Slack-style blocks: **Company** — Title, then dates, then one line.

"Do not invent" is in the prompt *and* in the Pydantic field descriptions
so the structured-output parser is steered the same way.
"""

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

import config
from tools import _hits_to_text


# Role: one job from the resume (company, title, dates, focus).
class Role(BaseModel):
    """One job from the resume. Empty dates are allowed; company+title are not."""

    company: str = Field(description="Employer name from the evidence.")
    title: str = Field(description="Job title from the evidence.")
    dates: str = Field(description="Date range if present, else empty.")
    focus: str = Field(description="One short line of what he did there.")


# ExperienceSummary: overview paragraph plus roles newest-first.
class ExperienceSummary(BaseModel):
    """Overview paragraph plus roles newest-first, all from RAG evidence."""

    overview: str = Field(
        description="2-3 sentence professional summary. No citations."
    )
    roles: list[Role] = Field(description="Roles newest first, only from evidence.")


# _format_experience: overview + per-role company / title / dates / focus.
def _format_experience(summary: ExperienceSummary) -> str:
    """
    Markdown the recruiter sees.

    Two trailing spaces before \\n is a markdown line break so
    "Cloudera — Staff Software Engineer" and the dates stay in one
    visual block without becoming a new paragraph.
    """
    blocks = [
        "**# experience**",
        "Grounded on Chandra’s resume and profile.",
        "",
        summary.overview.strip(),
        "",
    ]
    for role in summary.roles:
        company = role.company.strip()
        title = role.title.strip()
        dates = role.dates.strip()
        focus = role.focus.strip()
        if not company or not title:
            continue
        headline = f"**{company}** — {title}"
        if dates:
            headline = f"{headline}  \n{dates}"
        blocks.append(headline)
        if focus:
            blocks.append(focus)
        blocks.append("")
    return "\n".join(blocks).strip()


# list_experience: graph node — RAG, structured summary, formatted bubble.
async def list_experience(state: dict) -> dict:
    """LangGraph node: RAG then LLM summarize. No chat model, no evaluator."""
    print("GRAPH: list_experience")
    evidence = await _hits_to_text(
        "work experience roles companies titles dates",
        "Cloudera Target Best Buy Staff Software Engineer",
        "professional summary accomplishments projects",
        k=5,
    )
    llm = config.get_chat_llm().with_structured_output(ExperienceSummary)
    summary = await llm.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "Summarize Chandra Peravelli's professional experience "
                    "for a recruiter. Use only employers, titles, dates, and "
                    "accomplishments that appear in the evidence. Do not invent. "
                    "Newest role first. Keep the overview to 2-3 sentences. "
                    "Each role gets one short focus line. No [1] citations."
                ),
            },
            {
                "role": "user",
                "content": f"Evidence:\n{evidence}",
            },
        ]
    )
    return {"messages": [AIMessage(content=_format_experience(summary))]}
