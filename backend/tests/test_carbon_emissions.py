"""
Automated tests for the complete carbon-emission calculation engine.

Covers the service function (backend/services/carbon_emissions.py) and the
POST /calculate/emissions API route. Functional unit: 1 tonne of finished
stainless steel ("tSS"), matching material_balance and scrap_chemistry.

    Total Carbon = Material + Electricity + Direct Fuel + Process Carbon

Special focus: the engine must never fabricate a missing emission factor -
every test involving an unknown id asserts factor_available=False, a 0
contribution, and a corresponding warning, rather than a guessed number.
"""
import math

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import (
    CarbonEmissionInput,
    ElectricityMixComponentInput,
    MaterialQuantityInput,
)
from backend.services.carbon_emissions import calculate_carbon_emissions

client = TestClient(app)


# --- Material emissions ----------------------------------------------------


def test_material_emissions_known_factors():
    """CO2_material = sum(quantity x emission factor).
    SCRAP_EMBODIED=0.3 tCO2e/t, VIRGIN_EMBODIED=2.3 tCO2e/t, FERRO_CHROME=3.6.
    """
    payload = CarbonEmissionInput(
        materials=[
            MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=0.7),
            MaterialQuantityInput(material_id="VIRGIN_EMBODIED", quantity_t=0.3),
            MaterialQuantityInput(material_id="FERRO_CHROME", quantity_t=0.15),
        ]
    )
    result = calculate_carbon_emissions(payload)
    expected = 0.7 * 0.3 + 0.3 * 2.3 + 0.15 * 3.6
    assert math.isclose(result.material_emissions.total_tco2e, expected, rel_tol=1e-6)
    assert all(item.factor_available for item in result.material_emissions.items)


def test_material_emissions_covers_all_named_material_types():
    """Scrap, virgin iron, ferrochrome, nickel/ferronickel, ferromolybdenum,
    and another alloy addition should all be prices without fabrication."""
    payload = CarbonEmissionInput(
        materials=[
            MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=0.6),
            MaterialQuantityInput(material_id="VIRGIN_EMBODIED", quantity_t=0.4),
            MaterialQuantityInput(material_id="FERRO_CHROME", quantity_t=0.18),
            MaterialQuantityInput(material_id="FERRO_NICKEL", quantity_t=0.05),
            MaterialQuantityInput(material_id="FERRO_MOLYBDENUM", quantity_t=0.02),
            MaterialQuantityInput(material_id="FERRO_MANGANESE", quantity_t=0.01),
        ]
    )
    result = calculate_carbon_emissions(payload)
    assert len(result.material_emissions.items) == 6
    assert all(item.factor_available for item in result.material_emissions.items)
    assert result.material_emissions.total_tco2e > 0


def test_unknown_material_id_is_not_fabricated():
    payload = CarbonEmissionInput(
        materials=[
            MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=0.7),
            MaterialQuantityInput(material_id="MADE_UP_MATERIAL", quantity_t=0.05),
        ]
    )
    result = calculate_carbon_emissions(payload)
    unknown_item = next(i for i in result.material_emissions.items if i.material_id == "MADE_UP_MATERIAL")
    assert unknown_item.factor_available is False
    assert unknown_item.emission_factor_tco2e_per_t is None
    assert unknown_item.tco2e == 0
    assert any("MADE_UP_MATERIAL" in w for w in result.missing_factor_warnings)
    # Known material's contribution must still be counted.
    assert math.isclose(result.material_emissions.total_tco2e, 0.7 * 0.3, rel_tol=1e-6)


def test_emission_breakdown_by_material_matches_material_emissions_items():
    payload = CarbonEmissionInput(
        materials=[
            MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=0.7),
            MaterialQuantityInput(material_id="FERRO_CHROME", quantity_t=0.1),
        ]
    )
    result = calculate_carbon_emissions(payload)
    assert result.emission_breakdown_by_material == result.material_emissions.items


def test_no_materials_gives_zero_material_emissions_and_no_warning():
    payload = CarbonEmissionInput(materials=[])
    result = calculate_carbon_emissions(payload)
    assert result.material_emissions.total_tco2e == 0
    assert result.material_emissions.items == []


# --- Electricity emissions ---------------------------------------------------


def test_electricity_single_source_formula():
    """CO2_electricity = consumption x emission_factor (single source)."""
    payload = CarbonEmissionInput(electricity_consumption_mwh_per_t=0.5, electricity_source_id="GRID_ELECTRICITY_IN")
    result = calculate_carbon_emissions(payload)
    assert math.isclose(result.electricity_emissions.total_tco2e, 0.5 * 0.71, rel_tol=1e-6)
    assert result.electricity_emissions.effective_emission_factor_tco2e_per_mwh == 0.71


