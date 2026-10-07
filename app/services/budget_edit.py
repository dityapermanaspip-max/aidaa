from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.budget import BudgetLineUpdate
from app.services.masters import _update_row
from app.services.budget_core import LINE_COLS, get_line
from app.services.budget_plan import editable_plan
from app.services.budget_assignment import draft_assignment


def _assert_line_writable(db: Session, line: dict, user_id: UUID):
    if line["trip_leg_id"]:
        raise HTTPException(status_code=409, detail="Trip leg lines follow the leg estimate, edit the leg instead")
    if line["plan_id"]:
        version = editable_plan(db, line["plan_id"], user_id)
        if line["version_no"] != version:
            raise HTTPException(status_code=409, detail="Only lines of the draft version can be changed")
    else:
        draft_assignment(db, line["assignment_id"], user_id)


def update_line(db: Session, line_id: UUID, payload: BudgetLineUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    line = get_line(db, line_id)
    _assert_line_writable(db, line, user_id)
    if "unit_rate" in data and line["basis"] != "at_cost":
        raise HTTPException(status_code=400, detail="unit_rate is fixed by the approved rate for standard lines")
    return _update_row(db, "aidaa_core.budget_line", "line_id", line_id, data, set(), user_id, LINE_COLS)


def delete_line(db: Session, line_id: UUID, user_id: UUID) -> dict:
    line = get_line(db, line_id)
    _assert_line_writable(db, line, user_id)
    db.execute(text("DELETE FROM aidaa_core.budget_line WHERE line_id = CAST(:id AS uuid)"),
               {"id": str(line_id)})
    return line