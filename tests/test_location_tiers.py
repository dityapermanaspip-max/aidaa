"""ref_location has two tiers: the org's own rows and the shared national (BPS) master (root_org_id IS NULL).
The location pickers list both, so a unit and a cost rate must accept both, and still refuse another root's rows
(404, so a foreign location stays invisible). Everything runs in the rolled-back test transaction."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.schemas.aidaa import UnitCreate, UnitUpdate
from app.schemas.masters_costing import CostComponentCreate, CostRateCreate, CostRateUpdate
from app.services import masters, masters_costing
from app.services.audit_setting import ROOT_ATTR


@pytest.fixture()
def tiers(db, make_org, make_user, monkeypatch):
    """Two roots, a user, and one location in each tier: the active root's own, the national one, another root's."""
    root, other = make_org(), make_org()
    setattr(db, ROOT_ATTR, root)  # the active root, as the request middleware sets it
    # The IAU designation is not what these tests are about: the org check is replaced, the location check is not.
    monkeypatch.setattr(masters, "assert_client_org", lambda *a, **k: None)

    def location(root_id, tag):
        return db.execute(text("""
            INSERT INTO aidaa_core.ref_location (root_org_id, location_code, location_name, country)
            VALUES (CAST(:r AS uuid), :c, :n, 'Indonesia') RETURNING location_id
        """), {"r": str(root_id) if root_id else None, "c": f"PY-{tag}-{uuid4().hex[:8]}", "n": f"Pytest {tag}"}).scalar_one()

    return SimpleNamespace(
        root=root, user=make_user(), make_org=make_org,
        own=location(root, "OWN"), national=location(None, "NAT"), foreign=location(other, "FOR"),
    )


def new_unit(db, t, location_id):
    child = t.make_org(parent=t.root)
    return masters.create_unit(
        db, UnitCreate(unit_code=f"PY-{uuid4().hex[:8]}", unit_name="Pytest unit", org_id=child, location_id=location_id), t.user)


@pytest.mark.parametrize("tier", ["own", "national"])
def test_a_unit_may_use_the_orgs_own_or_the_national_location(db, tiers, tier):
    unit = new_unit(db, tiers, getattr(tiers, tier))
    assert str(unit["location_id"]) == str(getattr(tiers, tier))


def test_a_unit_cannot_use_another_roots_location(db, tiers):
    with pytest.raises(HTTPException) as caught:
        new_unit(db, tiers, tiers.foreign)
    assert (caught.value.status_code, caught.value.detail) == (404, "Location not found")


def test_a_unit_can_be_moved_to_a_national_location_but_not_to_a_foreign_one(db, tiers):
    unit = new_unit(db, tiers, tiers.own)
    moved = masters.update_unit(db, unit["unit_id"], UnitUpdate(location_id=tiers.national), tiers.user)
    assert str(moved["location_id"]) == str(tiers.national)
    with pytest.raises(HTTPException) as caught:
        masters.update_unit(db, unit["unit_id"], UnitUpdate(location_id=tiers.foreign), tiers.user)
    assert caught.value.status_code == 404
    assert str(masters.get_unit(db, tiers.user, unit["unit_id"])["location_id"]) == str(tiers.national)  # unchanged by the refusal


@pytest.fixture()
def component(db, tiers):
    return masters_costing.create_component(
        db, CostComponentCreate(component_code=f"PY-{uuid4().hex[:8]}", component_name="Pytest", calc_basis="fixed"), tiers.user)


def rate(component, **where):
    return CostRateCreate(component_id=component["component_id"], amount=100, effective_from=date(2026, 1, 1), **where)


@pytest.mark.parametrize("tier", ["own", "national"])
def test_a_rate_may_target_and_start_from_the_orgs_own_or_the_national_location(db, tiers, component, tier):
    place = getattr(tiers, tier)
    row = masters_costing.create_rate(db, rate(component, location_id=place, origin_location_id=place), tiers.user)
    assert (str(row["location_id"]), str(row["origin_location_id"])) == (str(place), str(place))


@pytest.mark.parametrize("field", ["location_id", "origin_location_id"])
def test_a_rate_cannot_use_another_roots_location(db, tiers, component, field):
    with pytest.raises(HTTPException) as caught:
        masters_costing.create_rate(db, rate(component, **{field: tiers.foreign}), tiers.user)
    assert caught.value.status_code == 404


def test_a_draft_rate_can_be_edited_to_a_national_location_but_not_a_foreign_one(db, tiers, component):
    row = masters_costing.create_rate(db, rate(component, location_id=tiers.own), tiers.user)
    for field in ("location_id", "origin_location_id"):
        moved = masters_costing.update_rate(db, row["rate_id"], CostRateUpdate(**{field: tiers.national}), tiers.user)
        assert str(moved[field]) == str(tiers.national)
        with pytest.raises(HTTPException) as caught:
            masters_costing.update_rate(db, row["rate_id"], CostRateUpdate(**{field: tiers.foreign}), tiers.user)
        assert caught.value.status_code == 404
