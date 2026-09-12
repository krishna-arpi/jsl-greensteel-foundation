"""
Automated tests for the LP/MILP carbon-intensity optimization engine.

Covers the service function (backend/optimization/lp_optimizer.py) and the
POST /optimize API route. Functional unit: 1 tonne of finished stainless
steel, matching every other engine in this application.

Key properties verified:
    - The optimizer never does worse than the caller's stated "current"
      scenario (optimized_carbon_intensity <= current_carbon_intensity),
      since the current scenario is itself always a feasible point.
    - Grade chemistry constraints (Cr/Ni/Mo) are respected in the solution.
    - An infeasible configuration returns the exact required message rather
      than a fabricated result or a crash.
    - Missing reference data is surfaced as status="ERROR", not a 500.
    - Binary (single-source) vs continuous (blending) energy modes both work.
"""
import math

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import OptimizationInput
from backend.optimization.lp_optimizer import optimize_carbon_and_energy

client = TestClient(app)


def _make_input(**overrides) -> OptimizationInput:
    defaults = dict(
        grade_id="SS316",
        scrap_quality_id="SCRAP_HIGH_QUALITY",
        scrap_pct_min=0,
        scrap_pct_max=95,
        energy_demand_mwh_equivalent_per_t=1.0,
        allow_energy_blending=True,
        current_scrap_pct=65,
        current_energy_mix_pct={"GRID_ELECTRICITY_IN": 100},
    )
    defaults.update(overrides)
    yield_value = defaults.pop("yield_fraction", 0.92)
    return OptimizationInput(**defaults, **{"yield": yield_value})


# --- Feasible optimization ---------------------------------------------------


def test_feasible_solution_is_optimal():
    result = optimize_carbon_and_energy(_make_input())
    assert result.status == "OPTIMAL"
    assert result.optimal_scrap_percentage is not None
    assert result.optimized_carbon_intensity is not None


def test_scrap_plus_virgin_equals_100():
    result = optimize_carbon_and_energy(_make_input())
    assert math.isclose(result.optimal_scrap_percentage + result.optimal_virgin_percentage, 100.0, abs_tol=1e-3)


def test_scrap_percentage_within_bounds():
    result = optimize_carbon_and_energy(_make_input(scrap_pct_min=10, scrap_pct_max=80))
    assert 10 - 1e-3 <= result.optimal_scrap_percentage <= 80 + 1e-3


def test_energy_mix_sums_to_100():
    result = optimize_carbon_and_energy(_make_input())
    total_share = sum(m.share_pct for m in result.optimal_energy_mix)
    assert math.isclose(total_share, 100.0, abs_tol=1e-3)


def test_optimizer_prefers_cheapest_energy_source_when_unconstrained():
    """Renewable electricity (0.02 tCO2e/MWh) is far cheaper than grid
    (0.71), NG (0.056*3.6), or coal (0.094*3.6); with no capacity caps the
    optimizer should allocate 100% to renewable."""
    result = optimize_carbon_and_energy(_make_input())
    renewable_share = next(m.share_pct for m in result.optimal_energy_mix if m.source_id == "RENEWABLE_ELECTRICITY_IN")
    assert math.isclose(renewable_share, 100.0, abs_tol=1e-3)


def test_optimizer_pushes_scrap_to_max_when_scrap_is_cleaner():
    """Scrap's embodied factor (0.3) is far below virgin's (2.3), so absent
    a chemistry constraint forcing it down, scrap should hit its S_max."""
    result = optimize_carbon_and_energy(_make_input(scrap_pct_max=80))
    assert math.isclose(result.optimal_scrap_percentage, 80.0, abs_tol=1e-3)


def test_optimizer_never_worse_than_current_scenario():
    """The current scenario is itself always a feasible point, so the
    optimum must be at least as good (<=)."""
    result = optimize_carbon_and_energy(_make_input())
    assert result.optimized_carbon_intensity <= result.current_carbon_intensity + 1e-6


