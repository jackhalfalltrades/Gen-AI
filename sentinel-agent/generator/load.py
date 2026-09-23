"""JSONL under data/generated/ → Postgres events."""

from pathlib import Path

import config
from api import db
from generator.models import Event


def load_file(path: Path) -> int:
    n = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        db.insert_event(Event.model_validate_json(line))
        n += 1
    return n


def load_all(out_dir: Path | None = None) -> int:
    db.init_schema()
    root = out_dir or config.OUT_DIR
    total = 0
    for path in sorted(root.glob("*.jsonl")):
        total += load_file(path)
    return total


def load_scenario(scenario_id: str, out_dir: Path | None = None) -> int:
    db.init_schema()
    path = (out_dir or config.OUT_DIR) / f"{scenario_id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(path)
    return load_file(path)
