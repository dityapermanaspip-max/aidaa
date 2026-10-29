import os
from dotenv import load_dotenv

# Loads variables from local .env file first, overriding system environment vars if necessary
load_dotenv()

# Database Connectivity
DB_HOST = os.getenv("DH_DB_HOST", os.getenv("DB_HOST", "localhost"))
DB_PORT = os.getenv("DH_DB_PORT", os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DH_DB_NAME", os.getenv("DB_NAME", "postgres"))
DB_USER = os.getenv("DH_DB_USER", os.getenv("DB_USER", "postgres"))
DB_PASSWORD = os.getenv("DH_DB_PASSWORD", os.getenv("DB_PASSWORD", ""))

if not DB_PASSWORD:
    raise ValueError("DH_DB_PASSWORD must be set in .env")

# Connection budget (docs/ops/connection-budget.md). Every API worker and every `app.worker`
# process owns its own pool, so the limit that matters is processes x (size + overflow), not one
# pool. Defaults keep five processes (IAM, AIDAA API, AIDAA worker, GRiMIS, HILDA) at 75 of
# Postgres' 100 connections. pool_timeout is short so a saturated pool fails before the BFF's
# 180 s timeout; pool_recycle drops connections a proxy would have already closed.
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "10"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

# JWT Security Settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY must be set in .env and minimum 32 characters long.")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# App identity
APP_CODE = "AIDAA"

# Browser origins allowed to call this API directly (comma-separated). Normal traffic comes
# through the Next.js BFF server-side, so localhost is enough in development; production lists
# the real site origins. "*" is not supported: credentials are enabled and browsers reject the
# wildcard with credentials.
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Cloud engine behind WEB_API: any OpenAI-compatible provider (default DeepSeek).
WEB_API_KEY = os.getenv("WEB_API_KEY", "").strip() or None
WEB_API_BASE_URL = os.getenv("WEB_API_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
WEB_API_MODEL = os.getenv("WEB_API_MODEL", "deepseek-flash")
# "enabled"|"disabled" (DeepSeek thinking toggle); any other value omits the field for strict providers.
_raw_thinking = os.getenv("WEB_API_THINKING", "disabled").strip().lower()
WEB_API_THINKING = _raw_thinking if _raw_thinking in ("enabled", "disabled") else ""

# Standardized default engine identifiers to match API & DB schemas ("OLLAMA" or "WEB_API")
_raw_engine = os.getenv("AI_ENGINE", "WEB_API").upper()
AI_ENGINE = "WEB_API" if _raw_engine in ("WEB_API", "CLOUD", "GEMINI") else "OLLAMA"

AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "300"))  # seconds per attempt, local models can be slow
# One overall budget for the whole retry loop. The BFF gives up at 180 s, so a call that lives longer
# only burns a worker thread and a database connection for an answer nobody reads.
AI_DEADLINE = int(os.getenv("AI_DEADLINE", "120"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

# PDF extraction (mirror of IAM/GrIMIS values)
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "100"))
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
OCR_LANGS = os.getenv("OCR_LANGS", "ind+eng")
OCR_MIN_TEXT_PER_PAGE = int(os.getenv("OCR_MIN_TEXT_PER_PAGE", "20"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")  # only if tesseract is not on PATH

# Scratch directory shared by the API (writes an upload) and the worker (reads and deletes it).
SPOOL_DIR = os.getenv("SPOOL_DIR", "./spool")