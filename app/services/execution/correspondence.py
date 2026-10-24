"""Korespondensi: document requests (A), interview schedules (C) and the berita acara penyampaian
notisi (D). Doc requests and interviews are per audited unit - list rows are filtered to the
caller's PIC orgs when the router passes a non-empty pic_orgs list (None = audit side, unfiltered).
Writes to doc requests and interviews stop once the assignment leaves _WORKABLE (submissions stop
when the audit is over). The BAP is post-audit correspondence and deliberately skips that check;
it covers the existing communicate/respond window and its recorded stance gates resolve_finding
in app/services/execution/findings.py. AIDAA stores document URLs, never the files themselves.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.execution import (
    BapCreate, BapResultIn, BapUpdate, DocReqCreate, DocReqSubmitIn, DocReqUpdate,
    InterviewCreate, InterviewUpdate,
)
from app.services.execution.helpers import _WORKABLE, _assignment_open, _now, _patch, _row
from app.services.execution.findings import get_finding
from app.services.logs import log_comment, log_status

_BAP_OK = ("communicated", "responded", "open")


# --- shared: the audited-unit whitelist ---

def _assert_unit(db: Session, assignment_id: UUID, unit_id: UUID):
    """Rows carry their own unit_id so PIC lists can be org-filtered; the unit must be audited here."""
    ok = db.execute(text("""
        SELECT 1 FROM aidaa_core.assignment a
        WHERE a.assignment_id = CAST(:a AS uuid)
          AND (a.unit_id = CAST(:u AS uuid) OR EXISTS (
               SELECT 1 FROM aidaa_core.assignment_unit au
               WHERE au.assignment_id = a.assignment_id AND au.unit_id = CAST(:u AS uuid)))
    """), {"a": str(assignment_id), "u": str(unit_id)}).fetchone()
    if not ok:
        raise HTTPException(status_code=400, detail="Unit must be one of the audited units of this assignment")


# --- A: permintaan dokumen awal ---

_DOC_SQL = """
    SELECT d.doc_req_id, d.assignment_id, d.unit_id, u.unit_code, u.org_id AS unit_org_id,
           d.item, d.notes, d.deadline, d.status, d.submitted_at, d.submitted_by,
           d.submitted_url, d.submitted_desc, d.verified_at, d.verified_by, d.verify_note,
           d.created_at, d.created_by, d.updated_at, d.updated_by
    FROM aidaa_core.assignment_doc_req d
    JOIN aidaa_core.ref_auditable_unit u ON u.unit_id = d.unit_id
