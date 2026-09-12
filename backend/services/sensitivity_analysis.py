"""
Sensitivity analysis engine.

Functional unit: 1 tonne of finished stainless steel, matching every other
engine in this application. Sweeps one dimension at a time while holding the
other three at their baseline value:

    1. Scrap percentage:  0, 10, 20, ..., 90 %
    2. Energy source:     Grid, Renewable, Natural Gas, Coal
    3. Scrap quality:     High, Medium, Low
    4. Steel grade:       304, 316, 430, 410, Duplex 2205

Each swept point is evaluated with the same deterministic formula used by
the optimizer's current-scenario check (backend/optimization/lp_optimizer.py
:_evaluate_current_scenario): scrap contributes Cr/Ni/Mo via its composition
and recovery; any deficit against the grade's minimum is closed with the
minimum alloy addition; the resulting composition is then validated against
the grade's FULL min/max envelope. A point that fails that validation is
marked chemistry_valid=False and excluded from being the sweep's "lowest
feasible" point, even if its raw carbon intensity happens to be lower - an
infeasible configuration is not a real option.

Insight text is generated per sweep entirely from the computed points -
trend direction, magnitude, and any infeasibility counts are derived from
the actual numbers, never asserted independently of them.
"""
from __future__ import annotations

from fastapi import HTTPException

from backend.data.loader import get_alloy_specifications, get_emission_factors, get_scrap_quality, get_steel_grades
from backend.models.schemas import SensitivityInput, SensitivityPoint, SensitivityResult, SensitivitySweep
from backend.validation.input_validation import validate_final_chemistry

_FUNCTIONAL_UNIT_MASS_T = 1.0
_GJ_PER_MWH = 3.6

_ALLOY_FOR_ELEMENT = {"Cr": "FERRO_CHROME", "Ni": "NICKEL_METAL", "Mo": "FERRO_MOLYBDENUM"}

_SCRAP_PCT_SWEEP_VALUES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
_ENERGY_SOURCE_SWEEP_IDS = ["GRID_ELECTRICITY_IN", "RENEWABLE_ELECTRICITY_IN", "NATURAL_GAS", "COAL"]
_SCRAP_QUALITY_SWEEP_IDS = ["SCRAP_HIGH_QUALITY", "SCRAP_MEDIUM_QUALITY", "SCRAP_LOW_QUALITY"]
_GRADE_SWEEP_IDS = ["SS304", "SS316", "SS430", "SS410", "SS2205"]

_TREND_EPSILON = 1e-6


def _normalized_energy_factor(factor_entry: dict) -> float:
    if factor_entry["unit"].endswith("/GJ"):
        return factor_entry["value"] * _GJ_PER_MWH
    return factor_entry["value"]


def _evaluate_point(
    grade: dict,
    scrap: dict,
    energy_factor_entry: dict,
    scrap_pct: float,
    yield_fraction: float,
    energy_demand: float,
    alloy_specs: dict[str, dict],
    factors: dict[str, dict],
    process_tco2e: float,
) -> tuple[float, bool]:
    """Returns (carbon_intensity_tco2e_per_t, chemistry_valid)."""
    charge_mass = 1.0 / yield_fraction
    s = scrap_pct / 100.0
    v = 1 - s
    scrap_recovery = scrap["alloy_recovery"] / 100.0

    scrap_mass = s * charge_mass
    virgin_mass = v * charge_mass

    material = scrap_mass * factors["SCRAP_EMBODIED"]["value"] + virgin_mass * factors["VIRGIN_EMBODIED"]["value"]

    final_pct_by_element: dict[str, float] = {}
    for element, alloy_id in _ALLOY_FOR_ELEMENT.items():
        spec = alloy_specs[alloy_id]
        concentration = spec["concentration_pct"] / 100.0
        recovery = spec["recovery_pct"] / 100.0
        supplied = scrap_mass * (scrap[element] / 100.0) * scrap_recovery
        required_pct = grade.get(f"{element}_min") or 0.0
        required_mass = (required_pct / 100.0) * _FUNCTIONAL_UNIT_MASS_T
        deficit = max(0.0, required_mass - supplied)
        alloy_mass = deficit / (concentration * recovery) if (deficit > 0 and concentration > 0 and recovery > 0) else 0.0
        material += alloy_mass * factors[alloy_id]["value"]
        final_mass = supplied + alloy_mass * concentration * recovery
        final_pct_by_element[element] = (final_mass / _FUNCTIONAL_UNIT_MASS_T) * 100.0

    _, chemistry_overall = validate_final_chemistry(final_pct_by_element, grade)

    energy = energy_demand * _normalized_energy_factor(energy_factor_entry)

    total = material + energy + process_tco2e
    return total, (chemistry_overall == "PASS")


def _mark_lowest_feasible(points: list[SensitivityPoint]) -> None:
    feasible = [p for p in points if p.chemistry_valid]
    if not feasible:
        return
    lowest = min(feasible, key=lambda p: p.carbon_intensity_tco2e_per_t)
    lowest.is_lowest_feasible = True


