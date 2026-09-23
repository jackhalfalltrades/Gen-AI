"""Expand a scenario YAML into a timed stream of Events. No LLM."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import yaml

import config
from generator.models import Event
from generator.sinks import JsonlSink, Sink

WORLD = config.WORLD
SCENARIOS = config.SCENARIOS
OUT_DIR = config.OUT_DIR


# Background chatter so RAG/search has more than the fault lines. 
# mimics lines othen error lines in logs.
_NOISE = {
    "checkout": "GET /checkout/cart latency_ms=42",
    "payment": "auth approved last4=****",
    "inventory": "stock snapshot sku=ok",
    "fulfillment": "shipment queued dc=MSP",
    "promotions": "price quote sku rule=default",
    "login": "session issued user=ok",
}

def list_scenarios() -> list[str]:
    """Scenario file stems in world/scenarios/."""
    return sorted(p.stem for p in SCENARIOS.glob("*.yaml"))


def load_scenario(scenario_id: str) -> dict:
    """Load one YAML. Raises FileNotFoundError if the id is unknown."""
    path = SCENARIOS / f"{scenario_id}.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)

def _severity_for(kind: str, index: int) -> str:
    if kind in {"auth", "iam"}:
        return "warn"
    if kind == "metric":
        return "info"
    return "error" if index % 3 == 0 else "warn"


def expand(scenario: dict, start: datetime | None = None) -> Iterator[Event]:
    """
    ~80–140 events: noise every minute, then each signature a few times.

    attrs.scenario and attrs.expected_root_cause stay on every row so
    the eval harness can join without a second file later.
    """
    start = start or datetime.now(timezone.utc).replace(microsecond=0)
    minutes = int(scenario.get("window_minutes") or 20)
    services = list(scenario.get("services") or [])
    signatures = list(scenario.get("signatures") or [])
    expected = scenario.get("expected") or {}
    base_attrs = {
        "scenario": scenario["id"],
        "kind_of_case": scenario.get("kind"),
        "expected_root_cause": expected.get("root_cause"),
    }

    for minute in range(minutes):
        timestamp = start + timedelta(minutes=minute)
        for service in services:
            yield Event(
                timestamp=timestamp,
                service=service,
                severity="info",
                kind="log",
                message=_NOISE.get(service, f"{service} heartbeat"),
                attrs={**base_attrs, "role": "noise"},
            )
        # After minute 3 the fault is visible.
        if minute < 3:
            continue
        for i, sig in enumerate(signatures):
            kind = sig.get("kind") or "log"
            message = sig.get("pattern") or ""
            if kind == "metric" and sig.get("name"):
                message = f"{sig['name']}={sig.get('value')}"
            yield Event(
                timestamp=timestamp + timedelta(seconds=5 + i),
                service=sig.get("service") or services[0],
                severity=_severity_for(kind, minute + i),
                kind=kind,
                message=message,
                attrs={
                    **base_attrs,
                    "role": "signature",
                    "metric": sig.get("name"),
                    "metric_value": sig.get("value"),
                },
            )


def emit(scenario_id: str, sink: Sink | None = None, out_dir: Path | None = None) -> Path:
    """Write one scenario through a Sink. Returns the JSONL path for JsonlSink."""
    scenario = load_scenario(scenario_id)
    dest = (out_dir or OUT_DIR) / f"{scenario_id}.jsonl"
    own = sink is None
    sink = sink or JsonlSink(dest)
    try:
        for event in expand(scenario):
            sink.write(event)
    finally:
        if own:
            sink.close()
    return dest


def emit_all(out_dir: Path | None = None) -> list[Path]:
    """Emit every scenario file."""
    return [emit(sid, out_dir=out_dir) for sid in list_scenarios()]
