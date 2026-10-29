"""Fixtures for the authorisation tests.

Every test runs inside a transaction that is rolled back, so the rows it creates
(users, organisations, role mappings) never reach the dev database. The tests use
the real IAM views on purpose: the recursion over the org tree is the part that
must be proven, not a Python double.
"""

from types import SimpleNamespace
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


@pytest.fixture()
def quiz(db):
    """One issued questionnaire with a single free-text question, inside the rollback transaction.

    The chain mirrors what the app creates: org -> auditable unit -> audit type -> assignment ->
    PKA -> procedure -> questionnaire -> question. Everything is uncommitted, so the transaction
    rollback leaves no rows; the capacity advisory lock the service takes is released with it.
    """
    suffix = uuid4().hex[:10].upper()
    org = db.execute(text(
        "INSERT INTO iam.organizations (org_code) VALUES (:c) RETURNING org_id"
    ), {"c": f"PYTEST-Q-{suffix}"}).scalar_one()
    unit = db.execute(text("""
        INSERT INTO aidaa_core.ref_auditable_unit (unit_code, unit_name, org_id, root_org_id)
        VALUES (:c, 'Pytest Unit', :o, :o) RETURNING unit_id
    """), {"c": f"PY-Q-{suffix}", "o": str(org)}).scalar_one()
    type_id = db.execute(text("""
        INSERT INTO aidaa_core.ref_audit_type (type_code, type_name, root_org_id)
        VALUES (:c, 'Pytest Type', :o) RETURNING type_id
    """), {"c": f"PY-Q-{suffix}", "o": str(org)}).scalar_one()
    assignment = db.execute(text("""
        INSERT INTO aidaa_core.assignment
            (assignment_no, unit_id, type_id, start_date, end_date, status, owner_org_id)
        VALUES (:n, :u, :t, CURRENT_DATE, CURRENT_DATE, 'issued', :o) RETURNING assignment_id
    """), {"n": f"PY-Q-{suffix}", "u": str(unit), "t": str(type_id), "o": str(org)}).scalar_one()
    pka = db.execute(text("""
        INSERT INTO aidaa_core.pka (assignment_id, title) VALUES (:a, 'Pytest PKA') RETURNING pka_id
    """), {"a": str(assignment)}).scalar_one()
    procedure = db.execute(text("""
        INSERT INTO aidaa_core.exe_procedure (pka_id, step_no, procedure_text)
        VALUES (:k, 1, 'Pytest step') RETURNING procedure_id
    """), {"k": str(pka)}).scalar_one()
    questionnaire = db.execute(text("""
        INSERT INTO aidaa_core.assignment_questionnaire
            (procedure_id, assignment_id, unit_id, title, status, respondents_needed,
             public_token, link_expires_at, issued_at)
        VALUES (:p, :a, :u, 'Pytest questionnaire', 'issued', 1, :tok,
                now() + interval '1 hour', now())
        RETURNING questionnaire_id, public_token
    """), {"p": str(procedure), "a": str(assignment), "u": str(unit),
           "tok": str(uuid4())}).one()
    question = db.execute(text("""
        INSERT INTO aidaa_core.questionnaire_question
            (questionnaire_id, question_no, kind, question_text)
        VALUES (:q, 1, 'free_text', 'Pytest question') RETURNING question_id
    """), {"q": str(questionnaire.questionnaire_id)}).scalar_one()

    return SimpleNamespace(
        org=org, unit=unit, type_id=type_id, assignment=assignment,
        questionnaire_id=questionnaire.questionnaire_id,
        token=questionnaire.public_token, question_id=question,
    )
