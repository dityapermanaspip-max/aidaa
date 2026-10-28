"""PDF text extraction (text layer first, OCR for empty pages) and the worker's spool file.

The parsing used to live in the HTTP router, where a 100-page scan at 300 DPI blocked a request
thread and a pooled database connection for minutes. It now runs in app/worker.py: the endpoint
writes the upload to ``SPOOL_DIR`` and the worker reads it, extracts, and deletes it. The spool is
short-lived scratch space, not storage, but the API and the worker must see the same directory
(same host, or a shared volume).
"""
import io
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.core import config

PDF_MAGIC = b"%PDF"
MAX_BYTES = 25 * 1024 * 1024


def _ocr_page(page) -> str:
    # Imported inside the function so the app still starts when Tesseract is not installed.
    import pytesseract
    from PIL import Image

    if config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
    pix = page.get_pixmap(dpi=config.OCR_DPI)
    return pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))), lang=config.OCR_LANGS)


def extract_text(data: bytes, filename: str = "") -> dict:
    """Get text from a PDF: text layer first, OCR only for empty pages.

    Mirrors GrIMIS app/routers/doc_extract.py.
    """
    try:
        import pymupdf  # PyMuPDF
    except ImportError:
        raise HTTPException(status_code=501, detail="Ekstraksi PDF belum terpasang (pasang PyMuPDF)")
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File terlalu besar (maks {MAX_BYTES // (1024 * 1024)} MB)")
    if not data.lstrip()[:5].startswith(PDF_MAGIC):
        raise HTTPException(status_code=400, detail="Hanya PDF yang didukung")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=400, detail="PDF tidak bisa dibaca")
    try:
        pages = doc.page_count
        if pages == 0:
            raise HTTPException(status_code=400, detail="PDF tidak punya halaman")
        if pages > config.OCR_MAX_PAGES:
            raise HTTPException(status_code=413, detail=f"PDF punya {pages} halaman, maksimal {config.OCR_MAX_PAGES}")

        chunks, methods, warnings = [], set(), []
        for i in range(pages):
            page = doc.load_page(i)
            raw = page.get_text("text") or ""
            if len(raw.strip()) >= config.OCR_MIN_TEXT_PER_PAGE:
                chunks.append(raw)
                methods.add("text-layer")
                continue
            try:
                ocr = _ocr_page(page)
            except Exception as exc:  # Tesseract missing, broken image, and the like
                warnings.append(f"Halaman {i + 1}: OCR gagal ({exc})")
                ocr = ""
            if not ocr.strip():
                warnings.append(f"Halaman {i + 1}: tidak ada teks terbaca")
            chunks.append(ocr)
            methods.add("tesseract")

        method = "mixed" if len(methods) > 1 else (next(iter(methods)) if methods else "text-layer")
        full = "".join(f"\n\n===== HALAMAN {i + 1} =====\n{t}" for i, t in enumerate(chunks))
        return {"text": full, "pages": pages, "method": method, "warnings": warnings, "filename": filename}
    finally:
        doc.close()


def extract_text_from_path(path: str, filename: str = "") -> dict:
    with open(path, "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    return extract_text(data, filename)


# --- spool: the upload waits here between the endpoint and the worker ---

def spool_root() -> Path:
    root = Path(config.SPOOL_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def spool_pdf(data: bytes) -> str:
    root = spool_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid4().hex}.pdf"
    path.write_bytes(data)
    return str(path)


def remove_spooled(path: str) -> None:
    """Delete a spool file, but only one inside SPOOL_DIR (a job payload is data, not a path grant)."""
    target = Path(path).resolve()
    if spool_root() in target.parents:
        try:
            os.remove(target)
        except FileNotFoundError:
            pass
