"""
Complete end-to-end test suite for the JSL GreenSteel calculation engine.

This file is deliberately distinct from the per-module unit test files
(test_material_balance.py, test_scrap_chemistry.py, etc.): those verify each
engine in isolation, while this file verifies the pipeline AS A WHOLE -
that engines agree with each other when fed the same configuration, and
that every one of the 12 required end-to-end areas plus the 10 required
edge cases behaves correctly across the full stack.

Areas covered (numbered per the test plan):
    1.  Material balance
    2.  Scrap/virgin calculation
    3.  Scrap chemistry
    4.  Alloy deficit
    5.  Carbon calculation
    6.  Energy calculation
    7.  Grade validation
    8.  Optimization
    9.  Sensitivity analysis
    10. Scenario comparison
    11. Monte Carlo analysis
    12. PDF export

Edge cases covered:
    - 0% scrap
    - maximum scrap (100%)
    - 100% renewable electricity
    - 100% grid electricity
    - high-quality scrap
    - low-quality scrap
    - impossible grade chemistry
    - missing emission factor
    - invalid energy mix
    - infeasible optimization

No scientific assumption (any DEMO_PLACEHOLDER value in /data/*.json) is
changed by this file. Where a genuine bug was found during this pass (the
scrap_mass validation bug fixed alongside this suite - see
test_scrap_chemistry.py's test_zero_scrap_mass_is_valid_and_models_all_virgin_charge),
the fix corrected input-validation logic only, never a data value.
"""
import io
import math
import shutil

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.main import app
from backend.models.schemas import (
    CarbonEmissionInput,
    MaterialBalanceInput,
    MaterialQuantityInput,
    OptimizationInput,
    ReportInput,
    ScrapChemistryInput,
    SensitivityInput,
    UncertaintyInput,
)
from backend.optimization.lp_optimizer import optimize_carbon_and_energy
from backend.services import scenario_store
from backend.services.carbon_emissions import calculate_carbon_emissions
from backend.services.material_balance import calculate_material_balance
from backend.services.report_generator import generate_report_pdf
from backend.services.scrap_chemistry import calculate_scrap_chemistry
from backend.services.sensitivity_analysis import run_sensitivity_analysis
from backend.services.uncertainty_analysis import run_uncertainty_analysis

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_scenario_store():
    """Scenario comparison (area 10) persists to disk - keep tests isolated."""
    store_dir = scenario_store._STORE_DIR
    if store_dir.exists():
        shutil.rmtree(store_dir)
    yield
    if store_dir.exists():
        shutil.rmtree(store_dir)


BASELINE = dict(grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=65, yield_fraction=0.92)


# =============================================================================
# 1. MATERIAL BALANCE
# =============================================================================


def test_area_1_material_balance_closes_for_baseline():
    mb = calculate_material_balance(MaterialBalanceInput(scrap_percentage=65, **{"yield": 0.92}))
    assert mb.validation_status.overall == "PASS"
    assert math.isclose(mb.scrap_mass + mb.virgin_mass, mb.charge_mass, rel_tol=1e-9)
    assert math.isclose(mb.charge_mass, 1 / 0.92, rel_tol=1e-6)


def test_area_1_material_balance_matches_across_endpoints():
    """The standalone endpoint and the internal service function must agree."""
    service_result = calculate_material_balance(MaterialBalanceInput(scrap_percentage=65, **{"yield": 0.92}))
    r = client.post("/calculate/material-balance", json={"scrap_percentage": 65, "yield": 0.92})
    assert r.json()["charge_mass"] == service_result.charge_mass
    assert r.json()["scrap_mass"] == service_result.scrap_mass


# =============================================================================
# 2. SCRAP/VIRGIN CALCULATION
# =============================================================================


