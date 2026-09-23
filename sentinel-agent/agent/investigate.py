"""One alert in, pause for approval, then ROOT_CAUSE. Not a chat."""

import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from agent.graph import get_graph
from api import db


def root_cause_line(report: str) -> str:
    for line in reversed(report.splitlines()):
        if line.startswith("ROOT_CAUSE:"):
            return line.split(":", 1)[1].strip()
    return report.strip()


def _report(messages) -> str:
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
    return {"configurable": {"thread_id": case_id}}


def _interrupt_value(case_id: str):
    snap = get_graph().get_state(_thread(case_id))
    if not snap.next:
        return None
    for task in snap.tasks:
        for item in task.interrupts:
            return item.value
    return {}


def _alert_from_messages(messages) -> str:
    for message in reversed(messages or []):
        if isinstance(message, HumanMessage):
            return message.content or ""
    return ""


def _persist(case: dict, *, alert: str, decided_by: str | None = None) -> dict:
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
    case_id = str(uuid.uuid4())
    graph = get_graph()
    result = graph.invoke(
        {"messages": [HumanMessage(content=alert)], "kind": kind, "approved": None},
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
    """CLI / eval: run the case and auto-approve so tests do not hang."""
    case = start_case(alert, kind=kind)
    if case["status"] == "pending_approval":
        case = decide_case(case["case_id"], approved=True)
    return case["report"]


if __name__ == "__main__":
    print(investigate("checkout p99 is high", kind="incident"))
