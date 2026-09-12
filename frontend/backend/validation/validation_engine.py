"""
Comprehensive validation engine.

Runs the 12 required checks across whichever domains the caller supplies,
and returns one detailed report so a caller (frontend or another service)
can decide whether it is safe to show a final result at all - "do not allow
invalid configurations to silently produce results" is enforced here by
giving every check an explicit PASS/WARNING/ERROR status and an overall
`blocked` flag when any check is ERROR.

Checks 1-6 run when `material` is supplied (scrap/virgin mix + yield):
    1. Scrap percentage is within allowed limits
    2. Virgin percentage = 100 - scrap percentage
    3. Scrap + virgin = 100%
    4. Material balance closes
    5. Yield is valid
    6. No negative material quantity

Checks 7, 8, 10, 11 run when `carbon_emission` is supplied (energy/emissions):
    7. Energy consumption is positive
    8. Energy shares equal 100%
    10. All required emission factors exist
    11. Units are compatible (plausibility heuristics)

Checks 9, 12 run when `scrap_chemistry` is supplied:
    9. Grade chemistry is satisfied
    12. Optimization inputs are feasible

A domain's checks are omitted from the report entirely when its inputs
aren't supplied - there is deliberately no fourth "not applicable" status;
the three-status contract (PASS/WARNING/ERROR) stays clean.
"""
from __future__ import annotations

from fastapi import HTTPException

from backend.models.schemas import (
    CarbonEmissionInput,
    MaterialBalanceInput,
    ScrapChemistryInput,
    ValidationCheckResult,
    ValidationReport,
    ValidationRequest,
)
from backend.services.carbon_emissions import calculate_carbon_emissions
from backend.services.material_balance import calculate_material_balance
from backend.services.scrap_chemistry import calculate_scrap_chemistry

_EPSILON = 1e-6

# Practical operating bounds are illustrative assumptions for this demo, not
# a validated plant/engineering standard - adjust to real plant limits.
PRACTICAL_SCRAP_PCT_MIN = 0.0
PRACTICAL_SCRAP_PCT_MAX = 95.0

# Plausibility bounds for check 11 (unit-mismatch heuristics), same caveat.
PLAUSIBLE_ELECTRICITY_MWH_PER_T_MAX = 5.0
PLAUSIBLE_FUEL_GJ_PER_T_MAX = 20.0


def _check(check_id: int, name: str, status: str, message: str, details: dict | None = None) -> ValidationCheckResult:
    return ValidationCheckResult(check_id=check_id, name=name, status=status, message=message, details=details)