"""


def get_doc_req(db: Session, doc_req_id: UUID) -> dict:
    return _row(db, f"{_DOC_SQL} WHERE d.doc_req_id = CAST(:d AS uuid)",
                {"d": str(doc_req_id)}, "Document request not found")


def list_doc_reqs(db: Session, assignment_id: UUID, pic_orgs=None) -> list[dict]:
    sql = f"{_DOC_SQL} WHERE d.assignment_id = CAST(:a AS uuid)"
    params: dict = {"a": str(assignment_id)}
    if pic_orgs is not None:
        sql += " AND u.org_id = ANY(CAST(:orgs AS uuid[]))"
        params["orgs"] = [str(o) for o in pic_orgs]
    sql += " ORDER BY d.status, d.deadline, u.unit_code, d.created_at"
    return [dict(r._mapping) for r in db.execute(text(sql), params).fetchall()]


def create_doc_req(db: Session, assignment_id: UUID, payload: DocReqCreate, user_id: UUID) -> dict:
    _assignment_open(db, assignment_id, _WORKABLE)
    _assert_unit(db, assignment_id, payload.unit_id)
    rid = db.execute(text("""
        INSERT INTO aidaa_core.assignment_doc_req
            (assignment_id, unit_id, item, notes, deadline, created_by, updated_by)
        VALUES (CAST(:a AS uuid), CAST(:u AS uuid), :item, :n, :d, CAST(:c AS uuid), CAST(:c AS uuid))
        RETURNING doc_req_id
    """), {"a": str(assignment_id), "u": str(payload.unit_id), "item": payload.item,
           "n": payload.notes, "d": payload.deadline, "c": str(user_id)}).scalar_one()
    log_status(db, "doc_req", rid, None, "requested", user_id)
    return get_doc_req(db, rid)


def update_doc_req(db: Session, doc_req_id: UUID, payload: DocReqUpdate, user_id: UUID) -> dict:
    d = get_doc_req(db, doc_req_id)
    _assignment_open(db, d["assignment_id"], _WORKABLE)
    if d["status"] != "requested":
        raise HTTPException(status_code=409, detail="Only a requested item can still be edited")
    cols = payload.model_dump(exclude_unset=True)
    if cols:
        _patch(db, "aidaa_core.assignment_doc_req", "doc_req_id", doc_req_id, cols, user_id)
    return get_doc_req(db, doc_req_id)


def submit_doc_req(db: Session, doc_req_id: UUID, payload: DocReqSubmitIn, user_id: UUID) -> dict:
    d = get_doc_req(db, doc_req_id)
    _assignment_open(db, d["assignment_id"], _WORKABLE)
    if d["status"] != "requested":
        raise HTTPException(status_code=409, detail="This request was already submitted or is verified")
    db.execute(text("""
        UPDATE aidaa_core.assignment_doc_req
           SET status = 'submitted', submitted_at = :t, submitted_by = CAST(:u AS uuid),
               submitted_url = :url, submitted_desc = :desc,
               updated_at = now(), updated_by = CAST(:u AS uuid)
         WHERE doc_req_id = CAST(:d AS uuid)
    """), {"t": _now(), "u": str(user_id), "url": payload.submitted_url,
           "desc": payload.submitted_desc, "d": str(doc_req_id)})
    log_status(db, "doc_req", doc_req_id, "requested", "submitted", user_id)
    return get_doc_req(db, doc_req_id)


def verify_doc_req(db: Session, doc_req_id: UUID, verify_note, user_id: UUID) -> dict:
    d = get_doc_req(db, doc_req_id)
    _assignment_open(db, d["assignment_id"], _WORKABLE)
    if d["status"] != "submitted":
        raise HTTPException(status_code=409, detail="Only a submitted document can be verified")
    db.execute(text("""
        UPDATE aidaa_core.assignment_doc_req
           SET status = 'verified', verified_at = :t, verified_by = CAST(:u AS uuid),
               verify_note = :n, updated_at = now(), updated_by = CAST(:u AS uuid)
         WHERE doc_req_id = CAST(:d AS uuid)
    """), {"t": _now(), "u": str(user_id), "n": verify_note, "d": str(doc_req_id)})
    log_status(db, "doc_req", doc_req_id, "submitted", "verified", user_id)
    return get_doc_req(db, doc_req_id)


# --- C: jadwal wawancara ---

_INT_SQL = """
    SELECT i.interview_id, i.assignment_id, i.unit_id, u.unit_code, u.org_id AS unit_org_id,
           i.topic, i.agenda, i.held_date, i.start_time, i.end_time, i.mode, i.location,
           i.attendees, i.status, i.cancel_reason, i.result, i.created_at, i.created_by,
           i.updated_at, i.updated_by
    FROM aidaa_core.assignment_interview i
    JOIN aidaa_core.ref_auditable_unit u ON u.unit_id = i.unit_id
