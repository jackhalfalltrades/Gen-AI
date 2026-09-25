"""API/CLI wrapper around the graph. Not a chat loop.

start_case runs until the interrupt. decide_case resumes it. investigate()
auto-approves so eval and `python -m agent.investigate` do not hang.
The cases table is the durable list; the checkpointer is how we resume.
"""

import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from agent.graph import get_graph
from api import db


def root_cause_line(report: str) -> str:
    """Last ROOT_CAUSE: line. Eval grades this, not the whole narrative."""
    for line in reversed(report.splitlines()):
        if line.startswith("ROOT_CAUSE:"):
            return line.split(":", 1)[1].strip()
    return report.strip()


def _report(messages) -> str:
    """Print tool previews + investigator text. Skip analyst SystemMessages.

    The human-facing report is the last AIMessage with content — that is the
    investigator, not the analyst.
    """
    last_text = ""
    for message in messages:
        if isinstance(message, ToolMessage):
            raw = message.content if isinstance(message.content, str) else str(message.content)
            preview = raw if len(raw) <= 240 else raw[:240] + f"... ({len(raw)} chars)"
            print(f"tool {message.name}: {preview}")
        elif isinstance(message, AIMessage) and message.content:
            last_text = message.content
            print(message.content)
    return last_text


def _thread(case_id: str) -> dict:
    """LangGraph thread_id. Same string as cases.id so resume finds the case."""
    return {"configurable": {"thread_id": case_id}}


def _interrupt_value(case_id: str):
    """Payload from await_approval, or None if the graph is not paused."""
    snap = get_graph().get_state(_thread(case_id))
    if not snap.next:
        return None
    for task in snap.tasks:
        for item in task.interrupts:
            return item.value
    return {}


def _alert_from_messages(messages) -> str:
    """Recover the alert if the cases row is missing (started before persist)."""
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return message.content or ""
    return ""


def _persist(case: dict, *, alert: str, decided_by: str | None = None) -> dict:
    """Write the cases row. Checkpoint is separate; this is what GET /cases lists."""
    db.upsert_case(
        case["case_id"],
        alert=alert,
        status=case["status"],
        kind=case.get("kind"),
        root_cause=case.get("root_cause"),
        report=case.get("report"),
        approved=case.get("approved"),
        decided_by=decided_by,
    )
    case["decided_by"] = decided_by
    return case


def start_case(alert: str, kind: str | None = None) -> dict:
    """Run the graph until it interrupts (or finishes without a pause).

    kind=None lets route_kind decide. analyst_rounds starts at 0 so the first
    draft always goes to the analyst before a human sees it.
    """
    case_id = str(uuid.uuid4())
    graph = get_graph()
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=alert)],
            "kind": kind,
            "approved": None,
            "analyst_rounds": 0,
            "analyst_verdict": None,
        },
        _thread(case_id),
    )
    report = _report(result["messages"])
    resolved = result.get("kind") or kind
    pending = _interrupt_value(case_id)
    if pending is not None:
        case = {
            "case_id": case_id,
            "status": "pending_approval",
            "kind": pending.get("kind") or resolved,
            "root_cause": pending.get("root_cause") or root_cause_line(report),
            "report": report,
            "approved": None,
        }
    else:
        case = {
            "case_id": case_id,
            "status": "completed",
            "kind": resolved,
            "root_cause": root_cause_line(report),
            "report": report,
            "approved": result.get("approved"),
        }
    return _persist(case, alert=alert)


def decide_case(case_id: str, approved: bool, decided_by: str = "operator") -> dict:
    """Resume the interrupt. This is the only place a case is accepted or rejected."""
    graph = get_graph()
    snap = graph.get_state(_thread(case_id))
    if snap.values is None or not snap.values:
        raise KeyError(case_id)
    if not snap.next:
        raise ValueError(f"case {case_id} is not waiting for approval")
    result = graph.invoke(Command(resume={"approved": approved}), _thread(case_id))
    report = _report(result["messages"])
    existing = db.get_case(case_id)
    alert = (existing or {}).get("alert") or _alert_from_messages(snap.values.get("messages"))
    case = {
        "case_id": case_id,
        "status": "accepted" if approved else "rejected",
        "kind": result.get("kind"),
        "root_cause": root_cause_line(report),
        "report": report,
        "approved": approved,
    }
    return _persist(case, alert=alert, decided_by=decided_by)


def investigate(alert: str, kind: str | None = None) -> str:
    """CLI / eval: full run with auto-approve so the harness does not wait on stdin."""
    case = start_case(alert, kind=kind)
    if case["status"] == "pending_approval":
        case = decide_case(case["case_id"], approved=True)
    return case["report"]


if __name__ == "__main__":
    print(investigate("checkout p99 is high", kind="incident"))
