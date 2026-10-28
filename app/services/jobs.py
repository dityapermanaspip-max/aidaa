"""The job contract shared by the API (enqueue, poll) and the worker (claim, finish, fail).

Why a table and not Redis: the only producer and consumer are this backend, the volume is a few
dozen AI calls and a handful of scans per day, and the database is already the source of truth for
the suggestion rows. `FOR UPDATE SKIP LOCKED` gives several worker processes without double work.

A row never leaves 'queued'/'running' silently: `locked_at` is refreshed when a worker claims a job
and `claim()` also reclaims a running row older than JOB_STALE_MINUTES, so a killed worker cannot
park a request forever.
"""
import json
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit_setting import ROOT_ATTR

JOB_STALE_MINUTES = int(os.getenv("JOB_STALE_MINUTES", "30"))

_JOB_COLUMNS = """
    job_id, job_type, status, user_id, payload, result, error, attempts,
    created_at, started_at, finished_at
"""


def _json_default(value):
    """Services return rows with UUID/date/Decimal values; the old pydantic response serialised them
    the same way, so the polled result keeps the exact shape the front end already expects."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def to_json(value) -> str:
    return json.dumps(value, default=_json_default)


def enqueue(db: Session, user_id: UUID, job_type: str, args: dict,
            audit: Optional[dict] = None) -> dict:
    """Insert a queued job and commit. The caller has already authorised the request.

    `audit` is replayed by the worker after a successful run: {"action", "target_type", "metadata"}.
    The active AIDAA root is copied from the request session so the worker derives the same root a
    multi-root user picked (trip, library, budget and SBM services read it).
    """
    root = getattr(db, ROOT_ATTR, None)
    payload = {"args": args}
    if root is not None:
        payload["root_id"] = str(root)
    if audit:
        payload["audit"] = audit

    row = db.execute(text("""
        INSERT INTO aidaa_core.job (job_type, user_id, payload)
        VALUES (:t, CAST(:u AS uuid), CAST(:p AS jsonb))
        RETURNING job_id, status
    """), {"t": job_type, "u": str(user_id), "p": to_json(payload)}).fetchone()
    db.commit()
    return {"job_id": row.job_id, "status": row.status}


def get_job(db: Session, job_id: UUID, user_id: UUID) -> dict:
    """Owner-scoped poll: a job id is not a capability, so another user's id reads as 404."""
    row = db.execute(text(f"""
        SELECT {_JOB_COLUMNS} FROM aidaa_core.job
        WHERE job_id = CAST(:j AS uuid) AND user_id = CAST(:u AS uuid)
    """), {"j": str(job_id), "u": str(user_id)}).mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


def claim(db: Session) -> Optional[dict]:
    """Take the oldest queued job (or a stale running one). Commit before the slow work starts."""
    row = db.execute(text(f"""
        UPDATE aidaa_core.job j
        SET status = 'running',
            attempts = j.attempts + 1,
            locked_at = now(),
            started_at = COALESCE(j.started_at, now())
        WHERE j.job_id = (
            SELECT job_id FROM aidaa_core.job
            WHERE status = 'queued'
               OR (status = 'running' AND locked_at < now() - make_interval(mins => :stale))
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING {_JOB_COLUMNS}
    """), {"stale": JOB_STALE_MINUTES}).mappings().fetchone()
    if row is None:
        db.rollback()
        return None
    db.commit()
    return dict(row)


def finish(db: Session, job_id: UUID, result: dict) -> None:
    db.execute(text("""
        UPDATE aidaa_core.job
        SET status = 'done', result = CAST(:r AS jsonb), error = NULL, finished_at = now()
        WHERE job_id = CAST(:j AS uuid)
    """), {"j": str(job_id), "r": to_json(result)})


def fail(db: Session, job_id: UUID, error: str) -> None:
    db.execute(text("""
        UPDATE aidaa_core.job
        SET status = 'failed', error = :e, finished_at = now()
        WHERE job_id = CAST(:j AS uuid)
    """), {"j": str(job_id), "e": (error or "unknown error")[:2000]})
