"""
Automated tests for the material balance calculation engine.

Covers both the pure calculation function (backend/services/material_balance.py)
and the POST /calculate/material-balance API route. Functional unit: 1 tonne
of finished stainless steel. No emissions are exercised here - this module
is mass accounting only.
"""
import math

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import MaterialBalanceInput
from backend.services.material_balance import calculate_material_balance

client = TestClient(app)


# --- Service-level unit tests --------------------------------------------------


def test_known_values_92_percent_yield_65_scrap():
    """Hand-computed reference case:
    scrap 65%, yield 0.92 -> charge_mass = 1/0.92 = 1.086957 t
    scrap_mass = 0.65 * 1.086957 = 0.706522 t
    virgin_mass = 0.35 * 1.086957 = 0.380435 t
    """
    payload = MaterialBalanceInput(scrap_percentage=65, **{"yield": 0.92})
    result = calculate_material_balance(payload)

    assert math.isclose(result.charge_mass, 1 / 0.92, rel_tol=1e-6)
    assert math.isclose(result.scrap_mass, 0.65 * (1 / 0.92), rel_tol=1e-6)
    assert math.isclose(result.virgin_mass, 0.35 * (1 / 0.92), rel_tol=1e-6)
    assert result.scrap_percentage == 65
    assert result.virgin_percentage == 35
    assert result.validation_status.overall == "PASS"


def test_virgin_percentage_is_complement_of_scrap():
    payload = MaterialBalanceInput(scrap_percentage=30, **{"yield": 0.9})
    result = calculate_material_balance(payload)
    assert result.virgin_percentage == 70
    assert result.scrap_percentage + result.virgin_percentage == 100


def test_mass_balance_closes():
    payload = MaterialBalanceInput(scrap_percentage=40, **{"yield": 0.85})
    result = calculate_material_balance(payload)
    assert math.isclose(result.scrap_mass + result.virgin_mass, result.charge_mass, rel_tol=1e-6)
    assert result.validation_status.mass_balance_closes is True


def test_perfect_yield_of_1_gives_charge_mass_of_1():
    payload = MaterialBalanceInput(scrap_percentage=50, **{"yield": 1.0})
    result = calculate_material_balance(payload)
    assert math.isclose(result.charge_mass, 1.0, rel_tol=1e-9)
    assert math.isclose(result.scrap_mass, 0.5, rel_tol=1e-9)
    assert math.isclose(result.virgin_mass, 0.5, rel_tol=1e-9)


def test_100_percent_scrap_has_zero_virgin_mass():
    payload = MaterialBalanceInput(scrap_percentage=100, **{"yield": 0.9})
    result = calculate_material_balance(payload)
    assert result.virgin_percentage == 0
    assert math.isclose(result.virgin_mass, 0.0, abs_tol=1e-9)
    assert result.validation_status.overall == "PASS"


def test_0_percent_scrap_has_zero_scrap_mass():
    payload = MaterialBalanceInput(scrap_percentage=0, **{"yield": 0.9})
    result = calculate_material_balance(payload)
    assert result.scrap_percentage == 0
    assert math.isclose(result.scrap_mass, 0.0, abs_tol=1e-9)


def test_no_mass_is_negative():
    payload = MaterialBalanceInput(scrap_percentage=17, **{"yield": 0.77})
    result = calculate_material_balance(payload)
    assert result.charge_mass >= 0
    assert result.scrap_mass >= 0
    assert result.virgin_mass >= 0
    assert result.validation_status.no_negative_mass is True


# --- Input validation (Pydantic-level) --------------------------------------


def test_rejects_scrap_percentage_above_100():
    with pytest.raises(Exception):
        MaterialBalanceInput(scrap_percentage=101, **{"yield": 0.9})


def test_rejects_scrap_percentage_below_0():
    with pytest.raises(Exception):
        MaterialBalanceInput(scrap_percentage=-1, **{"yield": 0.9})


def test_rejects_zero_yield():
    with pytest.raises(Exception):
        MaterialBalanceInput(scrap_percentage=50, **{"yield": 0})


def test_rejects_yield_above_1():
    with pytest.raises(Exception):
        MaterialBalanceInput(scrap_percentage=50, **{"yield": 1.01})


def test_rejects_negative_yield():
    with pytest.raises(Exception):
        MaterialBalanceInput(scrap_percentage=50, **{"yield": -0.5})


# --- API-level tests -----------------------------------------------------------


def test_endpoint_returns_all_required_fields():
    r = client.post("/calculate/material-balance", json={"scrap_percentage": 65, "yield": 0.92})
    assert r.status_code == 200
    body = r.json()
    required_fields = {
        "charge_mass",
        "scrap_mass",
        "virgin_mass",
        "scrap_percentage",
        "virgin_percentage",
        "yield",
        "validation_status",
    }
    assert required_fields.issubset(body.keys())
    assert body["validation_status"]["overall"] == "PASS"
    assert set(body["validation_status"].keys()) == {
        "mix_sums_to_100",
        "mass_balance_closes",
        "no_negative_mass",
        "overall",
    }


def test_endpoint_matches_service_calculation():
    r = client.post("/calculate/material-balance", json={"scrap_percentage": 65, "yield": 0.92})
    body = r.json()
    assert math.isclose(body["charge_mass"], 1 / 0.92, rel_tol=1e-6)
    assert math.isclose(body["scrap_mass"] + body["virgin_mass"], body["charge_mass"], rel_tol=1e-6)


def test_endpoint_rejects_invalid_scrap_percentage():
    r = client.post("/calculate/material-balance", json={"scrap_percentage": 150, "yield": 0.9})
    assert r.status_code == 422


def test_endpoint_rejects_zero_yield():
    r = client.post("/calculate/material-balance", json={"scrap_percentage": 50, "yield": 0})
    assert r.status_code == 422


def test_endpoint_rejects_missing_fields():
    r = client.post("/calculate/material-balance", json={"scrap_percentage": 50})
    assert r.status_code == 422


def test_endpoint_does_not_return_any_emissions_fields():
    """Explicit guard: this module must not calculate emissions yet."""
    r = client.post("/calculate/material-balance", json={"scrap_percentage": 65, "yield": 0.92})
    body = r.json()
    forbidden = {"tco2e_per_t", "total_tco2e_per_t", "breakdown", "emission_factor", "co2", "co2e"}
    assert forbidden.isdisjoint(body.keys())
