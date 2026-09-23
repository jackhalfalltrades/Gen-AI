"""GET /health, POST /events, POST /investigate, GET /cases, POST decision."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.investigate import decide_case, start_case
from api import db
from generator.models import Event


class Accepted(BaseModel):
    id: int
    accepted: bool = True


class InvestigateIn(BaseModel):
    alert: str
    kind: Literal["incident", "security"] | None = None


class CaseOut(BaseModel):
    case_id: str
    status: str
    kind: str | None
    root_cause: str
    report: str
    approved: bool | None
    decided_by: str | None = None


class CaseRecord(CaseOut):
    alert: str
    created_at: str | None = None
    updated_at: str | None = None


class DecisionIn(BaseModel):
    approved: bool
    decided_by: str = "operator"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        db.init_schema()
    except Exception as exc:
        print("api: schema init skipped:", exc)
    yield


app = FastAPI(title="Sentinel - Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/events", response_model=Accepted)
def post_event(event: Event) -> Accepted:
    try:
        event_id = db.insert_event(event)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"postgres: {exc}") from exc
    return Accepted(id=event_id)


@app.post("/investigate", response_model=CaseOut)
def post_investigate(body: InvestigateIn) -> CaseOut:
    try:
        return CaseOut(**start_case(body.alert, kind=body.kind))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/investigate/{case_id}/decision", response_model=CaseOut)
def post_decision(case_id: str, body: DecisionIn) -> CaseOut:
    try:
        return CaseOut(
            **decide_case(case_id, approved=body.approved, decided_by=body.decided_by)
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown case {case_id}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/cases", response_model=list[CaseRecord])
def get_cases() -> list[CaseRecord]:
    try:
        return [CaseRecord(**row) for row in db.list_cases()]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"postgres: {exc}") from exc


@app.get("/cases/{case_id}", response_model=CaseRecord)
def get_case(case_id: str) -> CaseRecord:
    try:
        row = db.get_case(case_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"postgres: {exc}") from exc
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown case {case_id}")
    return CaseRecord(**row)
