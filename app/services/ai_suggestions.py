import json
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.ai import PkaSuggestion, ReportSuggestion, SuggestionDecision
from app.schemas.execution import ReportCreate
from app.services.ai_engine import generate_json
from app.services.assignments import get_assignment
from app.services.execution_flow import create_report
from app.services.logs import log_status, log_edit

_COLS = ("suggestion_id, feature, record_type, record_id, engine, model_name, input_ref, output, "
         "status, decided_by, decided_at, created_by, created_at")
_MODELS = {"pka": PkaSuggestion, "report": ReportSuggestion}
_OPEN = ("draft", "issued", "ongoing")


def get_suggestion(db: Session, suggestion_id: UUID) -> dict:
    row = db.execute(text(f"SELECT {_COLS} FROM aidaa_ai.ai_suggestion WHERE suggestion_id = CAST(:id AS uuid)"),
                     {"id": str(suggestion_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return dict(row._mapping)


def list_suggestions(db: Session, assignment_id: UUID, feature: Optional[str] = None,
                     status: Optional[str] = None) -> list[dict]:
    get_assignment(db, assignment_id)
    rows = db.execute(text(f"""
        SELECT {_COLS} FROM aidaa_ai.ai_suggestion
        WHERE record_type = 'assignment' AND record_id = CAST(:a AS uuid)
          AND (CAST(:f AS text) IS NULL OR feature = CAST(:f AS text))
          AND (CAST(:s AS text) IS NULL OR status = CAST(:s AS text))
        ORDER BY created_at DESC
    """), {"a": str(assignment_id), "f": feature, "s": status}).fetchall()
    return [dict(r._mapping) for r in rows]


def _store(db: Session, feature: str, assignment_id: UUID, user_id: UUID, input_ref: str, prompt: str,
           ai_engine: Optional[str] = None, ai_model: Optional[str] = None) -> dict:
    raw, engine, model = generate_json(prompt, ai_engine, ai_model)
    try:
        out = _MODELS[feature](**raw).model_dump()
    except Exception:
        raise HTTPException(status_code=502, detail="AI answer did not match the expected format, try again")
    row = db.execute(text(f"""
        INSERT INTO aidaa_ai.ai_suggestion
            (feature, record_type, record_id, engine, model_name, input_ref, output, created_by)
        VALUES (:f, 'assignment', CAST(:r AS uuid), :e, :m, :i, CAST(:o AS jsonb), CAST(:u AS uuid))
        RETURNING {_COLS}
    """), {"f": feature, "r": str(assignment_id), "e": engine, "m": model, "i": input_ref,
           "o": json.dumps(out), "u": str(user_id)}).fetchone()
    s = dict(row._mapping)
    log_status(db, "ai_suggestion", s["suggestion_id"], None, "pending", user_id, by_ai=True)
    return s


def _open_assignment(db: Session, assignment_id: UUID) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in _OPEN:
        raise HTTPException(status_code=409, detail="Assignment is finished or cancelled")
    return a


def generate_pka(db: Session, assignment_id: UUID, user_id: UUID,
                 engine: Optional[str] = None, model: Optional[str] = None) -> dict:
    a = _open_assignment(db, assignment_id)
    ctx = db.execute(text("""
        SELECT t.type_name, u.unit_name FROM aidaa_core.ref_audit_type t, aidaa_core.ref_auditable_unit u
        WHERE t.type_id = CAST(:t AS uuid) AND u.unit_id = CAST(:u AS uuid)
    """), {"t": str(a["type_id"]), "u": str(a["unit_id"])}).fetchone()
    existing = [r.title for r in db.execute(text("""
        SELECT title FROM aidaa_core.pka WHERE assignment_id = CAST(:a AS uuid) AND NOT is_skipped
    """), {"a": str(assignment_id)}).fetchall()]
    prompt = (
        "You are an internal audit planning assistant. Propose audit work programs (PKA) for this audit.\n"
        f"Audit type: {ctx.type_name}\nAudited unit: {ctx.unit_name}\n"
        f"Period: {a['start_date']} to {a['end_date']}\n"
        f"Already planned PKA (do not repeat): {existing or 'none'}\n"
        'Answer ONLY with JSON: {"pkas":[{"title":str,"objective":str,"planned_hours":number,'
        '"procedures":[str]}]}. Give 3 to 6 PKA, each with 3 to 8 concrete procedure steps.'
    )
    return _store(db, "pka", assignment_id, user_id,
                  f"{a['assignment_no']} | {ctx.type_name} | {ctx.unit_name}", prompt, engine, model)


def generate_report(db: Session, assignment_id: UUID, user_id: UUID,
                    engine: Optional[str] = None, model: Optional[str] = None) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in ("issued", "ongoing"):
        raise HTTPException(status_code=409, detail="Assignment must be issued or ongoing")
    rows = db.execute(text("""
        SELECT finding_no, title, status, materiality_amount FROM aidaa_core.finding
        WHERE assignment_id = CAST(:a AS uuid) AND status NOT IN ('draft', 'leader_reviewed')
        ORDER BY finding_no LIMIT 50
    """), {"a": str(assignment_id)}).fetchall()
    if not rows:
        raise HTTPException(status_code=409, detail="No approved findings yet to summarize")
    lines = "\n".join(f"- {r.finding_no} {r.title} (status {r.status}, materiality {r.materiality_amount})" for r in rows)
    prompt = (
        "You are an internal audit report assistant. Draft the executive summary and an opinion "
        f"for audit {a['assignment_no']} using only these findings:\n{lines}\n"
        'Answer ONLY with JSON: {"summary":str,"opinion":str}.'
    )
    return _store(db, "report", assignment_id, user_id, f"{a['assignment_no']} | {len(rows)} findings",
                  prompt, engine, model)

# --- human decision: only here does AI output reach the real tables ---

def _apply_pka(db: Session, s: dict, out: dict, user_id: UUID):
    assignment_id = s["record_id"]
    _open_assignment(db, assignment_id)
    for item in out["pkas"]:
        k = db.execute(text("""
            INSERT INTO aidaa_core.pka
                (assignment_id, title, objective, planned_hours, source, ai_suggestion_id,
                 created_by, updated_by)
            VALUES (CAST(:a AS uuid), :t, :o, :h, 'ai_suggestion', CAST(:s AS uuid),
                    CAST(:u AS uuid), CAST(:u AS uuid))
            RETURNING pka_id
        """), {"a": str(assignment_id), "t": item["title"], "o": item["objective"],
               "h": item["planned_hours"], "s": str(s["suggestion_id"]), "u": str(user_id)}).fetchone()
        log_status(db, "pka", k.pka_id, None, "draft", user_id, by_ai=True)
        for no, step in enumerate(item["procedures"], start=1):
            db.execute(text("""
                INSERT INTO aidaa_core.exe_procedure (pka_id, step_no, procedure_text, created_by, updated_by)
                VALUES (CAST(:k AS uuid), :n, :t, CAST(:u AS uuid), CAST(:u AS uuid))
            """), {"k": str(k.pka_id), "n": no, "t": step, "u": str(user_id)})


def _apply_report(db: Session, s: dict, out: dict, user_id: UUID):
    rep = create_report(db, s["record_id"], ReportCreate(summary=out["summary"], opinion=out.get("opinion")), user_id)
    db.execute(text("""
        UPDATE aidaa_core.audit_report SET source = 'ai_suggestion', ai_suggestion_id = CAST(:s AS uuid)
        WHERE report_id = CAST(:r AS uuid)
    """), {"s": str(s["suggestion_id"]), "r": str(rep["report_id"])})
    log_status(db, "report", rep["report_id"], None, "draft", user_id, by_ai=True)


_APPLY = {"pka": _apply_pka, "report": _apply_report}


def decide(db: Session, suggestion_id: UUID, payload: SuggestionDecision, user_id: UUID) -> dict:
    s = get_suggestion(db, suggestion_id)
    if s["status"] != "pending":
        raise HTTPException(status_code=409, detail="Suggestion is already decided")
    out = s["output"]
    if payload.decision == "edited":
        if not payload.edited_output:
            raise HTTPException(status_code=400, detail="edited_output is required when decision is 'edited'")
        try:
            out = _MODELS[s["feature"]](**payload.edited_output).model_dump()
        except Exception:
            raise HTTPException(status_code=400, detail="edited_output does not match the expected format")
        log_edit(db, "ai_suggestion", suggestion_id, "output", json.dumps(s["output"]), json.dumps(out), user_id)
    elif payload.edited_output:
        raise HTTPException(status_code=400, detail="edited_output is only allowed when decision is 'edited'")

    if payload.decision != "rejected":
        _APPLY[s["feature"]](db, s, out, user_id)
    db.execute(text("""
        UPDATE aidaa_ai.ai_suggestion
        SET status = :st, decided_by = CAST(:u AS uuid), decided_at = now(), output = CAST(:o AS jsonb)
        WHERE suggestion_id = CAST(:id AS uuid)
    """), {"st": payload.decision, "u": str(user_id), "o": json.dumps(out), "id": str(suggestion_id)})
    log_status(db, "ai_suggestion", suggestion_id, "pending", payload.decision, user_id)
    return get_suggestion(db, suggestion_id)