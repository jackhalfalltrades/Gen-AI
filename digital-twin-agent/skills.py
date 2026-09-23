"""
skills.py — the #skills channel.

This is a graph *node*, not a chat turn. after_start routes here and
we go straight to END. That is why the reply is a categorized list
instead of "Sure, here are some of my skills…".

Flow
    1. Several RAG queries over resume + LinkedIn (same helper as tools).
    2. Structured SkillInventory (Pydantic) — category → names.
    3. Format as Slack-style markdown (bold heading + middot list).
       We tried a markdown table; it looked like a spreadsheet in chat.

The prompt forbids spoken languages under "Languages" so Hindi/Tamil
do not sit next to Java. Contact info and company names are skipped
unless they are actually tools.
"""

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

import config
from tools import _hits_to_text


# SkillGroup: one category bucket, e.g. Languages → [Java, Kotlin, Python].
class SkillGroup(BaseModel):
    """One category bucket, e.g. Languages → [Java, Kotlin, Python]."""

    category: str = Field(description="Category name, e.g. Languages, Frameworks, AI, or Cloud.")
    skills: list[str] = Field(description="Skill names that appear in the evidence.")


# SkillInventory: full categorized inventory the #skills node fills.
class SkillInventory(BaseModel):
    """Full categorized inventory the #skills node asks the LLM to fill."""

    groups: list[SkillGroup] = Field(description="Skills grouped by category.")


# _format_skills: Slack markdown — bold category, middot-separated names.
def _format_skills(inventory: SkillInventory) -> str:
    """Turn structured groups into the bubble the recruiter reads."""
    blocks = [
        "**# skills**",
        "Grounded on Chandra’s resume and profile.",
        "",
        "**Skills from Chandra’s resume and LinkedIn**",
        "",
    ]
    for group in inventory.groups:
        names = [s.strip() for s in group.skills if s.strip()]
        if not names:
            continue
        blocks.append(f"**{group.category}**")
        blocks.append(" · ".join(names))
        blocks.append("")
    return "\n".join(blocks).strip()


# list_skills: graph node — RAG, structured inventory, formatted bubble.
async def list_skills(state: dict) -> dict:
    """LangGraph node: RAG then LLM categorize. No chat model, no evaluator."""
    print("GRAPH: list_skills")
    # Four queries so we do not miss a section that embeds poorly
    # against a single "skills" string.
    evidence = await _hits_to_text(
        "technical skills programming languages",
        "frameworks libraries platforms",
        "Kafka Java Python cloud AWS GCP Kubernetes Docker",
        "LinkedIn skills certifications tools",
        k=5,
    )
    llm = config.get_chat_llm().with_structured_output(SkillInventory)
    inventory = await llm.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "Extract Chandra Peravelli's skills from resume and LinkedIn text. "
                    "Use only skills that appear in the evidence. Do not invent. "
                    "Group them into sensible categories (languages, frameworks, "
                    "data/streaming, cloud/DevOps, tools, etc.). Deduplicate. "
                    "Programming languages only under Languages — skip spoken "
                    "languages. Skip contact info and company names unless they are tools."
                ),
            },
            {
                "role": "user",
                "content": f"Evidence:\n{evidence}",
            },
        ]
    )
    return {"messages": [AIMessage(content=_format_skills(inventory))]}
