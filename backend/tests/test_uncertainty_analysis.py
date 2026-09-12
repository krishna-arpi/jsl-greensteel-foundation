"""
Automated tests for the uncertainty analysis engine.

Covers the service function (backend/services/uncertainty_analysis.py) and
the POST /uncertainty API route. Functional unit: 1 tonne of finished
stainless steel, matching every other engine in this application.

Key properties verified:
    - Best Case <= Base Case <= Worst Case (deterministic extremes bracket
      the nominal value, since each parameter is pushed toward whichever
      bound helps or hurts carbon intensity).
    - Monte Carlo statistics are internally consistent (min <= P5 <= median
      <= P95 <= max; mean is close to the base case since sampling is
      symmetric uniform around nominal values).
    - Monte Carlo's min/max are narrower than the Best/Worst deterministic
      extremes, since independent random draws rarely hit every parameter's
      extreme simultaneously.
    - A fixed random_seed gives reproducible results.
    - Histogram bin counts sum to n_simulations.
    - run_monte_carlo=False skips the simulation entirely.
"""
import math

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import UncertaintyInput
from backend.services.uncertainty_analysis import run_uncertainty_analysis

client = TestClient(app)


def _make_input(**overrides) -> UncertaintyInput:
    defaults = dict(
        grade_id="SS316",
        scrap_quality_id="SCRAP_HIGH_QUALITY",
        scrap_pct=65,
        energy_source_id="GRID_ELECTRICITY_IN",
        energy_demand_mwh_equivalent_per_t=1.0,
        n_simulations=300,
        random_seed=42,
    )
    defaults.update(overrides)
    yield_value = defaults.pop("yield_fraction", 0.92)
    return UncertaintyInput(**defaults, **{"yield": yield_value})


# --- Best/Base/Worst case ----------------------------------------------------


def test_best_case_is_lowest_and_worst_case_is_highest():
    result = run_uncertainty_analysis(_make_input())
    assert result.best_case.carbon_intensity_tco2e_per_t < result.base_case.carbon_intensity_tco2e_per_t
    assert result.base_case.carbon_intensity_tco2e_per_t < result.worst_case.carbon_intensity_tco2e_per_t


def test_base_case_uses_exact_nominal_values():
    """With 0% uncertainty everywhere, best/base/worst should all collapse
    to the same value as the nominal (unperturbed) calculation."""
    result = run_uncertainty_analysis(
        _make_input(
            emission_factor_uncertainty_pct=0,
            scrap_composition_uncertainty_pct=0,
            yield_uncertainty_pct=0,
            alloy_recovery_uncertainty_pct=0,
            energy_consumption_uncertainty_pct=0,
            run_monte_carlo=False,
        )
    )
    assert math.isclose(result.best_case.carbon_intensity_tco2e_per_t, result.base_case.carbon_intensity_tco2e_per_t, rel_tol=1e-6)
    assert math.isclose(result.worst_case.carbon_intensity_tco2e_per_t, result.base_case.carbon_intensity_tco2e_per_t, rel_tol=1e-6)


def test_wider_uncertainty_widens_the_best_worst_gap():
    narrow = run_uncertainty_analysis(_make_input(emission_factor_uncertainty_pct=5, run_monte_carlo=False))
    wide = run_uncertainty_analysis(_make_input(emission_factor_uncertainty_pct=30, run_monte_carlo=False))
    narrow_gap = narrow.worst_case.carbon_intensity_tco2e_per_t - narrow.best_case.carbon_intensity_tco2e_per_t
    wide_gap = wide.worst_case.carbon_intensity_tco2e_per_t - wide.best_case.carbon_intensity_tco2e_per_t
    assert wide_gap > narrow_gap


def test_uncertainty_ranges_used_reflects_input():
    result = run_uncertainty_analysis(_make_input(emission_factor_uncertainty_pct=20, yield_uncertainty_pct=7))
    assert result.uncertainty_ranges_used.emission_factor_uncertainty_pct == 20
    assert result.uncertainty_ranges_used.yield_uncertainty_pct == 7


# --- Monte Carlo statistics ---------------------------------------------------


def test_monte_carlo_runs_default_1000_simulations_when_unspecified():
    payload = UncertaintyInput(
        grade_id="SS316",
        scrap_quality_id="SCRAP_HIGH_QUALITY",
        scrap_pct=65,
        energy_source_id="GRID_ELECTRICITY_IN",
        energy_demand_mwh_equivalent_per_t=1.0,
        random_seed=1,
        **{"yield": 0.92},
    )
    assert payload.n_simulations == 1000
    result = run_uncertainty_analysis(payload)
    assert result.monte_carlo.n_simulations == 1000


def test_monte_carlo_percentiles_are_ordered():
    result = run_uncertainty_analysis(_make_input())
    mc = result.monte_carlo
    assert mc.min_tco2e_per_t <= mc.p5_tco2e_per_t <= mc.median_tco2e_per_t <= mc.p95_tco2e_per_t <= mc.max_tco2e_per_t


