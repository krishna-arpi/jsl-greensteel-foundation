"""
LP/MILP carbon-intensity optimization engine.

Functional unit: 1 tonne of finished stainless steel, matching every other
engine in this application (material_balance, scrap_chemistry, carbon_emissions).

    Minimize  Z = sum(M_i x EF_i)                      material carbon
                + E_total x sum(EF_j x x_j)             energy carbon
                + CO2_process                           process carbon (exogenous)

Decision variables:
    s        scrap fraction        (0 <= s <= 1)
    v        virgin fraction       (0 <= v <= 1)
    x_j      energy-source share, j in {grid electricity, renewable
             electricity, natural gas, coal} - continuous [0,1] if blending
             is allowed, binary {0,1} if exactly one source must be chosen
    a_Cr     ferrochrome addition (t)
    a_Ni     nickel-metal addition (t)
    a_Mo     ferromolybdenum addition (t)

Constraints (numbered per the spec):
    1.  s + v = 1
    2.  S_min <= s <= S_max
    3.  sum(x_j) = 1   (with x_j binary instead of continuous when
        allow_energy_blending is False)
    4.  Grade chemistry satisfied - the umbrella constraint that checks 5-7
        collectively; not a separate PuLP constraint of its own.
    5.  Cr_min <= Cr_final <= Cr_max
    6.  Ni_min <= Ni_final <= Ni_max
    7.  Mo_min <= Mo_final <= Mo_max
    8.  scrap_mass <= scrap_availability_t (if supplied)
    9.  x_j <= energy_capacity_pct[j] (if supplied, per source)
    10. Production yield is valid - checked up front (yield is a fixed
        input here, not a decision variable, so this is a precondition
        rather than a live LP constraint)

Modeling note on the energy term: natural gas and coal's native emission
factors are tCO2e/GJ while electricity's are tCO2e/MWh. To blend all four
sources in one linear objective term, GJ-based factors are converted to a
MWh-equivalent basis using the standard conversion 1 MWh = 3.6 GJ. This is a
deliberate simplification for a solvable single-commodity energy-mix
optimization - distinct from the richer, unit-separated electricity/NG/coal
accounting used by /calculate/emissions elsewhere in this application.

Every emission factor, alloy specification, and scrap composition value used
here is an unverified DEMO_PLACEHOLDER (see data/*.json). This engine does
not fabricate values that are missing from reference data - a missing
factor is surfaced as status="ERROR" with a clear message instead.
"""
from __future__ import annotations

import pulp

from backend.data.loader import get_alloy_specifications, get_emission_factors, get_scrap_quality, get_steel_grades
from backend.models.schemas import (
    AlloyAdditionOptimalResult,
    BindingConstraintResult,
    EnergyMixShareResult,
    OptimizationInput,
    OptimizationResult,
)
from backend.validation.input_validation import validate_final_chemistry

_FUNCTIONAL_UNIT_MASS_T = 1.0
_GJ_PER_MWH = 3.6  # standard unit conversion

_ENERGY_SOURCES = ["GRID_ELECTRICITY_IN", "RENEWABLE_ELECTRICITY_IN", "NATURAL_GAS", "COAL"]

_ALLOY_FOR_ELEMENT = {
    "Cr": "FERRO_CHROME",
    "Ni": "NICKEL_METAL",
    "Mo": "FERRO_MOLYBDENUM",
}

_BINDING_EPSILON = 1e-6


class OptimizationDataError(Exception):
    """Raised when required reference data is missing or an id is unknown.
    Caught by optimize_carbon_and_energy() and surfaced as status="ERROR"
    rather than fabricating a result or letting the request 500."""


def _factor_index() -> dict[str, dict]:
    return {f["id"]: f for f in get_emission_factors()["factors"]}


def _normalized_energy_factor(factor_entry: dict) -> float:
    """GJ-based factors are converted to MWh-equivalent; MWh-based factors
    pass through unchanged. See module docstring for the conversion note."""
    if factor_entry["unit"].endswith("/GJ"):
        return factor_entry["value"] * _GJ_PER_MWH
    return factor_entry["value"]


def optimize_carbon_and_energy(payload: OptimizationInput) -> OptimizationResult:
    try:
        return _optimize(payload)
    except OptimizationDataError as exc:
        return OptimizationResult(status="ERROR", message=str(exc))


