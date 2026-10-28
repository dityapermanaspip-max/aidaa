import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies import get_current_user
from app.core import config

router = APIRouter()

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

    Shared by the SBM AI import (and later the library AI draft), so the parsing logic
    is not duplicated. Mirrors GrIMIS app/routers/doc_extract.py.
    """
    try:
        import pymupdf  # PyMuPDF
    except ImportError:
        raise HTTPException(status_code=501, detail="Ekstraksi PDF belum terpasang (pasang PyMuPDF)")
    if not data:
        raise HTTPException(status_code=400, detail="File kosong")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File terlalu besar (maks {MAX_BYTES // (1024 * 1024)} MB)")
    if not data.lstrip()[:5].startswith(b"%PDF"):
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


@router.post("/documents/extract")
async def extract_document(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Accept a PDF, return its text. Reads no audit data, so authentication is enough."""
    # Cap the read itself: a huge body is never fully buffered before the 413 (audit #2).
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_BYTES // (1024 * 1024)} MB)")
    return extract_text(data, file.filename or "")