def test_monte_carlo_mean_close_to_base_case():
    """Uniform symmetric sampling around nominal values should center the
    distribution near the base case."""
    result = run_uncertainty_analysis(_make_input(n_simulations=2000))
    assert math.isclose(result.monte_carlo.mean_tco2e_per_t, result.base_case.carbon_intensity_tco2e_per_t, rel_tol=0.05)


def test_monte_carlo_range_is_narrower_than_deterministic_extremes():
    """Independent random draws rarely hit every parameter's extreme at
    once, so the simulated min/max should sit within the Best/Worst bounds."""
    result = run_uncertainty_analysis(_make_input(n_simulations=1000))
    assert result.monte_carlo.min_tco2e_per_t > result.best_case.carbon_intensity_tco2e_per_t
    assert result.monte_carlo.max_tco2e_per_t < result.worst_case.carbon_intensity_tco2e_per_t


def test_monte_carlo_histogram_counts_sum_to_n_simulations():
    result = run_uncertainty_analysis(_make_input(n_simulations=500))
    total = sum(b.count for b in result.monte_carlo.histogram)
    assert total == 500


def test_fixed_seed_is_reproducible():
    a = run_uncertainty_analysis(_make_input(random_seed=123))
    b = run_uncertainty_analysis(_make_input(random_seed=123))
    assert a.monte_carlo.mean_tco2e_per_t == b.monte_carlo.mean_tco2e_per_t
    assert a.monte_carlo.p5_tco2e_per_t == b.monte_carlo.p5_tco2e_per_t


def test_different_seeds_can_give_different_results():
    a = run_uncertainty_analysis(_make_input(random_seed=1))
    b = run_uncertainty_analysis(_make_input(random_seed=2))
    assert a.monte_carlo.mean_tco2e_per_t != b.monte_carlo.mean_tco2e_per_t


def test_run_monte_carlo_false_skips_simulation():
    result = run_uncertainty_analysis(_make_input(run_monte_carlo=False))
    assert result.monte_carlo is None
    # Best/base/worst should still be computed.
    assert result.best_case.carbon_intensity_tco2e_per_t > 0


def test_n_simulations_respected():
    result = run_uncertainty_analysis(_make_input(n_simulations=250))
    assert result.monte_carlo.n_simulations == 250
    assert sum(b.count for b in result.monte_carlo.histogram) == 250


# --- Interpretation / disclosure ---------------------------------------------


def test_interpretation_note_distinguishes_model_from_measurement_uncertainty():
    result = run_uncertainty_analysis(_make_input(run_monte_carlo=False))
    note = result.interpretation_note.lower()
    assert "model uncertainty" in note
    assert "measurement uncertainty" in note


# --- Data validation ----------------------------------------------------------


def test_unknown_grade_raises():
    with pytest.raises(Exception):
        run_uncertainty_analysis(_make_input(grade_id="NOT_REAL"))


def test_unknown_scrap_quality_raises():
    with pytest.raises(Exception):
        run_uncertainty_analysis(_make_input(scrap_quality_id="NOT_REAL"))


def test_unknown_energy_source_raises():
    with pytest.raises(Exception):
        run_uncertainty_analysis(_make_input(energy_source_id="NOT_REAL"))


def test_n_simulations_bounds_enforced_by_schema():
    with pytest.raises(Exception):
        UncertaintyInput(
            grade_id="SS316",
            scrap_quality_id="SCRAP_HIGH_QUALITY",
            scrap_pct=65,
            energy_source_id="GRID_ELECTRICITY_IN",
            energy_demand_mwh_equivalent_per_t=1.0,
            n_simulations=50,  # below the ge=100 floor
            **{"yield": 0.92},
        )


# --- API-level tests -----------------------------------------------------------


def test_endpoint_returns_all_required_sections():
    r = client.post(
        "/uncertainty",
        json={
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "scrap_pct": 65,
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "yield": 0.92,
            "energy_demand_mwh_equivalent_per_t": 1.0,
            "n_simulations": 200,
            "random_seed": 7,
        },
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("best_case", "base_case", "worst_case", "monte_carlo", "uncertainty_ranges_used", "interpretation_note"):
        assert key in body
    assert body["monte_carlo"]["n_simulations"] == 200


def test_endpoint_without_monte_carlo():
    r = client.post(
        "/uncertainty",
        json={
            "grade_id": "SS316",
            "scrap_quality_id": "SCRAP_HIGH_QUALITY",
            "scrap_pct": 65,
            "energy_source_id": "GRID_ELECTRICITY_IN",
            "yield": 0.92,
            "energy_demand_mwh_equivalent_per_t": 1.0,
            "run_monte_carlo": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["monte_carlo"] is None


def test_endpoint_rejects_unknown_grade():
    r = client.post(
        "/uncertainty",
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
    r = client.post("/uncertainty", json={})
    assert r.status_code == 422
