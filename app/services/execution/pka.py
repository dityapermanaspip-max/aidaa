from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.execution import ExePkaCreate, ExePkaUpdate
from app.services.assignments import get_assignment
from app.services.logs import log_status, log_comment
from app.services.scope import root_of_org
from app.services.execution.helpers import (
    _PREP, _now, _row, _patch, _assignment_open, _assert_member, _open_review,
)

_PKA_COLS = ("pka_id, assignment_id, library_pka_id, pka_code, title, objective, assigned_auditor_id, "
             "planned_hours, actual_hours, status, is_skipped, skip_reason, source, approved_by, "
             "approved_at, created_by, created_at, updated_at")


def get_pka(db: Session, pka_id: UUID) -> dict:
    return _row(db, f"SELECT {_PKA_COLS} FROM aidaa_core.pka WHERE pka_id = CAST(:id AS uuid)",
                {"id": str(pka_id)}, "PKA not found")


def list_pka(db: Session, assignment_id: UUID) -> list[dict]:
    get_assignment(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {_PKA_COLS} FROM aidaa_core.pka WHERE assignment_id = CAST(:a AS uuid)
        ORDER BY pka_code NULLS LAST, created_at
    """), {"a": str(assignment_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def copy_library(db: Session, assignment_id: UUID, library_pka_ids, user_id: UUID) -> list[dict]:
    a = _assignment_open(db, assignment_id, _PREP)
    ids = [str(i) for i in library_pka_ids] if library_pka_ids else None
    libs = db.execute(text("""
        SELECT l.library_pka_id, l.pka_code, l.title, l.objective,
               COALESCE((SELECT SUM(p.estimated_hours) FROM aidaa_core.library_procedure p
                         WHERE p.library_pka_id = l.library_pka_id AND p.is_active = TRUE), 0) AS procedure_hours
        FROM aidaa_core.library_pka l
        WHERE l.is_active = TRUE AND l.root_org_id = CAST(:root AS uuid)
          AND (CAST(:ids AS uuid[]) IS NULL OR l.library_pka_id = ANY(CAST(:ids AS uuid[])))
          AND (CAST(:ids AS uuid[]) IS NOT NULL OR l.type_id = CAST(:t AS uuid))
          AND NOT EXISTS (SELECT 1 FROM aidaa_core.pka k
                          WHERE k.assignment_id = CAST(:a AS uuid) AND k.library_pka_id = l.library_pka_id)
        ORDER BY l.pka_code
    """), {"ids": ids, "t": str(a["type_id"]), "a": str(assignment_id),
           "root": str(root_of_org(db, a["owner_org_id"]))}).fetchall()
    if not libs:
        raise HTTPException(status_code=409, detail="Nothing to copy, library PKA are missing or already copied")
    for l in libs:
        k = db.execute(text("""
            INSERT INTO aidaa_core.pka
                (assignment_id, library_pka_id, pka_code, title, objective, planned_hours, source,
                 created_by, updated_by)
            VALUES (CAST(:a AS uuid), CAST(:l AS uuid), :code, :title, :obj, :hrs,
                    'library', CAST(:u AS uuid), CAST(:u AS uuid))
            RETURNING pka_id
        """), {"a": str(assignment_id), "l": str(l.library_pka_id), "code": l.pka_code,
               "title": l.title, "obj": l.objective, "hrs": l.procedure_hours,
               "u": str(user_id)}).fetchone()
        db.execute(text("""
            INSERT INTO aidaa_core.exe_procedure
                (pka_id, library_procedure_id, step_no, procedure_text, created_by, updated_by)
            SELECT CAST(:k AS uuid), procedure_id, step_no, procedure_text,
                   CAST(:u AS uuid), CAST(:u AS uuid)
            FROM aidaa_core.library_procedure
            WHERE library_pka_id = CAST(:l AS uuid) AND is_active = TRUE
        """), {"k": str(k.pka_id), "l": str(l.library_pka_id), "u": str(user_id)})
        log_status(db, "pka", k.pka_id, None, "draft", user_id)
    return list_pka(db, assignment_id)


def create_pka(db: Session, assignment_id: UUID, payload: ExePkaCreate, user_id: UUID) -> dict:
    _assignment_open(db, assignment_id, _PREP)
    if payload.assigned_auditor_id:
        _assert_member(db, assignment_id, payload.assigned_auditor_id)
    row = db.execute(text("""
        INSERT INTO aidaa_core.pka
            (assignment_id, pka_code, title, objective, assigned_auditor_id, planned_hours, source,
             created_by, updated_by)
        VALUES (CAST(:a AS uuid), :code, :title, :obj, CAST(:au AS uuid), :hrs, 'manual',
                CAST(:u AS uuid), CAST(:u AS uuid))
        RETURNING pka_id
    """), {"a": str(assignment_id), "code": payload.pka_code, "title": payload.title,
           "obj": payload.objective,
           "au": str(payload.assigned_auditor_id) if payload.assigned_auditor_id else None,
           "hrs": payload.planned_hours, "u": str(user_id)}).fetchone()
    log_status(db, "pka", row.pka_id, None, "draft", user_id)
    return get_pka(db, row.pka_id)


def update_pka(db: Session, pka_id: UUID, payload: ExePkaUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    p = get_pka(db, pka_id)
    if p["status"] != "draft" or p["is_skipped"]:
        raise HTTPException(status_code=409, detail="Only draft PKA can be edited")
    if data.get("assigned_auditor_id"):
        _assert_member(db, p["assignment_id"], data["assigned_auditor_id"])
    _patch(db, "aidaa_core.pka", "pka_id", pka_id, data, user_id)
    return get_pka(db, pka_id)


def set_pka_skip(db: Session, pka_id: UUID, skip: bool, reason: Optional[str], user_id: UUID) -> dict:
    p = get_pka(db, pka_id)
    if p["status"] not in ("draft", "approved", "in_progress"):
        raise HTTPException(status_code=409, detail="PKA is under review or done")
    if skip:
        if p["is_skipped"]:
            raise HTTPException(status_code=409, detail="PKA is already skipped")
        if not (reason or "").strip():
            raise HTTPException(status_code=400, detail="reason is required to skip")
        _patch(db, "aidaa_core.pka", "pka_id", pka_id, {"is_skipped": True, "skip_reason": reason}, user_id)
        log_comment(db, "pka", pka_id, f"Skipped: {reason}", user_id)
    else:
        if not p["is_skipped"]:
            raise HTTPException(status_code=409, detail="PKA is not skipped")
        _patch(db, "aidaa_core.pka", "pka_id", pka_id, {"is_skipped": False, "skip_reason": None}, user_id)
        log_comment(db, "pka", pka_id, "Skip removed", user_id)
    return get_pka(db, pka_id)


def submit_pka(db: Session, pka_id: UUID, user_id: UUID) -> dict:
    p = get_pka(db, pka_id)
    if p["is_skipped"] or p["status"] != "draft":
        raise HTTPException(status_code=409, detail="Only a draft, non-skipped PKA can be submitted")
    _assignment_open(db, p["assignment_id"], _PREP)
    _open_review(db, "pka", pka_id, p["assignment_id"], 1, "supervisor", user_id, [p["created_by"]])
    _patch(db, "aidaa_core.pka", "pka_id", pka_id, {"status": "pending"}, user_id)
    log_status(db, "pka", pka_id, "draft", "pending", user_id)
    return get_pka(db, pka_id)


def complete_pka(db: Session, pka_id: UUID, actual_hours, user_id: UUID) -> dict:
    p = get_pka(db, pka_id)
    if p["is_skipped"] or p["status"] not in ("approved", "in_progress"):
        raise HTTPException(status_code=409, detail="Only an approved, non-skipped PKA can be completed")
    left = db.execute(text("""
        SELECT count(*) AS n FROM aidaa_core.exe_procedure
        WHERE pka_id = CAST(:k AS uuid) AND NOT is_skipped
          AND status NOT IN ('leader_reviewed', 'supervisor_reviewed')
    """), {"k": str(pka_id)}).fetchone().n
    if left:
        raise HTTPException(status_code=409, detail=f"{left} procedure(s) are not reviewed yet")
    cols = {"status": "done"}
    if actual_hours is not None:
        cols["actual_hours"] = actual_hours
    _patch(db, "aidaa_core.pka", "pka_id", pka_id, cols, user_id)
    log_status(db, "pka", pka_id, p["status"], "done", user_id)
    return get_pka(db, pka_id)


def _on_pka_task(db: Session, task: dict, user_id: UUID):
    p = get_pka(db, task["record_id"])
    if task.get("decision_note"):
        log_comment(db, "pka", p["pka_id"], task["decision_note"], user_id)
    if p["status"] != "pending":
        return
    if task["status"] == "approved":
        _patch(db, "aidaa_core.pka", "pka_id", p["pka_id"],
               {"status": "approved", "approved_by": user_id, "approved_at": _now()}, user_id)
        log_status(db, "pka", p["pka_id"], "pending", "approved", user_id)
    else:
        _patch(db, "aidaa_core.pka", "pka_id", p["pka_id"], {"status": "draft"}, user_id)
        log_status(db, "pka", p["pka_id"], "pending", "draft", user_id)