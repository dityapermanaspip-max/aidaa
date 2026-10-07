import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.api.dependencies import oauth2_scheme, get_current_user, log_audit
from app.schemas.iam import TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

_DUMMY_HASH = hash_password("dummy-password-for-timing")
MAX_FAILS = 5
WINDOW = "15 minutes"


class ResetConfirm(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)
    new_password: str = Field(..., min_length=10, max_length=128)


@router.post("/login", response_model=TokenResponse)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ident = form_data.username.strip().lower()[:150]
    fwd = request.headers.get("x-forwarded-for", "")
    ip = (fwd.split(",")[0].strip() or (request.client.host if request.client else ""))[:64]

    fails = db.execute(text(f"""
        SELECT count(*) FROM iam.login_attempts
        WHERE attempted_at > now() - interval '{WINDOW}'
          AND (identifier = :i OR (:ip <> '' AND ip = :ip))
    """), {"i": ident, "ip": ip}).scalar_one()
    if fails >= MAX_FAILS:
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan. Coba lagi beberapa menit lagi.")

    user = db.execute(text("""
        SELECT user_id, username, password_hash, is_active, token_version
        FROM iam.users WHERE lower(username) = :i OR lower(email) = :i
    """), {"i": ident}).fetchone()

    ok = verify_password(form_data.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        db.execute(text("INSERT INTO iam.login_attempts (identifier, ip) VALUES (:i, :ip)"), {"i": ident, "ip": ip})
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db.execute(text("DELETE FROM iam.login_attempts WHERE identifier = :i"), {"i": ident})
    token = create_access_token({"user_id": str(user.user_id), "username": user.username, "tv": user.token_version})
    log_audit(db, user.user_id, "LOGIN", "users", user.user_id)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "user_id": user.user_id, "username": user.username}


@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    payload = decode_access_token(token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    db.execute(text("""
        INSERT INTO iam.revoked_tokens (jti, user_id, expires_at)
        VALUES (CAST(:jti AS uuid), :uid, :exp) ON CONFLICT (jti) DO NOTHING
    """), {"jti": payload["jti"], "uid": current_user.user_id, "exp": expires_at})
    log_audit(db, current_user.user_id, "LOGOUT", "users", current_user.user_id)
    db.commit()
    return {"status": "success"}


@router.post("/reset-password/confirm")
def confirm_reset(payload: ResetConfirm, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT user_id FROM iam.password_reset_tokens
        WHERE token_hash = :h AND used_at IS NULL AND expires_at > now()
    """), {"h": hashlib.sha256(payload.token.encode()).hexdigest()}).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Link tidak valid atau sudah kadaluarsa")
    db.execute(text("""
        UPDATE iam.users SET password_hash = :p, token_version = token_version + 1 WHERE user_id = :u
    """), {"p": hash_password(payload.new_password), "u": row.user_id})
    db.execute(text("UPDATE iam.password_reset_tokens SET used_at = now() WHERE user_id = :u"), {"u": row.user_id})
    log_audit(db, row.user_id, "RESET_PASSWORD", "users", row.user_id)
    db.commit()
    return {"status": "success"}