"""Playbook lookup. Local markdown, not MCP and not RAG.

The model used to skip a search_runbooks tool and guess Prometheus names.
attach_runbook calls this as a graph node so a skill always lands in the thread.
Files under skills/ are how to search, not the expected.root_cause.
"""

from pathlib import Path

import config

SKILLS_DIR = config.PROJECT_ROOT / "skills"


def _score(query: str, text: str) -> int:
    """How many alert words (len > 2) appear in the skill title + body."""
    words = [w.lower() for w in query.replace("/", " ").replace("_", " ").split() if len(w) > 2]
    blob = text.lower()
    return sum(1 for w in words if w in blob)


def lookup_runbooks(query: str) -> str:
    """Top two matching skills, concatenated.

    Two, not one: checkout p99 can also match inventory. Zero hits: tell the
    investigator to search a concrete substring, not a metric name we do not emit.
    """
    hits: list[tuple[int, Path]] = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        body = path.read_text()
        score = _score(query, f"{path.stem} {body}")
        if score:
            hits.append((score, path))
    hits.sort(key=lambda item: item[0], reverse=True)
    if not hits:
        return (
            "No playbook matched. Try search_logs with a concrete substring "
            "(HikariPool, consumer lag, login_failed) — not Prometheus p99 names."
        )
    parts = []
    for _score_n, path in hits[:2]:
        parts.append(f"# {path.stem}\n{path.read_text().strip()}")
    return "\n\n".join(parts)
