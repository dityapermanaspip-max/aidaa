from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.aidaa import (
    AuditorCreate, AuditorUpdate, ExpertiseCreate, ExpertiseUpdate,
    ExpertiseVerify, DocumentCreate,
)
from app.services.masters import _exists, _update_row
from app.services.scope import get_root, root_of_org, assert_in_root

# --- auditor ---

_AUD_SQL = """
    SELECT a.auditor_id, a.user_id, u.username, u.email, a.home_org_id, a.home_location_id,
           a.root_org_id, a.employee_no, a.grade, a.status, a.joined_date, a.left_date, a.is_active,
           a.created_at, a.updated_at
    FROM aidaa_core.auditor a JOIN iam.users u ON u.user_id = a.user_id
"""


def _check_auditor_refs(db: Session, org_id: Optional[UUID], location_id: Optional[UUID]):
    if org_id:
        _exists(db, "iam.organizations", "org_id", org_id, "Organization")
    if location_id:
        _exists(db, "aidaa_core.ref_location", "location_id", location_id, "Location")


def list_auditors(db: Session, user_id: UUID, active_only: bool = True,
                  search: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""{_AUD_SQL}
        WHERE a.root_org_id = CAST(:r AS uuid)
          AND (:active_only = FALSE OR a.is_active = TRUE)
          AND (CAST(:q AS text) IS NULL
               OR u.username ILIKE CAST(:q AS text)
               OR u.email ILIKE CAST(:q AS text)
               OR a.employee_no ILIKE CAST(:q AS text))
        ORDER BY u.username
    """), {"r": str(get_root(db, user_id)), "active_only": active_only,
           "q": f"%{search}%" if search else None}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_auditor(db: Session, auditor_id: UUID, user_id: UUID) -> dict:
    row = db.execute(text(f"{_AUD_SQL} WHERE a.auditor_id = CAST(:id AS uuid)"
                          " AND a.root_org_id = CAST(:r AS uuid)"),
                     {"id": str(auditor_id), "r": str(get_root(db, user_id))}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Auditor not found")
    return dict(row._mapping)


def create_auditor(db: Session, payload: AuditorCreate, user_id: UUID) -> dict:
    root = get_root(db, user_id)
    _check_auditor_refs(db, payload.home_org_id, payload.home_location_id)
    if payload.home_org_id and str(root_of_org(db, payload.home_org_id)) != str(root):
        raise HTTPException(status_code=400,
                            detail="home_org_id must be inside the active root organization")
    if payload.home_location_id:
        assert_in_root(db, "aidaa_core.ref_location", payload.home_location_id, root, "Location")
    try:
        row = db.execute(text("""
            INSERT INTO aidaa_core.auditor
                (user_id, home_org_id, home_location_id, root_org_id, employee_no, grade, joined_date,
                 created_by, updated_by)
            VALUES (CAST(:u AS uuid), CAST(:org AS uuid), CAST(:loc AS uuid), CAST(:r AS uuid),
                    :emp, :grade, :joined, CAST(:uid AS uuid), CAST(:uid AS uuid))
            RETURNING auditor_id
        """), {
            "u": str(payload.user_id),
            "org": str(payload.home_org_id) if payload.home_org_id else None,
            "loc": str(payload.home_location_id) if payload.home_location_id else None,
            "r": str(root),
            "emp": payload.employee_no, "grade": payload.grade,
            "joined": payload.joined_date, "uid": str(user_id),
        }).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="User is already an auditor")
    return get_auditor(db, row.auditor_id, user_id)


def update_auditor(db: Session, auditor_id: UUID, payload: AuditorUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    _check_auditor_refs(db, data.get("home_org_id"), data.get("home_location_id"))
    root = get_root(db, user_id)
    if data.get("home_org_id") and str(root_of_org(db, data["home_org_id"])) != str(root):
        raise HTTPException(status_code=400,
                            detail="home_org_id must be inside the active root organization")
    if data.get("home_location_id"):
        assert_in_root(db, "aidaa_core.ref_location", data["home_location_id"], root, "Location")
    row = _update_row(db, "aidaa_core.auditor", "auditor_id", auditor_id, data,
                      {"home_org_id", "home_location_id"}, user_id, "auditor_id", root)
    if not row:
        raise HTTPException(status_code=404, detail="Auditor not found")
    return get_auditor(db, auditor_id, user_id)


def deactivate_auditor(db: Session, auditor_id: UUID, user_id: UUID) -> dict:
    row = _update_row(db, "aidaa_core.auditor", "auditor_id", auditor_id,
                      {"is_active": False}, set(), user_id, "auditor_id", get_root(db, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="Auditor not found")
    return get_auditor(db, auditor_id, user_id)


# --- expertise ---

_EXP_COLS = ("expertise_id, auditor_id, expertise_type, title, issuer, issued_date, expiry_date, "
             "type_id, points, source, verification_status, verified_by, verified_at, "
             "reject_reason, is_active, created_at, updated_at")

_ROOT_JOIN = """
    FROM aidaa_core.expertise e
    WHERE e.expertise_id = CAST(:id AS uuid)
      AND e.auditor_id IN (SELECT auditor_id FROM aidaa_core.auditor WHERE root_org_id = CAST(:r AS uuid))
"""


def _assert_owner(db: Session, auditor_id: UUID, user_id: UUID):
    row = db.execute(text("SELECT user_id FROM aidaa_core.auditor WHERE auditor_id = CAST(:id AS uuid)"),
                     {"id": str(auditor_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Auditor not found")
    if str(row.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="You can only manage your own expertise")


def _check_dates(issued, expiry):
    if issued and expiry and expiry < issued:
        raise HTTPException(status_code=400, detail="expiry_date cannot be before issued_date")


def _assert_expertise_root(db: Session, expertise_id: UUID, user_id: UUID):
    row = db.execute(text(f"SELECT 1 {_ROOT_JOIN}"),
                     {"id": str(expertise_id), "r": str(get_root(db, user_id))}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Expertise not found")


def get_expertise(db: Session, expertise_id: UUID, user_id: UUID) -> dict:
    row = db.execute(text(f"SELECT {_EXP_COLS} {_ROOT_JOIN}"),
                     {"id": str(expertise_id), "r": str(get_root(db, user_id))}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Expertise not found")
    return dict(row._mapping)


def list_expertise(db: Session, auditor_id: UUID, user_id: UUID) -> list[dict]:
    root = get_root(db, user_id)
    assert_in_root(db, "aidaa_core.auditor", auditor_id, root, "Auditor")
    rows = db.execute(text(f"""
        SELECT {_EXP_COLS} FROM aidaa_core.expertise e
        WHERE e.auditor_id = CAST(:a AS uuid) AND e.is_active = TRUE
          AND e.auditor_id IN (SELECT auditor_id FROM aidaa_core.auditor WHERE root_org_id = CAST(:r AS uuid))
        ORDER BY e.created_at DESC
    """), {"a": str(auditor_id), "r": str(root)}).fetchall()
    return [dict(r._mapping) for r in rows]


def create_expertise(db: Session, auditor_id: UUID, payload: ExpertiseCreate, user_id: UUID) -> dict:
    _assert_owner(db, auditor_id, user_id)
    root = get_root(db, user_id)
    assert_in_root(db, "aidaa_core.auditor", auditor_id, root, "Auditor")
    _check_dates(payload.issued_date, payload.expiry_date)
    if payload.type_id:
        _exists(db, "aidaa_core.ref_audit_type", "type_id", payload.type_id, "Audit type")
    row = db.execute(text(f"""
        INSERT INTO aidaa_core.expertise
            (auditor_id, expertise_type, title, issuer, issued_date, expiry_date, type_id,
             source, verification_status, created_by, updated_by)
        VALUES (CAST(:a AS uuid), :etype, :title, :issuer, :issued, :expiry, CAST(:t AS uuid),
                'manual', 'pending', CAST(:uid AS uuid), CAST(:uid AS uuid))
        RETURNING expertise_id
    """), {
        "a": str(auditor_id), "etype": payload.expertise_type, "title": payload.title,
        "issuer": payload.issuer, "issued": payload.issued_date, "expiry": payload.expiry_date,
        "t": str(payload.type_id) if payload.type_id else None, "uid": str(user_id),
    }).fetchone()
    return get_expertise(db, row.expertise_id, user_id)


def update_expertise(db: Session, expertise_id: UUID, payload: ExpertiseUpdate, user_id: UUID) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    current = get_expertise(db, expertise_id, user_id)
    _assert_owner(db, current["auditor_id"], user_id)
    if current["source"] == "system_credit":
        raise HTTPException(status_code=409, detail="System credit cannot be edited")
    if current["verification_status"] == "verified":
        raise HTTPException(status_code=409, detail="Verified expertise cannot be edited")
    _check_dates(data.get("issued_date", current["issued_date"]),
                 data.get("expiry_date", current["expiry_date"]))
    if data.get("type_id"):
        _exists(db, "aidaa_core.ref_audit_type", "type_id", data["type_id"], "Audit type")
    if current["verification_status"] == "rejected":  # edited after rejection: back to pending
        data.update({"verification_status": "pending", "reject_reason": None,
                     "verified_by": None, "verified_at": None})
    return _update_row(db, "aidaa_core.expertise", "expertise_id", expertise_id, data,
                       {"type_id", "verified_by"}, user_id, _EXP_COLS)


def verify_expertise(db: Session, expertise_id: UUID, payload: ExpertiseVerify, user_id: UUID) -> dict:
    current = get_expertise(db, expertise_id, user_id)
    owner = db.execute(text("SELECT user_id FROM aidaa_core.auditor WHERE auditor_id = CAST(:a AS uuid)"),
                       {"a": str(current["auditor_id"])}).fetchone()
    if owner and str(owner.user_id) == str(user_id):
        raise HTTPException(status_code=403, detail="You cannot verify your own expertise")
    if current["verification_status"] != "pending":
        raise HTTPException(status_code=409, detail="Only pending expertise can be verified")
    if payload.decision == "rejected" and not (payload.reject_reason or "").strip():
        raise HTTPException(status_code=400, detail="reject_reason is required when rejecting")
    row = db.execute(text(f"""
        UPDATE aidaa_core.expertise
        SET verification_status = :st, verified_by = CAST(:uid AS uuid), verified_at = now(),
            reject_reason = :reason, points = COALESCE(CAST(:pts AS numeric), points),
            updated_at = now(), updated_by = CAST(:uid AS uuid)
        WHERE expertise_id = CAST(:id AS uuid)
          AND auditor_id IN (SELECT auditor_id FROM aidaa_core.auditor WHERE root_org_id = CAST(:r AS uuid))
        RETURNING {_EXP_COLS}
    """), {
        "st": payload.decision, "uid": str(user_id), "id": str(expertise_id),
        "reason": payload.reject_reason if payload.decision == "rejected" else None,
        "pts": payload.points, "r": str(get_root(db, user_id)),
    }).fetchone()
    return dict(row._mapping)


# --- expertise_document (metadata only, no file storage yet) ---

_DOC_COLS = "doc_id, expertise_id, file_name, file_path, uploaded_by, uploaded_at"


def list_documents(db: Session, expertise_id: UUID, user_id: UUID) -> list[dict]:
    _assert_expertise_root(db, expertise_id, user_id)
    rows = db.execute(text(f"""
        SELECT {_DOC_COLS} FROM aidaa_core.expertise_document
        WHERE expertise_id = CAST(:e AS uuid) ORDER BY uploaded_at DESC
    """), {"e": str(expertise_id)}).fetchall()
    return [dict(r._mapping) for r in rows]


def add_document(db: Session, expertise_id: UUID, payload: DocumentCreate, user_id: UUID) -> dict:
    current = get_expertise(db, expertise_id, user_id)
    _assert_owner(db, current["auditor_id"], user_id)
    row = db.execute(text(f"""
        INSERT INTO aidaa_core.expertise_document (expertise_id, file_name, file_path, uploaded_by)
        VALUES (CAST(:e AS uuid), :fn, :fp, CAST(:uid AS uuid))
        RETURNING {_DOC_COLS}
    """), {"e": str(expertise_id), "fn": payload.file_name, "fp": payload.file_path,
           "uid": str(user_id)}).fetchone()
    return dict(row._mapping)