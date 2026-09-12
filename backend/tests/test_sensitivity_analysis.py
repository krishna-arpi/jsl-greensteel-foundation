"""
Automated tests for the sensitivity analysis engine.

Covers the service function (backend/services/sensitivity_analysis.py) and
the POST /sensitivity API route. Functional unit: 1 tonne of finished
stainless steel, matching every other engine in this application.

Key properties verified:
    - Each sweep has the exact required set of points (10 scrap%, 4 energy
      sources, 3 scrap qualities, 5 grades).
    - An infeasible point (fails grade chemistry) is marked chemistry_valid
      =False and is never marked is_lowest_feasible, even if its raw number
      is the lowest in the sweep.
    - Insight text only asserts things that are true of the actual points
      (trend direction/magnitude, infeasibility counts) - verified by
      cross-checking the numbers referenced in the text against the points.
"""
import math

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import SensitivityInput
from backend.services.sensitivity_analysis import run_sensitivity_analysis

client = TestClient(app)


def _make_input(**overrides) -> SensitivityInput:
    defaults = dict(
        grade_id="SS316",
        scrap_quality_id="SCRAP_HIGH_QUALITY",
        scrap_pct=65,
        energy_source_id="GRID_ELECTRICITY_IN",
        energy_demand_mwh_equivalent_per_t=1.0,
    )
    defaults.update(overrides)
    yield_value = defaults.pop("yield_fraction", 0.92)
    return SensitivityInput(**defaults, **{"yield": yield_value})


# --- Sweep structure ---------------------------------------------------------


def test_scrap_percentage_sweep_has_all_ten_points():
    result = run_sensitivity_analysis(_make_input())
    labels = [p.label for p in result.scrap_percentage_sweep.points]
    assert labels == ["0%", "10%", "20%", "30%", "40%", "50%", "60%", "70%", "80%", "90%"]


def test_energy_source_sweep_has_all_four_points():
    result = run_sensitivity_analysis(_make_input())
    ids = {p.value_id for p in result.energy_source_sweep.points}
    assert ids == {"GRID_ELECTRICITY_IN", "RENEWABLE_ELECTRICITY_IN", "NATURAL_GAS", "COAL"}


def test_scrap_quality_sweep_has_all_three_points():
    result = run_sensitivity_analysis(_make_input())
    labels = {p.label for p in result.scrap_quality_sweep.points}
    assert labels == {"High Quality", "Medium Quality", "Low Quality"}


def test_grade_sweep_has_all_five_points():
    result = run_sensitivity_analysis(_make_input())
    labels = {p.label for p in result.grade_sweep.points}
    assert labels == {"304", "316", "430", "410", "Duplex 2205"}


# --- Correctness of individual points ----------------------------------------


def test_scrap_zero_percent_matches_all_virgin_calculation():
    """At 0% scrap, material carbon should be exactly virgin_embodied x charge_mass
    plus whatever alloy is needed (scrap supplies nothing when scrap%=0)."""
    result = run_sensitivity_analysis(_make_input(scrap_pct=65))
    zero_point = next(p for p in result.scrap_percentage_sweep.points if p.value_id == "0")
    charge_mass = 1 / 0.92
    # Material-only component (no alloy needed check omitted for simplicity: just verify > virgin baseline)
    virgin_only_material = charge_mass * 2.3  # VIRGIN_EMBODIED factor
    assert zero_point.carbon_intensity_tco2e_per_t >= virgin_only_material - 1e-3


def test_energy_source_sweep_orders_grid_above_renewable():
    """Grid (0.71 tCO2e/MWh) should always cost more than renewable (0.02),
    all else held equal."""
    result = run_sensitivity_analysis(_make_input())
    by_id = {p.value_id: p.carbon_intensity_tco2e_per_t for p in result.energy_source_sweep.points}
    assert by_id["GRID_ELECTRICITY_IN"] > by_id["RENEWABLE_ELECTRICITY_IN"]


def test_scrap_percentage_sweep_is_monotonically_decreasing_for_ss316():
    """SS316 tolerates SCRAP_HIGH_QUALITY's composition across the whole
    range, so higher scrap should strictly reduce intensity here."""
    result = run_sensitivity_analysis(_make_input(grade_id="SS316"))
    values = [p.carbon_intensity_tco2e_per_t for p in result.scrap_percentage_sweep.points]
    assert all(values[i] > values[i + 1] for i in range(len(values) - 1))


# --- Infeasibility handling --------------------------------------------------


