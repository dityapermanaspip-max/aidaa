from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import (
    require_permission, require_global_permission, get_user_accessible_org_ids, log_audit,
)
from app.services.access import role_is_protected, role_permission_codes, can_grant

router = APIRouter(prefix="/roles", tags=["Roles"])

_COLS = "role_id, app_id, role_code, role_name, description, is_active, created_at"


class RoleCreate(BaseModel):
    app_id: UUID
    role_code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z][A-Z0-9_]*$")
    role_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    role_name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AssignRole(BaseModel):
    user_id: UUID
    role_id: UUID
    app_id: UUID
    org_id: Optional[UUID] = None  # NULL = mapping global (hanya untuk aktor global)


class MappingActive(BaseModel):
    is_active: bool


def _get_role(db: Session, role_id: UUID):
    row = db.execute(text(f"SELECT {_COLS} FROM iam.roles WHERE role_id = :r"), {"r": role_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Role tidak ditemukan")
    return row


def _check_org_scope(db: Session, actor_id, app_id, org_id):
    allowed = get_user_accessible_org_ids(db, actor_id, "iam.role.assign", app_id)
    if allowed is None:
        return
    if org_id is None or org_id not in allowed:
        raise HTTPException(status_code=403, detail="Anda tidak berwenang di organisasi ini")


@router.get("")
def list_roles(app_id: Optional[UUID] = Query(None), db: Session = Depends(get_db),
               current_user=Depends(require_permission("iam.role.read"))):
    rows = db.execute(text(f"""
        SELECT {_COLS} FROM iam.roles
        WHERE (CAST(:a AS uuid) IS NULL OR app_id = :a) ORDER BY role_name
    """), {"a": app_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/{role_id}")
def get_role(role_id: UUID, db: Session = Depends(get_db),
             current_user=Depends(require_permission("iam.role.read"))):
    role = _get_role(db, role_id)
    return {**dict(role._mapping), "permissions": sorted(role_permission_codes(db, role_id))}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, db: Session = Depends(get_db),
                current_user=Depends(require_global_permission("iam.role.create"))):
    app_ok = db.execute(text("SELECT 1 FROM iam.applications WHERE app_id = :a"), {"a": payload.app_id}).fetchone()
    if not app_ok:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    try:
        row = db.execute(text(f"""
            INSERT INTO iam.roles (app_id, role_code, role_name, description)
            VALUES (:a, :c, :n, :d) RETURNING {_COLS}
        """), {"a": payload.app_id, "c": payload.role_code, "n": payload.role_name,
               "d": payload.description}).fetchone()
        log_audit(db, current_user.user_id, "CREATE_ROLE", "roles", row.role_id, {"role_code": payload.role_code})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Kode role sudah dipakai di aplikasi ini")
    return dict(row._mapping)


@router.post("/assign", status_code=status.HTTP_201_CREATED)
def assign_role(payload: AssignRole, db: Session = Depends(get_db),
                current_user=Depends(require_permission("iam.role.assign"))):
    if payload.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Tidak bisa mengubah akses diri sendiri")
    _check_org_scope(db, current_user.user_id, payload.app_id, payload.org_id)

    target = db.execute(text("SELECT is_active FROM iam.users WHERE user_id = :u"), {"u": payload.user_id}).fetchone()
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="User tidak ditemukan atau nonaktif")

    role = _get_role(db, payload.role_id)
    if not role.is_active or (role.app_id is not None and role.app_id != payload.app_id):
        raise HTTPException(status_code=400, detail="Role tidak valid untuk aplikasi ini")

    if payload.org_id is not None:
        org_ok = db.execute(text("""
            SELECT 1 FROM iam.v_active_organization_applications v
            JOIN iam.organizations o ON o.org_id = v.org_id AND o.is_active = TRUE
            WHERE v.org_id = :o AND v.app_id = :a
        """), {"o": payload.org_id, "a": payload.app_id}).fetchone()
        if not org_ok:
            raise HTTPException(status_code=400, detail="Organisasi tidak aktif atau aplikasi belum diaktifkan di org ini")

    if not can_grant(db, current_user.user_id, role_permission_codes(db, payload.role_id)):
        raise HTTPException(status_code=403, detail="Anda tidak boleh memberikan role dengan izin melebihi izin Anda")

    params = {"u": payload.user_id, "o": payload.org_id, "a": payload.app_id, "r": payload.role_id}
    row = db.execute(text("""
        UPDATE iam.user_organization_roles SET is_active = TRUE
        WHERE user_id = :u AND role_id = :r
          AND org_id IS NOT DISTINCT FROM CAST(:o AS uuid)
          AND app_id IS NOT DISTINCT FROM CAST(:a AS uuid)
        RETURNING mapping_id
    """), params).fetchone()
    if not row:
        row = db.execute(text("""
            INSERT INTO iam.user_organization_roles (user_id, org_id, app_id, role_id)
            VALUES (:u, CAST(:o AS uuid), CAST(:a AS uuid), :r) RETURNING mapping_id
        """), params).fetchone()

    log_audit(db, current_user.user_id, "ASSIGN_ROLE", "user_organization_roles", row.mapping_id,
              {"user_id": str(payload.user_id), "role_id": str(payload.role_id),
               "org_id": str(payload.org_id) if payload.org_id else None, "app_id": str(payload.app_id)})
    db.commit()
    return {"status": "success", "mapping_id": str(row.mapping_id)}


@router.patch("/mappings/{mapping_id}")
def set_mapping_active(mapping_id: UUID, payload: MappingActive, db: Session = Depends(get_db),
                       current_user=Depends(require_permission("iam.role.assign"))):
    m = db.execute(text("""
        SELECT user_id, org_id, app_id, role_id FROM iam.user_organization_roles WHERE mapping_id = :m
    """), {"m": mapping_id}).fetchone()
    if not m:
        raise HTTPException(status_code=404, detail="Mapping tidak ditemukan")
    if m.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Tidak bisa mengubah akses diri sendiri")
    _check_org_scope(db, current_user.user_id, m.app_id, m.org_id)

    if payload.is_active and not can_grant(db, current_user.user_id, role_permission_codes(db, m.role_id)):
        raise HTTPException(status_code=403, detail="Anda tidak boleh mengaktifkan role dengan izin melebihi izin Anda")

    db.execute(text("UPDATE iam.user_organization_roles SET is_active = :a WHERE mapping_id = :m"),
               {"a": payload.is_active, "m": mapping_id})
    log_audit(db, current_user.user_id, "SET_MAPPING_ACTIVE", "user_organization_roles", mapping_id,
              {"is_active": payload.is_active})
    db.commit()
    return {"mapping_id": str(mapping_id), "is_active": payload.is_active}


@router.patch("/{role_id}")
def update_role(role_id: UUID, payload: RoleUpdate, db: Session = Depends(get_db),
                current_user=Depends(require_global_permission("iam.role.update"))):
    _get_role(db, role_id)
    if role_is_protected(db, role_id):
        raise HTTPException(status_code=403, detail="Role ini dikunci")
    row = db.execute(text(f"""
        UPDATE iam.roles SET
            role_name = COALESCE(:n, role_name),
            description = COALESCE(:d, description),
            is_active = COALESCE(:a, is_active)
        WHERE role_id = :r RETURNING {_COLS}
    """), {"n": payload.role_name, "d": payload.description, "a": payload.is_active, "r": role_id}).fetchone()
    log_audit(db, current_user.user_id, "UPDATE_ROLE", "roles", role_id, payload.model_dump(exclude_none=True))
    db.commit()
    return dict(row._mapping)


@router.delete("/{role_id}")
def deactivate_role(role_id: UUID, db: Session = Depends(get_db),
                    current_user=Depends(require_global_permission("iam.role.delete"))):
    _get_role(db, role_id)
    if role_is_protected(db, role_id):
        raise HTTPException(status_code=403, detail="Role ini dikunci")
    db.execute(text("UPDATE iam.roles SET is_active = FALSE WHERE role_id = :r"), {"r": role_id})
    log_audit(db, current_user.user_id, "DEACTIVATE_ROLE", "roles", role_id)
    db.commit()
    return {"status": "success"}