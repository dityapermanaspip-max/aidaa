from jose import jwt
from app.core.config import JWT_SECRET_KEY, JWT_ALGORITHM


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None