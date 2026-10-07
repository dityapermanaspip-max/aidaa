"""Layer 1: who is calling and which IAM permission they hold."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/iam/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalid or expired",
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
    """Layer 1: IAM permission check, e.g. require_permission("audit.plan.read")."""
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
                raise HTTPException(status_code=400, detail="Invalid org_id")

        row = db.execute(_PERMISSION_SQL, {
            "user_id": current_user.user_id,
            "code": permission_code,
            "org_id": org_id,
        }).fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: permission '{permission_code}' not held in this organization",
            )
        return current_user

    return checker


def require_any_permission(*permission_codes: str):
    """Layer 1 when several codes are acceptable (example: Head or General Affairs)."""
    def checker(request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
        org_id = request.path_params.get("org_id") or request.query_params.get("org_id")
        for code in permission_codes:
            if db.execute(_PERMISSION_SQL, {"user_id": current_user.user_id, "code": code,
                                            "org_id": org_id}).fetchone():
                return current_user
        raise HTTPException(status_code=403, detail=f"Access denied: one of {list(permission_codes)} required")
    return checker