def test_area_2_scrap_and_virgin_sum_to_100_for_a_range_of_inputs():
    for scrap_pct in (0, 10, 33.3, 50, 65, 90, 100):
        mb = calculate_material_balance(MaterialBalanceInput(scrap_percentage=scrap_pct, **{"yield": 0.9}))
        assert math.isclose(mb.scrap_percentage + mb.virgin_percentage, 100.0, abs_tol=1e-6)


def test_area_2_scrap_mass_proportional_to_scrap_percentage():
    low = calculate_material_balance(MaterialBalanceInput(scrap_percentage=20, **{"yield": 0.9}))
    high = calculate_material_balance(MaterialBalanceInput(scrap_percentage=80, **{"yield": 0.9}))
    assert high.scrap_mass > low.scrap_mass
    assert high.virgin_mass < low.virgin_mass


# =============================================================================
# 3. SCRAP CHEMISTRY
# =============================================================================


def test_area_3_scrap_chemistry_element_contribution_formula():
    """element_mass = scrap_mass x element_fraction x recovery."""
    result = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    expected_cr = 0.7 * 0.18 * 0.95
    assert math.isclose(result.element_contribution.Cr_from_scrap, expected_cr, rel_tol=1e-4)


def test_area_3_high_vs_low_quality_scrap_supply_different_amounts():
    high = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    low = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    assert high.element_contribution.Cr_from_scrap != low.element_contribution.Cr_from_scrap


# =============================================================================
# 4. ALLOY DEFICIT
# =============================================================================


def test_area_4_deficit_formula_is_max_zero_required_minus_supplied():
    result = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.4, grade_id="SS2205"))
    for d in result.element_deficits:
        assert d.deficit_mass == pytest.approx(max(0.0, d.required_mass - d.supplied_mass), abs=1e-6)


def test_area_4_alloy_addition_closes_deficit_to_grade_minimum():
    result = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.3, grade_id="SS316"))
    final_by_element = {f.element: f.pct for f in result.final_chemistry}
    assert final_by_element["Cr"] == pytest.approx(16.0, abs=1e-3)  # SS316 Cr_min
    assert final_by_element["Ni"] == pytest.approx(10.0, abs=1e-3)  # SS316 Ni_min
    assert final_by_element["Mo"] == pytest.approx(2.0, abs=1e-3)  # SS316 Mo_min


# =============================================================================
# 5. CARBON CALCULATION
# =============================================================================