"""


def get_interview(db: Session, interview_id: UUID) -> dict:
    return _row(db, f"{_INT_SQL} WHERE i.interview_id = CAST(:d AS uuid)",
                {"d": str(interview_id)}, "Interview not found")


def list_interviews(db: Session, assignment_id: UUID, pic_orgs=None) -> list[dict]:
    sql = f"{_INT_SQL} WHERE i.assignment_id = CAST(:a AS uuid)"
    params: dict = {"a": str(assignment_id)}
    if pic_orgs is not None:
        sql += " AND u.org_id = ANY(CAST(:orgs AS uuid[]))"
        params["orgs"] = [str(o) for o in pic_orgs]
    sql += " ORDER BY i.held_date, i.start_time NULLS FIRST, i.created_at"
    return [dict(r._mapping) for r in db.execute(text(sql), params).fetchall()]


def create_interview(db: Session, assignment_id: UUID, payload: InterviewCreate, user_id: UUID) -> dict:
    _assignment_open(db, assignment_id, _WORKABLE)
    _assert_unit(db, assignment_id, payload.unit_id)
    rid = db.execute(text("""
        INSERT INTO aidaa_core.assignment_interview
            (assignment_id, unit_id, topic, agenda, held_date, start_time, end_time,
             mode, location, attendees, created_by, updated_by)
        VALUES (CAST(:a AS uuid), CAST(:u AS uuid), :topic, :agenda, :date, :st, :et,
                :mode, :loc, :att, CAST(:c AS uuid), CAST(:c AS uuid))
        RETURNING interview_id
    """), {"a": str(assignment_id), "u": str(payload.unit_id), "topic": payload.topic,
           "agenda": payload.agenda, "date": payload.held_date, "st": payload.start_time,
           "et": payload.end_time, "mode": payload.mode, "loc": payload.location,
           "att": payload.attendees, "c": str(user_id)}).scalar_one()
    log_status(db, "interview", rid, None, "planned", user_id)
    return get_interview(db, rid)


def update_interview(db: Session, interview_id: UUID, payload: InterviewUpdate, user_id: UUID) -> dict:
    i = get_interview(db, interview_id)
    _assignment_open(db, i["assignment_id"], _WORKABLE)
    if i["status"] != "planned":
        raise HTTPException(status_code=409, detail="Only a planned interview can be edited; hold, finish or cancel it instead")
    cols = payload.model_dump(exclude_unset=True)
    if cols:
        _patch(db, "aidaa_core.assignment_interview", "interview_id", interview_id, cols, user_id)
    return get_interview(db, interview_id)


def hold_interview(db: Session, interview_id: UUID, user_id: UUID) -> dict:
    i = get_interview(db, interview_id)
    _assignment_open(db, i["assignment_id"], _WORKABLE)
    if i["status"] != "planned":
        raise HTTPException(status_code=409, detail="Only a planned interview can be held")
    _patch(db, "aidaa_core.assignment_interview", "interview_id", interview_id, {"status": "held"}, user_id)
    log_status(db, "interview", interview_id, "planned", "held", user_id)
    return get_interview(db, interview_id)


def done_interview(db: Session, interview_id: UUID, result, user_id: UUID) -> dict:
    i = get_interview(db, interview_id)
    _assignment_open(db, i["assignment_id"], _WORKABLE)
    if i["status"] != "held":
        raise HTTPException(status_code=409, detail="Only a held interview can be marked done")
    cols = {"status": "done"}
    if result is not None:
        cols["result"] = result
    _patch(db, "aidaa_core.assignment_interview", "interview_id", interview_id, cols, user_id)
    log_status(db, "interview", interview_id, "held", "done", user_id)
    return get_interview(db, interview_id)


def cancel_interview(db: Session, interview_id: UUID, reason: str, user_id: UUID) -> dict:
    i = get_interview(db, interview_id)
    _assignment_open(db, i["assignment_id"], _WORKABLE)
    if i["status"] not in ("planned", "held"):
        raise HTTPException(status_code=409, detail="Only a planned or held interview can be cancelled")
    old = i["status"]
    _patch(db, "aidaa_core.assignment_interview", "interview_id", interview_id,
           {"status": "cancelled", "cancel_reason": reason}, user_id)
    log_status(db, "interview", interview_id, old, "cancelled", user_id)
    return get_interview(db, interview_id)


# --- D: berita acara penyampaian notisi ---

_BAP_SQL = """
    SELECT b.bap_id, b.finding_id, f.assignment_id, b.bap_no, b.kepada, b.presented_date,
           b.deadline, b.stance_result, b.response_id, b.document_url, b.notes,
           f.status AS finding_status, b.created_at, b.created_by, b.updated_at, b.updated_by
    FROM aidaa_core.finding_bap b
    JOIN aidaa_core.finding f ON f.finding_id = b.finding_id