def _optimize(payload: OptimizationInput) -> OptimizationResult:  # noqa: C901
    factors = _factor_index()

    grades = {g["id"]: g for g in get_steel_grades()["grades"]}
    if payload.grade_id not in grades:
        raise OptimizationDataError(f"Unknown grade_id '{payload.grade_id}'.")
    grade = grades[payload.grade_id]

    scrap_categories = {c["id"]: c for c in get_scrap_quality()["categories"]}
    if payload.scrap_quality_id not in scrap_categories:
        raise OptimizationDataError(f"Unknown scrap_quality_id '{payload.scrap_quality_id}'.")
    scrap = scrap_categories[payload.scrap_quality_id]

    alloy_specs = {sp["id"]: sp for sp in get_alloy_specifications()["specifications"]}

    for eid in _ENERGY_SOURCES:
        if eid not in factors:
            raise OptimizationDataError(f"Missing emission factor for energy source '{eid}' in reference data.")
    for alloy_id in _ALLOY_FOR_ELEMENT.values():
        if alloy_id not in alloy_specs:
            raise OptimizationDataError(f"Missing alloy specification for '{alloy_id}' in reference data.")
        if alloy_id not in factors:
            raise OptimizationDataError(f"Missing emission factor for alloy '{alloy_id}' in reference data.")
    for mat_id in ("SCRAP_EMBODIED", "VIRGIN_EMBODIED"):
        if mat_id not in factors:
            raise OptimizationDataError(f"Missing emission factor for '{mat_id}' in reference data.")

    # Check 10: production yield is valid. Pydantic already enforces
    # 0 < yield <= 1 at the schema level, so this is a defensive re-check.
    if not (0 < payload.yield_fraction <= 1):
        raise OptimizationDataError(f"Invalid yield ({payload.yield_fraction}); expected 0 < yield <= 1.")

    charge_mass = 1.0 / payload.yield_fraction
    scrap_recovery = scrap["alloy_recovery"] / 100.0

    alloy_conc = {el: alloy_specs[aid]["concentration_pct"] / 100.0 for el, aid in _ALLOY_FOR_ELEMENT.items()}
    alloy_recovery = {el: alloy_specs[aid]["recovery_pct"] / 100.0 for el, aid in _ALLOY_FOR_ELEMENT.items()}

    # Process emissions: exogenous constant, not a decision variable.
    if payload.process_emission_override_tco2e_per_t is not None:
        process_tco2e = payload.process_emission_override_tco2e_per_t
    elif payload.process_route_id:
        if payload.process_route_id not in factors:
            raise OptimizationDataError(f"Unknown process_route_id '{payload.process_route_id}'.")
        process_tco2e = factors[payload.process_route_id]["value"]
    else:
        process_tco2e = 0.0

    # --- Build the LP/MILP model ---
    prob = pulp.LpProblem("jsl_greensteel_carbon_minimization", pulp.LpMinimize)

    s = pulp.LpVariable("scrap_fraction", lowBound=0, upBound=1)
    v = pulp.LpVariable("virgin_fraction", lowBound=0, upBound=1)

    if payload.allow_energy_blending:
        x = {j: pulp.LpVariable(f"energy_share_{j}", lowBound=0, upBound=1) for j in _ENERGY_SOURCES}
    else:
        x = {j: pulp.LpVariable(f"energy_share_{j}", cat="Binary") for j in _ENERGY_SOURCES}

    a = {el: pulp.LpVariable(f"alloy_addition_{el}", lowBound=0) for el in _ALLOY_FOR_ELEMENT}

    # Constraint 1: scrap + virgin = 1
    prob += s + v == 1, "scrap_plus_virgin_eq_1"

    # Constraint 2: S_min <= s <= S_max
    s_min = payload.scrap_pct_min / 100.0
    s_max = payload.scrap_pct_max / 100.0
    prob += s >= s_min, "scrap_pct_min"
    prob += s <= s_max, "scrap_pct_max"

    # Constraint 3: energy mix sums to 100%
    prob += pulp.lpSum(x[j] for j in _ENERGY_SOURCES) == 1, "energy_mix_sum_100pct"

    # Constraint 9: energy availability / capacity per source
    for source_id, cap_pct in payload.energy_capacity_pct.items():
        if source_id in x:
            prob += x[source_id] <= cap_pct / 100.0, f"energy_capacity_{source_id}"

    # Element mass balances feeding constraints 5-7 (grade chemistry, #4)
    element_final_expr = {}
    for element in _ALLOY_FOR_ELEMENT:
        scrap_term = s * charge_mass * (scrap[element] / 100.0) * scrap_recovery
        alloy_term = a[element] * alloy_conc[element] * alloy_recovery[element]
        element_final_expr[element] = scrap_term + alloy_term

    for element in ("Cr", "Ni", "Mo"):
        min_pct = grade.get(f"{element}_min")
        max_pct = grade.get(f"{element}_max")
        if min_pct is not None:
            prob += element_final_expr[element] >= (min_pct / 100.0) * _FUNCTIONAL_UNIT_MASS_T, f"{element}_min_limit"
        if max_pct is not None:
            prob += element_final_expr[element] <= (max_pct / 100.0) * _FUNCTIONAL_UNIT_MASS_T, f"{element}_max_limit"

    # Constraint 8: scrap availability
    if payload.scrap_availability_t is not None:
        prob += s * charge_mass <= payload.scrap_availability_t, "scrap_availability"

    # --- Objective: Z = material carbon + energy carbon + process carbon ---
    material_terms = (
        (s * charge_mass) * factors["SCRAP_EMBODIED"]["value"]
        + (v * charge_mass) * factors["VIRGIN_EMBODIED"]["value"]
        + pulp.lpSum(a[element] * factors[_ALLOY_FOR_ELEMENT[element]]["value"] for element in _ALLOY_FOR_ELEMENT)
    )
    energy_terms = payload.energy_demand_mwh_equivalent_per_t * pulp.lpSum(
        x[j] * _normalized_energy_factor(factors[j]) for j in _ENERGY_SOURCES
    )
    prob += material_terms + energy_terms + process_tco2e

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[prob.status]

    if status != "Optimal":
        return OptimizationResult(status="INFEASIBLE", message="No feasible solution found under the current constraints.")

    s_val = pulp.value(s)
    v_val = pulp.value(v)
    alloy_vals = {element: pulp.value(a[element]) for element in _ALLOY_FOR_ELEMENT}
    x_vals = {j: pulp.value(x[j]) for j in _ENERGY_SOURCES}
    optimized_intensity = pulp.value(prob.objective)

    current_intensity, current_chemistry_valid, current_chemistry_note = _evaluate_current_scenario(
        payload, factors, alloy_specs, grade, scrap, charge_mass, process_tco2e
    )
    absolute_reduction = current_intensity - optimized_intensity
    percentage_reduction = (absolute_reduction / current_intensity * 100.0) if current_intensity > 0 else 0.0

    binding = _find_binding_constraints(payload, s_val, s_min, s_max, x_vals, element_final_expr, grade, charge_mass)

    energy_mix_result = [
        EnergyMixShareResult(source_id=j, label=factors[j]["name"], share_pct=round(x_vals[j] * 100, 4))
        for j in _ENERGY_SOURCES
    ]
    alloy_additions_result = [
        AlloyAdditionOptimalResult(
            element=element,
            alloy_id=_ALLOY_FOR_ELEMENT[element],
            alloy_name=alloy_specs[_ALLOY_FOR_ELEMENT[element]]["name"],
            required_mass_kg=round(alloy_vals[element] * 1000, 4),
        )
        for element in _ALLOY_FOR_ELEMENT
    ]

    return OptimizationResult(
        status="OPTIMAL",
        message="Optimal solution found.",
        optimal_scrap_percentage=round(s_val * 100, 4),
        optimal_virgin_percentage=round(v_val * 100, 4),
        optimal_energy_mix=energy_mix_result,
        optimal_alloy_additions=alloy_additions_result,
        optimized_carbon_intensity=round(optimized_intensity, 6),
        current_carbon_intensity=round(current_intensity, 6),
        absolute_reduction=round(absolute_reduction, 6),
        percentage_reduction=round(percentage_reduction, 4),
        current_scenario_chemistry_valid=current_chemistry_valid,
        current_scenario_chemistry_note=current_chemistry_note,
        binding_constraints=binding,
    )


