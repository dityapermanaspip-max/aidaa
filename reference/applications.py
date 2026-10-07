from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import require_permission, require_global_permission, log_audit

router = APIRouter(prefix="/applications", tags=["Applications"])

_COLS = "app_id, app_code, app_name, description, is_active, created_at"


class AppCreate(BaseModel):
    app_code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z][A-Z0-9_]*$")
    app_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None


class AppUpdate(BaseModel):
    app_name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


def _get_app(db: Session, app_id: UUID):
    row = db.execute(text(f"SELECT {_COLS} FROM iam.applications WHERE app_id = :a"), {"a": app_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    return row


@router.get("")
def list_applications(db: Session = Depends(get_db), current_user=Depends(require_permission("iam.app.read"))):
    rows = db.execute(text(f"SELECT {_COLS} FROM iam.applications ORDER BY app_name")).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/{app_id}")
def get_application(app_id: UUID, db: Session = Depends(get_db),
                    current_user=Depends(require_permission("iam.app.read"))):
    return dict(_get_app(db, app_id)._mapping)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(payload: AppCreate, db: Session = Depends(get_db),
                       current_user=Depends(require_global_permission("iam.app.create"))):
    try:
        row = db.execute(text(f"""
            INSERT INTO iam.applications (app_code, app_name, description)
            VALUES (:c, :n, :d) RETURNING {_COLS}
        """), {"c": payload.app_code, "n": payload.app_name, "d": payload.description}).fetchone()
        log_audit(db, current_user.user_id, "CREATE_APP", "applications", row.app_id, {"app_code": payload.app_code})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Kode aplikasi sudah dipakai")
    return dict(row._mapping)


@router.patch("/{app_id}")
def update_application(app_id: UUID, payload: AppUpdate, db: Session = Depends(get_db),
                       current_user=Depends(require_global_permission("iam.app.update"))):
    current = _get_app(db, app_id)
    if current.app_code == "IAM" and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Aplikasi IAM tidak boleh dinonaktifkan")
    row = db.execute(text(f"""
        UPDATE iam.applications SET
            app_name = COALESCE(:n, app_name),
            description = COALESCE(:d, description),
            is_active = COALESCE(:a, is_active)
        WHERE app_id = :id RETURNING {_COLS}
    """), {"n": payload.app_name, "d": payload.description, "a": payload.is_active, "id": app_id}).fetchone()
    log_audit(db, current_user.user_id, "UPDATE_APP", "applications", app_id, payload.model_dump(exclude_none=True))
    db.commit()
    return dict(row._mapping)


@router.delete("/{app_id}")
def deactivate_application(app_id: UUID, db: Session = Depends(get_db),
                           current_user=Depends(require_global_permission("iam.app.delete"))):
    current = _get_app(db, app_id)
    if current.app_code == "IAM":
        raise HTTPException(status_code=400, detail="Aplikasi IAM tidak boleh dinonaktifkan")
    db.execute(text("UPDATE iam.applications SET is_active = FALSE WHERE app_id = :a"), {"a": app_id})
    log_audit(db, current_user.user_id, "DEACTIVATE_APP", "applications", app_id)
    db.commit()
    return {"status": "success"}