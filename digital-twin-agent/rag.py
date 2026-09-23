"""
rag.py — parse → chunk → embed → pgvector → top-k.

Goal
    Never send the whole resume on every question. Retrieve only the
    chunks that match this query.

Pipeline
    data/*.pdf (and .txt / .md)
           ↓  pypdf / file read
        LangChain Documents  (source + page in metadata)
           ↓  RecursiveCharacterTextSplitter
        chunks (~TOKEN_CHUNKS, 150-token overlap)
           ↓  OpenAIEmbeddings (EMBEDDING_MODEL)
        Postgres collection "profile"
           ↓  similarity_search_with_score
        top-k (doc, score) for tools.py / skills / experience

LangChain is used *here* (loaders + splitters + vector store), not as a
wrapper around the whole app.

Caveat: ingest() appends. Re-run rag.py without wiping the twin_pg
volume and you get duplicate chunks. docker compose down -v to reset.
"""

import asyncio
import glob
import os
import threading

from config import TOKEN_CHUNKS, DATA_DIR, DATABASE_URL, EMBEDDING_MODEL, OPENAI_API_KEY
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Same embedding model that built the index must be used at query time
# or similarity scores are meaningless.
_embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)

# langchain_postgres registers SQLAlchemy tables on a process-wide MetaData.
# asyncio.gather + to_thread used to construct a new PGVector per query and
# raced: "Table 'langchain_pg_collection' is already defined".
# Shared with memory.py so profile + session_memory never init together.
pg_init_lock = threading.Lock()
_store: PGVector | None = None


# _get_store: one cached pgvector collection "profile" (not chat memory).
def _get_store() -> PGVector:
    """
    Reuse one PGVector for collection "profile".

    Construction is locked so parallel retrieve() threads cannot each
    define langchain_pg_collection on the same MetaData.
    """
    global _store
    if _store is None:
        with pg_init_lock:
            if _store is None:
                _store = PGVector(
                    embeddings=_embeddings,
                    collection_name="profile",
                    connection=DATABASE_URL,
                    use_jsonb=True,
                )
    return _store


# load_documents: PDFs (one Document per page) plus .txt / .md files.
def load_documents(data_dir) -> list:
    """
    One Document per PDF page (page number in metadata) and one per
    text/markdown file. Page-level docs keep citations/debug logs useful.
    """
    documents: list[Document] = []

    pdf_files = sorted(glob.glob(os.path.join(data_dir, "*.pdf")))
    for pdf_file in pdf_files:
        reader = PdfReader(pdf_file)
        for i, page in enumerate(reader.pages):
            documents.append(
                Document(
                    page_content=page.extract_text() or "",
                    metadata={"source": pdf_file, "page": i},
                )
            )

    text_files = sorted(
        glob.glob(os.path.join(data_dir, "*.txt"))
        + glob.glob(os.path.join(data_dir, "*.md"))
    )
    for text_file in text_files:
        with open(text_file, "r", encoding="utf-8") as f:
            content = f.read()
        documents.append(
            Document(page_content=content, metadata={"source": text_file})
        )

    return documents


# chunk_documents: split with TOKEN_CHUNKS and 150-token overlap.
def chunk_documents(documents: list) -> list:
    """
    800 / 150 is the default we ship. Overlap keeps a job title that
    sits on a split boundary from disappearing from both chunks.
    Try 500 / 800 / 1200 and re-run retrieve("Kafka") to compare.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=TOKEN_CHUNKS, chunk_overlap=150)
    return splitter.split_documents(documents)


# ingest: embed chunks and insert into the profile collection.
def ingest() -> int:
    """Embed and insert. Returns how many chunks were written this run."""
    documents = load_documents(DATA_DIR)
    store = _get_store()
    chunks = chunk_documents(documents)
    store.add_documents(chunks)
    return len(chunks)


# retrieve_sync: blocking embed + similarity search (CLI / to_thread).
def retrieve_sync(query: str, k: int = 5) -> list:
    """Blocking retrieve. Used by the CLI and wrapped by retrieve()."""
    store = _get_store()
    return store.similarity_search_with_score(query, k=k)


# retrieve: async wrapper — offloads retrieve_sync so the event loop stays free.
async def retrieve(query: str, k: int = 5) -> list:
    """
    Offload embed + pgvector to a worker thread.

    langchain_postgres has no async search. to_thread keeps the event
    loop free so other recruiter requests can wait on OpenAI at the same time.
    """
    return await asyncio.to_thread(retrieve_sync, query, k)


if __name__ == "__main__":
    n = ingest()
    print("ingested chunks:", n)
    for doc, score in retrieve_sync("Kafka", k=3):
        print(score, doc.metadata.get("source"))
        print(doc.page_content[:300])
        print("---")
