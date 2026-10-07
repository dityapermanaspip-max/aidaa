from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import unit_read, auditor_create, setting_read, setting_update, log_audit
from app.schemas.org_options import OrgOptionOut, AuditorCandidateOut, AuditSettingIn, AuditSettingOut
from app.services import org_options as svc
from app.services import audit_setting as ssvc

router = APIRouter()


@router.get("/org-options", response_model=List[OrgOptionOut])
def org_options(db: Session = Depends(get_db), user=Depends(unit_read)):
    return svc.list_org_options(db, user.user_id)


@router.get("/auditor-candidates", response_model=List[AuditorCandidateOut])
def auditor_candidates(db: Session = Depends(get_db), user=Depends(auditor_create)):
    return svc.list_auditor_candidates(db, user.user_id)


@router.get("/audit-setting", response_model=AuditSettingOut)
def get_audit_setting(db: Session = Depends(get_db), user=Depends(setting_read)):
    return ssvc.get_setting(db, user.user_id)


@router.put("/audit-setting", response_model=AuditSettingOut)
def put_audit_setting(payload: AuditSettingIn, db: Session = Depends(get_db), user=Depends(setting_update)):
    row = ssvc.set_iau(db, user.user_id, payload.iau_org_id)
    log_audit(db, user.user_id, "audit_setting.set_iau", "audit_setting", payload.iau_org_id,
              {"root_org_id": str(row["root_org_id"])})
    db.commit()
    return row