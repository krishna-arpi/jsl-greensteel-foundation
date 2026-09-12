"""
Validation module.

Currently implemented:
  - Structural/range validation of CarbonCalculationInput and
    MaterialBalanceInput (handled by Pydantic in backend/models/schemas.py).
  - Reference-id existence checks against /data/*.json (handled inline in
    backend/services/carbon_calculator.py and backend/services/scrap_chemistry.py).
  - Reference-data file integrity checks (validate_reference_data_integrity,
    below): confirms each /data/*.json file loaded and carries its expected
    status flag.
  - Composition-vs-grade chemistry validation (validate_final_chemistry,
    below): compares a computed final composition against a grade's
    Cr/Ni/Mo/C/Si/Mn/N bounds from steel_grades.json. Used by
    backend/services/scrap_chemistry.py.

Planned (not implemented yet - future scope per project roadmap):
  - Cross-field engineering plausibility checks (e.g. energy consumption
    within plausible plant ranges).
  - Data-file schema validation (e.g. via a JSON Schema / Pydantic model
    for the reference files themselves, run at startup / in CI).
"""
from __future__ import annotations

from typing import Any, Optional

_CHEMISTRY_EPSILON = 1e-6


class ValidationIssue:
    def __init__(self, field: str, message: str, severity: str = "warning"):
        self.field = field
        self.message = message
        self.severity = severity  # "warning" | "error"

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "message": self.message, "severity": self.severity}


# Each reference file's _meta.status is expected to be one of these.
# "baseline" is unique: its corporate_benchmark block is a stated JSL FY26
# figure (STATED_INPUT), not a placeholder - but it must still be explicitly
# flagged as something, and its demo_scenario sub-block keeps its own
# DEMO_PLACEHOLDER flag independently.
_EXPECTED_STATUS = {
    "emission_factors": {"DEMO_PLACEHOLDER"},
    "steel_grades": {"DEMO_PLACEHOLDER"},
    "scrap_quality": {"DEMO_PLACEHOLDER"},
    "energy_sources": {"DEMO_PLACEHOLDER"},
    "baseline": {"STATED_INPUT", "DEMO_PLACEHOLDER"},
    "alloy_specifications": {"DEMO_PLACEHOLDER"},
}


def validate_reference_data_integrity(reference_data: dict) -> list[ValidationIssue]:
    """Minimal sanity check that each reference file loaded and carries an
    explicit, expected status flag. Extend this as real validation rules
    are added."""
    issues: list[ValidationIssue] = []
    for key, expected_statuses in _EXPECTED_STATUS.items():
        section = reference_data.get(key)
        if section is None:
            issues.append(ValidationIssue(key, "Missing reference data section.", "error"))
            continue
        meta = section.get("_meta")
        if not meta or meta.get("status") not in expected_statuses:
            issues.append(
                ValidationIssue(
                    key,
                    f"Reference data is missing an explicit status flag from {sorted(expected_statuses)}.",
                    "warning",
                )
            )

    # baseline.json additionally nests a demo_scenario block that must carry
    # its own DEMO_PLACEHOLDER flag, separate from the corporate benchmark.
    baseline = reference_data.get("baseline")
    if baseline is not None:
        demo_scenario = baseline.get("demo_scenario")
        if not demo_scenario or demo_scenario.get("_status") != "DEMO_PLACEHOLDER":
            issues.append(
                ValidationIssue(
                    "baseline.demo_scenario",
                    "baseline.json's demo_scenario block is missing its DEMO_PLACEHOLDER flag.",
                    "warning",
                )
            )
        if "corporate_benchmark" not in baseline:
            issues.append(
                ValidationIssue(
                    "baseline.corporate_benchmark",
                    "baseline.json is missing the corporate_benchmark block.",
                    "error",
                )
            )

    return issues


# --- Chemistry validation ---------------------------------------------------
#
# Compares a computed final composition (wt%) against a stainless steel
# grade's bounds from steel_grades.json. Cr/Ni/Mo are validated against both
# a minimum and a maximum; C/Si/Mn/N are ceiling-only (max) elements per the
# grade schema. A None bound means that element isn't constrained for this
# grade and is skipped.

# element -> (min_key, max_key); min_key is None where the grade schema has
# no minimum for that element.
_GRADE_BOUND_KEYS: dict[str, tuple[Optional[str], Optional[str]]] = {
    "Cr": ("Cr_min", "Cr_max"),
    "Ni": ("Ni_min", "Ni_max"),
    "Mo": ("Mo_min", "Mo_max"),
    "C": (None, "C_max"),
    "Si": (None, "Si_max"),
    "Mn": (None, "Mn_max"),
    "N": (None, "N_max"),
}


def validate_final_chemistry(
    final_pct_by_element: dict[str, float], grade: dict
) -> tuple[list[dict[str, Any]], str]:
    """Check each element's final wt% against the selected grade's bounds.

    Returns (items, overall) where each item is a dict with keys:
    element, min_required_pct, max_allowed_pct, actual_pct, status.
    overall is "PASS" if every item passes, else "FAIL".
    """
    items: list[dict[str, Any]] = []
    overall_pass = True

    for element, (min_key, max_key) in _GRADE_BOUND_KEYS.items():
        actual = final_pct_by_element.get(element, 0.0)
        min_v = grade.get(min_key) if min_key else None
        max_v = grade.get(max_key) if max_key else None

        element_pass = True
        if min_v is not None and actual < (min_v - _CHEMISTRY_EPSILON):
            element_pass = False
        if max_v is not None and actual > (max_v + _CHEMISTRY_EPSILON):
            element_pass = False

        if not element_pass:
            overall_pass = False

        items.append(
            {
                "element": element,
                "min_required_pct": min_v,
                "max_allowed_pct": max_v,
                "actual_pct": round(actual, 4),
                "status": "PASS" if element_pass else "FAIL",
            }
        )

    return items, ("PASS" if overall_pass else "FAIL")
