from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    require_permission, require_global_permission, get_user_accessible_org_ids, log_audit,
)
from app.schemas.iam import (
    OrganizationCreate, OrganizationUpdate, OrganizationDetailsLogBase,
    OrganizationDetailsUpdate, OrgAppToggle,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])

_DETAIL_INSERT = text("""
    INSERT INTO iam.organization_details_log
        (org_id, official_name, short_name, address, leader_name, phone_number, email,
         fax_number, logo_url, created_by)
    VALUES (:org_id, :official_name, :short_name, :address, :leader_name, :phone_number,
            :email, :fax_number, :logo_url, :created_by)
    RETURNING log_id, valid_from
""")


def _insert_details(db: Session, org_id, d: OrganizationDetailsLogBase, actor_id):
    return db.execute(_DETAIL_INSERT, {"org_id": org_id, "created_by": actor_id, **d.model_dump()}).fetchone()


@router.get("")
def list_organizations(db: Session = Depends(get_db),
                       current_user=Depends(require_permission("iam.org.read"))):
    allowed = get_user_accessible_org_ids(db, current_user.user_id, "iam.org.read")
    allowed = None if allowed is None else [str(o) for o in allowed]
    rows = db.execute(text("""
        SELECT o.org_id, o.org_code, o.parent_id, o.root_org_id, o.is_active, o.created_at,
               d.official_name, d.short_name, d.leader_name
        FROM iam.organizations o
        LEFT JOIN LATERAL (
            SELECT official_name, short_name, leader_name FROM iam.organization_details_log
            WHERE org_id = o.org_id ORDER BY valid_from DESC LIMIT 1
        ) d ON TRUE
        WHERE CAST(:a AS uuid[]) IS NULL OR o.org_id = ANY(CAST(:a AS uuid[]))
        ORDER BY o.created_at DESC
    """), {"a": allowed}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/root", status_code=status.HTTP_201_CREATED)
def create_root_organization(payload: OrganizationCreate, db: Session = Depends(get_db),
                             current_user=Depends(require_global_permission("iam.org.create_root"))):
    new_id = uuid4()
    try:
        db.execute(text("""
            INSERT INTO iam.organizations (org_id, org_code, parent_id, root_org_id)
            VALUES (:id, :code, NULL, :id)
        """), {"id": new_id, "code": payload.org_code})
        _insert_details(db, new_id, payload.details, current_user.user_id)
        log_audit(db, current_user.user_id, "CREATE_ROOT_ORG", "organizations", new_id,
                  {"org_code": payload.org_code})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Kode organisasi sudah dipakai")
    return {"org_id": str(new_id), "org_code": payload.org_code}


@router.post("/{parent_id}/children", status_code=status.HTTP_201_CREATED)
def create_child_organization(parent_id: UUID, payload: OrganizationCreate, db: Session = Depends(get_db),
                              current_user=Depends(require_permission("iam.org.create", org_param="parent_id"))):
    parent = db.execute(text("""
        SELECT COALESCE(root_org_id, org_id) AS root_id FROM iam.organizations WHERE org_id = :p
    """), {"p": parent_id}).fetchone()
    if not parent:
        raise HTTPException(status_code=404, detail="Organisasi induk tidak ditemukan")
    new_id = uuid4()
    try:
        db.execute(text("""
            INSERT INTO iam.organizations (org_id, org_code, parent_id, root_org_id)
            VALUES (:id, :code, :p, :root)
        """), {"id": new_id, "code": payload.org_code, "p": parent_id, "root": parent.root_id})
        _insert_details(db, new_id, payload.details, current_user.user_id)
        log_audit(db, current_user.user_id, "CREATE_CHILD_ORG", "organizations", new_id,
                  {"org_code": payload.org_code, "parent_id": str(parent_id)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Kode organisasi sudah dipakai")
    return {"org_id": str(new_id)}


@router.get("/{org_id}")
def get_organization(org_id: UUID, db: Session = Depends(get_db),
                     current_user=Depends(require_permission("iam.org.read"))):
    row = db.execute(text("""
        SELECT o.org_id, o.org_code, o.parent_id, o.root_org_id, o.is_active, o.created_at,
               d.official_name, d.short_name, d.address, d.leader_name,
               d.phone_number, d.email, d.fax_number, d.logo_url
        FROM iam.organizations o
        LEFT JOIN LATERAL (
            SELECT * FROM iam.organization_details_log
            WHERE org_id = o.org_id ORDER BY valid_from DESC LIMIT 1
        ) d ON TRUE
        WHERE o.org_id = :o
    """), {"o": org_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Organisasi tidak ditemukan")
    return dict(row._mapping)


@router.patch("/{org_id}")
def update_organization(org_id: UUID, payload: OrganizationUpdate, db: Session = Depends(get_db),
                        current_user=Depends(require_permission("iam.org.update"))):
    try:
        row = db.execute(text("""
            UPDATE iam.organizations SET
                org_code = COALESCE(:code, org_code),
                is_active = COALESCE(:active, is_active)
            WHERE org_id = :o RETURNING org_id, org_code, is_active
        """), {"code": payload.org_code, "active": payload.is_active, "o": org_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Organisasi tidak ditemukan")
        log_audit(db, current_user.user_id, "UPDATE_ORG", "organizations", org_id,
                  payload.model_dump(exclude_none=True))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Kode organisasi sudah dipakai")
    return dict(row._mapping)


@router.delete("/{org_id}")
def deactivate_organization(org_id: UUID, db: Session = Depends(get_db),
                            current_user=Depends(require_permission("iam.org.delete"))):
    has_children = db.execute(text(
        "SELECT 1 FROM iam.organizations WHERE parent_id = :o AND is_active = TRUE LIMIT 1"), {"o": org_id}).fetchone()
    if has_children:
        raise HTTPException(status_code=409, detail="Nonaktifkan dulu semua organisasi anak")
    res = db.execute(text("UPDATE iam.organizations SET is_active = FALSE WHERE org_id = :o RETURNING org_id"),
                     {"o": org_id}).fetchone()
    if not res:
        raise HTTPException(status_code=404, detail="Organisasi tidak ditemukan")
    log_audit(db, current_user.user_id, "DEACTIVATE_ORG", "organizations", org_id)
    db.commit()
    return {"status": "success"}


@router.post("/{org_id}/details", status_code=status.HTTP_201_CREATED)
def add_organization_details(org_id: UUID, payload: OrganizationDetailsUpdate, db: Session = Depends(get_db),
                             current_user=Depends(require_permission("iam.org.update"))):
    exists = db.execute(text("SELECT 1 FROM iam.organizations WHERE org_id = :o"), {"o": org_id}).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Organisasi tidak ditemukan")
    res = _insert_details(db, org_id, payload, current_user.user_id)
    log_audit(db, current_user.user_id, "UPDATE_ORG_DETAILS", "organization_details_log", res.log_id,
              {"org_id": str(org_id)})
    db.commit()
    return {"status": "success", "log_id": str(res.log_id), "valid_from": res.valid_from}


@router.get("/{org_id}/details-history")
def get_details_history(org_id: UUID, db: Session = Depends(get_db),
                        current_user=Depends(require_permission("iam.org.read"))):
    rows = db.execute(text("""
        SELECT dl.log_id, dl.official_name, dl.short_name, dl.address, dl.leader_name,
               dl.phone_number, dl.email, dl.fax_number, dl.logo_url, dl.valid_from,
               u.username AS changed_by
        FROM iam.organization_details_log dl
        LEFT JOIN iam.users u ON u.user_id = dl.created_by
        WHERE dl.org_id = :o ORDER BY dl.valid_from DESC
    """), {"o": org_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/{org_id}/apps")
def get_org_apps(org_id: UUID, db: Session = Depends(get_db),
                 current_user=Depends(require_permission("iam.org.read"))):
    rows = db.execute(text("""
        SELECT app_id, app_code, app_name FROM iam.v_active_organization_applications
        WHERE org_id = :o ORDER BY app_name
    """), {"o": org_id}).fetchall()
    return [dict(r._mapping) for r in rows]

@router.get("/{org_id}/users")
def get_org_users(org_id: UUID, db: Session = Depends(get_db),
                  current_user=Depends(require_permission("iam.org.read"))):
    rows = db.execute(text("""
        SELECT m.mapping_id, m.is_active, u.user_id, u.username, u.full_name,
               a.app_code, a.app_name, r.role_code, r.role_name
        FROM iam.user_organization_roles m
        JOIN iam.users u ON u.user_id = m.user_id
        JOIN iam.roles r ON r.role_id = m.role_id
        LEFT JOIN iam.applications a ON a.app_id = m.app_id
        WHERE m.org_id = :o ORDER BY u.username
    """), {"o": org_id}).fetchall()
    return [dict(r._mapping) for r in rows]
    
@router.post("/{org_id}/apps", status_code=status.HTTP_201_CREATED)
def toggle_org_app(org_id: UUID, payload: OrgAppToggle, db: Session = Depends(get_db),
                   current_user=Depends(require_global_permission("iam.org.app_manage"))):
    root = db.execute(text("SELECT 1 FROM iam.organizations WHERE org_id = :o AND parent_id IS NULL"),
                      {"o": org_id}).fetchone()
    if not root:
        raise HTTPException(status_code=400, detail="Aplikasi hanya bisa diatur di root organisasi")
    app_ok = db.execute(text("SELECT 1 FROM iam.applications WHERE app_id = :a"), {"a": payload.app_id}).fetchone()
    if not app_ok:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")

    res = db.execute(text("""
        UPDATE iam.organization_applications SET is_active = :act
        WHERE org_id = :o AND app_id = :a RETURNING org_app_id
    """), {"act": payload.is_active, "o": org_id, "a": payload.app_id}).fetchone()
    if not res:
        res = db.execute(text("""
            INSERT INTO iam.organization_applications (org_id, app_id, is_active)
            VALUES (:o, :a, :act) RETURNING org_app_id
        """), {"o": org_id, "a": payload.app_id, "act": payload.is_active}).fetchone()

    log_audit(db, current_user.user_id, "TOGGLE_ORG_APP", "organization_applications", res.org_app_id,
              {"org_id": str(org_id), "app_id": str(payload.app_id), "is_active": payload.is_active})
    db.commit()
    return {"status": "success", "org_app_id": str(res.org_app_id)}