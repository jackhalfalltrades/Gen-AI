"""Where events go. JsonlSink now; KafkaSink later implements the same protocol."""

from pathlib import Path
from typing import Protocol

from generator.models import Event


class Sink(Protocol):
    """Write one Event. Add KafkaSink later without changing emit()."""

    def write(self, event: Event) -> None: ...

    def close(self) -> None: ...


class JsonlSink:
    """One JSON object per line under data/generated/<scenario>.jsonl."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._fh = path.open("w", encoding="utf-8")

    def write(self, event: Event) -> None:
        self._fh.write(event.model_dump_json() + "\n")

    def close(self) -> None:
        self._fh.close()