def test_area_5_carbon_calculation_sums_material_energy_process():
    ce = calculate_carbon_emissions(
        CarbonEmissionInput(
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
    )
    expected = (
        ce.material_emissions.total_tco2e + ce.electricity_emissions.total_tco2e + ce.fuel_emissions.total_tco2e + ce.process_emissions.tco2e_per_t
    )
    assert math.isclose(ce.carbon_intensity_tCO2e_per_tSS, expected, rel_tol=1e-6)


# =============================================================================
# 6. ENERGY CALCULATION
# =============================================================================


def test_area_6_energy_mix_formula():
    """CO2_electricity = consumption x sum(share x factor)."""
    ce = calculate_carbon_emissions(
        CarbonEmissionInput(
            electricity_consumption_mwh_per_t=1.0,
            electricity_mix=[{"source_id": "GRID_ELECTRICITY_IN", "share_pct": 70}, {"source_id": "RENEWABLE_ELECTRICITY_IN", "share_pct": 30}],
        )
    )
    expected_factor = 0.7 * 0.71 + 0.3 * 0.02
    assert math.isclose(ce.electricity_emissions.effective_emission_factor_tco2e_per_mwh, expected_factor, rel_tol=1e-6)


def test_area_6_fuel_calculation_ng_and_coal():
    ce = calculate_carbon_emissions(CarbonEmissionInput(natural_gas_consumption_gj_per_t=0.9, coal_consumption_gj_per_t=0.4))
    assert math.isclose(ce.fuel_emissions.natural_gas.tco2e, 0.9 * 0.056, rel_tol=1e-6)
    assert math.isclose(ce.fuel_emissions.coal.tco2e, 0.4 * 0.094, rel_tol=1e-6)


# =============================================================================
# 7. GRADE VALIDATION
# =============================================================================


def test_area_7_grade_validation_passes_for_compatible_scrap():
    result = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    assert result.chemistry_validation.overall == "PASS"


def test_area_7_grade_validation_fails_for_incompatible_scrap():
    """SS304 (Mo_max=0) + SCRAP_HIGH_QUALITY (carries trace Mo) is a real failure."""
    result = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS304"))
    assert result.chemistry_validation.overall == "FAIL"
    mo_item = next(i for i in result.chemistry_validation.items if i.element == "Mo")
    assert mo_item.status == "FAIL"


# =============================================================================
# 8. OPTIMIZATION
# =============================================================================


def test_area_8_optimizer_finds_optimal_and_beats_baseline():
    result = optimize_carbon_and_energy(
        OptimizationInput(
            grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", **{"yield": 0.92},
            scrap_pct_min=0, scrap_pct_max=95, energy_demand_mwh_equivalent_per_t=1.0,
            current_scrap_pct=65, current_energy_mix_pct={"GRID_ELECTRICITY_IN": 100},
        )
    )
    assert result.status == "OPTIMAL"
    assert result.optimized_carbon_intensity <= result.current_carbon_intensity


# =============================================================================
# 9. SENSITIVITY ANALYSIS
# =============================================================================


def test_area_9_sensitivity_sweeps_all_four_dimensions():
    result = run_sensitivity_analysis(
        SensitivityInput(
            grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=65,
            energy_source_id="GRID_ELECTRICITY_IN", **{"yield": 0.92}, energy_demand_mwh_equivalent_per_t=1.0,
        )
    )
    assert len(result.scrap_percentage_sweep.points) == 10
    assert len(result.energy_source_sweep.points) == 4
    assert len(result.scrap_quality_sweep.points) == 3
    assert len(result.grade_sweep.points) == 5


# =============================================================================
# 10. SCENARIO COMPARISON
# =============================================================================


def test_area_10_scenario_save_list_delete_round_trip():
    r1 = client.post(
        "/scenarios",
        json={
            "name": "E2E Scenario", "grade_id": "SS316", "scrap_pct": 65, "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "energy_source_id": "GRID_ELECTRICITY_IN", "electricity_consumption_mwh_per_t": 0.55,
            "natural_gas_consumption_gj_per_t": 0.9, "coal_consumption_gj_per_t": 0.1, "yield": 0.92,
        },
    )
    assert r1.status_code == 200
    scenario_id = r1.json()["id"]

    r2 = client.get("/scenarios")
    assert any(s["id"] == scenario_id for s in r2.json()["scenarios"])

    r3 = client.delete(f"/scenarios/{scenario_id}")
    assert r3.status_code == 200
    assert all(s["id"] != scenario_id for s in client.get("/scenarios").json()["scenarios"])


# =============================================================================
# 11. MONTE CARLO ANALYSIS
# =============================================================================


def test_area_11_monte_carlo_default_1000_and_ordered_percentiles():
    payload = UncertaintyInput(
        grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=65,
        energy_source_id="GRID_ELECTRICITY_IN", **{"yield": 0.92}, energy_demand_mwh_equivalent_per_t=1.0,
        random_seed=42,
    )
    assert payload.n_simulations == 1000
    result = run_uncertainty_analysis(payload)
    mc = result.monte_carlo
    assert mc.min_tco2e_per_t <= mc.p5_tco2e_per_t <= mc.median_tco2e_per_t <= mc.p95_tco2e_per_t <= mc.max_tco2e_per_t
    assert result.best_case.carbon_intensity_tco2e_per_t < result.base_case.carbon_intensity_tco2e_per_t < result.worst_case.carbon_intensity_tco2e_per_t


# =============================================================================
# 12. PDF EXPORT
# =============================================================================


def test_area_12_pdf_export_contains_title_and_all_key_sections():
    pdf_bytes = generate_report_pdf(
        ReportInput(
            scenario_name="E2E PDF Test", grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=65,
            energy_source_id="GRID_ELECTRICITY_IN", electricity_consumption_mwh_per_t=0.55,
            natural_gas_consumption_gj_per_t=0.9, coal_consumption_gj_per_t=0.1, **{"yield": 0.92},
        )
    )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "JSL GreenSteel Carbon Optimization Report" in text
    assert "Material Balance" in text
    assert "Emission Breakdown" in text
    assert "Model Limitations" in text


# =============================================================================
# EDGE CASES
# =============================================================================


def test_edge_zero_percent_scrap_end_to_end():
    """0% scrap must work across material balance, scrap chemistry (now that
    the scrap_mass>=0 fix is in place), carbon emissions, and PDF export."""
    mb = calculate_material_balance(MaterialBalanceInput(scrap_percentage=0, **{"yield": 0.92}))
    assert mb.scrap_mass == 0

    sc = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=mb.scrap_mass, grade_id="SS316"))
    assert sc.element_contribution.Cr_from_scrap == 0
    # All Cr must come from alloy addition when scrap supplies none.
    cr_addition = next(a for a in sc.alloy_additions if a.element == "Cr")
    assert cr_addition.required_mass_kg > 0

    pdf_bytes = generate_report_pdf(
        ReportInput(
            scenario_name="Zero Scrap", grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=0,
            energy_source_id="GRID_ELECTRICITY_IN", electricity_consumption_mwh_per_t=0.55,
            natural_gas_consumption_gj_per_t=0.9, coal_consumption_gj_per_t=0.1, **{"yield": 0.92},
        )
    )
    assert pdf_bytes[:4] == b"%PDF"


