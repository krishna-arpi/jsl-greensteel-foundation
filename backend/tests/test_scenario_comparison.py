"""
Automated tests for scenario comparison: save/list/delete and the
server-side CO2 computation. Functional unit: 1 tonne of finished stainless
steel. Each test resets the JSON-file store to a clean state first, since
scenarios persist across process runs by design.
"""
import math
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import ScenarioInput
from backend.services import scenario_store

client = TestClient(app)

_TEST_STORE_DIR = scenario_store._STORE_DIR


@pytest.fixture(autouse=True)
def clean_store():
    """Ensure every test starts from an empty scenario store."""
    if _TEST_STORE_DIR.exists():
        shutil.rmtree(_TEST_STORE_DIR)
    yield
    if _TEST_STORE_DIR.exists():
        shutil.rmtree(_TEST_STORE_DIR)


def _make_scenario(**overrides) -> ScenarioInput:
    defaults = dict(
        name="Test Scenario",
        grade_id="SS316",
        scrap_pct=65,
        scrap_quality_id="SCRAP_HIGH_QUALITY",
        energy_source_id="GRID_ELECTRICITY_IN",
        electricity_consumption_mwh_per_t=0.55,
        natural_gas_consumption_gj_per_t=0.9,
        coal_consumption_gj_per_t=0.1,
    )
    defaults.update(overrides)
    yield_value = defaults.pop("yield_fraction", 0.92)
    return ScenarioInput(**defaults, **{"yield": yield_value})


# --- Service-level tests -----------------------------------------------------


def test_create_scenario_computes_co2_breakdown():
    record = scenario_store.create_scenario(_make_scenario())
    assert record.material_co2_tco2e_per_t > 0
    assert record.energy_co2_tco2e_per_t > 0
    assert math.isclose(
        record.total_co2_tco2e_per_t, record.material_co2_tco2e_per_t + record.energy_co2_tco2e_per_t, rel_tol=1e-6
    )


def test_create_scenario_resolves_display_names():
    record = scenario_store.create_scenario(_make_scenario())
    assert record.grade_name == "316"
    assert record.scrap_quality_name == "High Quality"
    assert record.energy_source_name == "Grid Electricity"


def test_create_scenario_assigns_unique_id_and_timestamp():
    a = scenario_store.create_scenario(_make_scenario(name="A"))
    b = scenario_store.create_scenario(_make_scenario(name="B"))
    assert a.id != b.id
    assert a.created_at
    assert b.created_at


def test_scenario_persists_across_store_reloads():
    """Simulates a server restart: a fresh call to list_scenarios() (which
    re-reads the JSON file from disk) should still see the saved scenario."""
    created = scenario_store.create_scenario(_make_scenario(name="Persisted"))
    reloaded = scenario_store.list_scenarios()
    assert any(r.id == created.id and r.name == "Persisted" for r in reloaded)


def test_higher_scrap_gives_lower_material_co2_all_else_equal():
    """Scrap's embodied factor (0.3) is well below virgin's (2.3)."""
    low_scrap = scenario_store.create_scenario(_make_scenario(name="Low", scrap_pct=20))
    high_scrap = scenario_store.create_scenario(_make_scenario(name="High", scrap_pct=80))
    assert high_scrap.material_co2_tco2e_per_t < low_scrap.material_co2_tco2e_per_t


def test_renewable_energy_source_gives_lower_energy_co2():
    grid = scenario_store.create_scenario(_make_scenario(name="Grid", energy_source_id="GRID_ELECTRICITY_IN"))
    renewable = scenario_store.create_scenario(_make_scenario(name="Renewable", energy_source_id="RENEWABLE_ELECTRICITY_IN"))
    assert renewable.energy_co2_tco2e_per_t < grid.energy_co2_tco2e_per_t


def test_delete_scenario_removes_it():
    record = scenario_store.create_scenario(_make_scenario())
    assert scenario_store.delete_scenario(record.id) is True
    assert all(r.id != record.id for r in scenario_store.list_scenarios())


def test_delete_nonexistent_scenario_returns_false():
    assert scenario_store.delete_scenario("not-a-real-id") is False


def test_create_scenario_rejects_unknown_grade():
    with pytest.raises(Exception):
        scenario_store.create_scenario(_make_scenario(grade_id="NOT_A_REAL_GRADE"))


def test_create_scenario_rejects_unknown_energy_source():
    with pytest.raises(Exception):
        scenario_store.create_scenario(_make_scenario(energy_source_id="NOT_REAL"))


# --- API-level tests -----------------------------------------------------------


def test_endpoint_create_and_list():
    r = client.post(
        "/scenarios",
        json={
            "name": "API Scenario",
            "grade_id": "SS316",
            "scrap_pct": 65,
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "yield": 0.92,
        },
    )
    assert r.status_code == 200
    created = r.json()
    assert created["name"] == "API Scenario"
    assert "id" in created

    r2 = client.get("/scenarios")
    assert r2.status_code == 200
    body = r2.json()
    assert any(s["id"] == created["id"] for s in body["scenarios"])


def test_endpoint_delete():
    r = client.post(
        "/scenarios",
        json={
            "name": "To Delete",
            "grade_id": "SS316",
            "scrap_pct": 65,
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "yield": 0.92,
        },
    )
    scenario_id = r.json()["id"]

    r2 = client.delete(f"/scenarios/{scenario_id}")
    assert r2.status_code == 200
    assert r2.json()["deleted"] is True

    r3 = client.get("/scenarios")
    assert all(s["id"] != scenario_id for s in r3.json()["scenarios"])


def test_endpoint_delete_nonexistent_returns_404():
    r = client.delete("/scenarios/not-a-real-id")
    assert r.status_code == 404


def test_endpoint_rejects_unknown_grade():
    r = client.post(
        "/scenarios",
        json={
            "name": "Bad Grade",
            "grade_id": "NOT_REAL",
            "scrap_pct": 65,
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "yield": 0.92,
        },
    )
    assert r.status_code == 422


def test_endpoint_rejects_missing_fields():
    r = client.post("/scenarios", json={"name": "Incomplete"})
    assert r.status_code == 422


def test_endpoint_rejects_invalid_yield():
    r = client.post(
        "/scenarios",
        json={
            "name": "Bad Yield",
            "grade_id": "SS316",
            "scrap_pct": 65,
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "yield": 0,
        },
    )
    assert r.status_code == 422


def test_endpoint_list_returns_empty_when_no_scenarios():
    r = client.get("/scenarios")
    assert r.status_code == 200
    assert r.json()["scenarios"] == []
