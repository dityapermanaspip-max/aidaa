"""Cross-assignment temuan/rekomendasi monitoring (Monev Temuan).

Read-only lists over the assignments the CALLER may see. The visibility rule is the same one the
surat tugas list uses (services/assignments.py): a global permission mapping sees everything, an
org-mapped caller sees assignments they own (internal audit) or, for non-draft assignments, any of
the audited units belonging to their organisations (the auditee side - the owner explicitly wants
this view usable by people outside the internal audit org). Rows are deliberately slim: no
description or criteria leaves the service, so the view is safe to share wider than the finding
edit screens. Rekomendasi is monitored AFTER the audit (see docs/domains/execution.md), which is
why the view spans finished and ongoing assignments alike.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

# Same shape as list_assignments: owner match (IAU) or unit-org match after issue (auditee).
_VIS = """
    (:all_orgs OR a.owner_org_id = ANY(CAST(:orgs AS uuid[]))
     OR (a.status <> 'draft' AND EXISTS (
           SELECT 1 FROM aidaa_core.assignment_unit au
           JOIN aidaa_core.ref_auditable_unit au_u ON au_u.unit_id = au.unit_id
           WHERE au.assignment_id = a.assignment_id
             AND au_u.org_id = ANY(CAST(:orgs AS uuid[])))))
"""

_UNIT_NAMES = """
    (SELECT string_agg(DISTINCT au_u.unit_code, ', ') FROM aidaa_core.assignment_unit au
     JOIN aidaa_core.ref_auditable_unit au_u ON au_u.unit_id = au.unit_id
     WHERE au.assignment_id = a.assignment_id)
"""

_FIND_SQL = f"""
    SELECT f.finding_id, f.assignment_id, a.assignment_no, f.finding_no, f.title, f.status,
           f.materiality_amount, f.communicated_at, f.response_due_date,
           COALESCE(f.status = 'communicated' AND f.response_due_date < CURRENT_DATE, FALSE) AS no_response,
           COALESCE((SELECT TRUE FROM aidaa_core.approval_task t
                     WHERE t.record_type = 'finding' AND t.record_id = f.finding_id
                       AND t.status = 'pending' LIMIT 1), FALSE) AS under_review,
           {_UNIT_NAMES} AS unit_names
    FROM aidaa_core.finding f
    JOIN aidaa_core.assignment a ON a.assignment_id = f.assignment_id
    WHERE a.is_active = TRUE AND {_VIS}
      AND (CAST(:assg AS uuid) IS NULL OR f.assignment_id = CAST(:assg AS uuid))
      AND (:overdue = FALSE OR (f.status = 'communicated' AND f.response_due_date < CURRENT_DATE))
      AND (CAST(:q AS text) IS NULL
           OR f.title ILIKE CAST(:q AS text) OR f.finding_no ILIKE CAST(:q AS text))
    ORDER BY no_response DESC, f.response_due_date NULLS LAST, a.assignment_no, f.finding_no
"""

_REK_SQL = f"""
    SELECT r.rekomend_id, f.assignment_id, a.assignment_no, f.finding_no,
           f.title AS finding_title, r.rekomend_no, r.recommendation_text, r.due_date, r.status,
           r.followup_at, r.last_monitored_at, r.closed_during_audit, r.closed_at,
           (r.due_date IS NOT NULL AND r.due_date < CURRENT_DATE AND r.status <> 'closed') AS overdue,
           {_UNIT_NAMES} AS unit_names
    FROM aidaa_core.rekomend r
    JOIN aidaa_core.finding f ON f.finding_id = r.finding_id
    JOIN aidaa_core.assignment a ON a.assignment_id = f.assignment_id
    WHERE a.is_active = TRUE AND {_VIS}
      AND (CAST(:assg AS uuid) IS NULL OR f.assignment_id = CAST(:assg AS uuid))
      AND (:overdue = FALSE OR (r.due_date IS NOT NULL AND r.due_date < CURRENT_DATE AND r.status <> 'closed'))
      AND (CAST(:q AS text) IS NULL
           OR r.recommendation_text ILIKE CAST(:q AS text) OR f.title ILIKE CAST(:q AS text))
    ORDER BY overdue DESC, r.due_date NULLS LAST, a.assignment_no, r.rekomend_no
"""


def list_monev(db: Session, org_ids: Optional[List[UUID]], assignment_id: Optional[UUID] = None,
               overdue_only: bool = False, search: Optional[str] = None) -> dict:
    p = {
        "all_orgs": org_ids is None,
        "orgs": [str(o) for o in (org_ids or [])],
        "assg": str(assignment_id) if assignment_id else None,
        "overdue": overdue_only,
        "q": f"%{search.strip()}%" if search and search.strip() else None,
    }
    findings = [dict(r._mapping) for r in db.execute(text(_FIND_SQL), p).fetchall()]
    rekomend = [dict(r._mapping) for r in db.execute(text(_REK_SQL), p).fetchall()]
    return {"findings": findings, "rekomendasi": rekomend}
