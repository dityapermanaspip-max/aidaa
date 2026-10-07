import json
from typing import Optional, List
from uuid import UUID
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/iam/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau kadaluarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None or "user_id" not in payload or "jti" not in payload:
        raise credentials_exception

    revoked = db.execute(
        text("SELECT 1 FROM iam.revoked_tokens WHERE jti = CAST(:jti AS uuid)"),
        {"jti": payload["jti"]},
    ).fetchone()
    if revoked:
        raise credentials_exception

    user = db.execute(text("""
        SELECT user_id, username, email, is_active, token_version
        FROM iam.users WHERE user_id = :user_id
    """), {"user_id": payload["user_id"]}).fetchone()

    if not user or not user.is_active or payload.get("tv") != user.token_version:
        raise credentials_exception
    return user
    
_PERMISSION_SQL = text("""
    WITH RECURSIVE ancestors AS (
        SELECT org_id, parent_id FROM iam.organizations
        WHERE org_id = CAST(:org_id AS uuid)
        UNION ALL
        SELECT o.org_id, o.parent_id FROM iam.organizations o
        JOIN ancestors a ON o.org_id = a.parent_id
    )
    SELECT 1
    FROM iam.active_user_roles m
    JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
    JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
    JOIN iam.permissions p ON p.permission_id = rp.permission_id
    WHERE m.user_id = :user_id
      AND p.permission_code IN (:code, '*')
      AND (
            CAST(:org_id AS uuid) IS NULL
            OR m.org_id IS NULL
            OR m.org_id IN (SELECT org_id FROM ancestors)
      )
      AND (
            m.org_id IS NULL OR m.app_id IS NULL
            OR EXISTS (
                SELECT 1 FROM iam.v_active_organization_applications v
                WHERE v.org_id = m.org_id AND v.app_id = m.app_id
            )
      )
    LIMIT 1
""")


def require_permission(permission_code: str, org_param: str = "org_id"):
    def checker(
        request: Request,
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        org_id = request.path_params.get(org_param) or request.query_params.get(org_param)

        if org_id:
            try:
                UUID(str(org_id))
            except ValueError:
                raise HTTPException(status_code=400, detail="org_id tidak valid")

        row = db.execute(_PERMISSION_SQL, {
            "user_id": current_user.user_id,
            "code": permission_code,
            "org_id": org_id,
        }).fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Akses ditolak: izin '{permission_code}' tidak dimiliki di organisasi ini",
            )
        return current_user

    return checker

def require_global_permission(permission_code: str):
    """Hanya untuk mapping global (org_id NULL)."""
    def checker(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
        row = db.execute(text("""
            SELECT 1 FROM iam.active_user_roles m
            JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
            JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
            JOIN iam.permissions p ON p.permission_id = rp.permission_id
            WHERE m.user_id = :u AND m.org_id IS NULL
              AND p.permission_code IN (:c, '*')
            LIMIT 1
        """), {"u": current_user.user_id, "c": permission_code}).fetchone()
        if not row:
            raise HTTPException(status_code=403, detail=f"Akses ditolak: izin global '{permission_code}' diperlukan")
        return current_user
    return checker
    

def get_user_accessible_org_ids(
    db: Session,
    user_id: UUID,
    permission_code: str,
    app_id: Optional[UUID] = None,  # aplikasi TARGET, tidak dipakai menyaring izin
) -> Optional[List[UUID]]:
    """None = akses semua org (mapping global yang PUNYA izin). List = org yang boleh."""
    global_check = db.execute(text("""
        SELECT 1
        FROM iam.active_user_roles m
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
        JOIN iam.permissions p ON p.permission_id = rp.permission_id
        WHERE m.user_id = :user_id AND m.org_id IS NULL
          AND p.permission_code IN (:code, '*')
        LIMIT 1
    """), {"user_id": user_id, "code": permission_code}).fetchone()

    if global_check:
        return None

    rows = db.execute(text("""
        WITH RECURSIVE assigned_orgs AS (
            SELECT DISTINCT m.org_id
            FROM iam.active_user_roles m
            JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
            JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
            JOIN iam.permissions p ON p.permission_id = rp.permission_id
            JOIN iam.v_active_organization_applications voa
              ON voa.org_id = m.org_id AND voa.app_id = m.app_id
            WHERE m.user_id = :user_id
              AND p.permission_code IN (:code, '*')
              AND m.org_id IS NOT NULL
        ),
        org_hierarchy AS (
            SELECT o.org_id FROM iam.organizations o
            JOIN assigned_orgs ao ON o.org_id = ao.org_id
            UNION
            SELECT child.org_id FROM iam.organizations child
            JOIN org_hierarchy parent ON child.parent_id = parent.org_id
        )
        SELECT org_id FROM org_hierarchy
    """), {"user_id": user_id, "code": permission_code}).fetchall()

    return [row.org_id for row in rows]

def log_audit(
    db: Session,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: Optional[UUID] = None,
    metadata: Optional[dict] = None,
):
    db.execute(text("""
        INSERT INTO iam.audit_log (actor_id, action, target_type, target_id, metadata)
        VALUES (CAST(:actor_id AS uuid), :action, :target_type,
                CAST(:target_id AS uuid), CAST(:metadata AS jsonb))
    """), {
        "actor_id": str(actor_id),
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id else None,
        "metadata": json.dumps(metadata) if metadata is not None else None,
    })