def _find_binding_constraints(payload, s_val, s_min, s_max, x_vals, element_final_expr, grade, charge_mass):  # noqa: ANN001
    binding: list[BindingConstraintResult] = []

    if abs(s_val - s_min) < _BINDING_EPSILON:
        binding.append(BindingConstraintResult(name="scrap_pct_min", description=f"Scrap % is at its minimum bound ({payload.scrap_pct_min}%)."))
    if abs(s_val - s_max) < _BINDING_EPSILON:
        binding.append(BindingConstraintResult(name="scrap_pct_max", description=f"Scrap % is at its maximum bound ({payload.scrap_pct_max}%)."))

    for element in ("Cr", "Ni", "Mo"):
        val = pulp.value(element_final_expr[element])
        min_pct = grade.get(f"{element}_min")
        max_pct = grade.get(f"{element}_max")
        if min_pct is not None and abs(val - (min_pct / 100.0)) < _BINDING_EPSILON:
            binding.append(
                BindingConstraintResult(name=f"{element}_min_limit", description=f"{element} is at the grade's minimum limit ({min_pct}%).")
            )
        if max_pct is not None and abs(val - (max_pct / 100.0)) < _BINDING_EPSILON:
            binding.append(
                BindingConstraintResult(name=f"{element}_max_limit", description=f"{element} is at the grade's maximum limit ({max_pct}%).")
            )

    if payload.scrap_availability_t is not None and abs(s_val * charge_mass - payload.scrap_availability_t) < _BINDING_EPSILON:
        binding.append(
            BindingConstraintResult(
                name="scrap_availability", description=f"Scrap usage is at the availability cap ({payload.scrap_availability_t} t)."
            )
        )

    for source_id, cap_pct in payload.energy_capacity_pct.items():
        if source_id in x_vals and abs(x_vals[source_id] - cap_pct / 100.0) < _BINDING_EPSILON:
            binding.append(
                BindingConstraintResult(
                    name=f"energy_capacity_{source_id}", description=f"{source_id} share is at its capacity cap ({cap_pct}%)."
                )
            )

    return binding


