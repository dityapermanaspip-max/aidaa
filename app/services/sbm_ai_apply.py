"""Applying an accepted sbm_draft suggestion: components, locations and DRAFT rates.

Called by sbm_ai.decide_draft only; the human decision is the gate, and this half
never runs on its own. Rates are written as approval_status 'draft' - Finance
submits and Board approves them through the normal cost-rate flow afterwards.
"""
import json
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.sbm_ai_parse import PROV_NAMES


def _ensure_place(db: Session, root: str, uid: str, spec: dict):
    """Existing location wins (the organisation's row or the shared national master); missing
    ones are created under the root."""
    if spec.get("location_id"):
        ok = db.execute(text("""
            SELECT 1 FROM aidaa_core.ref_location
            WHERE location_id = CAST(:i AS uuid)
              AND (root_org_id = CAST(:r AS uuid) OR root_org_id IS NULL)
        """), {"i": str(spec["location_id"]), "r": root}).fetchone()
        if ok:
            return spec["location_id"]
    r = db.execute(text("""
        SELECT location_id FROM aidaa_core.ref_location
        WHERE (root_org_id = CAST(:r AS uuid) OR root_org_id IS NULL) AND location_code = :c
        ORDER BY root_org_id IS NULL, location_id LIMIT 1
    """), {"r": root, "c": spec["code"]}).fetchone()
    if r:
        return r.location_id
    r = db.execute(text("""
        INSERT INTO aidaa_core.ref_location
            (root_org_id, location_code, location_name, country, province, city, created_by, updated_by)
        VALUES (CAST(:r AS uuid), :c, :n, 'Indonesia', :p, :ci, CAST(:u AS uuid), CAST(:u AS uuid))
        RETURNING location_id
    """), {"r": root, "c": spec["code"], "n": spec["name"][:150], "p": spec.get("province"),
           "ci": spec.get("city"), "u": uid}).fetchone()
    return r.location_id


def apply_draft(db: Session, s: dict, out: dict, user_id):
    root, uid = str(s["record_id"]), str(user_id)
    comp_ids = {}
    for c in out["components"]:
        r = db.execute(text("""
            SELECT component_id FROM aidaa_core.ref_cost_component
            WHERE root_org_id = CAST(:r AS uuid) AND component_code = :c
        """), {"r": root, "c": c["code"]}).fetchone()
        if not r:
            r = db.execute(text("""
                INSERT INTO aidaa_core.ref_cost_component
                    (root_org_id, component_code, component_name, calc_basis, sort_order, created_by, updated_by)
                VALUES (CAST(:r AS uuid), :c, :n, :b, 100, CAST(:u AS uuid), CAST(:u AS uuid))
                RETURNING component_id
            """), {"r": root, "c": c["code"], "n": c["name"], "b": c["calc_basis"], "u": uid}).fetchone()
        comp_ids[c["code"]] = r.component_id

    specs = {p["code"]: p for p in out.get("places", [])}
    used = {c for x in out["rates"] for c in (x.get("location_code"), x.get("origin_code")) if c}
    loc_ids = {}
    for code in sorted(used):  # only the places that still have a rate after the human edit
        spec = specs.get(code)
        if not spec:  # drafts made before places existed only carry province codes
            name = PROV_NAMES.get(code)
            if not name:
                raise HTTPException(status_code=400, detail=f"Unknown location code {code}")
            spec = {"code": code, "name": f"Provinsi {name}", "city": None, "province": name, "location_id": None}
        loc_ids[code] = _ensure_place(db, root, uid, spec)

    for x in out["rates"]:
        cid = comp_ids.get(x["component_code"])
        if not cid:
            raise HTTPException(status_code=400, detail=f"Rate uses unknown component {x['component_code']}")
        lid = loc_ids.get(x.get("location_code")) if x.get("location_code") else None
        oid = loc_ids.get(x.get("origin_code")) if x.get("origin_code") else None
        p = {"c": str(cid), "l": str(lid) if lid else None, "o": str(oid) if oid else None,
             "g": json.dumps(x["grade"]) if x["grade"] else None, "a": x["amount"],
             "f": out["effective_from"], "t": out["effective_to"], "u": uid}
        dup = db.execute(text("""
            SELECT 1 FROM aidaa_core.ref_cost_rate
            WHERE component_id = CAST(:c AS uuid)
              AND location_id IS NOT DISTINCT FROM CAST(:l AS uuid)
              AND origin_location_id IS NOT DISTINCT FROM CAST(:o AS uuid)
              AND grade IS NOT DISTINCT FROM CAST(:g AS jsonb)
              AND effective_from = CAST(:f AS date) AND is_active = TRUE
        """), p).fetchone()
        if dup:
            continue
        db.execute(text("""
            INSERT INTO aidaa_core.ref_cost_rate
                (component_id, origin_location_id, location_id, grade, amount, effective_from, effective_to,
                 approval_status, created_by, updated_by)
            VALUES (CAST(:c AS uuid), CAST(:o AS uuid), CAST(:l AS uuid), CAST(:g AS jsonb), :a, CAST(:f AS date),
                    CAST(:t AS date), 'draft', CAST(:u AS uuid), CAST(:u AS uuid))
        """), p)
