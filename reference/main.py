from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.iam import (
    auth, organizations, users, context,
    applications, permissions, roles, preferences, profile
)
import asyncio
import logging
from contextlib import asynccontextmanager
from sqlalchemy import text
from app.core.database import SessionLocal


def _cleanup():
    with SessionLocal() as db:
        db.execute(text("DELETE FROM iam.revoked_tokens WHERE expires_at < now()"))
        db.execute(text("DELETE FROM iam.password_reset_tokens WHERE expires_at < now() - interval '1 day'"))
        db.execute(text("DELETE FROM iam.login_attempts WHERE attempted_at < now() - interval '1 day'"))
        db.commit()


async def _cleanup_loop():
    while True:
        try:
            await asyncio.to_thread(_cleanup)
        except Exception:
            logging.exception("Cleanup gagal")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(
    title="Darkhive API Engine",
    description="Backend API untuk Enterprise Identity, Performance & Closed-Loop Risk System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1/iam"
app.include_router(auth.router, prefix=PREFIX, tags=["IAM - Auth"])
app.include_router(organizations.router, prefix=PREFIX, tags=["IAM - Organizations"])
app.include_router(users.router, prefix=PREFIX, tags=["IAM - Users"])
app.include_router(context.router, prefix=PREFIX, tags=["IAM - Context"])
app.include_router(applications.router, prefix=PREFIX, tags=["IAM - Applications"])
app.include_router(permissions.router, prefix=PREFIX, tags=["IAM - Permissions"])
app.include_router(roles.router, prefix=PREFIX, tags=["IAM - Roles"])
app.include_router(preferences.router, prefix=PREFIX, tags=["IAM - Preferences"])
app.include_router(profile.router, prefix=PREFIX, tags=["IAM - Profile"])


@app.get("/", tags=["Health Check"])
def root_check():
    return {"status": "online", "system": "Darkhive Core API", "version": "1.0.0"}
    
    