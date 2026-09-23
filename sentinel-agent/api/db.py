"""Postgres events + cases. No Alembic — CREATE IF NOT EXISTS on startup."""

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

import config
from generator.models import Event

DATABASE_URL = config.DATABASE_URL

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id          bigserial PRIMARY KEY,
    timestamp   timestamptz NOT NULL,
    service     text NOT NULL,
    severity    text NOT NULL,
    kind        text NOT NULL,
    message     text NOT NULL,
    attrs       jsonb NOT NULL DEFAULT '{}'::jsonb
);
"""

_CREATE_CASES = """
CREATE TABLE IF NOT EXISTS cases (
    id            text PRIMARY KEY,
    alert         text NOT NULL,
    kind          text,
    status        text NOT NULL,
    root_cause    text,
    report        text,
    approved      boolean,
    decided_by    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
"""

_INSERT = """
INSERT INTO events (timestamp, service, severity, kind, message, attrs)
VALUES (%s, %s, %s, %s, %s, %s::jsonb)
RETURNING id;
"""

_UPSERT_CASE = """
INSERT INTO cases (id, alert, kind, status, root_cause, report, approved, decided_by)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    kind = COALESCE(EXCLUDED.kind, cases.kind),
    status = EXCLUDED.status,
    root_cause = COALESCE(EXCLUDED.root_cause, cases.root_cause),
    report = COALESCE(EXCLUDED.report, cases.report),
    approved = EXCLUDED.approved,
    decided_by = COALESCE(EXCLUDED.decided_by, cases.decided_by),
    updated_at = now()
"""

_GET_CASE = """
SELECT id, alert, kind, status, root_cause, report, approved, decided_by, created_at, updated_at
FROM cases
WHERE id = %s
"""

_LIST_CASES = """
SELECT id, alert, kind, status, root_cause, report, approved, decided_by, created_at, updated_at
FROM cases
ORDER BY created_at DESC
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


def init_schema() -> None:
    with connect() as conn:
        conn.execute(_CREATE_EVENTS)
        conn.execute(_CREATE_CASES)
        conn.commit()


def _case_from_row(row: dict) -> dict:
    created = row.get("created_at")
    updated = row.get("updated_at")
    return {
        "case_id": row["id"],
        "alert": row["alert"],
        "kind": row.get("kind"),
        "status": row["status"],
        "root_cause": row.get("root_cause") or "",
        "report": row.get("report") or "",
        "approved": row.get("approved"),
        "decided_by": row.get("decided_by"),
        "created_at": created.isoformat() if isinstance(created, datetime) else created,
        "updated_at": updated.isoformat() if isinstance(updated, datetime) else updated,
    }


def insert_event(event: Event) -> int:
    import json

    with connect() as conn:
        row = conn.execute(
            _INSERT,
            (
                event.timestamp,
                event.service,
                event.severity,
                event.kind,
                event.message,
                json.dumps(event.attrs),
            ),
        ).fetchone()
        conn.commit()
    return int(row[0])


def upsert_case(
    case_id: str,
    *,
    alert: str,
    status: str,
    kind: str | None = None,
    root_cause: str | None = None,
    report: str | None = None,
    approved: bool | None = None,
    decided_by: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            _UPSERT_CASE,
            (case_id, alert, kind, status, root_cause, report, approved, decided_by),
        )
        conn.commit()


def get_case(case_id: str) -> dict | None:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        row = conn.execute(_GET_CASE, (case_id,)).fetchone()
        conn.commit()
    if row is None:
        return None
    return _case_from_row(row)


def list_cases() -> list[dict]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(_LIST_CASES).fetchall()
        conn.commit()
    return [_case_from_row(row) for row in rows]