def test_current_scenario_chemistry_valid_flag_true_for_normal_case():
    """SS316 + high-quality scrap at 65% scrap is a legitimate composition -
    the current scenario should be flagged chemistry-valid."""
    result = optimize_carbon_and_energy(_make_input())
    assert result.current_scenario_chemistry_valid is True
    assert result.current_scenario_chemistry_note is None


def test_current_scenario_chemistry_invalid_flagged_when_scrap_contaminates_beyond_max():
    """SS304 has Mo_max=0; SCRAP_HIGH_QUALITY carries 0.3% Mo. At any
    positive current_scrap_pct, the 'current' composition inherently
    exceeds Mo_max regardless of alloy top-up - this must be flagged
    rather than silently presented as a valid, cheaper baseline than the
    (fully chemistry-respecting) optimized result."""
    result = optimize_carbon_and_energy(
        _make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY", current_scrap_pct=65, scrap_pct_min=0, scrap_pct_max=95)
    )
    assert result.status == "OPTIMAL"
    assert result.current_scenario_chemistry_valid is False
    assert result.current_scenario_chemistry_note is not None
    assert "Mo" in result.current_scenario_chemistry_note


def test_current_scenario_chemistry_invalid_can_make_optimized_appear_worse():
    """This is the honest, expected consequence of the flag above: when the
    'current' baseline is itself chemistry-invalid (silently over Mo_max),
    it can look artificially cheap, so the fully-valid optimized result may
    show a negative 'reduction'. The flag is what makes that legible rather
    than misleading."""
    result = optimize_carbon_and_energy(
        _make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY", current_scrap_pct=65, scrap_pct_min=0, scrap_pct_max=95)
    )
    assert result.current_scenario_chemistry_valid is False
    # optimized_carbon_intensity may legitimately exceed current_carbon_intensity here;
    # what matters is that the flag/note explain why, not that reduction stays positive.
    assert result.optimized_carbon_intensity is not None
    assert result.current_carbon_intensity is not None


def test_absolute_and_percentage_reduction_consistent():
    result = optimize_carbon_and_energy(_make_input())
    expected_abs = result.current_carbon_intensity - result.optimized_carbon_intensity
    assert math.isclose(result.absolute_reduction, expected_abs, rel_tol=1e-4)
    expected_pct = expected_abs / result.current_carbon_intensity * 100
    assert math.isclose(result.percentage_reduction, expected_pct, rel_tol=1e-3)


def test_grade_chemistry_respected_in_solution():
    """SS316 requires Cr 16-18%, Ni 10-14%, Mo 2-3%; verify the optimizer's
    alloy additions plus scrap contribution land within these bounds."""
    result = optimize_carbon_and_energy(_make_input(grade_id="SS316", scrap_pct_max=95))
    # Reconstruct final Cr/Ni/Mo the same way the engine does, to cross-check.
    from backend.data.loader import get_alloy_specifications, get_emission_factors, get_scrap_quality, get_steel_grades

    grade = next(g for g in get_steel_grades()["grades"] if g["id"] == "SS316")
    scrap = next(c for c in get_scrap_quality()["categories"] if c["id"] == "SCRAP_HIGH_QUALITY")
    specs = {s["id"]: s for s in get_alloy_specifications()["specifications"]}

    charge_mass = 1 / 0.92
    scrap_mass = (result.optimal_scrap_percentage / 100) * charge_mass
    scrap_recovery = scrap["alloy_recovery"] / 100

    alloy_by_element = {a.element: a.required_mass_kg / 1000 for a in result.optimal_alloy_additions}
    alloy_id_by_element = {"Cr": "FERRO_CHROME", "Ni": "NICKEL_METAL", "Mo": "FERRO_MOLYBDENUM"}

    for element in ("Cr", "Ni", "Mo"):
        spec = specs[alloy_id_by_element[element]]
        final_mass = scrap_mass * (scrap[element] / 100) * scrap_recovery + alloy_by_element[element] * (
            spec["concentration_pct"] / 100
        ) * (spec["recovery_pct"] / 100)
        final_pct = final_mass * 100
        assert grade[f"{element}_min"] - 1e-2 <= final_pct <= grade[f"{element}_max"] + 1e-2


