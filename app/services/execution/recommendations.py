from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.execution import RekCreate, RekUpdate, RekFollowupIn
from app.services.assignments import get_assignment
from app.services.logs import log_status
from app.services.execution.helpers import _WORKABLE, _REK_EDIT, _now, _row, _patch, _has_pending
from app.services.execution.findings import get_finding

_REK_SQL = """
    SELECT r.rekomend_id, r.finding_id, r.rekomend_no, r.recommendation_text, r.due_date, r.status,
           r.followup_note, r.followup_url, r.followup_by, r.followup_at, r.closed_during_audit,
           r.closed_by, r.closed_at, r.last_monitored_at, r.created_at, r.updated_at,
           f.assignment_id, f.status AS finding_status
    FROM aidaa_core.rekomend r JOIN aidaa_core.finding f ON f.finding_id = r.finding_id
"""


def get_rekomend(db: Session, rekomend_id: UUID) -> dict:
    return _row(db, f"{_REK_SQL} WHERE r.rekomend_id = CAST(:id AS uuid)",
                {"id": str(rekomend_id)}, "Recommendation not found")


def list_rekomend(db: Session, finding_id: UUID) -> list[dict]:
    get_finding(db, finding_id)
    rows = db.execute(text(f"{_REK_SQL} WHERE r.finding_id = CAST(:f AS uuid) ORDER BY r.rekomend_no"),
                      {"f": str(finding_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def _rek_editable(db: Session, finding_id: UUID, finding_status: str):
    if finding_status not in _REK_EDIT or _has_pending(db, "finding", finding_id):
        raise HTTPException(status_code=409, detail="Recommendations cannot be changed at this finding stage")


def create_rekomend(db: Session, finding_id: UUID, payload: RekCreate, user_id: UUID) -> dict:
    f = get_finding(db, finding_id)
    _rek_editable(db, finding_id, f["status"])
    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.rekomend
                (finding_id, rekomend_no, recommendation_text, due_date, created_by, updated_by)
            VALUES (CAST(:f AS uuid),
                    'R-' || lpad(CAST((SELECT COALESCE(MAX(CAST(NULLIF(regexp_replace(rekomend_no, '[^0-9]', '', 'g'), '') AS int)), 0) + 1
                                       FROM aidaa_core.rekomend WHERE finding_id = CAST(:f AS uuid)) AS text), 3, '0'),
                    :t, :d, CAST(:u AS uuid), CAST(:u AS uuid))
            RETURNING rekomend_id
        """), {"f": str(finding_id), "t": payload.recommendation_text, "d": payload.due_date,
               "u": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Recommendation number clash, please retry")
    return get_rekomend(db, row.rekomend_id)


def update_rekomend(db: Session, rekomend_id: UUID, payload: RekUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    r = get_rekomend(db, rekomend_id)
    if r["status"] != "open":
        raise HTTPException(status_code=409, detail="Only an open recommendation can be edited")
    _rek_editable(db, r["finding_id"], r["finding_status"])
    _patch(db, "aidaa_core.rekomend", "rekomend_id", rekomend_id, data, user_id)
    return get_rekomend(db, rekomend_id)


def followup_rekomend(db: Session, rekomend_id: UUID, payload: RekFollowupIn, user_id: UUID) -> dict:
    r = get_rekomend(db, rekomend_id)
    if r["finding_status"] not in ("responded", "open") or r["status"] not in ("open", "in_progress"):
        raise HTTPException(status_code=409, detail="Follow-up is not possible at this stage")
    _patch(db, "aidaa_core.rekomend", "rekomend_id", rekomend_id,
           {"followup_note": payload.followup_note, "followup_url": payload.followup_url,
            "followup_by": user_id, "followup_at": _now(), "status": "in_progress"}, user_id)
    return get_rekomend(db, rekomend_id)


def close_rekomend(db: Session, rekomend_id: UUID, user_id: UUID) -> dict:
    r = get_rekomend(db, rekomend_id)
    if r["status"] != "in_progress":
        raise HTTPException(status_code=409, detail="The auditee follow-up is required before closing")
    if r["finding_status"] != "open":
        raise HTTPException(status_code=409, detail="The finding must be resolved (open) before closing recommendations")
    a = get_assignment(db, r["assignment_id"])
    _patch(db, "aidaa_core.rekomend", "rekomend_id", rekomend_id,
           {"status": "closed", "closed_by": user_id, "closed_at": _now(),
            "closed_during_audit": a["status"] in _WORKABLE}, user_id)
    left = db.execute(text("""
        SELECT 1 FROM aidaa_core.rekomend
        WHERE finding_id = CAST(:f AS uuid) AND status <> 'closed' LIMIT 1
    """), {"f": str(r["finding_id"])}).fetchone()
    if not left:
        _patch(db, "aidaa_core.finding", "finding_id", r["finding_id"], {"status": "closed"}, user_id)
        log_status(db, "finding", r["finding_id"], "open", "closed", user_id)
    return get_rekomend(db, rekomend_id)


def monitor_rekomend(db: Session, rekomend_id: UUID, user_id: UUID) -> dict:
    r = get_rekomend(db, rekomend_id)
    if r["status"] == "closed":
        raise HTTPException(status_code=409, detail="Recommendation is already closed")
    _patch(db, "aidaa_core.rekomend", "rekomend_id", rekomend_id, {"last_monitored_at": _now()}, user_id)
    return get_rekomend(db, rekomend_id)