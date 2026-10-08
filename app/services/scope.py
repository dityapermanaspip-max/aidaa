"""Organisation scope. Master data belongs to ONE root organisation (the owner of the audit universe).

The caller's root comes from get_root(db, user_id) (the audit_setting of their organisation).
Cost rates have no root column, they inherit the root of their cost component.
"""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit_setting import get_root  # noqa: F401  (re-exported for the other services)

# Tables with a root_org_id column -> primary key. A whitelist: table names never come from input.
SCOPED = {
    "aidaa_core.ref_location": "location_id",
    "aidaa_core.ref_audit_type": "type_id",
    "aidaa_core.ref_cost_component": "component_id",
    "aidaa_core.ref_funding_source": "funding_id",
    "aidaa_core.library_pka": "library_pka_id",
    "aidaa_core.ref_auditable_unit": "unit_id",
    "aidaa_core.auditor": "auditor_id",
}


def root_of_org(db: Session, org_id: UUID) -> UUID:
    row = db.execute(text("SELECT COALESCE(root_org_id, org_id) AS r FROM iam.organizations WHERE org_id = CAST(:o AS uuid)"),
                     {"o": str(org_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    return row.r


def assert_in_root(db: Session, table: str, value: UUID, root_id: UUID, label: str):
    """The record must exist in this root. A record of another root answers 404, so it stays invisible."""
    pk = SCOPED[table]
    row = db.execute(text(f"SELECT root_org_id FROM {table} WHERE {pk} = CAST(:v AS uuid)"), {"v": str(value)}).fetchone()
    if not row or str(row.root_org_id) != str(root_id):
        raise HTTPException(status_code=404, detail=f"{label} not found")


def scoped_get(db: Session, table: str, cols: str, value: UUID, root_id: UUID, label: str) -> dict:
    pk = SCOPED[table]
    row = db.execute(text(f"SELECT {cols} FROM {table} WHERE {pk} = CAST(:v AS uuid) AND root_org_id = CAST(:r AS uuid)"),
                     {"v": str(value), "r": str(root_id)}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return dict(row._mapping)