def test_edge_maximum_scrap_100_percent_end_to_end():
    mb = calculate_material_balance(MaterialBalanceInput(scrap_percentage=100, **{"yield": 0.92}))
    assert mb.virgin_mass == 0
    assert mb.validation_status.overall == "PASS"

    pdf_bytes = generate_report_pdf(
        ReportInput(
            scenario_name="Max Scrap", grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=100,
            energy_source_id="RENEWABLE_ELECTRICITY_IN", electricity_consumption_mwh_per_t=0.55,
            natural_gas_consumption_gj_per_t=0, coal_consumption_gj_per_t=0, **{"yield": 0.92},
        )
    )
    assert pdf_bytes[:4] == b"%PDF"


def test_edge_100_percent_renewable_electricity():
    ce = calculate_carbon_emissions(
        CarbonEmissionInput(electricity_consumption_mwh_per_t=0.55, electricity_mix=[{"source_id": "RENEWABLE_ELECTRICITY_IN", "share_pct": 100}])
    )
    assert math.isclose(ce.electricity_emissions.total_tco2e, 0.55 * 0.02, rel_tol=1e-6)


def test_edge_100_percent_grid_electricity():
    ce = calculate_carbon_emissions(CarbonEmissionInput(electricity_consumption_mwh_per_t=0.55, electricity_source_id="GRID_ELECTRICITY_IN"))
    assert math.isclose(ce.electricity_emissions.total_tco2e, 0.55 * 0.71, rel_tol=1e-6)


def test_edge_high_quality_scrap():
    result = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    assert result.scrap_chemistry.category_name == "High Quality"
    assert result.chemistry_validation.overall == "PASS"


def test_edge_low_quality_scrap_needs_more_alloy():
    high = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    low = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_LOW_QUALITY", scrap_mass=0.7, grade_id="SS316"))
    high_cr_addition = next(a for a in high.alloy_additions if a.element == "Cr").required_mass_kg
    low_cr_addition = next(a for a in low.alloy_additions if a.element == "Cr").required_mass_kg
    assert low_cr_addition >= high_cr_addition


