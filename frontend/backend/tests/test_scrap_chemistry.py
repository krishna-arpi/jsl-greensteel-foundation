"""
Automated tests for the scrap chemistry calculation engine.

Covers the service function (backend/services/scrap_chemistry.py), the
validation helper (backend/validation/input_validation.py:validate_final_chemistry),
and the POST /calculate/scrap-chemistry API route. Functional unit: 1 tonne
of finished stainless steel, matching the material balance module. No
emissions are exercised here - this module is composition accounting only.
"""
import math

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import ScrapChemistryInput
from backend.services.scrap_chemistry import calculate_scrap_chemistry

client = TestClient(app)


# --- Service-level unit tests: element contribution ------------------------


def test_element_contribution_matches_formula():
    """element_mass = scrap_mass x element_fraction x recovery.

    SCRAP_HIGH_QUALITY: Cr=18.0%, alloy_recovery=95%. scrap_mass=0.7 t.
    Cr_from_scrap = 0.7 * 0.18 * 0.95
    """
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS304")
    result = calculate_scrap_chemistry(payload)

    expected_cr = 0.7 * 0.18 * 0.95
    assert math.isclose(result.element_contribution.Cr_from_scrap, expected_cr, rel_tol=1e-4)

    expected_ni = 0.7 * 0.085 * 0.95
    assert math.isclose(result.element_contribution.Ni_from_scrap, expected_ni, rel_tol=1e-4)

    expected_fe = 0.7 * 0.715 * 0.95
    assert math.isclose(result.element_contribution.Fe_from_scrap, expected_fe, rel_tol=1e-4)


def test_all_eight_elements_are_present():
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_MEDIUM_QUALITY", scrap_mass=0.5, grade_id="SS316")
    result = calculate_scrap_chemistry(payload)
    contribution = result.element_contribution.model_dump()
    for element in ("Cr", "Ni", "Mo", "Fe", "C", "Si", "Mn", "N"):
        assert f"{element}_from_scrap" in contribution
        assert contribution[f"{element}_from_scrap"] >= 0


# --- Service-level unit tests: deficits ------------------------------------


def test_deficit_is_zero_when_scrap_alone_meets_requirement():
    """SS304 needs Cr_min=18%. A scrap mass large enough to supply >= 0.18 t
    Cr on its own should show zero Cr deficit."""
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=1.5, grade_id="SS304")
    result = calculate_scrap_chemistry(payload)
    cr_deficit = next(d for d in result.element_deficits if d.element == "Cr")
    assert cr_deficit.deficit_mass == 0
    assert cr_deficit.supplied_mass >= cr_deficit.required_mass


def test_deficit_formula_is_max_zero_required_minus_supplied():
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.4, grade_id="SS2205")
    result = calculate_scrap_chemistry(payload)
    for d in result.element_deficits:
        assert d.deficit_mass == pytest.approx(max(0.0, d.required_mass - d.supplied_mass), abs=1e-6)
        assert d.deficit_mass >= 0


def test_deficit_uses_grade_minimum_not_maximum():
    """SS304 Cr_min=18.0. Deficit's required_mass should reflect the
    minimum, not the maximum (20.0), over the 1 t functional unit."""
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.1, grade_id="SS304")
    result = calculate_scrap_chemistry(payload)
    cr_deficit = next(d for d in result.element_deficits if d.element == "Cr")
    assert math.isclose(cr_deficit.required_mass, 0.18, rel_tol=1e-6)


def test_grade_with_zero_mo_requirement_has_zero_mo_deficit():
    """SS304 has Mo_min=0, so even with no Mo in the scrap the deficit stays 0."""
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.1, grade_id="SS304")
    result = calculate_scrap_chemistry(payload)
    mo_deficit = next(d for d in result.element_deficits if d.element == "Mo")
    assert mo_deficit.deficit_mass == 0


# --- Service-level unit tests: alloy additions -----------------------------


