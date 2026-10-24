"""library_improvement helper: the AI rewrites ONE library PKA of the library.

Like library_draft, the AI output is only a suggestion. On accept (decide_improvement)
the old library_pka row is deactivated and a NEW row takes over with the next
<type>-NNN code, together with the improved procedures - the old procedure rows stay
attached to the deactivated head for history. One pending improvement per PKA.
"""
import json
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.ai import SuggestionDecision
from app.schemas.library_ai import LibraryImproveRequest, LibraryImprovement
from app.services.ai_engine import generate_json
from app.services.library_ai import _next_number
from app.services.logs import log_edit, log_status
from app.services.scope import get_root

_COLS = ("suggestion_id, feature, record_type, record_id, engine, model_name, input_ref, output, "
         "status, decided_by, decided_at, created_by, created_at")
_COLS_S = ", ".join("s." + c.strip() for c in _COLS.split(","))
# An improvement suggestion is scoped through the PKA head it rewrites (record_id = library_pka_id).
# library_pka has no root_org_id; the root comes from its audit type.
_FROM = ("FROM aidaa_ai.ai_suggestion s JOIN aidaa_core.library_pka k ON k.library_pka_id = s.record_id "
         "JOIN aidaa_core.ref_audit_type t ON t.type_id = k.type_id")

_HEAD_SQL = """
    SELECT k.library_pka_id, k.type_id, k.pka_code, k.title, k.objective, k.is_active,
           t.type_code, t.type_name, t.root_org_id
    FROM aidaa_core.library_pka k JOIN aidaa_core.ref_audit_type t ON t.type_id = k.type_id
    WHERE k.library_pka_id = CAST(:id AS uuid) AND t.root_org_id = CAST(:r AS uuid)
"""