def _material_checks(material) -> list[ValidationCheckResult]:  # noqa: ANN001
    checks: list[ValidationCheckResult] = []
    scrap_pct = material.scrap_percentage
    yield_fraction = material.yield_fraction

    # --- Check 1: scrap percentage within allowed limits ---
    if scrap_pct < 0 or scrap_pct > 100:
        checks.append(
            _check(1, "Scrap percentage limit", "ERROR", f"Scrap percentage ({scrap_pct}%) is outside the physically valid 0-100% range.")
        )
    elif scrap_pct > PRACTICAL_SCRAP_PCT_MAX:
        checks.append(
            _check(
                1,
                "Scrap percentage limit",
                "ERROR",
                f"Scrap percentage ({scrap_pct}%) exceeds practical limit ({PRACTICAL_SCRAP_PCT_MAX}%).",
                details={"assumed_practical_max_pct": PRACTICAL_SCRAP_PCT_MAX, "note": "Illustrative assumption, not a validated plant limit."},
            )
        )
    else:
        checks.append(_check(1, "Scrap percentage limit", "PASS", "Scrap percentage is within allowed limits."))

    # --- Check 2: virgin_percentage = 100 - scrap_percentage ---
    derived_virgin = 100.0 - scrap_pct
    if material.virgin_percentage is not None:
        if abs(material.virgin_percentage - derived_virgin) > _EPSILON:
            checks.append(
                _check(
                    2,
                    "Virgin percentage derivation",
                    "ERROR",
                    f"Virgin percentage ({material.virgin_percentage}%) does not equal 100 - scrap percentage ({derived_virgin}%).",
                )
            )
        else:
            checks.append(_check(2, "Virgin percentage derivation", "PASS", "Virgin percentage equals 100 - scrap percentage."))
    else:
        checks.append(
            _check(2, "Virgin percentage derivation", "PASS", "Virgin percentage derived as 100 - scrap percentage (not separately supplied).")
        )

    # --- Check 3: scrap + virgin = 100% ---
    virgin_for_sum = material.virgin_percentage if material.virgin_percentage is not None else derived_virgin
    total = scrap_pct + virgin_for_sum
    if abs(total - 100.0) > _EPSILON:
        checks.append(_check(3, "Scrap + virgin = 100%", "ERROR", f"Scrap + virgin percentage sums to {total}%, not 100%."))
    else:
        checks.append(_check(3, "Scrap + virgin = 100%", "PASS", "Scrap and virgin percentages sum to 100%."))

    # --- Check 5: yield is valid ---
    yield_ok = 0 < yield_fraction <= 1
    if not yield_ok:
        checks.append(
            _check(
                5,
                "Yield validity",
                "ERROR",
                f"Yield ({yield_fraction}) is not a valid fraction; expected 0 < yield <= 1.",
            )
        )
    else:
        checks.append(_check(5, "Yield validity", "PASS", "Yield is within the valid (0, 1] range."))

    # --- Check 4: material balance closes ---
    mb_result = None
    scrap_in_range = 0 <= scrap_pct <= 100
    if yield_ok and scrap_in_range:
        try:
            mb_result = calculate_material_balance(MaterialBalanceInput(scrap_percentage=scrap_pct, **{"yield": yield_fraction}))
        except Exception as exc:  # defensive: report, don't crash the whole validation run
            checks.append(_check(4, "Material balance closes", "ERROR", f"Could not compute material balance: {exc}"))
        else:
            if mb_result.validation_status.overall == "PASS":
                checks.append(_check(4, "Material balance closes", "PASS", "Material balance closes (scrap + virgin mass = charge mass)."))
            else:
                checks.append(_check(4, "Material balance closes", "ERROR", "Material balance does not close."))
    else:
        checks.append(
            _check(
                4,
                "Material balance closes",
                "ERROR",
                "Material balance cannot be computed because scrap percentage or yield is invalid.",
            )
        )

    # --- Check 6: no negative material quantity ---
    if mb_result is not None:
        negative = mb_result.charge_mass < 0 or mb_result.scrap_mass < 0 or mb_result.virgin_mass < 0
        if negative:
            checks.append(_check(6, "No negative material quantity", "ERROR", "A negative material quantity was computed."))
        else:
            checks.append(_check(6, "No negative material quantity", "PASS", "No negative material quantities."))
    elif scrap_pct < 0:
        checks.append(_check(6, "No negative material quantity", "ERROR", "Scrap percentage is negative."))
    # else: insufficient data to assess (yield invalid) - omitted rather than guessed.

    return checks


def _energy_checks(carbon_emission: CarbonEmissionInput) -> list[ValidationCheckResult]:
    checks: list[ValidationCheckResult] = []
    ce = carbon_emission

    # --- Check 7: energy consumption is positive ---
    negative_energy = (
        ce.electricity_consumption_mwh_per_t < 0
        or ce.natural_gas_consumption_gj_per_t < 0
        or ce.coal_consumption_gj_per_t < 0
    )
    all_zero = (
        ce.electricity_consumption_mwh_per_t == 0
        and ce.natural_gas_consumption_gj_per_t == 0
        and ce.coal_consumption_gj_per_t == 0
    )
    if negative_energy:
        checks.append(_check(7, "Energy consumption is positive", "ERROR", "Energy consumption cannot be negative."))
    elif all_zero:
        checks.append(
            _check(7, "Energy consumption is positive", "WARNING", "All energy consumption values are zero - double-check inputs.")
        )
    else:
        checks.append(_check(7, "Energy consumption is positive", "PASS", "Energy consumption is positive."))

    # --- Check 8: energy shares equal 100% ---
    if ce.electricity_mix:
        total_share = sum(c.share_pct for c in ce.electricity_mix)
        if abs(total_share - 100.0) > _EPSILON:
            checks.append(
                _check(8, "Energy mix shares equal 100%", "ERROR", f"Electricity mix shares sum to {total_share}%, not 100%.")
            )
        else:
            checks.append(_check(8, "Energy mix shares equal 100%", "PASS", "Energy mix shares sum to 100%."))
    elif ce.electricity_source_id:
        checks.append(_check(8, "Energy mix shares equal 100%", "PASS", "Single electricity source implies a 100% share."))
    else:
        checks.append(
            _check(8, "Energy mix shares equal 100%", "WARNING", "No electricity source or mix was configured.")
        )

    # Run the actual emissions calculation to inspect factor availability.
    ce_result = calculate_carbon_emissions(ce)

    # --- Check 10: all required emission factors exist ---
    missing_only = [w for w in ce_result.missing_factor_warnings if "No emission factor on file" in w]
    if missing_only:
        checks.append(
            _check(
                10,
                "Required emission factors exist",
                "ERROR",
                f"{len(missing_only)} required emission factor(s) are missing.",
                details={"missing": missing_only},
            )
        )
    else:
        checks.append(
            _check(
                10,
                "Required emission factors exist",
                "WARNING",
                "All required emission factors exist, but are DEMO_PLACEHOLDER values, not independently verified.",
            )
        )

    # --- Check 11: units are compatible (plausibility heuristics) ---
    implausible: list[str] = []
    if ce.electricity_consumption_mwh_per_t > PLAUSIBLE_ELECTRICITY_MWH_PER_T_MAX:
        implausible.append("electricity_consumption_mwh_per_t")
    if ce.natural_gas_consumption_gj_per_t > PLAUSIBLE_FUEL_GJ_PER_T_MAX:
        implausible.append("natural_gas_consumption_gj_per_t")
    if ce.coal_consumption_gj_per_t > PLAUSIBLE_FUEL_GJ_PER_T_MAX:
        implausible.append("coal_consumption_gj_per_t")

    if implausible:
        checks.append(
            _check(
                11,
                "Units are compatible",
                "WARNING",
                f"Value(s) for {', '.join(implausible)} look implausible for their stated units - "
                "double-check MWh vs kWh, GJ vs MJ, etc.",
                details={
                    "assumed_plausible_max": {
                        "electricity_consumption_mwh_per_t": PLAUSIBLE_ELECTRICITY_MWH_PER_T_MAX,
                        "fuel_gj_per_t": PLAUSIBLE_FUEL_GJ_PER_T_MAX,
                    }
                },
            )
        )
    else:
        checks.append(_check(11, "Units are compatible", "PASS", "Energy values look plausible for their stated units."))

    return checks


