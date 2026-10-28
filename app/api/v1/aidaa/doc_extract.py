"""PDF upload: spool the file and let the worker extract it.

OCR is CPU work (a 100-page scan at 300 DPI is minutes), so it no longer runs on the request thread.
The endpoint validates size and type immediately, writes the upload to SPOOL_DIR and returns 202
with a job id; GET /jobs/{id} carries the same payload the old synchronous endpoint returned.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.schemas.jobs import JobAccepted
from app.services import doc_text
from app.services import jobs as jobsvc
from app.services.doc_text import MAX_BYTES, PDF_MAGIC, extract_text  # noqa: F401  (compat re-export)

router = APIRouter()


@router.post("/documents/extract", response_model=JobAccepted, status_code=202)
async def extract_document(file: UploadFile = File(...), db: Session = Depends(get_db),
                           user=Depends(get_current_user)):
    """Accept a PDF, queue its text extraction. Reads no audit data, so authentication is enough."""
    # Cap the read itself: a huge body is never fully buffered before the 413.
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_BYTES // (1024 * 1024)} MB)")
    if not data.lstrip()[:5].startswith(PDF_MAGIC):
        raise HTTPException(status_code=400, detail="Hanya PDF yang didukung")
    path = doc_text.spool_pdf(data)
    try:
        return jobsvc.enqueue(db, user.user_id, "doc.extract",
                              {"path": path, "filename": file.filename or ""})
    except Exception:  # no row, no reader: do not leave the upload behind
        doc_text.remove_spooled(path)
        raise
