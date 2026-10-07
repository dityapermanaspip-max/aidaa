import json
from typing import Optional
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import APP_CODE


def _s(value) -> Optional[str]:
    return str(value) if value is not None else None


def log_approval(db: Session, record_type: str, record_id: UUID, step_code: Optional[str],
                 decision: str, actor_id: UUID, reason: Optional[str] = None):
    db.execute(text("""
        INSERT INTO aidaa_log.approval_log (record_type, record_id, step_code, decision, reason, actor_id)
        VALUES (:rt, CAST(:rid AS uuid), :step, :dec, :reason, CAST(:actor AS uuid))
    """), {"rt": record_type, "rid": str(record_id), "step": step_code, "dec": decision,
           "reason": reason, "actor": _s(actor_id)})


def log_status(db: Session, record_type: str, record_id: UUID, old_status: Optional[str],
               new_status: str, actor_id: UUID, by_ai: bool = False):
    db.execute(text("""
        INSERT INTO aidaa_log.status_log (record_type, record_id, old_status, new_status, by_ai, actor_id)
        VALUES (:rt, CAST(:rid AS uuid), :old, :new, :ai, CAST(:actor AS uuid))
    """), {"rt": record_type, "rid": str(record_id), "old": old_status, "new": new_status,
           "ai": by_ai, "actor": _s(actor_id)})


def log_edit(db: Session, table_name: str, record_id: UUID, field_name: str,
             old_value, new_value, actor_id: UUID, reason: Optional[str] = None):
    db.execute(text("""
        INSERT INTO aidaa_log.edit_log (table_name, record_id, field_name, old_value, new_value, reason, actor_id)
        VALUES (:tbl, CAST(:rid AS uuid), :field, :old, :new, :reason, CAST(:actor AS uuid))
    """), {"tbl": table_name, "rid": str(record_id), "field": field_name,
           "old": _s(old_value), "new": _s(new_value), "reason": reason, "actor": _s(actor_id)})


def log_comment(db: Session, record_type: str, record_id: UUID, comment_text: str, actor_id: UUID):
    db.execute(text("""
        INSERT INTO aidaa_log.comment_log (record_type, record_id, comment_text, actor_id)
        VALUES (:rt, CAST(:rid AS uuid), :txt, CAST(:actor AS uuid))
    """), {"rt": record_type, "rid": str(record_id), "txt": comment_text, "actor": _s(actor_id)})


def log_team(db: Session, action: str, actor_id: UUID, plan_id: Optional[UUID] = None,
             assignment_id: Optional[UUID] = None, auditor_id: Optional[UUID] = None,
             role: Optional[str] = None, reason: Optional[str] = None):
    db.execute(text("""
        INSERT INTO aidaa_log.team_log (plan_id, assignment_id, auditor_id, action, role, reason, actor_id)
        VALUES (CAST(:p AS uuid), CAST(:a AS uuid), CAST(:au AS uuid), :act, :role, :reason, CAST(:actor AS uuid))
    """), {"p": _s(plan_id), "a": _s(assignment_id), "au": _s(auditor_id), "act": action,
           "role": role, "reason": reason, "actor": _s(actor_id)})
           


def log_audit(db: Session, actor_id: UUID, action: str, target_type: str,
              target_id: Optional[UUID] = None, metadata: Optional[dict] = None):
    """Cross-app audit trail in iam.audit_log (the only iam table AIDAA writes to)."""
    meta = dict(metadata or {})
    meta["app"] = APP_CODE
    db.execute(text("""
        INSERT INTO iam.audit_log (actor_id, action, target_type, target_id, metadata)
        VALUES (CAST(:actor_id AS uuid), :action, :target_type,
                CAST(:target_id AS uuid), CAST(:metadata AS jsonb))
    """), {
        "actor_id": str(actor_id),
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id else None,
        "metadata": json.dumps(meta),
    })