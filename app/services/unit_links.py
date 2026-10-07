"""Units of a plan or an assignment.

The main table keeps the FIRST (primary) unit in unit_id. The link table (audit_plan_unit or
assignment_unit) holds ALL units, the primary one included. Most records have exactly one unit.
"""
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

# kind -> (main table, primary key, link table). A whitelist, table names never come from input.
_KINDS = {
    "plan": ("aidaa_core.audit_plan", "plan_id", "aidaa_core.audit_plan_unit"),
    "assignment": ("aidaa_core.assignment", "assignment_id", "aidaa_core.assignment_unit"),
}


def clean_units(primary, extras) -> list:
    """Primary first, then the extra units without duplicates. A one-unit record has no extras."""
    out = [str(primary)]
    for u in extras or []:
        if str(u) not in out:
            out.append(str(u))
    return out


def check_units(db: Session, unit_ids: list):
    rows = db.execute(text("""
        SELECT unit_id, is_active FROM aidaa_core.ref_auditable_unit
        WHERE unit_id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": [str(u) for u in unit_ids]}).fetchall()
    found = {str(r.unit_id): r.is_active for r in rows}
    for u in unit_ids:
        if str(u) not in found:
            raise HTTPException(status_code=404, detail="Unit not found")
        if not found[str(u)]:
            raise HTTPException(status_code=409, detail="Unit is inactive")


def unit_org_ids(db: Session, unit_ids: list) -> list:
    """The IAM orgs of these units, used for conflict-of-interest and auditee access checks."""
    rows = db.execute(text("""
        SELECT DISTINCT org_id FROM aidaa_core.ref_auditable_unit
        WHERE unit_id = ANY(CAST(:ids AS uuid[])) AND org_id IS NOT NULL
    """), {"ids": [str(u) for u in unit_ids]}).fetchall()
    return [r.org_id for r in rows]


def unit_ids_for(db: Session, kind: str, record_ids: list) -> dict:
    """{record id as text: [unit ids, primary first]} for several plans or assignments at once."""
    main, pk, link = _KINDS[kind]
    if not record_ids:
        return {}
    rows = db.execute(text(f"""
        SELECT l.{pk} AS rid, l.unit_id FROM {link} l
        JOIN {main} m ON m.{pk} = l.{pk}
        WHERE l.{pk} = ANY(CAST(:ids AS uuid[]))
        ORDER BY (l.unit_id <> m.unit_id), l.created_at, l.unit_id
    """), {"ids": [str(r) for r in record_ids]}).fetchall()
    out: dict = {}
    for r in rows:
        out.setdefault(str(r.rid), []).append(r.unit_id)
    return out


def unit_ids_of(db: Session, kind: str, record_id) -> list:
    return unit_ids_for(db, kind, [record_id]).get(str(record_id), [])


def sync_units(db: Session, kind: str, record_id, unit_ids: list, user_id):
    """Makes the link table match unit_ids exactly (the primary unit must be in the list)."""
    _, pk, link = _KINDS[kind]
    db.execute(text(f"""
        DELETE FROM {link} WHERE {pk} = CAST(:r AS uuid) AND unit_id <> ALL(CAST(:keep AS uuid[]))
    """), {"r": str(record_id), "keep": [str(u) for u in unit_ids]})
    for u in unit_ids:
        db.execute(text(f"""
            INSERT INTO {link} ({pk}, unit_id, created_by)
            VALUES (CAST(:r AS uuid), CAST(:u AS uuid), CAST(:uid AS uuid))
            ON CONFLICT ({pk}, unit_id) DO NOTHING
        """), {"r": str(record_id), "u": str(u), "uid": str(user_id)})