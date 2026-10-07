import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import FRONTEND_URL
from app.core.database import get_db
from app.core.security import hash_password
from app.api.dependencies import require_permission, get_user_accessible_org_ids, log_audit
from app.schemas.iam import UserCreate, UserUpdate
from app.services.email import send_email, smtp_ready

router = APIRouter(prefix="/users", tags=["Users"])


def _scope(db: Session, actor_id, code: str):
    """None = semua user; list = hanya user yang punya mapping di org tsb."""
    allowed = get_user_accessible_org_ids(db, actor_id, code)
    return None if allowed is None else [str(o) for o in allowed]


def _check_target(db: Session, target_id: UUID, allowed):
    exists = db.execute(text("SELECT 1 FROM iam.users WHERE user_id = :u"), {"u": target_id}).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if allowed is None:
        return
    ok = db.execute(text("""
        SELECT 1 FROM iam.active_user_roles
        WHERE user_id = :u AND org_id = ANY(CAST(:o AS uuid[])) LIMIT 1
    """), {"u": target_id, "o": allowed}).fetchone()
    if not ok:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")


_LIST_SQL = """
    SELECT u.user_id, u.username, u.email, u.full_name, u.is_active, u.created_at, d.position_title
    FROM iam.users u
    LEFT JOIN LATERAL (
        SELECT position_title FROM iam.user_details_log
        WHERE user_id = u.user_id ORDER BY valid_from DESC LIMIT 1
    ) d ON TRUE
    WHERE (CAST(:o AS uuid[]) IS NULL OR EXISTS (
        SELECT 1 FROM iam.active_user_roles m
        WHERE m.user_id = u.user_id AND m.org_id = ANY(CAST(:o AS uuid[]))
    ))
    {extra}
    ORDER BY u.username
    LIMIT :limit OFFSET :offset
"""


@router.get("")
def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("iam.user.read")),
):
    allowed = _scope(db, current_user.user_id, "iam.user.read")
    rows = db.execute(text(_LIST_SQL.format(extra="")), {"o": allowed, "limit": limit, "offset": offset}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/search")
def search_users(
    q: str = Query(..., min_length=3, max_length=50),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("iam.user.read")),
):
    allowed = _scope(db, current_user.user_id, "iam.user.read")
    extra = "AND (u.username ILIKE :s OR u.email ILIKE :s)"
    rows = db.execute(text(_LIST_SQL.format(extra=extra)),
                      {"o": allowed, "s": f"%{q}%", "limit": 10, "offset": 0}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db),
                current_user=Depends(require_permission("iam.user.create"))):
    d = payload.details
    try:
        new_user = db.execute(text("""
            INSERT INTO iam.users (username, email, password_hash, full_name)
            VALUES (:username, :email, :pw, :full_name)
            RETURNING user_id, username, email, full_name, is_active, created_at
        """), {"username": payload.username, "email": payload.email,
               "pw": hash_password(payload.password), "full_name": payload.full_name}).fetchone()

        db.execute(text("""
            INSERT INTO iam.user_details_log
                (user_id, full_name, identity_number, position_title, phone_number, avatar_url, updated_by)
            VALUES (:uid, :full_name, :idn, :pos, :phone, :avatar, :actor)
        """), {"uid": new_user.user_id, "full_name": payload.full_name,
               "idn": d.identity_number if d else None, "pos": d.position_title if d else None,
               "phone": d.phone_number if d else None, "avatar": d.avatar_url if d else None,
               "actor": current_user.user_id})

        log_audit(db, current_user.user_id, "CREATE_USER", "users", new_user.user_id,
                  {"username": payload.username, "email": payload.email})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username atau email sudah dipakai")
    return dict(new_user._mapping)


@router.get("/{user_id}")
def get_user(user_id: UUID, db: Session = Depends(get_db),
             current_user=Depends(require_permission("iam.user.read"))):
    _check_target(db, user_id, _scope(db, current_user.user_id, "iam.user.read"))
    row = db.execute(text("""
        SELECT u.user_id, u.username, u.email, u.full_name, u.is_active, u.created_at,
               d.identity_number, d.position_title, d.phone_number, d.avatar_url
        FROM iam.users u
        LEFT JOIN LATERAL (
            SELECT identity_number, position_title, phone_number, avatar_url
            FROM iam.user_details_log WHERE user_id = u.user_id ORDER BY valid_from DESC LIMIT 1
        ) d ON TRUE
        WHERE u.user_id = :u
    """), {"u": user_id}).fetchone()
    return dict(row._mapping)


