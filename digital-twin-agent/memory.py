"""
memory.py — short window + LLM compact + long-term vectors.

Three layers, on purpose
    1. Live list (max_messages): follow-ups like "what about there?" work
       because the last turns are still real Human/AI/Tool messages.
    2. Running summary: when the list overflows, compact_memory folds
       the oldest turns into a paragraph we keep as a SystemMessage.
    3. session_memory (pgvector): that paragraph is also embedded.
       Later questions similarity-search it — so a fact from turn 2 can
       come back on turn 30 without sitting in the prompt the whole time.

session_memory is a *different collection* than profile (resume RAG).
Same Postgres, different job.
"""

import asyncio

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

import config
from rag import pg_init_lock
from tools import compact_memory

# Prefixes let _is_meta() strip our own bookkeeping messages so we do
# not compact the compact, and so we do not count them toward the window.
SUMMARY_PREFIX = "[Conversation memory]"
RECALL_PREFIX = "[Recalled earlier conversation]"

_embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL, api_key=config.OPENAI_API_KEY)

# Same langchain_postgres MetaData race as rag.py — cache one store.
_store: PGVector | None = None


# _session_store: one cached pgvector collection "session_memory".
def _session_store() -> PGVector:
    """
    Reuse one PGVector for compacted chat (not resume).

    Same DATABASE_URL as rag.py, different collection_name so a memory
    write can never pollute profile retrieval. Locked so parallel
    remember/recall threads do not redefine langchain_pg_collection.
    """
    global _store
    if _store is None:
        with pg_init_lock:
            if _store is None:
                _store = PGVector(
                    embeddings=_embeddings,
                    collection_name="session_memory",
                    connection=config.DATABASE_URL,
                    use_jsonb=True,
                )
    return _store


# _remember_sync: blocking insert used by remember() in a worker thread.
def _remember_sync(text: str) -> None:
    """Blocking insert. Called from remember() via asyncio.to_thread."""
    _session_store().add_documents(
        [Document(page_content=text, metadata={"type": "compacted"})]
    )


# remember: embed one compacted summary without blocking the event loop.
async def remember(text: str) -> None:
    """Write one compacted summary into session_memory (thread offload)."""
    text = (text or "").strip()
    if not text:
        return
    await asyncio.to_thread(_remember_sync, text)
    print("MEMORY: stored summary in session_memory (pgvector)")


# _recall_sync: blocking similarity search used by recall() in a worker thread.
def _recall_sync(query: str, k: int) -> list:
    """Blocking similarity search. Called from recall() via asyncio.to_thread."""
    return _session_store().similarity_search_with_score(query, k=k)


# recall: vector-search older compacted turns for this user question.
async def recall(query: str, k: int = 3) -> str:
    """
    Vector-search older compacted turns.

    Empty string if the collection does not exist yet (first session)
    or Postgres is down — chat still works from the live window.
    """
    try:
        hits = await asyncio.to_thread(_recall_sync, query, k)
    except Exception as exc:
        print("MEMORY: recall skipped:", exc)
        return ""
    if not hits:
        return ""
    print(f"MEMORY: recalled {len(hits)} vector hit(s)")
    return "\n".join(doc.page_content for doc, _score in hits)


# _is_meta: True for our summary/recall SystemMessages (not the policy prompt).
def _is_meta(message: BaseMessage) -> bool:
    """True for the system notes *we* inject (summary / recall), not the policy prompt."""
    if not isinstance(message, SystemMessage):
        return False
    return message.content.startswith(SUMMARY_PREFIX) or message.content.startswith(
        RECALL_PREFIX
    )


# _format_messages: truncate overflow so compact_memory stays cheap.
def _format_messages(messages: list[BaseMessage]) -> str:
    """Truncated dump so compact_memory does not get a 20k-token overflow blob."""
    lines = []
    for message in messages:
        content = getattr(message, "content", "") or ""
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"{type(message).__name__}: {content}")
    return "\n".join(lines)


# CompactSession: Gradio-held window — system prompt + summary + last N turns.
class CompactSession:
    """
    Gradio holds one of these in gr.State.

    Rebuild order is always:
        [system prompt] + optional [summary] + last N real messages
    so the model never loses identity when we drop overflow.
    """

    # __init__: start with policy prompt only; summary fills in after overflow.
    def __init__(self, system_prompt: str, max_messages: int = 8):
        """
        Start a thread with only the policy prompt.

        max_messages is the live window (not counting system / summary /
        recall notes). 8 is enough for a follow-up without burning tokens.
        """
        self.system_prompt = system_prompt
        self.max_messages = max_messages
        self.summary = ""
        self.messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]

    # add: append, maybe recall old facts, then compact the window.
    async def add(self, message: BaseMessage) -> None:
        """
        Append one message, optionally recall old facts, then compact.

        Recall runs only on HumanMessage and only after we already have
        a summary — otherwise there is nothing in session_memory yet.
        """
        if isinstance(message, HumanMessage) and self.summary:
            recalled = await recall(message.content)
            if recalled:
                self.messages.append(
                    SystemMessage(content=f"{RECALL_PREFIX}\n{recalled}")
                )
        self.messages.append(message)
        await self._compact()

    # get_messages: copy of the current window for graph.ainvoke.
    def get_messages(self) -> list[BaseMessage]:
        """Copy of the current window — graph.ainvoke must not mutate this list."""
        return list(self.messages)

    # replace: take LangGraph's list after a pass and re-apply the window.
    async def replace(self, messages: list[BaseMessage]) -> None:
        """After a graph pass, take LangGraph's list and re-apply the window."""
        self.messages = list(messages)
        await self._compact()

    # _rebuild: [policy] + optional [summary] + kept tail.
    def _rebuild(self, kept: list[BaseMessage]) -> None:
        """
        Replace self.messages with [policy] + optional [summary] + kept.

        Always rewrite the policy SystemMessage so a compact pass cannot
        drop identity even if kept is empty.
        """
        system = SystemMessage(content=self.system_prompt)
        extra: list[BaseMessage] = []
        if self.summary:
            extra.append(SystemMessage(content=f"{SUMMARY_PREFIX}\n{self.summary}"))
        self.messages = [system] + extra + kept

    # _compact: if over max_messages, summarize overflow and keep the tail.
    async def _compact(self) -> None:
        """
        If the live list is over max_messages: summarize the overflow,
        embed it, keep only the tail.

        No-op when the window still fits — cheap path for the first turns.
        """
        # Drop the leading system prompt and our meta notes before counting.
        rest = [m for m in self.messages[1:] if not _is_meta(m)]
        if len(rest) <= self.max_messages:
            self._rebuild(rest)
            return

        overflow = rest[: -self.max_messages]
        kept = rest[-self.max_messages :]
        # A ToolMessage with no preceding AI tool_call confuses the next
        # provider call. Slide the window until kept starts cleanly.
        while kept and isinstance(kept[0], ToolMessage):
            kept = kept[1:]

        print(f"MEMORY: compacting {len(overflow)} overflow message(s) via LLM tool")
        self.summary = await compact_memory.ainvoke(
            {
                "existing_summary": self.summary or "(none yet)",
                "new_messages": _format_messages(overflow),
            }
        )
        await remember(self.summary)
        self._rebuild(kept)