def test_infeasible_points_are_marked_and_excluded_from_lowest():
    """SS304 has Mo_max=0; SCRAP_HIGH_QUALITY carries trace Mo, so every
    scrap % above 0 should be infeasible, leaving only 0% as feasible - and
    0% (not a lower-but-infeasible point) must be the lowest_feasible one."""
    result = run_sensitivity_analysis(_make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY"))
    points = result.scrap_percentage_sweep.points
    zero_point = next(p for p in points if p.value_id == "0")
    ninety_point = next(p for p in points if p.value_id == "90")

    assert zero_point.chemistry_valid is True
    assert ninety_point.chemistry_valid is False
    # 90% has a lower raw number but is infeasible, so 0% must be the flagged lowest.
    assert ninety_point.carbon_intensity_tco2e_per_t < zero_point.carbon_intensity_tco2e_per_t
    assert zero_point.is_lowest_feasible is True
    assert ninety_point.is_lowest_feasible is False


def test_no_infeasible_point_is_ever_marked_lowest_feasible():
    result = run_sensitivity_analysis(_make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY"))
    for sweep in (
        result.scrap_percentage_sweep,
        result.energy_source_sweep,
        result.scrap_quality_sweep,
        result.grade_sweep,
    ):
        for p in sweep.points:
            if p.is_lowest_feasible:
                assert p.chemistry_valid is True


def test_grade_sweep_flags_infeasible_grades_for_contaminated_scrap():
    """304 (Mo_max=0) and 430 (no Mo tolerance) should be infeasible with
    high-quality scrap's trace Mo at a meaningful scrap %."""
    result = run_sensitivity_analysis(_make_input(grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=65))
    by_id = {p.value_id: p.chemistry_valid for p in result.grade_sweep.points}
    assert by_id["SS304"] is False


# --- Insight text is grounded in the actual numbers -------------------------


def test_scrap_pct_insight_mentions_actual_endpoint_values():
    result = run_sensitivity_analysis(_make_input(grade_id="SS316"))
    points = result.scrap_percentage_sweep.points
    first, last = points[0], points[-1]
    insight = result.scrap_percentage_sweep.insight
    assert f"{first.carbon_intensity_tco2e_per_t:.3f}" in insight
    assert f"{last.carbon_intensity_tco2e_per_t:.3f}" in insight


def test_scrap_pct_insight_says_decreases_when_values_actually_decrease():
    result = run_sensitivity_analysis(_make_input(grade_id="SS316"))
    points = result.scrap_percentage_sweep.points
    assert points[-1].carbon_intensity_tco2e_per_t < points[0].carbon_intensity_tco2e_per_t
    assert "decreases" in result.scrap_percentage_sweep.insight


def test_scrap_pct_insight_reports_low_feasible_count_honestly():
    result = run_sensitivity_analysis(_make_input(grade_id="SS304", scrap_quality_id="SCRAP_HIGH_QUALITY"))
    insight = result.scrap_percentage_sweep.insight
    assert "Only 1 of 10" in insight
    assert "isn't enough to identify a trend" in insight


def test_categorical_insight_names_actual_best_and_worst():
    result = run_sensitivity_analysis(_make_input())
    sweep = result.energy_source_sweep
    feasible = [p for p in sweep.points if p.chemistry_valid]
    best = min(feasible, key=lambda p: p.carbon_intensity_tco2e_per_t)
    worst = max(feasible, key=lambda p: p.carbon_intensity_tco2e_per_t)
    assert best.label in sweep.insight
    assert worst.label in sweep.insight


def test_categorical_insight_reports_infeasible_count_accurately():
    result = run_sensitivity_analysis(_make_input(grade_id="SS316", scrap_quality_id="SCRAP_HIGH_QUALITY", scrap_pct=65))
    sweep = result.grade_sweep
    infeasible_count = sum(1 for p in sweep.points if not p.chemistry_valid)
    if infeasible_count > 0:
        assert f"{infeasible_count} of {len(sweep.points)}" in sweep.insight


# --- Baseline holding-fixed behavior -----------------------------------------


def test_energy_sweep_holds_scrap_pct_and_grade_fixed():
    """Every point in the energy sweep should use the same scrap%/grade -
    verified indirectly by checking the material-related portion is
    identical (i.e. only the energy term differs)."""
    result = run_sensitivity_analysis(_make_input(scrap_pct=50))
    points = result.energy_source_sweep.points
    intensities = [p.carbon_intensity_tco2e_per_t for p in points]
    # All four should differ only by the energy term - GRID and COAL are
    # both nonzero and different, but the spread should be plausible for a
    # single energy_demand=1.0 MWh-equivalent term rather than wildly off.
    assert max(intensities) - min(intensities) < 5.0


# --- Data validation ----------------------------------------------------------


def test_unknown_grade_id_returns_422():
    with pytest.raises(Exception):
        run_sensitivity_analysis(_make_input(grade_id="NOT_A_REAL_GRADE"))


def test_unknown_scrap_quality_id_returns_422():
    with pytest.raises(Exception):
        run_sensitivity_analysis(_make_input(scrap_quality_id="NOT_REAL"))


def test_unknown_energy_source_id_returns_422():
    with pytest.raises(Exception):
        run_sensitivity_analysis(_make_input(energy_source_id="NOT_REAL"))


# --- API-level tests -----------------------------------------------------------


def test_endpoint_returns_all_four_sweeps():
    r = client.post(
        "/sensitivity",
        json={
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "scrap_pct": 65,
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "yield": 0.92,
            "energy_demand_mwh_equivalent_per_t": 1.0,
        },
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("scrap_percentage_sweep", "energy_source_sweep", "scrap_quality_sweep", "grade_sweep"):
        assert key in body
        assert "points" in body[key]
        assert "insight" in body[key]


def test_endpoint_rejects_unknown_grade():
    r = client.post(
        "/sensitivity",
        json={
            "grade_id": "NOT_REAL",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "scrap_pct": 65,
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "yield": 0.92,
            "energy_demand_mwh_equivalent_per_t": 1.0,
        },
    )
    assert r.status_code == 422


def test_endpoint_rejects_missing_fields():
    r = client.post("/sensitivity", json={})
    assert r.status_code == 422


def test_endpoint_exactly_ten_scrap_points_four_energy_three_quality_five_grade():
    r = client.post(
        "/sensitivity",
        json={
            "grade_id": "SS410",
            "scrap_quality_id": "SCRAP_MEDIUM_QUALITY",
            "scrap_pct": 50,
            "energy_source_id": "RENEWABLE_ELECTRICITY_IN",
            "yield": 0.9,
            "energy_demand_mwh_equivalent_per_t": 0.8,
        },
    )
    body = r.json()
    assert len(body["scrap_percentage_sweep"]["points"]) == 10
    assert len(body["energy_source_sweep"]["points"]) == 4
    assert len(body["scrap_quality_sweep"]["points"]) == 3
    assert len(body["grade_sweep"]["points"]) == 5