def test_alloy_addition_formula():
    """alloy_required = deficit / (concentration x recovery).

    FERRO_CHROME: concentration_pct=60, recovery_pct=92 (see
    alloy_specifications.json).
    """
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.3, grade_id="SS316")
    result = calculate_scrap_chemistry(payload)

    cr_deficit = next(d for d in result.element_deficits if d.element == "Cr")
    cr_addition = next(a for a in result.alloy_additions if a.element == "Cr")

    expected_t = cr_deficit.deficit_mass / (0.60 * 0.92)
    assert math.isclose(cr_addition.required_mass_t, expected_t, rel_tol=1e-4)
    assert math.isclose(cr_addition.required_mass_kg, expected_t * 1000, rel_tol=1e-4)
    assert cr_addition.alloy_id == "FERRO_CHROME"


def test_alloy_addition_uses_correct_alloy_per_element():
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.3, grade_id="SS2205")
    result = calculate_scrap_chemistry(payload)
    by_element = {a.element: a.alloy_id for a in result.alloy_additions}
    assert by_element["Cr"] == "FERRO_CHROME"
    assert by_element["Ni"] == "NICKEL_METAL"
    assert by_element["Mo"] == "FERRO_MOLYBDENUM"


def test_zero_deficit_means_zero_alloy_addition():
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=2.0, grade_id="SS304")
    result = calculate_scrap_chemistry(payload)
    cr_addition = next(a for a in result.alloy_additions if a.element == "Cr")
    assert cr_addition.required_mass_t == 0
    assert cr_addition.required_mass_kg == 0


# --- Service-level unit tests: final chemistry + validation ----------------


def test_final_chemistry_closes_deficit_to_grade_minimum():
    """When there is a deficit, the alloy addition should bring the final
    mass up to (approximately) the grade's minimum requirement."""
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.3, grade_id="SS316")
    result = calculate_scrap_chemistry(payload)
    final_by_element = {f.element: f.pct for f in result.final_chemistry}
    assert final_by_element["Cr"] == pytest.approx(16.0, abs=1e-3)
    assert final_by_element["Ni"] == pytest.approx(10.0, abs=1e-3)
    assert final_by_element["Mo"] == pytest.approx(2.0, abs=1e-3)


def test_final_chemistry_passes_validation_when_deficits_are_closed():
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.3, grade_id="SS316")
    result = calculate_scrap_chemistry(payload)
    assert result.chemistry_validation.overall == "PASS"
    for item in result.chemistry_validation.items:
        assert item.status == "PASS"


def test_validation_fails_when_element_exceeds_grade_max():
    """SS304 has Mo_max=0. High-quality scrap carries trace Mo (0.3%), so a
    large enough scrap charge pushes Mo above 304's zero-Mo ceiling even
    though Cr/Ni are satisfied - a real tramp-element failure mode."""
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS304")
    result = calculate_scrap_chemistry(payload)
    mo_item = next(i for i in result.chemistry_validation.items if i.element == "Mo")
    assert mo_item.status == "FAIL"
    assert result.chemistry_validation.overall == "FAIL"


def test_final_chemistry_covers_all_eight_elements():
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_MEDIUM_QUALITY", scrap_mass=0.6, grade_id="SS410")
    result = calculate_scrap_chemistry(payload)
    elements = {f.element for f in result.final_chemistry}
    assert elements == {"Cr", "Ni", "Mo", "Fe", "C", "Si", "Mn", "N"}


def test_chemistry_validation_checks_seven_elements():
    """Cr/Ni/Mo (min+max) plus C/Si/Mn/N (max-only) = 7 validation items."""
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_MEDIUM_QUALITY", scrap_mass=0.6, grade_id="SS430")
    result = calculate_scrap_chemistry(payload)
    assert len(result.chemistry_validation.items) == 7


# --- Input validation (Pydantic-level) --------------------------------------


