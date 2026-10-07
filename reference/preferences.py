import json
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.schemas.iam import UserPreferenceUpdate

router = APIRouter(prefix="/me/preferences", tags=["Preferences"])

_MODES = {"dark", "warm-light", "custom"}
_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")


@router.get("")
def get_my_preferences(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    row = db.execute(text("""
        SELECT user_id, theme_mode, custom_theme FROM iam.user_preferences WHERE user_id = :u
    """), {"u": current_user.user_id}).fetchone()
    if not row:
        return {"user_id": str(current_user.user_id), "theme_mode": "dark", "custom_theme": None}
    return {"user_id": str(row.user_id), "theme_mode": row.theme_mode, "custom_theme": row.custom_theme}


@router.put("")
def update_my_preferences(payload: UserPreferenceUpdate, db: Session = Depends(get_db),
                          current_user=Depends(get_current_user)):
    if payload.theme_mode not in _MODES:
        raise HTTPException(status_code=422, detail="theme_mode harus dark, warm-light, atau custom")

    theme = None
    if payload.theme_mode == "custom":
        if not payload.custom_theme:
            raise HTTPException(status_code=422, detail="custom_theme wajib untuk mode custom")
        theme = payload.custom_theme.model_dump()
        if not all(_COLOR.match(v) for v in theme.values()):
            raise HTTPException(status_code=422, detail="Warna harus berformat hex, contoh #1a2b3c")

    row = db.execute(text("""
        INSERT INTO iam.user_preferences (user_id, theme_mode, custom_theme, updated_at)
        VALUES (:u, :m, CAST(:t AS jsonb), now())
        ON CONFLICT (user_id) DO UPDATE SET
            theme_mode = EXCLUDED.theme_mode,
            custom_theme = EXCLUDED.custom_theme,
            updated_at = now()
        RETURNING user_id, theme_mode, custom_theme
    """), {"u": current_user.user_id, "m": payload.theme_mode,
           "t": json.dumps(theme) if theme else None}).fetchone()
    db.commit()
    return {"user_id": str(row.user_id), "theme_mode": row.theme_mode, "custom_theme": row.custom_theme}