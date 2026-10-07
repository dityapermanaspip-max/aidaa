from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.schemas.iam import UserContextResponse

router = APIRouter(tags=["User Context"])


@router.get("/auth/my-contexts", response_model=List[UserContextResponse])
def get_my_contexts(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT m.mapping_id, m.org_id, o.org_code, od.official_name AS org_name,
               m.app_id, a.app_code, a.app_name, m.role_id, r.role_code, r.role_name,
               COALESCE((
                   SELECT ARRAY_AGG(p.permission_code)
                   FROM iam.role_permissions rp
                   JOIN iam.permissions p ON p.permission_id = rp.permission_id
                   WHERE rp.role_id = r.role_id AND rp.is_allowed = TRUE
               ), ARRAY[]::varchar[]) AS permissions
        FROM iam.active_user_roles m
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        LEFT JOIN iam.organizations o ON o.org_id = m.org_id
        LEFT JOIN LATERAL (
            SELECT official_name FROM iam.organization_details_log
            WHERE org_id = o.org_id ORDER BY valid_from DESC LIMIT 1
        ) od ON TRUE
        LEFT JOIN iam.applications a ON a.app_id = m.app_id
        WHERE m.user_id = :uid
          AND (m.org_id IS NULL OR m.app_id IS NULL OR EXISTS (
              SELECT 1 FROM iam.v_active_organization_applications v
              WHERE v.org_id = m.org_id AND v.app_id = m.app_id
          ))
    """), {"uid": current_user.user_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/my-permissions")
def get_my_permissions(app_id: UUID, org_id: UUID, db: Session = Depends(get_db),
                       current_user=Depends(get_current_user)):
    rows = db.execute(text("""
        WITH RECURSIVE anc AS (
            SELECT org_id, parent_id FROM iam.organizations WHERE org_id = :org
            UNION ALL
            SELECT o.org_id, o.parent_id FROM iam.organizations o JOIN anc a ON o.org_id = a.parent_id
        )
        SELECT DISTINCT p.permission_code
        FROM iam.active_user_roles m
        JOIN iam.roles r ON r.role_id = m.role_id AND r.is_active = TRUE
        JOIN iam.role_permissions rp ON rp.role_id = r.role_id AND rp.is_allowed = TRUE
        JOIN iam.permissions p ON p.permission_id = rp.permission_id
        WHERE m.user_id = :uid
          AND (m.org_id IS NULL OR m.org_id IN (SELECT org_id FROM anc))
          AND (m.app_id IS NULL OR m.app_id = :app)
    """), {"uid": current_user.user_id, "org": org_id, "app": app_id}).fetchall()
    return {"permissions": [r.permission_code for r in rows]}