def _evaluate_current_scenario(payload, factors, alloy_specs, grade, scrap, charge_mass, process_tco2e):  # noqa: ANN001
    """Deterministically evaluate the same objective formula at the caller's
    current scrap % and energy mix, closing any Cr/Ni/Mo deficit with the
    minimum alloy addition (same logic as scrap_chemistry.py), so the
    reported reduction compares like with like.

    Also validates the resulting composition against the grade's FULL
    Cr/Ni/Mo bounds (min AND max) - closing a deficit against the minimum
    can't undo contamination that pushes another element over its maximum
    (e.g. a scrap quality whose trace Mo already exceeds a grade's Mo_max
    regardless of how much scrap is used). When that happens the current
    scenario is not actually chemistry-valid, and the returned validity
    flag/note say so explicitly rather than let a chemistry-invalid
    baseline look like a fair comparison against the optimizer's result,
    which always respects the full bounds.

    Returns (intensity, chemistry_valid, note).
    """
    s_cur = payload.current_scrap_pct / 100.0
    v_cur = 1 - s_cur
    scrap_recovery = scrap["alloy_recovery"] / 100.0

    scrap_mass = s_cur * charge_mass
    virgin_mass = v_cur * charge_mass

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
    chemistry_valid = chemistry_overall == "PASS"
    chemistry_note = None
    if not chemistry_valid:
        over_limit = [
            element
            for element in _ALLOY_FOR_ELEMENT
            if grade.get(f"{element}_max") is not None and final_pct_by_element[element] > grade[f"{element}_max"] + 1e-6
        ]
        chemistry_note = (
            f"At {payload.current_scrap_pct}% scrap, the '{payload.scrap_quality_id}' composition pushes "
            f"{', '.join(over_limit) if over_limit else 'one or more elements'} over the grade's maximum limit "
            "even after closing minimum deficits with alloy additions. current_carbon_intensity is the honest "
            "cost of this composition, but it does not actually satisfy grade chemistry - the optimized result "
            "is the first solution here that both minimizes carbon and is chemistry-valid."
        )

    mix = payload.current_energy_mix_pct
    total_share = sum(mix.values())
    energy = 0.0
    if total_share > 0:
        for source_id, share in mix.items():
            if source_id in factors:
                energy += payload.energy_demand_mwh_equivalent_per_t * (share / total_share) * _normalized_energy_factor(factors[source_id])

    return material + energy + process_tco2e, chemistry_valid, chemistry_note