def _head(db: Session, root, library_pka_id):
    row = db.execute(text(_HEAD_SQL), {"id": str(library_pka_id), "r": str(root)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Library PKA not found")
    return row


def _active_procedures(db: Session, library_pka_id):
    return db.execute(text("""
        SELECT step_no, procedure_text, expected_evidence, estimated_hours
        FROM aidaa_core.library_procedure
        WHERE library_pka_id = CAST(:k AS uuid) AND is_active = TRUE ORDER BY step_no
    """), {"k": str(library_pka_id)}).fetchall()


def list_improvements(db: Session, user_id: UUID, library_pka_id: Optional[UUID] = None,
                      status: Optional[str] = None) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT {_COLS_S} {_FROM}
        WHERE s.feature = 'library_improvement' AND s.record_type = 'library_pka'
          AND t.root_org_id = CAST(:r AS uuid)
          AND (CAST(:k AS uuid) IS NULL OR s.record_id = CAST(:k AS uuid))
          AND (CAST(:st AS text) IS NULL OR s.status = CAST(:st AS text))
        ORDER BY s.created_at DESC
    """), {"r": str(get_root(db, user_id)), "k": str(library_pka_id) if library_pka_id else None,
           "st": status}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_improvement(db: Session, user_id: UUID, suggestion_id: UUID) -> dict:
    row = db.execute(text(f"""
        SELECT {_COLS_S} {_FROM}
        WHERE s.suggestion_id = CAST(:id AS uuid) AND s.feature = 'library_improvement'
          AND s.record_type = 'library_pka' AND t.root_org_id = CAST(:r AS uuid)
    """), {"id": str(suggestion_id), "r": str(get_root(db, user_id))}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Improvement suggestion not found")
    return dict(row._mapping)


def generate_improvement(db: Session, user_id: UUID, library_pka_id: UUID,
                         payload: LibraryImproveRequest) -> dict:
    root = get_root(db, user_id)
    head = _head(db, root, library_pka_id)
    if not head.is_active:
        raise HTTPException(status_code=409, detail="Only an active library PKA can be improved")
    if db.execute(text("""
        SELECT 1 FROM aidaa_ai.ai_suggestion
        WHERE feature = 'library_improvement' AND record_id = CAST(:k AS uuid) AND status = 'pending'
    """), {"k": str(library_pka_id)}).fetchone():
        raise HTTPException(status_code=409, detail="This library PKA already has a pending improvement")

    lines = "\n".join(
        f"{p.step_no}. {p.procedure_text} (evidence: {p.expected_evidence or '-'}"
        + (f", {p.estimated_hours} h" if p.estimated_hours else "") + ")"
        for p in _active_procedures(db, library_pka_id))
    prompt = (
        "You are an internal audit planning assistant. Improve ONE standard audit work program (PKA) of a "
        "library, using its current text and the user instruction below.\n"
        f"Audit type: {head.type_name}\nCurrent PKA: {head.pka_code} - {head.title}\n"
        f"Current objective: {head.objective or '-'}\nCurrent procedures:\n{lines or 'none'}\n"
        f"Extra instruction from the user: {payload.instruction or 'none'}\n"
        "Keep the good parts, fix the weak ones, keep every step concrete and verifiable.\n"
        'Answer ONLY with JSON: {"title":str,"objective":str,"procedures":[{"procedure_text":str,'
        '"expected_evidence":str,"estimated_hours":number}]}. Give 3 to 10 procedure steps.\n'
    )
    raw, engine, model = generate_json(prompt, payload.engine, payload.model)
    try:
        out = LibraryImprovement(**raw).model_dump()
    except Exception:
        raise HTTPException(status_code=502, detail="AI answer did not match the expected format, try again")

    row = db.execute(text(f"""
        INSERT INTO aidaa_ai.ai_suggestion
            (feature, record_type, record_id, engine, model_name, input_ref, output, created_by)
        VALUES ('library_improvement', 'library_pka', CAST(:k AS uuid), :e, :m, :i, CAST(:o AS jsonb), CAST(:u AS uuid))
        RETURNING {_COLS}
    """), {"k": str(library_pka_id), "e": engine, "m": model,
           "i": f"{head.pka_code} - {head.title}", "o": json.dumps(out), "u": str(user_id)}).fetchone()
    s = dict(row._mapping)
    log_status(db, "ai_suggestion", s["suggestion_id"], None, "pending", user_id, by_ai=True)
    return s


# --- human decision: accept replaces the library PKA head (old row deactivated) ---

def _apply(db: Session, s: dict, out: dict, user_id: UUID):
    root = get_root(db, user_id)
    head = _head(db, root, s["record_id"])
    if not head.is_active:
        raise HTTPException(status_code=409, detail="This library PKA is no longer active")
    n = _next_number(db, head.type_code, head.root_org_id)
    try:
        nova = db.execute(text("""
            INSERT INTO aidaa_core.library_pka
                (type_id, pka_code, title, objective, ai_suggestion_id, created_by, updated_by)
            VALUES (CAST(:t AS uuid), :code, :title, :obj, CAST(:s AS uuid),
                    CAST(:u AS uuid), CAST(:u AS uuid))
            RETURNING library_pka_id
        """), {"t": str(head.type_id), "code": f"{head.type_code}-{n:03d}",
               "title": out["title"], "obj": out["objective"], "s": str(s["suggestion_id"]),
               "u": str(user_id)}).fetchone()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="PKA code already taken by another request, try again")
    log_status(db, "library_pka", nova.library_pka_id, None, "active", user_id, by_ai=True)
    for no, p in enumerate(out["procedures"], start=1):
        db.execute(text("""
            INSERT INTO aidaa_core.library_procedure
                (library_pka_id, step_no, procedure_text, expected_evidence, estimated_hours, created_by, updated_by)
            VALUES (CAST(:k AS uuid), :n, :txt, :ev, :hrs, CAST(:u AS uuid), CAST(:u AS uuid))
        """), {"k": str(nova.library_pka_id), "n": no, "txt": p["procedure_text"],
               "ev": p["expected_evidence"], "hrs": p["estimated_hours"] or 0, "u": str(user_id)})
    db.execute(text("""
        UPDATE aidaa_core.library_pka
        SET is_active = FALSE, updated_at = now(), updated_by = CAST(:u AS uuid)
        WHERE library_pka_id = CAST(:id AS uuid) AND root_org_id = CAST(:r AS uuid)
    """), {"id": str(s["record_id"]), "r": str(root), "u": str(user_id)})
    log_status(db, "library_pka", s["record_id"], "active", "inactive", user_id)


def decide_improvement(db: Session, user_id: UUID, suggestion_id: UUID, payload: SuggestionDecision) -> dict:
    s = get_improvement(db, user_id, suggestion_id)
    if s["status"] != "pending":
        raise HTTPException(status_code=409, detail="Improvement is already decided")
    out = s["output"]
    if payload.decision == "edited":
        if not payload.edited_output:
            raise HTTPException(status_code=400, detail="edited_output is required when decision is 'edited'")
        try:
            out = LibraryImprovement(**payload.edited_output).model_dump()
        except Exception:
            raise HTTPException(status_code=400, detail="edited_output does not match the expected format")
        log_edit(db, "ai_suggestion", suggestion_id, "output", json.dumps(s["output"]), json.dumps(out), user_id)
    elif payload.edited_output:
        raise HTTPException(status_code=400, detail="edited_output is only allowed when decision is 'edited'")

    if payload.decision != "rejected":
        _apply(db, s, out, user_id)
    db.execute(text("""
        UPDATE aidaa_ai.ai_suggestion
        SET status = :st, decided_by = CAST(:u AS uuid), decided_at = now(), output = CAST(:o AS jsonb)
        WHERE suggestion_id = CAST(:id AS uuid)
    """), {"st": payload.decision, "u": str(user_id), "o": json.dumps(out), "id": str(suggestion_id)})
    log_status(db, "ai_suggestion", suggestion_id, "pending", payload.decision, user_id)
    return get_improvement(db, user_id, suggestion_id)
