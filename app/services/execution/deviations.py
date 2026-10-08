"""Plan deviation read-only access over aidaa_core.v_plan_deviation (calculated, never stored)."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

_SQL = """
    SELECT v.assignment_id, v.assignment_no, v.plan_id, v.plan_no, v.is_unplanned,
           v.planned_auditors, v.actual_auditors, v.planned_days, v.actual_days,
           v.planned_man_days, v.actual_man_days, v.planned_budget, v.actual_budget,
           v.leader_changed, v.pka_planned_days
    FROM aidaa_core.v_plan_deviation v
    LEFT JOIN aidaa_core.assignment a ON a.assignment_id = v.assignment_id
    WHERE (:all_orgs OR a.owner_org_id = ANY(CAST(:orgs AS uuid[])))
    ORDER BY v.is_unplanned DESC, a.start_date DESC, v.assignment_no
"""


def list_deviations(db: Session, org_ids: Optional[List[UUID]]) -> list[dict]:
    rows = db.execute(
        text(_SQL),
        {"all_orgs": org_ids is None, "orgs": [str(o) for o in (org_ids or [])]},
    ).fetchall()
    return [dict(r._mapping) for r in rows]