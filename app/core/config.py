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

# JWT Security Settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY must be set in .env and minimum 32 characters long.")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# App identity
APP_CODE = "AIDAA"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Standardized default engine identifiers to match API & DB schemas ("OLLAMA" or "WEB_API")
_raw_engine = os.getenv("AI_ENGINE", "OLLAMA").upper()
AI_ENGINE = "WEB_API" if _raw_engine in ("WEB_API", "CLOUD", "GEMINI") else "OLLAMA"

AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "300"))  # seconds, local models can be slow
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")