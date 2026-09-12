"""
Uncertainty analysis engine.

Functional unit: 1 tonne of finished stainless steel, matching every other
engine in this application.

Five uncertain categories, each with an assumed +/- percentage spread around
its nominal (DEMO_PLACEHOLDER) value:
    1. Emission factors    (scrap/virgin embodied, energy, alloy, process)
    2. Scrap composition   (Cr/Ni/Mo wt% in the selected scrap quality)
    3. Yield
    4. Alloy recovery      (scrap's alloy_recovery AND each alloy spec's
                            recovery_pct - concentration is not varied)
    5. Energy consumption  (the nominal energy_demand_mwh_equivalent_per_t)

scrap_pct (the charge mix ratio) is a user-chosen configuration, not an
uncertain input, and is held fixed throughout.

Best/Base/Worst case:
    Base  = every parameter at its nominal value.
    Best  = every parameter pushed to whichever bound of its range reduces
            carbon intensity (lower emission factors and energy demand;
            higher scrap composition, yield, and alloy recovery).
    Worst = the opposite bound for every parameter.
These are not random draws - they are the deterministic extremes of the
assumed ranges, evaluated with the same formula used everywhere else in
this application.

Monte Carlo (optional, on by default): draws each uncertain parameter
independently and uniformly within its nominal +/- range, computes carbon
intensity for each draw, and summarizes the resulting distribution (mean,
median, min, max, P5, P95, histogram).

IMPORTANT: every uncertainty_pct is an assumed spread, not a measured
variability. This module characterizes MODEL uncertainty - never presented
as measurement uncertainty from real plant data (see UncertaintyResult's
interpretation_note).
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field

from fastapi import HTTPException

from backend.data.loader import get_alloy_specifications, get_emission_factors, get_scrap_quality, get_steel_grades
from backend.models.schemas import (
    HistogramBin,
    MonteCarloResult,
    ScenarioCaseResult,
    UncertaintyInput,
    UncertaintyRangesUsed,
    UncertaintyResult,
)

_FUNCTIONAL_UNIT_MASS_T = 1.0
_GJ_PER_MWH = 3.6
_ALLOY_FOR_ELEMENT = {"Cr": "FERRO_CHROME", "Ni": "NICKEL_METAL", "Mo": "FERRO_MOLYBDENUM"}
_HISTOGRAM_BIN_COUNT = 20


def _normalized_energy_factor_value(factor_entry: dict) -> float:
    if factor_entry["unit"].endswith("/GJ"):
        return factor_entry["value"] * _GJ_PER_MWH
    return factor_entry["value"]


@dataclass
class _ResolvedParams:
    """One fully-resolved set of parameter values - either a deterministic
    Best/Base/Worst case, or a single Monte Carlo draw."""

    scrap_pct: float
    yield_fraction: float
    energy_demand: float
    scrap_embodied_ef: float
    virgin_embodied_ef: float
    energy_ef: float
    process_ef: float
    scrap_composition: dict[str, float]
    scrap_recovery: float
    alloy_concentration: dict[str, float] = field(default_factory=dict)
    alloy_recovery: dict[str, float] = field(default_factory=dict)
    alloy_ef: dict[str, float] = field(default_factory=dict)


def _compute_intensity(p: _ResolvedParams, grade: dict) -> float:
    charge_mass = 1.0 / p.yield_fraction
    s = p.scrap_pct / 100.0
    v = 1 - s
    scrap_mass = s * charge_mass
    virgin_mass = v * charge_mass

    material = scrap_mass * p.scrap_embodied_ef + virgin_mass * p.virgin_embodied_ef

    for element in ("Cr", "Ni", "Mo"):
        supplied = scrap_mass * (p.scrap_composition[element] / 100.0) * p.scrap_recovery
        required_pct = grade.get(f"{element}_min") or 0.0
        required_mass = (required_pct / 100.0) * _FUNCTIONAL_UNIT_MASS_T
        deficit = max(0.0, required_mass - supplied)
        conc = p.alloy_concentration[element]
        rec = p.alloy_recovery[element]
        alloy_mass = deficit / (conc * rec) if (deficit > 0 and conc > 0 and rec > 0) else 0.0
        material += alloy_mass * p.alloy_ef[element]

    energy = p.energy_demand * p.energy_ef
    return material + energy + p.process_ef


def _bound(nominal: float, pct: float, want_best: bool, higher_is_worse: bool) -> float:
    """Deterministic extreme of a range for the Best/Worst case."""
    lower = nominal * (1 - pct / 100.0)
    upper = nominal * (1 + pct / 100.0)
    if higher_is_worse:
        return lower if want_best else upper
    return upper if want_best else lower


def _sample(rng: random.Random, nominal: float, pct: float) -> float:
    lower = nominal * (1 - pct / 100.0)
    upper = nominal * (1 + pct / 100.0)
    return rng.uniform(lower, upper)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _build_histogram(values: list[float], bin_count: int = _HISTOGRAM_BIN_COUNT) -> list[HistogramBin]:
    lo, hi = min(values), max(values)
    if lo == hi:
        return [HistogramBin(bin_start=lo, bin_end=hi, count=len(values))]
    width = (hi - lo) / bin_count
    counts = [0] * bin_count
    for v in values:
        idx = min(int((v - lo) / width), bin_count - 1)
        counts[idx] += 1
    return [HistogramBin(bin_start=lo + i * width, bin_end=lo + (i + 1) * width, count=counts[i]) for i in range(bin_count)]


def run_uncertainty_analysis(payload: UncertaintyInput) -> UncertaintyResult:  # noqa: C901
    factors = {f["id"]: f for f in get_emission_factors()["factors"]}
    grades = {g["id"]: g for g in get_steel_grades()["grades"]}
    scrap_categories = {c["id"]: c for c in get_scrap_quality()["categories"]}
    alloy_specs = {sp["id"]: sp for sp in get_alloy_specifications()["specifications"]}

    if payload.grade_id not in grades:
        raise HTTPException(status_code=422, detail=f"Unknown grade_id '{payload.grade_id}'.")
    grade = grades[payload.grade_id]

    if payload.scrap_quality_id not in scrap_categories:
        raise HTTPException(status_code=422, detail=f"Unknown scrap_quality_id '{payload.scrap_quality_id}'.")
    scrap = scrap_categories[payload.scrap_quality_id]

    if payload.energy_source_id not in factors:
        raise HTTPException(status_code=422, detail=f"Unknown energy_source_id '{payload.energy_source_id}'.")
    energy_factor_entry = factors[payload.energy_source_id]

    if payload.process_emission_override_tco2e_per_t is not None:
        process_ef_nominal = payload.process_emission_override_tco2e_per_t
    elif payload.process_route_id:
        if payload.process_route_id not in factors:
            raise HTTPException(status_code=422, detail=f"Unknown process_route_id '{payload.process_route_id}'.")
        process_ef_nominal = factors[payload.process_route_id]["value"]
    else:
        process_ef_nominal = 0.0

    nominal_scrap_embodied = factors["SCRAP_EMBODIED"]["value"]
    nominal_virgin_embodied = factors["VIRGIN_EMBODIED"]["value"]
    nominal_energy_ef = _normalized_energy_factor_value(energy_factor_entry)
    nominal_alloy_ef = {el: factors[aid]["value"] for el, aid in _ALLOY_FOR_ELEMENT.items()}
    nominal_scrap_composition = {el: scrap[el] for el in ("Cr", "Ni", "Mo")}
    nominal_scrap_recovery = scrap["alloy_recovery"] / 100.0
    nominal_alloy_concentration = {el: alloy_specs[aid]["concentration_pct"] / 100.0 for el, aid in _ALLOY_FOR_ELEMENT.items()}
    nominal_alloy_recovery = {el: alloy_specs[aid]["recovery_pct"] / 100.0 for el, aid in _ALLOY_FOR_ELEMENT.items()}

    ef_pct = payload.emission_factor_uncertainty_pct
    comp_pct = payload.scrap_composition_uncertainty_pct
    yield_pct = payload.yield_uncertainty_pct
    recovery_pct = payload.alloy_recovery_uncertainty_pct
    energy_pct = payload.energy_consumption_uncertainty_pct

    def make_case(want_best) -> _ResolvedParams:
        """want_best=True -> Best Case, False -> Worst Case, None -> Base Case (nominal)."""
        if want_best is None:
            return _ResolvedParams(
                scrap_pct=payload.scrap_pct,
                yield_fraction=payload.yield_fraction,
                energy_demand=payload.energy_demand_mwh_equivalent_per_t,
                scrap_embodied_ef=nominal_scrap_embodied,
                virgin_embodied_ef=nominal_virgin_embodied,
                energy_ef=nominal_energy_ef,
                process_ef=process_ef_nominal,
                scrap_composition=dict(nominal_scrap_composition),
                scrap_recovery=nominal_scrap_recovery,
                alloy_concentration=dict(nominal_alloy_concentration),
                alloy_recovery=dict(nominal_alloy_recovery),
                alloy_ef=dict(nominal_alloy_ef),
            )
        return _ResolvedParams(
            scrap_pct=payload.scrap_pct,
            yield_fraction=_bound(payload.yield_fraction, yield_pct, want_best, higher_is_worse=False),
            energy_demand=_bound(payload.energy_demand_mwh_equivalent_per_t, energy_pct, want_best, higher_is_worse=True),
            scrap_embodied_ef=_bound(nominal_scrap_embodied, ef_pct, want_best, higher_is_worse=True),
            virgin_embodied_ef=_bound(nominal_virgin_embodied, ef_pct, want_best, higher_is_worse=True),
            energy_ef=_bound(nominal_energy_ef, ef_pct, want_best, higher_is_worse=True),
            process_ef=_bound(process_ef_nominal, ef_pct, want_best, higher_is_worse=True) if process_ef_nominal > 0 else 0.0,
            scrap_composition={el: _bound(v, comp_pct, want_best, higher_is_worse=False) for el, v in nominal_scrap_composition.items()},
            scrap_recovery=_bound(nominal_scrap_recovery, recovery_pct, want_best, higher_is_worse=False),
            alloy_concentration=dict(nominal_alloy_concentration),
            alloy_recovery={el: _bound(v, recovery_pct, want_best, higher_is_worse=False) for el, v in nominal_alloy_recovery.items()},
            alloy_ef={el: _bound(v, ef_pct, want_best, higher_is_worse=True) for el, v in nominal_alloy_ef.items()},
        )

    best_case = ScenarioCaseResult(label="Best Case", carbon_intensity_tco2e_per_t=round(_compute_intensity(make_case(True), grade), 6))
    base_case = ScenarioCaseResult(label="Base Case", carbon_intensity_tco2e_per_t=round(_compute_intensity(make_case(None), grade), 6))
    worst_case = ScenarioCaseResult(label="Worst Case", carbon_intensity_tco2e_per_t=round(_compute_intensity(make_case(False), grade), 6))

    monte_carlo = None
    if payload.run_monte_carlo:
        rng = random.Random(payload.random_seed)
        samples: list[float] = []
        for _ in range(payload.n_simulations):
            params = _ResolvedParams(
                scrap_pct=payload.scrap_pct,
                yield_fraction=_sample(rng, payload.yield_fraction, yield_pct),
                energy_demand=_sample(rng, payload.energy_demand_mwh_equivalent_per_t, energy_pct),
                scrap_embodied_ef=_sample(rng, nominal_scrap_embodied, ef_pct),
                virgin_embodied_ef=_sample(rng, nominal_virgin_embodied, ef_pct),
                energy_ef=_sample(rng, nominal_energy_ef, ef_pct),
                process_ef=_sample(rng, process_ef_nominal, ef_pct) if process_ef_nominal > 0 else 0.0,
                scrap_composition={el: _sample(rng, v, comp_pct) for el, v in nominal_scrap_composition.items()},
                scrap_recovery=_sample(rng, nominal_scrap_recovery, recovery_pct),
                alloy_concentration=dict(nominal_alloy_concentration),
                alloy_recovery={el: _sample(rng, v, recovery_pct) for el, v in nominal_alloy_recovery.items()},
                alloy_ef={el: _sample(rng, v, ef_pct) for el, v in nominal_alloy_ef.items()},
            )
            samples.append(_compute_intensity(params, grade))

        sorted_samples = sorted(samples)
        monte_carlo = MonteCarloResult(
            n_simulations=payload.n_simulations,
            mean_tco2e_per_t=round(statistics.mean(samples), 6),
            median_tco2e_per_t=round(statistics.median(samples), 6),
            min_tco2e_per_t=round(sorted_samples[0], 6),
            max_tco2e_per_t=round(sorted_samples[-1], 6),
            p5_tco2e_per_t=round(_percentile(sorted_samples, 5), 6),
            p95_tco2e_per_t=round(_percentile(sorted_samples, 95), 6),
            histogram=_build_histogram(samples),
        )

    return UncertaintyResult(
        uncertainty_ranges_used=UncertaintyRangesUsed(
            emission_factor_uncertainty_pct=ef_pct,
            scrap_composition_uncertainty_pct=comp_pct,
            yield_uncertainty_pct=yield_pct,
            alloy_recovery_uncertainty_pct=recovery_pct,
            energy_consumption_uncertainty_pct=energy_pct,
        ),
        best_case=best_case,
        base_case=base_case,
        worst_case=worst_case,
        monte_carlo=monte_carlo,
    )
