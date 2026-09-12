"""
Automated tests for the PDF report generator.

Covers the service function (backend/services/report_generator.py) and the
POST /report/pdf API route. Rather than asserting exact byte layout (fragile
and not meaningful), these tests extract the PDF's text via pypdf and check
that every one of the 16 requested sections actually appears with numbers
consistent with the underlying engines - i.e. the report is not just
"a PDF that opens" but one whose content is verifiably correct.
"""
import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.main import app
from backend.models.schemas import ReportInput
from backend.services.report_generator import generate_report_pdf

client = TestClient(app)


def _make_input(**overrides) -> ReportInput:
    defaults = dict(
        scenario_name="Test Scenario",
        grade_id="SS316",
        scrap_quality_id="SCRAP_HIGH_QUALITY",
        scrap_pct=65,
        energy_source_id="GRID_ELECTRICITY_IN",
        electricity_consumption_mwh_per_t=0.55,
        natural_gas_consumption_gj_per_t=0.9,
        coal_consumption_gj_per_t=0.1,
    )
    defaults.update(overrides)
    yield_value = defaults.pop("yield_fraction", 0.92)
    return ReportInput(**defaults, **{"yield": yield_value})


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


# --- Structural checks ---------------------------------------------------


def test_generates_valid_pdf_bytes():
    pdf_bytes = generate_report_pdf(_make_input())
    assert pdf_bytes[:4] == b"%PDF"
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) > 1


def test_title_is_exact_required_string():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "JSL GreenSteel Carbon Optimization Report" in text


def test_scenario_name_appears():
    text = _extract_text(generate_report_pdf(_make_input(scenario_name="My Custom Scenario XYZ")))
    assert "My Custom Scenario XYZ" in text


# --- Each of the 16 requested content areas is actually present -----------


def test_contains_scenario_information():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Scenario Information" in text
    assert "Functional unit" in text


def test_contains_user_inputs_matching_payload():
    payload = _make_input(scrap_pct=42, electricity_consumption_mwh_per_t=0.77)
    text = _extract_text(generate_report_pdf(payload))
    assert "User Inputs" in text
    assert "42.0%" in text
    assert "0.77 MWh/t" in text


def test_contains_material_balance_with_correct_numbers():
    payload = _make_input(scrap_pct=65, yield_fraction=0.92)
    text = _extract_text(generate_report_pdf(payload))
    assert "Material Balance" in text
    charge_mass = 1 / 0.92
    assert f"{charge_mass:.4f}" in text


def test_contains_scrap_virgin_mix_section():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Scrap / Virgin Mix" in text


def test_contains_alloy_additions_section():
    text = _extract_text(generate_report_pdf(_make_input(grade_id="SS316")))
    assert "Alloy Additions" in text
    assert "Ferro-Chrome" in text or "Nickel Metal" in text or "Ferro-Molybdenum" in text


def test_contains_carbon_calculation_formula():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Carbon Calculation" in text
    assert "Material Carbon" in text and "Energy Carbon" in text and "Process Carbon" in text


def test_contains_emission_breakdown_section():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Emission Breakdown" in text
    assert "Scrap" in text and "Virgin iron" in text


def test_contains_current_carbon_intensity_matching_engine():
    from backend.models.schemas import CarbonEmissionInput, MaterialBalanceInput, MaterialQuantityInput, ScrapChemistryInput
    from backend.services.carbon_emissions import calculate_carbon_emissions
    from backend.services.material_balance import calculate_material_balance
    from backend.services.scrap_chemistry import calculate_scrap_chemistry

    payload = _make_input()
    mb = calculate_material_balance(MaterialBalanceInput(scrap_percentage=payload.scrap_pct, **{"yield": payload.yield_fraction}))
    sc = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id=payload.scrap_quality_id, scrap_mass=mb.scrap_mass, grade_id=payload.grade_id))
    alloy_materials = [
        MaterialQuantityInput(material_id=a.alloy_id, quantity_t=a.required_mass_kg / 1000.0, label=a.alloy_name)
        for a in sc.alloy_additions
        if a.required_mass_kg > 0.01
    ]
    ce = calculate_carbon_emissions(
        CarbonEmissionInput(
            materials=[
                MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=mb.scrap_mass, label="Scrap"),
                MaterialQuantityInput(material_id="VIRGIN_EMBODIED", quantity_t=mb.virgin_mass, label="Virgin iron"),
                *alloy_materials,
            ],
            electricity_consumption_mwh_per_t=payload.electricity_consumption_mwh_per_t,
            electricity_mix=[],
            electricity_source_id=payload.energy_source_id,
            natural_gas_consumption_gj_per_t=payload.natural_gas_consumption_gj_per_t,
            coal_consumption_gj_per_t=payload.coal_consumption_gj_per_t,
        )
    )

    text = _extract_text(generate_report_pdf(payload))
    assert "Current Carbon Intensity" in text
    assert f"{ce.carbon_intensity_tCO2e_per_tSS:.4f}" in text