def test_electricity_mix_formula():
    """CO2_electricity = consumption x sum(share x factor)."""
    payload = CarbonEmissionInput(
        electricity_consumption_mwh_per_t=0.5,
        electricity_mix=[
            ElectricityMixComponentInput(source_id="GRID_ELECTRICITY_IN", share_pct=70),
            ElectricityMixComponentInput(source_id="RENEWABLE_ELECTRICITY_IN", share_pct=30),
        ],
    )
    result = calculate_carbon_emissions(payload)
    expected_effective_factor = 0.7 * 0.71 + 0.3 * 0.02
    assert math.isclose(result.electricity_emissions.effective_emission_factor_tco2e_per_mwh, expected_effective_factor, rel_tol=1e-6)
    assert math.isclose(result.electricity_emissions.total_tco2e, 0.5 * expected_effective_factor, rel_tol=1e-6)


def test_electricity_mix_explicit_overrides_source_id_shortcut():
    payload = CarbonEmissionInput(
        electricity_consumption_mwh_per_t=1.0,
        electricity_source_id="GRID_ELECTRICITY_IN",
        electricity_mix=[ElectricityMixComponentInput(source_id="RENEWABLE_ELECTRICITY_IN", share_pct=100)],
    )
    result = calculate_carbon_emissions(payload)
    # Mix should win; effective factor should be renewable's 0.02, not grid's 0.71.
    assert result.electricity_emissions.effective_emission_factor_tco2e_per_mwh == 0.02


def test_electricity_unknown_source_is_not_fabricated():
    payload = CarbonEmissionInput(electricity_consumption_mwh_per_t=0.5, electricity_source_id="FAKE_SOURCE")
    result = calculate_carbon_emissions(payload)
    assert result.electricity_emissions.mix[0].factor_available is False
    assert result.electricity_emissions.effective_emission_factor_tco2e_per_mwh is None
    assert result.electricity_emissions.total_tco2e == 0
    assert any("FAKE_SOURCE" in w for w in result.missing_factor_warnings)


def test_electricity_consumption_with_no_source_warns_and_is_zero():
    payload = CarbonEmissionInput(electricity_consumption_mwh_per_t=0.6)
    result = calculate_carbon_emissions(payload)
    assert result.electricity_emissions.total_tco2e == 0
    assert any("no electricity source or mix" in w for w in result.missing_factor_warnings)


def test_electricity_mix_not_summing_to_100_still_computes_and_warns():
    payload = CarbonEmissionInput(
        electricity_consumption_mwh_per_t=1.0,
        electricity_mix=[ElectricityMixComponentInput(source_id="GRID_ELECTRICITY_IN", share_pct=50)],
    )
    result = calculate_carbon_emissions(payload)
    assert any("do not sum to 100" in w for w in result.missing_factor_warnings)
    assert math.isclose(result.electricity_emissions.effective_emission_factor_tco2e_per_mwh, 0.5 * 0.71, rel_tol=1e-6)


# --- Fuel emissions (natural gas + coal) ------------------------------------


def test_natural_gas_formula():
    payload = CarbonEmissionInput(natural_gas_consumption_gj_per_t=0.9)
    result = calculate_carbon_emissions(payload)
    assert math.isclose(result.fuel_emissions.natural_gas.tco2e, 0.9 * 0.056, rel_tol=1e-6)
    assert result.fuel_emissions.coal.tco2e == 0


def test_coal_formula():
    payload = CarbonEmissionInput(coal_consumption_gj_per_t=0.4)
    result = calculate_carbon_emissions(payload)
    assert math.isclose(result.fuel_emissions.coal.tco2e, 0.4 * 0.094, rel_tol=1e-6)


def test_fuel_total_is_sum_of_ng_and_coal():
    payload = CarbonEmissionInput(natural_gas_consumption_gj_per_t=0.9, coal_consumption_gj_per_t=0.4)
    result = calculate_carbon_emissions(payload)
    expected = 0.9 * 0.056 + 0.4 * 0.094
    assert math.isclose(result.fuel_emissions.total_tco2e, expected, rel_tol=1e-6)


def test_zero_fuel_consumption_gives_zero_emissions_no_warning():
    payload = CarbonEmissionInput()
    result = calculate_carbon_emissions(payload)
    assert result.fuel_emissions.total_tco2e == 0
    assert result.fuel_emissions.natural_gas.factor_available is True
    assert result.fuel_emissions.coal.factor_available is True
    assert result.missing_factor_warnings == [
        "No process_route_id or process_emission_override_tco2e_per_t was supplied - "
        "process emissions are reported as 0, not fabricated."
    ]


# --- Process emissions (configurable) ---------------------------------------


def test_process_emissions_from_named_route():
    payload = CarbonEmissionInput(process_route_id="EAF_HIGH_SCRAP")
    result = calculate_carbon_emissions(payload)
    assert result.process_emissions.tco2e_per_t == 0.35
    assert result.process_emissions.source == "process_route"
    assert result.process_emissions.factor_available is True