# --- MILP: single-source (binary) mode --------------------------------------


def test_single_source_mode_picks_exactly_one_source():
    result = optimize_carbon_and_energy(_make_input(allow_energy_blending=False))
    assert result.status == "OPTIMAL"
    shares = [m.share_pct for m in result.optimal_energy_mix]
    ones = [s for s in shares if math.isclose(s, 100.0, abs_tol=1e-3)]
    zeros = [s for s in shares if math.isclose(s, 0.0, abs_tol=1e-3)]
    assert len(ones) == 1
    assert len(zeros) == 3


def test_single_source_mode_picks_renewable_when_cheapest():
    result = optimize_carbon_and_energy(_make_input(allow_energy_blending=False))
    chosen = next(m.source_id for m in result.optimal_energy_mix if math.isclose(m.share_pct, 100.0, abs_tol=1e-3))
    assert chosen == "RENEWABLE_ELECTRICITY_IN"


# --- Constraint 8 & 9: availability / capacity ------------------------------


def test_scrap_availability_constraint_caps_scrap_mass():
    """A tight scrap availability cap should force less scrap than S_max would otherwise allow."""
    result = optimize_carbon_and_energy(_make_input(scrap_pct_max=95, scrap_availability_t=0.3))
    charge_mass = 1 / 0.92
    scrap_mass = (result.optimal_scrap_percentage / 100) * charge_mass
    assert scrap_mass <= 0.3 + 1e-3
    assert any(b.name == "scrap_availability" for b in result.binding_constraints)


def test_energy_capacity_constraint_caps_renewable_share():
    """Capping renewable at 30% should force the remaining 70% onto other sources."""
    result = optimize_carbon_and_energy(_make_input(energy_capacity_pct={"RENEWABLE_ELECTRICITY_IN": 30}))
    renewable_share = next(m.share_pct for m in result.optimal_energy_mix if m.source_id == "RENEWABLE_ELECTRICITY_IN")
    assert renewable_share <= 30 + 1e-3
    assert any(b.name == "energy_capacity_RENEWABLE_ELECTRICITY_IN" for b in result.binding_constraints)


# --- Binding constraints ------------------------------------------------------


def test_binding_constraints_include_scrap_max_when_active():
    result = optimize_carbon_and_energy(_make_input(scrap_pct_max=80))
    assert any(b.name == "scrap_pct_max" for b in result.binding_constraints)


def test_binding_constraints_include_grade_min_limits():
    result = optimize_carbon_and_energy(_make_input(grade_id="SS316"))
    names = {b.name for b in result.binding_constraints}
    assert "Ni_min_limit" in names or "Mo_min_limit" in names


# --- Infeasibility -----------------------------------------------------------


def test_infeasible_scenario_returns_exact_message():
    """SS304 has Mo_max=0; forcing at least 50% high-quality scrap (which
    carries trace Mo) makes the Mo ceiling unsatisfiable."""
    result = optimize_carbon_and_energy(
        _make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct_min=50, scrap_pct_max=95)
    )
    assert result.status == "INFEASIBLE"
    assert result.message == "No feasible solution found under the current constraints."
    assert result.optimal_scrap_percentage is None
    assert result.optimized_carbon_intensity is None


def test_infeasible_scenario_returns_no_binding_constraints():
    result = optimize_carbon_and_energy(
        _make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct_min=50, scrap_pct_max=95)
    )
    assert result.binding_constraints == []


def test_feasible_ss304_with_low_scrap_min():
    """SS304 is feasible when scrap isn't forced high enough to violate the
    Mo ceiling (S_min=0 allows the solver to use more virgin material)."""
    result = optimize_carbon_and_energy(
        _make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct_min=0, scrap_pct_max=95)
    )
    assert result.status == "OPTIMAL"


# --- Data errors: never fabricate, never 500 --------------------------------