"""


def get_bap(db: Session, bap_id: UUID) -> dict:
    return _row(db, f"{_BAP_SQL} WHERE b.bap_id = CAST(:d AS uuid)",
                {"d": str(bap_id)}, "Berita acara not found")


def get_bap_of_finding(db: Session, finding_id: UUID) -> dict:
    return _row(db, f"{_BAP_SQL} WHERE b.finding_id = CAST(:d AS uuid)",
                {"d": str(finding_id)}, "Berita acara not found")


def list_baps(db: Session, assignment_id: UUID) -> list[dict]:
    """Every communicated+ finding LEFT JOINed with its BAP (nullable fields when it has none)."""
    rows = db.execute(text("""
        SELECT f.finding_id, f.assignment_id, f.finding_no, f.title, f.status AS finding_status,
               f.communicated_at, f.response_due_date,
               b.bap_id, b.bap_no, b.kepada, b.presented_date, b.deadline, b.stance_result,
               b.response_id, b.document_url, b.notes
        FROM aidaa_core.finding f
        LEFT JOIN aidaa_core.finding_bap b ON b.finding_id = f.finding_id
        WHERE f.assignment_id = CAST(:a AS uuid)
          AND f.status IN ('communicated','responded','open','closed')
        ORDER BY f.finding_no
    """), {"a": str(assignment_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_bap(db: Session, finding_id: UUID, payload: BapCreate, user_id: UUID) -> dict:
    f = get_finding(db, finding_id)
    if f["status"] not in _BAP_OK:
        raise HTTPException(status_code=409, detail="A berita acara exists only after the finding is communicated")
    try:
        db.execute(text("""
            INSERT INTO aidaa_core.finding_bap
                (finding_id, bap_no, kepada, presented_date, deadline, document_url, notes, created_by, updated_by)
            VALUES (CAST(:f AS uuid), :no, :kp, :pd, :dl, :du, :n, CAST(:c AS uuid), CAST(:c AS uuid))
        """), {"f": str(finding_id), "no": payload.bap_no, "kp": payload.kepada,
               "pd": payload.presented_date, "dl": payload.deadline, "du": payload.document_url,
               "n": payload.notes, "c": str(user_id)})
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A berita acara already exists for this finding")
    return get_bap_of_finding(db, finding_id)


def update_bap(db: Session, bap_id: UUID, payload: BapUpdate, user_id: UUID) -> dict:
    b = get_bap(db, bap_id)
    if b["stance_result"] is not None:
        raise HTTPException(status_code=409, detail="The berita acara already records a result and is final")
    cols = payload.model_dump(exclude_unset=True)
    if cols:
        _patch(db, "aidaa_core.finding_bap", "bap_id", bap_id, cols, user_id)
    return get_bap(db, bap_id)


def record_bap_result(db: Session, bap_id: UUID, payload: BapResultIn, user_id: UUID) -> dict:
    b = get_bap(db, bap_id)
    if b["stance_result"] is not None:
        raise HTTPException(status_code=409, detail="The berita acara already records a result")
    if b["finding_status"] not in _BAP_OK:
        raise HTTPException(status_code=409, detail="The finding is no longer in the notis window")
    if payload.response_id:
        ok = db.execute(text("""
            SELECT 1 FROM aidaa_core.finding_response
            WHERE response_id = CAST(:r AS uuid) AND finding_id = CAST(:f AS uuid)
        """), {"r": str(payload.response_id), "f": str(b["finding_id"])}).fetchone()
        if not ok:
            raise HTTPException(status_code=400, detail="Response does not belong to this finding")
    db.execute(text("""
        UPDATE aidaa_core.finding_bap
           SET stance_result = :s, response_id = CAST(:r AS uuid),
               deadline = COALESCE(CAST(:dl AS date), deadline), notes = COALESCE(:n, notes),
               updated_at = now(), updated_by = CAST(:u AS uuid)
         WHERE bap_id = CAST(:b AS uuid)
    """), {"s": payload.stance_result, "r": str(payload.response_id) if payload.response_id else None,
           "dl": payload.deadline, "n": payload.notes, "b": str(bap_id), "u": str(user_id)})
    log_comment(db, "finding", b["finding_id"], f"Berita acara stance recorded: {payload.stance_result}", user_id)
    return get_bap(db, bap_id)
