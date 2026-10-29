"""Fixtures for the authorisation tests.

Every test runs inside a transaction that is rolled back, so the rows it creates
(users, organisations, role mappings) never reach the dev database. The tests use
the real IAM views on purpose: the recursion over the org tree is the part that
must be proven, not a Python double.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import engine


@pytest.fixture()
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def make_user(db):
    def _make():
        suffix = uuid4().hex[:12]
        return db.execute(text("""
            INSERT INTO iam.users (username, email, password_hash, full_name)
            VALUES (:u, :e, 'not-a-real-hash', 'Pytest User')
            RETURNING user_id
        """), {"u": f"pytest-{suffix}", "e": f"pytest-{suffix}@example.test"}).scalar_one()

    return _make


@pytest.fixture()
def grant(db):
    def _grant(user_id, role_code: str, org_id=None, app_id=None):
        db.execute(text("""
            INSERT INTO iam.user_organization_roles (user_id, org_id, app_id, role_id)
            SELECT CAST(:u AS uuid), CAST(:o AS uuid), CAST(:a AS uuid), r.role_id
            FROM iam.roles r WHERE r.role_code = :role
        """), {"u": str(user_id), "o": str(org_id) if org_id else None,
               "a": str(app_id) if app_id else None, "role": role_code})

    return _grant


@pytest.fixture()
def make_org(db):
    def _make(parent=None):
        code = f"PYTEST-{uuid4().hex[:10].upper()}"
        root = None
        if parent is not None:
            root = db.execute(text(
                "SELECT COALESCE(root_org_id, org_id) FROM iam.organizations WHERE org_id = :p"
            ), {"p": str(parent)}).scalar_one()
        return db.execute(text("""
            INSERT INTO iam.organizations (org_code, parent_id, root_org_id)
            VALUES (:code, CAST(:parent AS uuid), CAST(:root AS uuid))
            RETURNING org_id
        """), {"code": code, "parent": str(parent) if parent else None,
               "root": str(root) if root else None}).scalar_one()

    return _make


@pytest.fixture()
def app_scope(db):
    """An existing, app-enabled root and one of its descendants.

    ``get_user_accessible_org_ids`` joins ``v_active_organization_applications``,
    derived from IAM's org-application rows; a brand-new org has no such row, so
    this check borrows a seeded root that already has the AIDAA app enabled.
    """
    from types import SimpleNamespace

    app_id, root = db.execute(text("""
        SELECT m.app_id, o.root_org_id
        FROM iam.user_organization_roles m
        JOIN iam.roles r ON r.role_id = m.role_id
        JOIN iam.organizations o ON o.org_id = m.org_id
        WHERE r.role_code LIKE 'AIDAA.%' AND m.org_id IS NOT NULL
          AND m.app_id IS NOT NULL AND o.root_org_id IS NOT NULL
        LIMIT 1
    """)).one()
    child = db.execute(text("""
        SELECT org_id FROM iam.organizations
        WHERE COALESCE(root_org_id, org_id) = :root AND org_id <> :root
        ORDER BY org_code LIMIT 1
    """), {"root": root}).scalar_one()
    return SimpleNamespace(app_id=app_id, root=root, child=child)