def test_unknown_grade_id_returns_error_status():
    result = optimize_carbon_and_energy(_make_input(grade_id="NOT_A_REAL_GRADE"))
    assert result.status == "ERROR"
    assert "NOT_A_REAL_GRADE" in result.message


def test_unknown_scrap_quality_id_returns_error_status():
    result = optimize_carbon_and_energy(_make_input(scrap_quality_id="NOT_REAL"))
    assert result.status == "ERROR"
    assert "NOT_REAL" in result.message


def test_unknown_process_route_id_returns_error_status():
    result = optimize_carbon_and_energy(_make_input(process_route_id="NOT_A_REAL_ROUTE"))
    assert result.status == "ERROR"


# --- Process emissions (exogenous) ------------------------------------------


def test_process_route_adds_constant_to_objective():
    without_process = optimize_carbon_and_energy(_make_input())
    with_process = optimize_carbon_and_energy(_make_input(process_route_id="EAF_HIGH_SCRAP"))
    # Same decisions, but +0.35 tCO2e/t from the EAF_HIGH_SCRAP process factor.
    assert math.isclose(with_process.optimized_carbon_intensity - without_process.optimized_carbon_intensity, 0.35, abs_tol=1e-3)


def test_process_override_takes_precedence_over_route():
    result = optimize_carbon_and_energy(_make_input(process_route_id="EAF_HIGH_SCRAP", process_emission_override_tco2e_per_t=5.0))
    baseline = optimize_carbon_and_energy(_make_input())
    assert math.isclose(result.optimized_carbon_intensity - baseline.optimized_carbon_intensity, 5.0, abs_tol=1e-3)


# --- API-level tests -----------------------------------------------------------


def test_endpoint_feasible_scenario():
    r = client.post(
        "/optimize",
        json={
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "yield": 0.92,
            "scrap_pct_min": 0,
            "scrap_pct_max": 95,
            "energy_demand_mwh_equivalent_per_t": 1.0,
            "current_scrap_pct": 65,
            "current_energy_mix_pct": {"GRID_ELECTRICITY_IN": 100},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OPTIMAL"
    required_fields = {
        "status",
        "optimal_scrap_percentage",
        "optimal_virgin_percentage",
        "optimal_energy_mix",
        "optimal_alloy_additions",
        "optimized_carbon_intensity",
        "current_carbon_intensity",
        "absolute_reduction",
        "percentage_reduction",
        "binding_constraints",
    }
    assert required_fields.issubset(body.keys())


def test_endpoint_infeasible_scenario_returns_200_not_error_code():
    r = client.post(
        "/optimize",
        json={
            "grade_id": "SS304",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "yield": 0.92,
            "scrap_pct_min": 50,
            "scrap_pct_max": 95,
            "energy_demand_mwh_equivalent_per_t": 1.0,
            "current_scrap_pct": 65,
            "current_energy_mix_pct": {"GRID_ELECTRICITY_IN": 100},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "INFEASIBLE"
    assert body["message"] == "No feasible solution found under the current constraints."


def test_endpoint_rejects_missing_required_fields():
    r = client.post("/optimize", json={})
    assert r.status_code == 422


def test_endpoint_rejects_invalid_yield():
    r = client.post(
        "/optimize",
        json={
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "yield": 0,
            "energy_demand_mwh_equivalent_per_t": 1.0,
            "current_scrap_pct": 65,
            "current_energy_mix_pct": {"GRID_ELECTRICITY_IN": 100},
        },
    )
    assert r.status_code == 422


def test_endpoint_single_source_mode():
    r = client.post(
        "/optimize",
        json={
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "yield": 0.92,
            "energy_demand_mwh_equivalent_per_t": 1.0,
            "allow_energy_blending": False,
            "current_scrap_pct": 65,
            "current_energy_mix_pct": {"GRID_ELECTRICITY_IN": 100},
        },
    )
    assert r.status_code == 200
    body = r.json()
    shares = [m["share_pct"] for m in body["optimal_energy_mix"]]
    assert sorted(shares) == pytest.approx([0.0, 0.0, 0.0, 100.0], abs=1e-3)