def test_edge_impossible_grade_chemistry():
    """SS304 requires Mo_max=0; SCRAP_HIGH_QUALITY inherently carries Mo."""
    result = calculate_scrap_chemistry(ScrapChemistryInput(scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_mass=0.7, grade_id="SS304"))
    assert result.chemistry_validation.overall == "FAIL"


def test_edge_missing_emission_factor_not_fabricated():
    ce = calculate_carbon_emissions(CarbonEmissionInput(materials=[MaterialQuantityInput(material_id="UNOBTAINIUM", quantity_t=0.5)]))
    item = ce.material_emissions.items[0]
    assert item.factor_available is False
    assert item.emission_factor_tco2e_per_t is None
    assert item.tco2e == 0
    assert any("UNOBTAINIUM" in w for w in ce.missing_factor_warnings)


def test_edge_invalid_energy_mix_flagged_by_validation():
    r = client.post(
        "/validate",
        json={
            "carbon_emission": {
                "materials": [], "electricity_consumption_mwh_per_t": 0.5,
                "electricity_mix": [{"source_id": "GRID_ELECTRICITY_IN", "share_pct": 100}, {"source_id": "RENEWABLE_ELECTRICITY_IN", "share_pct": 50}],
            }
        },
    )
    body = r.json()
    assert body["overall_status"] == "ERROR"
    assert body["blocked"] is True


def test_edge_infeasible_optimization_returns_exact_message():
    result = optimize_carbon_and_energy(
        OptimizationInput(
            grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY", **{"yield": 0.92},
            scrap_pct_min=50, scrap_pct_max=95, energy_demand_mwh_equivalent_per_t=1.0,
            current_scrap_pct=65, current_energy_mix_pct={"GRID_ELECTRICITY_IN": 100},
        )
    )
    assert result.status == "INFEASIBLE"
    assert result.message == "No feasible solution found under the current constraints."


def test_edge_full_scrap_can_be_infeasible_due_to_yield_concentration():
    """A genuine, non-obvious model finding (not a bug): charging 100% of a
    scrap quality whose Cr is already near a grade's Cr_max can push Cr
    over that max once yield losses concentrate the charge above 1 t."""
    result = optimize_carbon_and_energy(
        OptimizationInput(
            grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", **{"yield": 0.92},
            scrap_pct_min=100, scrap_pct_max=100, energy_demand_mwh_equivalent_per_t=1.0,
            current_scrap_pct=65, current_energy_mix_pct={"GRID_ELECTRICITY_IN": 100},
        )
    )
    assert result.status == "INFEASIBLE"


# =============================================================================
# DEMO VALUE AUDIT
# =============================================================================


def test_every_reference_data_file_is_explicitly_flagged():
    """Every /data/*.json file must carry an explicit status flag identifying
    it as DEMO_PLACEHOLDER (or, for baseline.json, STATED_INPUT for the real
    JSL corporate figures) - this test fails loudly if a future data change
    silently drops the disclosure."""
    r = client.get("/reference-data")
    assert r.status_code == 200
    body = r.json()
    assert body["validation_issues"] == []

    data = body["data"]
    for key in ("emission_factors", "steel_grades", "scrap_quality", "energy_sources", "alloy_specifications"):
        assert data[key]["_meta"]["status"] == "DEMO_PLACEHOLDER", key

    assert data["baseline"]["_meta"]["status"] == "STATED_INPUT"
    assert data["baseline"]["demo_scenario"]["_status"] == "DEMO_PLACEHOLDER"


def test_every_emission_factor_discloses_confidence_and_source():
    r = client.get("/reference-data/emission-factors")
    factors = r.json()["factors"]
    assert len(factors) > 0
    for f in factors:
        assert "DEMO_PLACEHOLDER" in f["source"] or "PLACEHOLDER" in f["source"]
        assert "unverified" in f["confidence"].lower() or "not assessed" in f["confidence"].lower()
