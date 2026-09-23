"""
tools.py — the model asks for data; this file hits RAG.

search_profile and compact_memory are async so LangGraph ToolNode /
CompactSession can await them instead of blocking the server worker.

_hits_to_text fans out its RAG queries with asyncio.gather — a greeting
plus two fallback queries used to run one after another.
"""

import asyncio

from langchain_core.tools import tool

import config
from rag import retrieve


# _hits_to_text: parallel RAG queries, de-dupe chunks, join as one string.
async def _hits_to_text(*queries: str, k: int = 5) -> str:
    """
    Run several queries in parallel, drop duplicate page text, join the rest.

    Multiple queries exist because a greeting like "Hi" is a terrible
    embedding for "Staff Software Engineer at Cloudera". We always add
    role/skill fallbacks so the first chat turn still has evidence.
    """
    batches = await asyncio.gather(*[retrieve(query, k=k) for query in queries])
    seen: set[str] = set()
    parts: list[str] = []
    for query, hits in zip(queries, batches):
        print(f"RAG retrieve: {query!r}")
        for doc, score in hits:
            text = (doc.page_content or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            source = doc.metadata.get("source", "?")
            print(f"  [{score:.3f}] {source}: {text[:80]!r}")
            parts.append(text)
    return "\n\n".join(parts) or "No matching profile facts."


# search_profile: bound chat tool — always retrieves, never a canned bio.
@tool
async def search_profile(query: str) -> str:
    """Search Chandra's resume and profile for work history, skills, or a professional summary.

    For greetings or 'tell me about yourself', query roles, companies, and skills
    (not the words 'professional summary').
    """
    return await _hits_to_text(
        query,
        "work experience roles companies titles",
        "skills Kafka Java Python distributed systems",
        k=4,
    )


# compact_memory: LLM-summarize overflow turns. Not bound on the chat agent.
@tool
async def compact_memory(existing_summary: str, new_messages: str) -> str:
    """Fold older Digital Twin chat turns into a short running summary.

    Called by CompactSession when the window overflows — not bound on the
    career agent (the model must not decide when to compact).
    """
    print("TOOL: compact_memory (LLM summarize)")
    llm = config.get_chat_llm()
    result = await llm.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "You compress conversation history for Chandra's career digital twin. "
                    "Keep companies, roles, skills, and questions already discussed. "
                    "Be factual and short. Do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Existing summary:\n{existing_summary or '(none yet)'}\n\n"
                    f"New messages to fold in:\n{new_messages}\n\n"
                    "Return only the updated summary."
                ),
            },
        ]
    )
    return result.content