def test_zero_scrap_mass_is_valid_and_models_all_virgin_charge():
    """0 scrap mass is a legitimate scenario (100% virgin charge) - every
    alloying element must then come entirely from purchased alloy addition.
    This must not be rejected; the deficit-closing math already handles it
    correctly (scrap contributes exactly 0 of everything)."""
    payload = ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0, grade_id="SS316")
    result = calculate_scrap_chemistry(payload)

    assert result.element_contribution.Cr_from_scrap == 0
    assert result.element_contribution.Ni_from_scrap == 0
    assert result.element_contribution.Mo_from_scrap == 0

    cr_deficit = next(d for d in result.element_deficits if d.element == "Cr")
    assert cr_deficit.supplied_mass == 0
    assert cr_deficit.deficit_mass == pytest.approx(cr_deficit.required_mass, abs=1e-6)

    # The alloy addition should fully close the deficit, passing validation.
    assert result.chemistry_validation.overall == "PASS"


def test_rejects_negative_scrap_mass():
    with pytest.raises(Exception):
        ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=-0.5, grade_id="SS304")


# --- API-level tests -----------------------------------------------------------


def test_endpoint_returns_all_required_sections():
    r = client.post(
        "/calculate/scrap-chemistry",
        json={"scrap_quality_id": "SCRAP_HIGH_QUALITY", "scrap_mass": 0.7, "grade_id": "SS316"},
    )
    assert r.status_code == 200
    body = r.json()
    required_sections = {
        "scrap_chemistry",
        "element_contribution",
        "element_deficits",
        "alloy_additions",
        "final_chemistry",
        "chemistry_validation",
    }
    assert required_sections.issubset(body.keys())


def test_endpoint_element_contribution_field_names():
    r = client.post(
        "/calculate/scrap-chemistry",
        json={"scrap_quality_id": "SCRAP_HIGH_QUALITY", "scrap_mass": 0.7, "grade_id": "SS316"},
    )
    contribution = r.json()["element_contribution"]
    expected_fields = {
        "Cr_from_scrap",
        "Ni_from_scrap",
        "Mo_from_scrap",
        "Fe_from_scrap",
        "C_from_scrap",
        "Si_from_scrap",
        "Mn_from_scrap",
        "N_from_scrap",
    }
    assert set(contribution.keys()) == expected_fields


def test_endpoint_rejects_unknown_scrap_quality_id():
    r = client.post(
        "/calculate/scrap-chemistry",
        json={"scrap_quality_id": "NOT_REAL", "scrap_mass": 0.7, "grade_id": "SS304"},
    )
    assert r.status_code == 422


def test_endpoint_rejects_unknown_grade_id():
    r = client.post(
        "/calculate/scrap-chemistry",
        json={"scrap_quality_id": "SCRAP_HIGH_QUALITY", "scrap_mass": 0.7, "grade_id": "NOT_REAL"},
    )
    assert r.status_code == 422


def test_endpoint_rejects_missing_fields():
    r = client.post("/calculate/scrap-chemistry", json={"scrap_mass": 0.7})
    assert r.status_code == 422


def test_endpoint_does_not_return_any_emissions_fields():
    """Explicit guard: this module must not calculate emissions yet."""
    r = client.post(
        "/calculate/scrap-chemistry",
        json={"scrap_quality_id": "SCRAP_HIGH_QUALITY", "scrap_mass": 0.7, "grade_id": "SS316"},
    )
    body = r.json()
    forbidden = {"tco2e_per_t", "total_tco2e_per_t", "breakdown", "emission_factor", "co2", "co2e"}
    assert forbidden.isdisjoint(body.keys())


def test_alloy_specifications_reference_endpoint():
    r = client.get("/reference-data/alloy-specifications")
    assert r.status_code == 200
    specs = r.json()["specifications"]
    ids = {s["id"] for s in specs}
    assert {"FERRO_CHROME", "NICKEL_METAL", "FERRO_MOLYBDENUM"}.issubset(ids)
    for s in specs:
        assert {"target_element", "concentration_pct", "recovery_pct", "source", "confidence"}.issubset(s.keys())
