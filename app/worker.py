"""AIDAA background worker: consumes aidaa_core.job (AI generation and PDF/OCR extraction).

Run one process next to the API:  python -m app.worker
Several processes are safe (the claim uses FOR UPDATE SKIP LOCKED). The worker needs the same
environment as the API, the same SPOOL_DIR, and Tesseract/PyMuPDF for document jobs.

A job's payload carries the service arguments and, for AI jobs, the audit entry the old synchronous
endpoint wrote, so the trail is identical to before the split. Failures are stored on the job row
(the HTTP detail for a handled error, the exception otherwise); nothing is retried automatically —
the user sees the message and decides whether to ask again.
"""
import logging
import os
import time
from uuid import UUID

from fastapi import HTTPException

from app.core.database import SessionLocal
from app.schemas.expertise_ai import ExpertiseExtractRequest
from app.schemas.library_ai import LibraryDraftRequest, LibraryImproveRequest
from app.schemas.plan_budget_ai import PlanBudgetRequest
from app.schemas.sbm_ai import SbmDraftRequest
from app.schemas.trip_ai import TripDraftRequest
from app.services import ai_suggestions
from app.services import doc_text
from app.services import expertise_ai
from app.services import jobs
from app.services import library_ai
from app.services import library_ai_improvement
from app.services import plan_budget_ai
from app.services import sbm_ai
from app.services import team_ai
from app.services import trip_ai
from app.services.audit_setting import ROOT_ATTR
from app.services.logs import log_audit

POLL_SECONDS = float(os.getenv("JOB_POLL_SECONDS", "1"))
logger = logging.getLogger("aidaa.worker")


def _ai_pka(db, user_id, args):
    return ai_suggestions.generate_pka(db, UUID(args["assignment_id"]), user_id,
                                       args.get("engine"), args.get("model"))


def _ai_report(db, user_id, args):
    return ai_suggestions.generate_report(db, UUID(args["assignment_id"]), user_id,
                                          args.get("engine"), args.get("model"))


def _ai_team(db, user_id, args):
    return team_ai.generate_suggestions(db, UUID(args["assignment_id"]), user_id,
                                        args.get("engine"), args.get("model"))


def _ai_trip_draft(db, user_id, args):
    return trip_ai.generate_draft(db, UUID(args["assignment_id"]),
                                  TripDraftRequest(**args["request"]), user_id)


def _ai_library_draft(db, user_id, args):
    return library_ai.generate_draft(db, LibraryDraftRequest(**args["request"]), user_id)


def _ai_library_improvement(db, user_id, args):
    return library_ai_improvement.generate_improvement(
        db, user_id, UUID(args["library_pka_id"]), LibraryImproveRequest(**args["request"]))


def _ai_expertise_extract(db, user_id, args):
    return expertise_ai.generate_extract(
        db, UUID(args["auditor_id"]), ExpertiseExtractRequest(**args["request"]), user_id)


def _ai_plan_budget(db, user_id, args):
    return plan_budget_ai.generate_draft(
        db, UUID(args["plan_id"]), PlanBudgetRequest(**args["request"]), user_id)


def _ai_sbm(db, user_id, args):
    return sbm_ai.generate_draft(db, SbmDraftRequest(**args["request"]), user_id)


def _doc_extract(db, user_id, args):
    return doc_text.extract_text_from_path(args["path"], args.get("filename") or "")


_HANDLERS = {
    "ai.pka": _ai_pka,
    "ai.report": _ai_report,
    "ai.team": _ai_team,
    "ai.trip_draft": _ai_trip_draft,
    "ai.library_draft": _ai_library_draft,
    "ai.library_improvement": _ai_library_improvement,
    "ai.expertise_extract": _ai_expertise_extract,
    "ai.plan_budget": _ai_plan_budget,
    "ai.sbm": _ai_sbm,
    "doc.extract": _doc_extract,
}


def _run(db, job: dict) -> None:
    payload = job["payload"] or {}
    args = payload.get("args") or {}
    job_id, user_id = job["job_id"], job["user_id"]

    if payload.get("root_id"):  # the root the caller picked, not a re-derived one
        setattr(db, ROOT_ATTR, UUID(payload["root_id"]))

    handler = _HANDLERS.get(job["job_type"])
    if handler is None:
        raise RuntimeError(f"unknown job type {job['job_type']!r}")

    result = handler(db, user_id, args)

    audit = payload.get("audit")
    if audit:
        meta = dict(audit.get("metadata") or {})
        for key in ("engine", "model_name"):  # known only after the AI answered
            if result.get(key):
                meta[key] = result[key]
        log_audit(db, user_id, audit["action"], audit["target_type"],
                  result.get("suggestion_id"), meta)

    jobs.finish(db, job_id, result)


def run_once() -> bool:
    """Claim and run one job. Returns False when the queue is empty."""
    db = SessionLocal()
    job = None
    try:
        job = jobs.claim(db)
        if job is None:
            return False
        started = time.monotonic()
        try:
            _run(db, job)
            db.commit()
            logger.info("job %s %s done in %.1fs", job["job_id"], job["job_type"],
                        time.monotonic() - started)
        except HTTPException as exc:
            db.rollback()
            jobs.fail(db, job["job_id"], str(exc.detail))
            db.commit()
            logger.warning("job %s %s failed: %s", job["job_id"], job["job_type"], exc.detail)
        except Exception as exc:
            db.rollback()
            jobs.fail(db, job["job_id"], f"{type(exc).__name__}: {exc}")
            db.commit()
            logger.exception("job %s %s crashed", job["job_id"], job["job_type"])
        return True
    finally:
        # The upload is scratch space even when the job failed.
        if job is not None and job["job_type"] == "doc.extract":
            path = ((job["payload"] or {}).get("args") or {}).get("path")
            if path:
                doc_text.remove_spooled(path)
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger.info("AIDAA worker started (poll %.1fs)", POLL_SECONDS)
    while True:
        try:
            worked = run_once()
        except KeyboardInterrupt:
            logger.info("AIDAA worker stopped")
            return
        except Exception:
            logger.exception("worker loop error")
            worked = False
            time.sleep(max(POLL_SECONDS, 5))  # a missing table or a dead DB must not spin the log
        if not worked:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
