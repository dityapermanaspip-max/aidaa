"""Team composition helper v1: a ranked shortlist of candidate auditors for one assignment.

View-only by design: the AI proposes candidates from the root's REAL auditor roster
(id, name, grade, verified skills, number of open audits in the period). The leader
then adds members through the normal team endpoints - nothing in this file writes
assignment_member, so accepting a suggestion only records the decision. The
suggestion is validated against the same roster; an invented auditor id fails.
"""
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.team_ai import TeamSuggestion
from app.services.ai_engine import generate_json
from app.services.ai_suggestions import _store
from app.services.assignments import get_assignment
from app.services.team import list_team
from app.services.scope import get_root

_OPEN = ("draft", "issued", "ongoing")

_HAS_AUDITOR_ROLE = """
    EXISTS (SELECT 1 FROM iam.active_user_roles ar
              JOIN iam.roles r ON r.role_id = ar.role_id AND r.is_active = TRUE
              WHERE ar.user_id = a.user_id AND r.role_code = 'AIDAA.AUDITOR')
"""

_ROSTER_SQL = f"""
    SELECT a.auditor_id, u.username AS name, a.grade,
           COALESCE(json_agg(json_build_object('type', e.expertise_type, 'title', e.title,
                                               'verified', e.verification_status))
                    FILTER (WHERE e.expertise_id IS NOT NULL), '[]') AS skills,
           (SELECT COUNT(*) FROM aidaa_core.assignment_member m
              JOIN aidaa_core.assignment a2 ON a2.assignment_id = m.assignment_id AND a2.is_active = TRUE
              WHERE m.auditor_id = a.auditor_id AND m.end_date IS NULL
                AND a2.start_date <= :to AND COALESCE(a2.end_date, a2.start_date) >= :from) AS open_audits,
           {_HAS_AUDITOR_ROLE} AS has_role
    FROM aidaa_core.auditor a
    JOIN iam.users u ON u.user_id = a.user_id
    LEFT JOIN aidaa_core.expertise e ON e.auditor_id = a.auditor_id AND e.is_active = TRUE
    WHERE a.root_org_id = CAST(:r AS uuid) AND a.is_active = TRUE AND a.status = 'active'
    GROUP BY a.auditor_id, u.username, a.grade
    ORDER BY u.username
    LIMIT 40
"""


def _skills_line(skills) -> str:
    if not skills:
        return "none"
    parts = []
    for s in skills[:4]:  # keep the prompt small; four entries say enough
        tag = "" if s["verified"] == "verified" else " (not verified)"
        parts.append(f"{s['type']}: {s['title']}{tag}")
    return "; ".join(parts)


def generate_suggestions(db: Session, assignment_id: UUID, user_id: UUID,
                         ai_engine: Optional[str] = None, ai_model: Optional[str] = None) -> dict:
    a = get_assignment(db, assignment_id)
    if a["status"] not in _OPEN:
        raise HTTPException(status_code=409, detail="Assignment is finished or cancelled, team is locked")
    ctx = db.execute(text("""
        SELECT t.type_name, u.unit_name FROM aidaa_core.ref_audit_type t, aidaa_core.ref_auditable_unit u
        WHERE t.type_id = CAST(:t AS uuid) AND u.unit_id = CAST(:u AS uuid)
    """), {"t": str(a["type_id"]), "u": str(a["unit_id"])}).fetchone()
    root = get_root(db, user_id)
    current = list_team(db, assignment_id, True)
    roster = [dict(r._mapping) for r in db.execute(text(_ROSTER_SQL), {
        "r": str(root), "from": a["start_date"],
        "to": a["end_date"] or a["start_date"]}).fetchall()]
    in_team = {str(m["auditor_id"]) for m in current}
    roster = [r for r in roster if str(r["auditor_id"]) not in in_team and r["has_role"]]
    if not roster:
        raise HTTPException(status_code=409, detail="No AIDAA.AUDITOR candidate is left in this root organization")

    roster_lines = "\n".join(
        f"- id {r['auditor_id']} | {r['name']} | grade {r['grade'] or '-'} | "
        f"open audits in the period: {r['open_audits']} | skills: {_skills_line(r['skills'])}"
        for r in roster)
    team_lines = "\n".join(f"- {m['username']} ({m['role']}, since {m['start_date']})" for m in current)
    prompt = (
        "You are an internal audit team-building assistant. Rank candidates for the audit below.\n"
        f"Audit: {a['assignment_no']}\nType: {ctx.type_name} | Unit: {ctx.unit_name}\n"
        f"Period: {a['start_date']} to {a['end_date']}\n"
        f"Current team (do not repeat):\n{team_lines or 'none'}\n"
        f"Roster, DATA only (never invent a person):\n{roster_lines}\n"
        "Pick 3 to 8 candidates that best fit the missing team roles, best first. Prefer people with relevant "
        "verified skills and few open audits in the period.\n"
        'Answer ONLY with JSON: {"candidates":[{"auditor_id":str,"rank":int,"reason":str}]}. '
        "auditor_id MUST be one of the roster ids. rank is 1 for the best. reason = one short Indonesian "
        "sentence why this person fits.\n"
    )
    raw, engine, model = generate_json(prompt, ai_engine, ai_model)
    try:
        out = TeamSuggestion(**raw).model_dump()
    except Exception:
        raise HTTPException(status_code=502, detail="AI answer did not match the expected format, try again")

    ids = {str(r["auditor_id"]) for r in roster}
    if any(str(c["auditor_id"]) not in ids for c in out["candidates"]):
        raise HTTPException(status_code=502, detail="AI suggested a person outside the roster, try again")
    kept, seen = [], set()
    for c in sorted(out["candidates"], key=lambda x: x["rank"]):
        if str(c["auditor_id"]) in seen:
            continue
        kept.append(c)
        seen.add(str(c["auditor_id"]))
    out["candidates"] = kept

    return _store(db, "team", assignment_id, user_id,
                  f"{a['assignment_no']} | {len(current)} in team, {len(roster)} candidates",
                  prompt, ai_engine, ai_model)