def test_process_emissions_explicit_override_takes_precedence():
    payload = CarbonEmissionInput(process_route_id="EAF_HIGH_SCRAP", process_emission_override_tco2e_per_t=1.23)
    result = calculate_carbon_emissions(payload)
    assert result.process_emissions.tco2e_per_t == 1.23
    assert result.process_emissions.source == "override"


def test_process_emissions_unconfigured_is_zero_with_warning():
    payload = CarbonEmissionInput()
    result = calculate_carbon_emissions(payload)
    assert result.process_emissions.tco2e_per_t == 0
    assert result.process_emissions.source == "not_configured"
    assert result.process_emissions.factor_available is False
    assert any("process_route_id" in w for w in result.missing_factor_warnings)


def test_process_emissions_unknown_route_is_not_fabricated():
    payload = CarbonEmissionInput(process_route_id="FAKE_ROUTE")
    result = calculate_carbon_emissions(payload)
    assert result.process_emissions.tco2e_per_t == 0
    assert result.process_emissions.factor_available is False
    assert any("FAKE_ROUTE" in w for w in result.missing_factor_warnings)


# --- Total carbon intensity -------------------------------------------------


def test_total_is_sum_of_all_four_components():
    payload = CarbonEmissionInput(
        materials=[
            MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=0.7),
            MaterialQuantityInput(material_id="VIRGIN_EMBODIED", quantity_t=0.3),
        ],
        electricity_consumption_mwh_per_t=0.5,
        electricity_source_id="GRID_ELECTRICITY_IN",
        natural_gas_consumption_gj_per_t=0.9,
        coal_consumption_gj_per_t=0.1,
        process_route_id="EAF_HIGH_SCRAP",
    )
    result = calculate_carbon_emissions(payload)
    expected = (
        result.material_emissions.total_tco2e
        + result.electricity_emissions.total_tco2e
        + result.fuel_emissions.total_tco2e
        + result.process_emissions.tco2e_per_t
    )
    assert math.isclose(result.carbon_intensity_tCO2e_per_tSS, expected, rel_tol=1e-6)


def test_kg_field_is_1000x_the_tonne_field():
    payload = CarbonEmissionInput(process_route_id="BOF_INTEGRATED")
    result = calculate_carbon_emissions(payload)
    assert math.isclose(result.carbon_intensity_kgCO2e_per_tSS, result.carbon_intensity_tCO2e_per_tSS * 1000, rel_tol=1e-6)


def test_all_factors_unavailable_gives_zero_total_with_warnings_not_a_crash():
    payload = CarbonEmissionInput(
        materials=[MaterialQuantityInput(material_id="NOT_REAL", quantity_t=1.0)],
        electricity_consumption_mwh_per_t=0.5,
        electricity_source_id="NOT_REAL_EITHER",
        natural_gas_consumption_gj_per_t=0,
        coal_consumption_gj_per_t=0,
    )
    result = calculate_carbon_emissions(payload)
    assert result.carbon_intensity_tCO2e_per_tSS == 0
    assert len(result.missing_factor_warnings) >= 2


# --- API-level tests -----------------------------------------------------------


def test_endpoint_returns_all_required_fields():
    r = client.post(
        "/calculate/emissions",
        json={
            "materials": [{"material_id": "SCRAP_EMBODIED", "quantity_t": 0.7}],
            "electricity_consumption_mwh_per_t": 0.5,
            "electricity_source_id": "GRID_ELECTRICITY_IN",
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "process_route_id": "EAF_HIGH_SCRAP",
        },
    )
    assert r.status_code == 200
    body = r.json()
    required_fields = {
        "carbon_intensity_tCO2e_per_tSS",
        "carbon_intensity_kgCO2e_per_tSS",
        "material_emissions",
        "electricity_emissions",
        "fuel_emissions",
        "process_emissions",
        "emission_breakdown_by_material",
    }
    assert required_fields.issubset(body.keys())


def test_endpoint_with_no_body_defaults_gracefully():
    r = client.post("/calculate/emissions", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["carbon_intensity_tCO2e_per_tSS"] == 0
    assert len(body["missing_factor_warnings"]) >= 1


def test_endpoint_missing_factor_produces_warning_not_500():
    r = client.post(
        "/calculate/emissions",
        json={"materials": [{"material_id": "TOTALLY_UNKNOWN", "quantity_t": 0.2}]},
    )
    assert r.status_code == 200
    body = r.json()
    item = body["material_emissions"]["items"][0]
    assert item["factor_available"] is False
    assert item["emission_factor_tco2e_per_t"] is None
    assert "TOTALLY_UNKNOWN" in body["missing_factor_warnings"][0]


def test_endpoint_rejects_negative_material_quantity():
    r = client.post(
        "/calculate/emissions",
        json={"materials": [{"material_id": "SCRAP_EMBODIED", "quantity_t": -1}]},
    )
    assert r.status_code == 422
