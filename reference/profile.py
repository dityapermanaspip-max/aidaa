from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.api.dependencies import get_current_user, log_audit
from app.schemas.iam import UserDetailsUpdate, PasswordChange

router = APIRouter(prefix="/me", tags=["Profile"])


@router.get("")
def get_my_profile(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT u.user_id, u.username, u.email, u.full_name, u.is_active, u.created_at,
               d.identity_number, d.position_title, d.phone_number, d.avatar_url
        FROM iam.users u
        LEFT JOIN LATERAL (
            SELECT identity_number, position_title, phone_number, avatar_url
            FROM iam.user_details_log WHERE user_id = u.user_id
            ORDER BY valid_from DESC LIMIT 1
        ) d ON TRUE
        WHERE u.user_id = :uid
    """), {"uid": current_user.user_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return dict(row._mapping)


@router.put("/details", status_code=status.HTTP_201_CREATED)
def update_my_details(payload: UserDetailsUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    row = db.execute(text("""
        INSERT INTO iam.user_details_log
            (user_id, full_name, identity_number, position_title, phone_number, avatar_url, updated_by)
        VALUES (:uid, :full_name, :identity_number, :position_title, :phone_number, :avatar_url, :uid)
        RETURNING log_id, valid_from
    """), {"uid": current_user.user_id, **payload.model_dump()}).fetchone()
    db.execute(text("UPDATE iam.users SET full_name = :n WHERE user_id = :uid"),
               {"n": payload.full_name, "uid": current_user.user_id})
    log_audit(db, current_user.user_id, "UPDATE_MY_DETAILS", "user_details_log", row.log_id)
    db.commit()
    return {"status": "success", "log_id": str(row.log_id), "valid_from": row.valid_from}


@router.get("/details-history")
def get_my_details_history(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT log_id, full_name, identity_number, position_title, phone_number, avatar_url, valid_from
        FROM iam.user_details_log WHERE user_id = :uid ORDER BY valid_from DESC
    """), {"uid": current_user.user_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/change-password")
def change_my_password(payload: PasswordChange, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    current_hash = db.execute(text("SELECT password_hash FROM iam.users WHERE user_id = :uid"),
                              {"uid": current_user.user_id}).scalar_one()
    if not verify_password(payload.old_password, current_hash):
        raise HTTPException(status_code=400, detail="Password lama salah")
    
    db.execute(text("UPDATE iam.users SET password_hash = :h, token_version = token_version + 1 WHERE user_id = :uid"),
               {"h": hash_password(payload.new_password), "uid": current_user.user_id})
    log_audit(db, current_user.user_id, "CHANGE_PASSWORD", "users", current_user.user_id)
    db.commit()
    return {"status": "success"}