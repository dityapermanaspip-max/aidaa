from uuid import UUID
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.realisation import BalanceLine, BalanceOut, VarianceLine, VarianceOut
from app.services.realisation_common import assert_realisable, username_map


def balance_out(db: Session, assignment_id: UUID) -> dict:
    """Per-auditor advance vs realised. balance = advance - realised (positive = to be returned)."""
    assert_realisable(db, assignment_id)
    rows = db.execute(text("""
        SELECT COALESCE(a.auditor_id, c.auditor_id) AS auditor_id,
               COALESCE(a.advance_total, 0) AS advance_total,
               COALESCE(c.realised_total, 0) AS realised_total
        FROM (SELECT auditor_id, SUM(amount) AS advance_total
              FROM aidaa_core.realisation_advance
              WHERE assignment_id = CAST(:a AS uuid) GROUP BY auditor_id) a
        FULL JOIN (SELECT auditor_id, SUM(amount) AS realised_total
                   FROM aidaa_core.realisation_cost
                   WHERE assignment_id = CAST(:a AS uuid) GROUP BY auditor_id) c
               ON c.auditor_id = a.auditor_id
        ORDER BY auditor_id
    """), {"a": str(assignment_id)}).fetchall()
    names = username_map(db, assignment_id)
    lines = []
    for r in rows:
        adv = float(r.advance_total or 0)
        rl = float(r.realised_total or 0)
        lines.append(BalanceLine(auditor_id=r.auditor_id, username=names.get(r.auditor_id),
                                 advance_total=adv, realised_total=rl, balance=round(adv - rl, 2)))
    at = round(sum(l.advance_total for l in lines), 2)
    rt = round(sum(l.realised_total for l in lines), 2)
    return BalanceOut(lines=lines, advance_total=at, realised_total=rt,
                      balance=round(at - rt, 2)).model_dump()


def variance_out(db: Session, assignment_id: UUID) -> dict:
    """Planned (budget_line) vs realised (realisation_cost) per component. variance = planned - realised."""
    assert_realisable(db, assignment_id)
    rows = db.execute(text("""
        SELECT COALESCE(b.component_id, c.component_id) AS component_id,
               COALESCE(b.planned, 0) AS planned,
               COALESCE(c.realised, 0) AS realised
        FROM (SELECT component_id, SUM(amount) AS planned
              FROM aidaa_core.budget_line
              WHERE assignment_id = CAST(:a AS uuid) GROUP BY component_id) b
        FULL JOIN (SELECT component_id, SUM(amount) AS realised
                   FROM aidaa_core.realisation_cost
                   WHERE assignment_id = CAST(:a AS uuid) GROUP BY component_id) c
               ON c.component_id = b.component_id
        ORDER BY component_id
    """), {"a": str(assignment_id)}).fetchall()
    comp_ids = {r.component_id for r in rows}
    comps = {}
    if comp_ids:
        comp_rows = db.execute(text("""
            SELECT component_id, component_code, component_name
            FROM aidaa_core.ref_cost_component
            WHERE component_id = ANY(CAST(:ids AS uuid[]))
        """), {"ids": list(comp_ids)}).fetchall()
        comps = {r.component_id: (r.component_code, r.component_name) for r in comp_rows}
    lines = []
    for r in rows:
        code, name = comps.get(r.component_id, ("-", "-"))
        planned = float(r.planned or 0)
        realised = float(r.realised or 0)
        lines.append(VarianceLine(component_id=r.component_id, component_code=code, component_name=name,
                                  planned=planned, realised=realised, variance=round(planned - realised, 2)))
    planned = round(sum(l.planned for l in lines), 2)
    realised = round(sum(l.realised for l in lines), 2)
    return VarianceOut(lines=lines, planned=planned, realised=realised,
                       variance=round(planned - realised, 2)).model_dump()