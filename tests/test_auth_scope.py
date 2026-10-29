"""Authorisation footprint #3: callable orgs, roots, PIC units and the request memo.

Each test seeds IAM rows inside a transaction that is rolled back, so the dev
database keeps no test users, orgs or mappings.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api import deps_org, deps_root
from app.api.deps_org import check_org_any_permission, get_user_accessible_org_ids
from app.core.database import engine
from app.services import roles
from app.services.audit_setting import ROOT_ATTR, get_root
from app.services.roles import pic_unit_orgs

def identity(user_id):
    return SimpleNamespace(user_id=user_id)


@contextmanager
def count_queries(fragment):
    hits = []

    def before(conn, cursor, statement, params, context, executemany):
        if fragment in statement:
            hits.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield hits
    finally:
        event.remove(engine, "before_cursor_execute", before)


# --- get_user_accessible_org_ids (finding 11) -------------------------------


def test_global_grant_returns_none(db, make_user, grant):
    user_id = make_user()
    grant(user_id, "AIDAA.ADMIN", org_id=None)

    assert get_user_accessible_org_ids(db, user_id, "audit.assignment.read") is None


def test_org_grant_expands_to_descendants(db, make_user, grant, app_scope):
    user_id = make_user()
    grant(user_id, "AIDAA.AUDITOR", org_id=app_scope.root, app_id=app_scope.app_id)

    allowed = get_user_accessible_org_ids(db, user_id, "audit.assignment.read")

    assert allowed is not None
    assert app_scope.root in allowed
    assert app_scope.child in allowed


def test_no_grant_returns_empty_list(db, make_user):
    user_id = make_user()

    assert get_user_accessible_org_ids(db, user_id, "audit.assignment.read") == []


# --- request memo -----------------------------------------------------------


def test_memo_loads_once_per_user_and_permission(db, make_user, monkeypatch):
    calls = []

    def fake_load(session, user_id, permission_code):
        calls.append((str(user_id), permission_code))
        return ["cached"]

    monkeypatch.setattr(deps_org, "_load_accessible_org_ids", fake_load)
    user_a, user_b = make_user(), make_user()

    first = get_user_accessible_org_ids(db, user_a, "audit.assignment.read")
    second = get_user_accessible_org_ids(db, user_a, "audit.assignment.read")
    get_user_accessible_org_ids(db, user_a, "audit.plan.read")
    get_user_accessible_org_ids(db, user_b, "audit.assignment.read")

    assert first is second
    assert calls == [
        (str(user_a), "audit.assignment.read"),
        (str(user_a), "audit.plan.read"),
        (str(user_b), "audit.assignment.read"),
    ]


def test_memo_does_not_leak_between_sessions(db, make_user, monkeypatch):
    calls = []

    def fake_load(session, user_id, permission_code):
        calls.append(str(user_id))
        return []

    monkeypatch.setattr(deps_org, "_load_accessible_org_ids", fake_load)
    user_id = make_user()

    get_user_accessible_org_ids(db, user_id, "audit.assignment.read")

    other = Session(bind=db.connection())
    try:
        get_user_accessible_org_ids(other, user_id, "audit.assignment.read")
    finally:
        other.close()

    assert len(calls) == 2


# --- roots (findings 8 and 13) ---------------------------------------------


def test_get_root_derives_the_single_root(db, make_user, grant, make_org):
    root = make_org()
    user_id = make_user()
    grant(user_id, "AIDAA.ADMIN", org_id=root)

    assert get_root(db, user_id) == root


def test_get_root_409_when_two_roots(db, make_user, grant, make_org):
    root_a, root_b = make_org(), make_org()
    user_id = make_user()
    grant(user_id, "AIDAA.ADMIN", org_id=root_a)
    grant(user_id, "AIDAA.AUDITOR", org_id=root_b)

    with pytest.raises(Exception) as exc:
        get_root(db, user_id)

    assert getattr(exc.value, "status_code", None) == 409


def test_get_root_honours_the_pinned_root(db, make_user, grant, make_org):
    root_a, root_b = make_org(), make_org()
    user_id = make_user()
    grant(user_id, "AIDAA.ADMIN", org_id=root_a)
    grant(user_id, "AIDAA.AUDITOR", org_id=root_b)

    setattr(db, ROOT_ATTR, root_b)

    assert get_root(db, user_id) == root_b


def test_resolve_root_is_lazy_without_an_explicit_root(db, make_user, monkeypatch):
    user_id = make_user()

    def fail(*args, **kwargs):
        raise AssertionError("resolve_root must not read roots without an explicit root")

    monkeypatch.setattr(deps_root, "get_accessible_roots", fail)

    assert deps_root.resolve_root(root_id=None, x_dh_root=None, db=db,
                                  current_user=identity(user_id)) is db
    assert getattr(db, ROOT_ATTR, None) is None


def test_resolve_root_rejects_an_unknown_root(db, make_user, grant, make_org):
    allowed = make_org()
    user_id = make_user()
    grant(user_id, "AIDAA.ADMIN", org_id=allowed)

    with pytest.raises(Exception) as exc:
        deps_root.resolve_root(root_id=uuid4(), x_dh_root=None, db=db,
                               current_user=identity(user_id))

    assert getattr(exc.value, "status_code", None) == 403
    assert getattr(db, ROOT_ATTR, None) is None


def test_resolve_root_pins_a_valid_root(db, make_user, grant, make_org):
    allowed = make_org()
    user_id = make_user()
    grant(user_id, "AIDAA.ADMIN", org_id=allowed)

    deps_root.resolve_root(root_id=None, x_dh_root=allowed, db=db,
                           current_user=identity(user_id))

    assert getattr(db, ROOT_ATTR) == allowed
    assert get_root(db, user_id) == allowed


# --- PIC units (finding 14) -------------------------------------------------


def test_pic_unit_orgs_covers_descendants_in_one_query(db, make_user, grant, make_org):
    root = make_org()
    child_a = make_org(root)
    child_b = make_org(root)
    unrelated = make_org()
    user_id = make_user()
    grant(user_id, "AIDAA.AUDITEE_PIC", org_id=root)

    with count_queries("WITH RECURSIVE anc") as hits:
        covered = pic_unit_orgs(db, user_id, [child_a, child_b, unrelated])

    assert covered == [child_a, child_b]
    assert len(hits) == 1


def test_pic_unit_orgs_ignores_orgs_outside_the_grant(db, make_user, grant, make_org):
    root = make_org()
    child_a = make_org(root)
    child_b = make_org(root)
    user_id = make_user()
    grant(user_id, "AIDAA.AUDITEE_PIC", org_id=child_a)

    assert pic_unit_orgs(db, user_id, [child_a, child_b]) == [child_a]


def test_is_auditee_pic_delegates_to_the_same_query(db, make_user, grant, make_org):
    root = make_org()
    child = make_org(root)
    user_id = make_user()
    grant(user_id, "AIDAA.AUDITEE_PIC", org_id=root)

    assert roles.is_auditee_pic(db, user_id, child) is True
    assert roles.is_auditee_pic(db, user_id, None) is False


# --- any-of permission check (finding 13) ----------------------------------


def test_check_org_any_permission_resolves_the_record_once(db, make_user, grant,
                                                           app_scope, monkeypatch):
    user_id = make_user()
    grant(user_id, "AIDAA.AUDITOR", org_id=app_scope.root, app_id=app_scope.app_id)
    lookups = []

    def fake_org(session, resource, resource_id):
        lookups.append(resource_id)
        return app_scope.root

    monkeypatch.setattr(deps_org, "get_resource_org_id", fake_org)
    rid = uuid4()

    org_id = check_org_any_permission(
        db, identity(user_id),
        ["audit.not.held", "audit.assignment.read"],
        "assignment", rid,
    )

    assert org_id == app_scope.root
    assert lookups == [rid]


def test_check_org_any_permission_403_without_any_grant(db, make_user, make_org,
                                                        monkeypatch):
    user_id = make_user()
    org = make_org()

    monkeypatch.setattr(deps_org, "get_resource_org_id",
                        lambda session, resource, resource_id: org)

    with pytest.raises(Exception) as exc:
        check_org_any_permission(db, identity(user_id),
                                 ["audit.not.held"], "assignment", uuid4())

    assert getattr(exc.value, "status_code", None) == 403