def _scrap_chemistry_checks(scrap_chemistry: ScrapChemistryInput) -> list[ValidationCheckResult]:
    checks: list[ValidationCheckResult] = []

    try:
        sc_result = calculate_scrap_chemistry(scrap_chemistry)
    except HTTPException as exc:
        checks.append(_check(9, "Grade chemistry satisfied", "ERROR", f"Could not compute scrap chemistry: {exc.detail}"))
        checks.append(_check(12, "Optimization inputs feasible", "ERROR", f"Could not compute scrap chemistry: {exc.detail}"))
        return checks

    # --- Check 9: grade chemistry is satisfied ---
    if sc_result.chemistry_validation.overall == "PASS":
        checks.append(_check(9, "Grade chemistry satisfied", "PASS", "Grade chemistry passed."))
    else:
        failed_elements = [i.element for i in sc_result.chemistry_validation.items if i.status == "FAIL"]
        checks.append(
            _check(
                9,
                "Grade chemistry satisfied",
                "ERROR",
                f"Grade chemistry failed for: {', '.join(failed_elements)}.",
                details={"failed_elements": failed_elements},
            )
        )

    # --- Check 12: optimization inputs are feasible ---
    deficit_by_element = {d.element: d.deficit_mass for d in sc_result.element_deficits}
    infeasible_elements = [
        addition.element
        for addition in sc_result.alloy_additions
        if deficit_by_element.get(addition.element, 0) > 0 and (addition.concentration_pct <= 0 or addition.recovery_pct <= 0)
    ]
    if infeasible_elements:
        checks.append(
            _check(
                12,
                "Optimization inputs feasible",
                "ERROR",
                f"Cannot supply required {', '.join(infeasible_elements)} with the available alloy "
                "specification (zero concentration or recovery) - deficit is unclosable.",
                details={"infeasible_elements": infeasible_elements},
            )
        )
    else:
        checks.append(
            _check(12, "Optimization inputs feasible", "PASS", "All element deficits are closable with the available alloy specifications.")
        )

    return checks


def run_validation(payload: ValidationRequest) -> ValidationReport:
    checks: list[ValidationCheckResult] = []

    if payload.material is not None:
        checks.extend(_material_checks(payload.material))

    if payload.carbon_emission is not None:
        checks.extend(_energy_checks(payload.carbon_emission))

    if payload.scrap_chemistry is not None:
        checks.extend(_scrap_chemistry_checks(payload.scrap_chemistry))

    checks.sort(key=lambda c: c.check_id)

    error_count = sum(1 for c in checks if c.status == "ERROR")
    warning_count = sum(1 for c in checks if c.status == "WARNING")
    pass_count = sum(1 for c in checks if c.status == "PASS")

    if error_count > 0:
        overall_status = "ERROR"
    elif warning_count > 0:
        overall_status = "WARNING"
    else:
        overall_status = "PASS"

    summary = f"{pass_count} passed, {warning_count} warning(s), {error_count} error(s)"

    return ValidationReport(
        overall_status=overall_status,
        blocked=(overall_status == "ERROR"),
        summary=summary,
        checks=checks,
    )
