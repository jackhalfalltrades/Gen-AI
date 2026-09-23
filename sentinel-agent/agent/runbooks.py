"""Local playbooks. Not MCP — markdown under skills/, not Postgres."""

from pathlib import Path

import config

SKILLS_DIR = config.PROJECT_ROOT / "skills"


def _score(query: str, text: str) -> int:
    words = [w.lower() for w in query.replace("/", " ").replace("_", " ").split() if len(w) > 2]
    blob = text.lower()
    return sum(1 for w in words if w in blob)


def lookup_runbooks(query: str) -> str:
    """Return up to two matching playbooks. How to search, not the root cause."""
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
