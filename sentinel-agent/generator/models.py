"""Shared event schema — generator and FastAPI import this."""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

class Event(BaseModel):
    """One log, metric, auth, or IAM row the later graphs will retrieve."""

    timestamp: datetime
    service: str
    severity: Literal["debug", "error", "warn", "info"]
    kind: Literal["log", "metric", "auth", "iam"]
    message: str
    attrs: dict[str, Any] = Field(default_factory=dict)