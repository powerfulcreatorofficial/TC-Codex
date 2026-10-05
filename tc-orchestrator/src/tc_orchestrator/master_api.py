"""Small FastAPI router for the TC master/delegation surface."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .master import TCMaster


router = APIRouter(prefix="/v1/master", tags=["master"])
_master = TCMaster.create()


class DelegationRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=12000)
    workspace: str = "."


@router.get("/capabilities")
def capabilities() -> dict:
    return {"capabilities": _master.capabilities()}


@router.post("/delegate")
def delegate(req: DelegationRequest) -> dict:
    report = _master.delegate(req.objective, req.workspace)
    return {
        "objective": report.objective,
        "delegated_task_id": report.delegated_task_id,
        "worker": report.worker,
        "evidence": [e.__dict__ for e in report.evidence],
        "notes": report.notes,
    }
