from typing import List, Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import task_read, log_audit
from app.schemas.aidaa import TaskDecision, TaskOut
from app.services import approval as svc

router = APIRouter()


@router.get("/my-tasks", response_model=List[TaskOut])
def my_tasks(status: Literal["pending", "approved", "rejected", "returned", "cancelled"] = "pending",
             db: Session = Depends(get_db), user=Depends(task_read)):
    return svc.list_my_tasks(db, user.user_id, status)


@router.post("/tasks/{task_id}/decide", response_model=TaskOut)
def decide_task(task_id: UUID, payload: TaskDecision,
                db: Session = Depends(get_db), user=Depends(task_read)):
    row = svc.decide_task(db, task_id, user.user_id, payload)
    log_audit(db, user.user_id, f"task.{payload.decision}", "approval_task", task_id,
              {"record_type": row["record_type"], "record_id": str(row["record_id"]),
               "step_code": row["step_code"]})
    db.commit()
    return row