@router.patch("/{user_id}")
def update_user(user_id: UUID, payload: UserUpdate, db: Session = Depends(get_db),
                current_user=Depends(require_permission("iam.user.update"))):
    _check_target(db, user_id, _scope(db, current_user.user_id, "iam.user.update"))
    if user_id == current_user.user_id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Tidak bisa menonaktifkan akun sendiri")
    try:
        row = db.execute(text("""
            UPDATE iam.users SET
                email = COALESCE(:email, email),
                full_name = COALESCE(:full_name, full_name),
                is_active = COALESCE(:is_active, is_active)
            WHERE user_id = :u
            RETURNING user_id, username, email, full_name, is_active
        """), {"email": payload.email, "full_name": payload.full_name,
               "is_active": payload.is_active, "u": user_id}).fetchone()
        log_audit(db, current_user.user_id, "UPDATE_USER", "users", user_id,
                  payload.model_dump(exclude_none=True))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email sudah dipakai")
    return dict(row._mapping)


@router.delete("/{user_id}")
def deactivate_user(user_id: UUID, db: Session = Depends(get_db),
                    current_user=Depends(require_permission("iam.user.delete"))):
    _check_target(db, user_id, _scope(db, current_user.user_id, "iam.user.delete"))
    if user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Tidak bisa menonaktifkan akun sendiri")
    db.execute(text("UPDATE iam.users SET is_active = FALSE WHERE user_id = :u"), {"u": user_id})
    log_audit(db, current_user.user_id, "DEACTIVATE_USER", "users", user_id)
    db.commit()
    return {"status": "success"}


@router.post("/{user_id}/send-reset-link")
def send_reset_link(user_id: UUID, background: BackgroundTasks, db: Session = Depends(get_db),
                    current_user=Depends(require_permission("iam.user.password_reset"))):
    _check_target(db, user_id, _scope(db, current_user.user_id, "iam.user.password_reset"))
    if not smtp_ready():
        raise HTTPException(status_code=503, detail="Layanan email belum dikonfigurasi")
    target = db.execute(text("SELECT email, is_active FROM iam.users WHERE user_id = :u"),
                        {"u": user_id}).fetchone()
    if not target.is_active:
        raise HTTPException(status_code=400, detail="User nonaktif")

    token = secrets.token_urlsafe(32)
    db.execute(text("DELETE FROM iam.password_reset_tokens WHERE user_id = :u AND used_at IS NULL"),
               {"u": user_id})
    db.execute(text("""
        INSERT INTO iam.password_reset_tokens (token_hash, user_id, expires_at)
        VALUES (:h, :u, :e)
    """), {"h": hashlib.sha256(token.encode()).hexdigest(), "u": user_id,
           "e": datetime.now(timezone.utc) + timedelta(minutes=30)})
    log_audit(db, current_user.user_id, "SEND_RESET_LINK", "users", user_id)
    db.commit()

    link = f"{FRONTEND_URL}/reset-password?token={token}"
    background.add_task(send_email, target.email, "Reset password Darkhive",
                        f"Klik link berikut untuk membuat password baru (berlaku 30 menit):\n\n{link}\n\n"
                        "Abaikan email ini jika Anda tidak memintanya.")
    return {"status": "success"}


@router.get("/{user_id}/access")
def get_user_access(user_id: UUID, db: Session = Depends(get_db),
                    current_user=Depends(require_permission("iam.user.read"))):
    _check_target(db, user_id, _scope(db, current_user.user_id, "iam.user.read"))
    rows = db.execute(text("""
        SELECT m.mapping_id, m.is_active, m.org_id, o.org_code,
               m.app_id, a.app_code, a.app_name, m.role_id, r.role_code, r.role_name
        FROM iam.user_organization_roles m
        LEFT JOIN iam.organizations o ON o.org_id = m.org_id
        LEFT JOIN iam.applications a ON a.app_id = m.app_id
        JOIN iam.roles r ON r.role_id = m.role_id
        WHERE m.user_id = :u ORDER BY a.app_name, o.org_code
    """), {"u": user_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/{user_id}/details-history")
def get_user_details_history(user_id: UUID, db: Session = Depends(get_db),
                             current_user=Depends(require_permission("iam.user.read"))):
    _check_target(db, user_id, _scope(db, current_user.user_id, "iam.user.read"))
    rows = db.execute(text("""
        SELECT log_id, full_name, identity_number, position_title, phone_number, avatar_url,
               valid_from, updated_by
        FROM iam.user_details_log WHERE user_id = :u ORDER BY valid_from DESC
    """), {"u": user_id}).fetchall()
    return [dict(r._mapping) for r in rows]