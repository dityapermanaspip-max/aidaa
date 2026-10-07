from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import require_permission, require_global_permission, log_audit
from app.services.access import role_is_protected, can_grant

router = APIRouter(prefix="/permissions", tags=["Permissions"])

_COLS = "permission_id, app_id, permission_code, permission_label, description, created_at"


class PermCreate(BaseModel):
    app_id: UUID
    permission_code: str = Field(..., min_length=3, max_length=100,
                                 pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    permission_label: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None


class PermUpdate(BaseModel):
    permission_label: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = None


class MatrixItem(BaseModel):
    role_id: UUID
    permission_id: UUID
    is_allowed: bool


class MatrixUpdate(BaseModel):
    updates: List[MatrixItem] = Field(..., min_length=1, max_length=500)


def _get_perm(db: Session, permission_id: UUID):
    row = db.execute(text(f"SELECT {_COLS} FROM iam.permissions WHERE permission_id = :p"),
                     {"p": permission_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Permission tidak ditemukan")
    if row.permission_code == "*":
        raise HTTPException(status_code=403, detail="Permission wildcard tidak boleh diubah lewat API")
    return row


@router.get("")
def list_permissions(app_id: Optional[UUID] = Query(None), db: Session = Depends(get_db),
                     current_user=Depends(require_permission("iam.permission.read"))):
    rows = db.execute(text(f"""
        SELECT {_COLS} FROM iam.permissions
        WHERE permission_code <> '*' AND (CAST(:a AS uuid) IS NULL OR app_id = :a)
        ORDER BY permission_code
    """), {"a": app_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/apps/{app_id}/matrix")
def get_permission_matrix(app_id: UUID, db: Session = Depends(get_db),
                          current_user=Depends(require_permission("iam.permission.read"))):
    roles = db.execute(text("""
        SELECT role_id, role_code, role_name FROM iam.roles
        WHERE app_id = :a AND role_code <> 'SUPERADMIN' ORDER BY role_name
    """), {"a": app_id}).fetchall()
    perms = db.execute(text("""
        SELECT permission_id, permission_code, permission_label FROM iam.permissions
        WHERE app_id = :a AND permission_code <> '*' ORDER BY permission_code
    """), {"a": app_id}).fetchall()
    rows = db.execute(text("""
        SELECT rp.role_id, rp.permission_id, rp.is_allowed FROM iam.role_permissions rp
        JOIN iam.roles r ON r.role_id = rp.role_id WHERE r.app_id = :a
    """), {"a": app_id}).fetchall()
    allowed = {(str(x.role_id), str(x.permission_id)): x.is_allowed for x in rows}
    return {
        "roles": [dict(r._mapping) for r in roles],
        "permissions": [dict(p._mapping) for p in perms],
        "matrix": [
            {"role_id": str(r.role_id), "permission_id": str(p.permission_id),
             "is_allowed": allowed.get((str(r.role_id), str(p.permission_id)), False)}
            for r in roles for p in perms
        ],
    }


@router.put("/matrix")
def update_matrix(payload: MatrixUpdate, db: Session = Depends(get_db),
                  current_user=Depends(require_global_permission("iam.permission.matrix_manage"))):
    for u in payload.updates:
        role = db.execute(text("SELECT role_id, app_id FROM iam.roles WHERE role_id = :r"),
                          {"r": u.role_id}).fetchone()
        perm = db.execute(text("SELECT permission_id, app_id, permission_code FROM iam.permissions WHERE permission_id = :p"),
                          {"p": u.permission_id}).fetchone()
        if not role or not perm:
            raise HTTPException(status_code=404, detail="Role atau permission tidak ditemukan")
        if role.app_id != perm.app_id:
            raise HTTPException(status_code=400, detail="Role dan permission harus dari aplikasi yang sama")
        if perm.permission_code == "*" or role_is_protected(db, u.role_id):
            raise HTTPException(status_code=403, detail="Role/permission ini dikunci")
        if not can_grant(db, current_user.user_id, {perm.permission_code}):
            raise HTTPException(status_code=403, detail=f"Anda tidak memiliki izin '{perm.permission_code}' untuk diberikan")

        db.execute(text("""
            INSERT INTO iam.role_permissions (role_id, permission_id, is_allowed)
            VALUES (:r, :p, :a)
            ON CONFLICT (role_id, permission_id) DO UPDATE SET is_allowed = :a, updated_at = now()
        """), {"r": u.role_id, "p": u.permission_id, "a": u.is_allowed})

    log_audit(db, current_user.user_id, "UPDATE_PERMISSION_MATRIX", "role_permissions", None,
              {"updates": [{"role_id": str(u.role_id), "permission_id": str(u.permission_id),
                            "is_allowed": u.is_allowed} for u in payload.updates]})
    db.commit()
    return {"status": "success"}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_permission(payload: PermCreate, db: Session = Depends(get_db),
                      current_user=Depends(require_global_permission("iam.permission.create"))):
    app_ok = db.execute(text("SELECT 1 FROM iam.applications WHERE app_id = :a"), {"a": payload.app_id}).fetchone()
    if not app_ok:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    try:
        row = db.execute(text(f"""
            INSERT INTO iam.permissions (app_id, permission_code, permission_label, description)
            VALUES (:a, :c, :l, :d) RETURNING {_COLS}
        """), {"a": payload.app_id, "c": payload.permission_code,
               "l": payload.permission_label, "d": payload.description}).fetchone()
        log_audit(db, current_user.user_id, "CREATE_PERMISSION", "permissions", row.permission_id,
                  {"permission_code": payload.permission_code})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Kode permission sudah dipakai")
    return dict(row._mapping)


@router.patch("/{permission_id}")
def update_permission(permission_id: UUID, payload: PermUpdate, db: Session = Depends(get_db),
                      current_user=Depends(require_global_permission("iam.permission.update"))):
    _get_perm(db, permission_id)
    row = db.execute(text(f"""
        UPDATE iam.permissions SET
            permission_label = COALESCE(:l, permission_label),
            description = COALESCE(:d, description)
        WHERE permission_id = :p RETURNING {_COLS}
    """), {"l": payload.permission_label, "d": payload.description, "p": permission_id}).fetchone()
    log_audit(db, current_user.user_id, "UPDATE_PERMISSION", "permissions", permission_id,
              payload.model_dump(exclude_none=True))
    db.commit()
    return dict(row._mapping)


@router.delete("/{permission_id}")
def delete_permission(permission_id: UUID, db: Session = Depends(get_db),
                      current_user=Depends(require_global_permission("iam.permission.delete"))):
    perm = _get_perm(db, permission_id)
    db.execute(text("DELETE FROM iam.role_permissions WHERE permission_id = :p"), {"p": permission_id})
    db.execute(text("DELETE FROM iam.permissions WHERE permission_id = :p"), {"p": permission_id})
    log_audit(db, current_user.user_id, "DELETE_PERMISSION", "permissions", permission_id,
              {"permission_code": perm.permission_code})
    db.commit()
    return {"status": "success"}