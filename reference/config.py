import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DH_DB_HOST", os.getenv("DB_HOST", "localhost"))
DB_PORT = os.getenv("DH_DB_PORT", os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DH_DB_NAME", os.getenv("DB_NAME", "postgres"))
DB_USER = os.getenv("DH_DB_USER", os.getenv("DB_USER", "postgres"))
DB_PASSWORD = os.getenv("DH_DB_PASSWORD", os.getenv("DB_PASSWORD", ""))

if not DB_PASSWORD:
    raise ValueError("DH_DB_PASSWORD wajib diisi di .env")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY wajib diisi di .env dan minimal 32 karakter")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")