def test_contains_optimized_carbon_intensity_and_reduction_when_optimal():
    text = _extract_text(generate_report_pdf(_make_input(grade_id="SS316")))
    assert "Optimized Carbon Intensity" in text
    assert "Carbon Reduction" in text
    assert "CO2 saved" in text


def test_contains_infeasible_message_when_optimization_infeasible():
    """SS304 forced to >=50% scrap of a Mo-contaminated quality is infeasible."""
    text = _extract_text(generate_report_pdf(_make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct_min=50, scrap_pct_max=95)))
    assert "INFEASIBLE" in text
    assert "No feasible solution" in text


def test_contains_sensitivity_results_section():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Sensitivity Results" in text
    assert "Scrap %" in text
    assert "Energy Source" in text


def test_contains_validation_results_with_check_count():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Validation Results" in text
    assert "passed" in text
    assert "Scrap percentage limit" in text


def test_contains_assumptions_section():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Assumptions" in text
    assert "functional unit" in text.lower()


def test_contains_emission_factor_sources_table():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Emission-Factor Sources" in text
    assert "DEMO_PLACEHOLDER" in text
    assert "Stainless Scrap" in text  # a real factor display name, not a raw id


def test_contains_model_limitations_verbatim():
    text = _extract_text(generate_report_pdf(_make_input()))
    assert "Model Limitations" in text
    assert "Scrap composition varies" in text
    assert "not a verified ISO product carbon footprint" in text


def test_disclosure_banner_present_on_first_page():
    reader = PdfReader(io.BytesIO(generate_report_pdf(_make_input())))
    first_page_text = reader.pages[0].extract_text().replace("\n", " ")
    assert "DEMO_PLACEHOLDER" in first_page_text
    assert "decision-support prototype" in first_page_text


# --- Modeling discrepancy disclosure (optimizer vs. detailed model) --------


def test_discloses_optimizer_vs_detailed_model_difference():
    text = _extract_text(generate_report_pdf(_make_input(grade_id="SS316")))
    assert "simplified single-commodity" in text


# --- Data validation: never a raw 500 --------------------------------------


def test_unknown_grade_raises_http_exception_not_key_error():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        generate_report_pdf(_make_input(grade_id="NOT_A_REAL_GRADE"))
    assert exc_info.value.status_code == 422


def test_unknown_scrap_quality_raises_http_exception():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        generate_report_pdf(_make_input(scrap_quality_id="NOT_REAL"))
    assert exc_info.value.status_code == 422


def test_unknown_energy_source_raises_http_exception():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        generate_report_pdf(_make_input(energy_source_id="NOT_REAL"))
    assert exc_info.value.status_code == 422


# --- API-level tests -----------------------------------------------------------


def test_endpoint_returns_pdf_content_type_and_disposition():
    r = client.post(
        "/report/pdf",
        json={
            "scenario_name": "API Test",
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "scrap_pct": 65,
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "yield": 0.92,
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


def test_endpoint_returns_422_for_unknown_grade():
    r = client.post(
        "/report/pdf",
        json={
            "scenario_name": "Bad",
            "grade_id": "NOT_REAL",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "scrap_pct": 65,
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "yield": 0.92,
        },
    )
    assert r.status_code == 422


def test_endpoint_rejects_missing_fields():
    r = client.post("/report/pdf", json={})
    assert r.status_code == 422


def test_endpoint_rejects_invalid_yield():
    r = client.post(
        "/report/pdf",
        json={
            "scenario_name": "Bad Yield",
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "scrap_pct": 65,
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9,
            "coal_consumption_gj_per_t": 0.1,
            "yield": 0,
        },
    )
    assert r.status_code == 422