def _generate_scrap_pct_insight(points: list[SensitivityPoint]) -> str:
    feasible = [p for p in points if p.chemistry_valid]
    infeasible_count = len(points) - len(feasible)

    if len(feasible) < 2:
        return (
            f"Only {len(feasible)} of {len(points)} scrap-percentage scenarios satisfy this grade's chemistry "
            "limits, which isn't enough to identify a trend."
        )

    feasible_sorted = sorted(feasible, key=lambda p: float(p.value_id))
    first, last = feasible_sorted[0], feasible_sorted[-1]
    delta = last.carbon_intensity_tco2e_per_t - first.carbon_intensity_tco2e_per_t
    pct_delta = (delta / first.carbon_intensity_tco2e_per_t * 100) if first.carbon_intensity_tco2e_per_t else 0.0

    deltas = [
        feasible_sorted[i + 1].carbon_intensity_tco2e_per_t - feasible_sorted[i].carbon_intensity_tco2e_per_t
        for i in range(len(feasible_sorted) - 1)
    ]
    signs = {1 if d > _TREND_EPSILON else (-1 if d < -_TREND_EPSILON else 0) for d in deltas}
    monotonic = len(signs - {0}) <= 1

    direction = "decreases" if delta < -_TREND_EPSILON else ("increases" if delta > _TREND_EPSILON else "stays roughly flat")

    sentence = (
        f"Across {first.label} to {last.label} scrap (the feasible range), carbon intensity {direction} from "
        f"{first.carbon_intensity_tco2e_per_t:.3f} to {last.carbon_intensity_tco2e_per_t:.3f} tCO2e/t "
        f"({pct_delta:+.1f}%)."
    )

    if not monotonic:
        sentence += " The change is not monotonic across the sweep, consistent with alloy additions being required at some scrap levels but not others as the grade's Cr/Ni/Mo limits come into play."
    elif len(deltas) >= 2:
        first_half_avg = sum(abs(d) for d in deltas[: len(deltas) // 2]) / max(1, len(deltas) // 2)
        second_half_avg = sum(abs(d) for d in deltas[len(deltas) // 2 :]) / max(1, len(deltas) - len(deltas) // 2)
        if second_half_avg < first_half_avg * 0.8:
            sentence += " The benefit per additional 10% of scrap is smaller at the higher end of the range, consistent with alloy additions still being needed to meet the grade's minimum chemistry."

    if infeasible_count > 0:
        sentence += f" {infeasible_count} of {len(points)} scrap levels tested were infeasible for this grade/scrap-quality combination and are excluded from this trend."

    return sentence


def _generate_categorical_insight(dimension_label: str, points: list[SensitivityPoint]) -> str:
    feasible = [p for p in points if p.chemistry_valid]
    infeasible_count = len(points) - len(feasible)

    if not feasible:
        return f"None of the {dimension_label} options tested satisfy the applicable grade chemistry limits at this baseline."

    best = min(feasible, key=lambda p: p.carbon_intensity_tco2e_per_t)
    worst = max(feasible, key=lambda p: p.carbon_intensity_tco2e_per_t)

    if best.value_id == worst.value_id:
        return f"All feasible {dimension_label} options tested produce essentially the same carbon intensity ({best.carbon_intensity_tco2e_per_t:.3f} tCO2e/t)."

    delta = worst.carbon_intensity_tco2e_per_t - best.carbon_intensity_tco2e_per_t
    pct_delta = (delta / worst.carbon_intensity_tco2e_per_t * 100) if worst.carbon_intensity_tco2e_per_t else 0.0

    sentence = (
        f"{best.label} gives the lowest carbon intensity among feasible {dimension_label} options tested "
        f"({best.carbon_intensity_tco2e_per_t:.3f} tCO2e/t), {pct_delta:.1f}% lower than {worst.label} "
        f"({worst.carbon_intensity_tco2e_per_t:.3f} tCO2e/t)."
    )
    if infeasible_count > 0:
        sentence += f" {infeasible_count} of {len(points)} {dimension_label} options tested did not satisfy the applicable grade chemistry limits and are excluded from this comparison."

    return sentence


def _get_or_422(index: dict[str, dict], key: str, kind: str) -> dict:
    if key not in index:
        valid = ", ".join(sorted(index.keys()))
        raise HTTPException(status_code=422, detail=f"Unknown {kind} '{key}'. Valid options: {valid}")
    return index[key]


def run_sensitivity_analysis(payload: SensitivityInput) -> SensitivityResult:
    factors = {f["id"]: f for f in get_emission_factors()["factors"]}
    grades = {g["id"]: g for g in get_steel_grades()["grades"]}
    scrap_categories = {c["id"]: c for c in get_scrap_quality()["categories"]}
    alloy_specs = {sp["id"]: sp for sp in get_alloy_specifications()["specifications"]}

    baseline_grade = _get_or_422(grades, payload.grade_id, "grade_id")
    baseline_scrap = _get_or_422(scrap_categories, payload.scrap_quality_id, "scrap_quality_id")
    baseline_energy_factor = _get_or_422(factors, payload.energy_source_id, "energy_source_id")

    if payload.process_emission_override_tco2e_per_t is not None:
        process_tco2e = payload.process_emission_override_tco2e_per_t
    elif payload.process_route_id:
        process_tco2e = _get_or_422(factors, payload.process_route_id, "process_route_id")["value"]
    else:
        process_tco2e = 0.0

    # --- Sweep 1: scrap percentage ---
    scrap_pct_points: list[SensitivityPoint] = []
    for pct in _SCRAP_PCT_SWEEP_VALUES:
        intensity, valid = _evaluate_point(
            baseline_grade, baseline_scrap, baseline_energy_factor, pct, payload.yield_fraction,
            payload.energy_demand_mwh_equivalent_per_t, alloy_specs, factors, process_tco2e,
        )
        scrap_pct_points.append(
            SensitivityPoint(label=f"{pct}%", value_id=str(pct), carbon_intensity_tco2e_per_t=round(intensity, 6), chemistry_valid=valid, is_lowest_feasible=False)
        )
    _mark_lowest_feasible(scrap_pct_points)

    # --- Sweep 2: energy source ---
    energy_points: list[SensitivityPoint] = []
    for source_id in _ENERGY_SOURCE_SWEEP_IDS:
        factor_entry = _get_or_422(factors, source_id, "energy source")
        intensity, valid = _evaluate_point(
            baseline_grade, baseline_scrap, factor_entry, payload.scrap_pct, payload.yield_fraction,
            payload.energy_demand_mwh_equivalent_per_t, alloy_specs, factors, process_tco2e,
        )
        energy_points.append(
            SensitivityPoint(label=factor_entry["name"], value_id=source_id, carbon_intensity_tco2e_per_t=round(intensity, 6), chemistry_valid=valid, is_lowest_feasible=False)
        )
    _mark_lowest_feasible(energy_points)

    # --- Sweep 3: scrap quality ---
    quality_points: list[SensitivityPoint] = []
    for quality_id in _SCRAP_QUALITY_SWEEP_IDS:
        quality = _get_or_422(scrap_categories, quality_id, "scrap quality")
        intensity, valid = _evaluate_point(
            baseline_grade, quality, baseline_energy_factor, payload.scrap_pct, payload.yield_fraction,
            payload.energy_demand_mwh_equivalent_per_t, alloy_specs, factors, process_tco2e,
        )
        quality_points.append(
            SensitivityPoint(label=quality["category_name"], value_id=quality_id, carbon_intensity_tco2e_per_t=round(intensity, 6), chemistry_valid=valid, is_lowest_feasible=False)
        )
    _mark_lowest_feasible(quality_points)

    # --- Sweep 4: grade ---
    grade_points: list[SensitivityPoint] = []
    for grade_id in _GRADE_SWEEP_IDS:
        grade = _get_or_422(grades, grade_id, "grade")
        intensity, valid = _evaluate_point(
            grade, baseline_scrap, baseline_energy_factor, payload.scrap_pct, payload.yield_fraction,
            payload.energy_demand_mwh_equivalent_per_t, alloy_specs, factors, process_tco2e,
        )
        grade_points.append(
            SensitivityPoint(label=grade["grade_name"], value_id=grade_id, carbon_intensity_tco2e_per_t=round(intensity, 6), chemistry_valid=valid, is_lowest_feasible=False)
        )
    _mark_lowest_feasible(grade_points)

    return SensitivityResult(
        scrap_percentage_sweep=SensitivitySweep(
            dimension="scrap_percentage",
            baseline_note=f"Grade {baseline_grade['grade_name']}, {baseline_scrap['category_name']} scrap quality, {baseline_energy_factor['name']} held fixed.",
            points=scrap_pct_points,
            insight=_generate_scrap_pct_insight(scrap_pct_points),
        ),
        energy_source_sweep=SensitivitySweep(
            dimension="energy_source",
            baseline_note=f"Grade {baseline_grade['grade_name']}, {baseline_scrap['category_name']} scrap quality, {payload.scrap_pct}% scrap held fixed.",
            points=energy_points,
            insight=_generate_categorical_insight("energy source", energy_points),
        ),
        scrap_quality_sweep=SensitivitySweep(
            dimension="scrap_quality",
            baseline_note=f"Grade {baseline_grade['grade_name']}, {payload.scrap_pct}% scrap, {baseline_energy_factor['name']} held fixed.",
            points=quality_points,
            insight=_generate_categorical_insight("scrap quality", quality_points),
        ),
        grade_sweep=SensitivitySweep(
            dimension="grade",
            baseline_note=f"{baseline_scrap['category_name']} scrap quality, {payload.scrap_pct}% scrap, {baseline_energy_factor['name']} held fixed.",
            points=grade_points,
            insight=_generate_categorical_insight("grade", grade_points),
        ),
    )
