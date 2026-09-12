"""
Scrap chemistry calculation engine.

Functional unit: 1 tonne of finished stainless steel (matches
backend/services/material_balance.py).

Pipeline:
  1. Look up the selected scrap quality category's composition, yield, and
     alloy_recovery from scrap_quality.json.
  2. For each of the 8 tracked elements, compute the mass contributed by the
     scrap charge:
         element_mass = scrap_mass x element_fraction x recovery
  3. For the three critical alloying elements (Cr, Ni, Mo), compare the
     supplied mass against what the selected grade requires (its Cr_min /
     Ni_min / Mo_min from steel_grades.json, expressed as mass over the 1 t
     functional unit):
         deficit = max(0, required_mass - supplied_mass)
  4. Convert each deficit into an alloy addition using that alloy's
     concentration and recovery from alloy_specifications.json:
         alloy_required = deficit / (concentration x recovery)
  5. Compute the final composition (scrap contribution plus any alloy
     addition) and validate it against the grade's full Cr/Ni/Mo/C/Si/Mn/N
     bounds via backend/validation/input_validation.py.

This module does NOT calculate emissions - see carbon_calculator.py.
"""
from __future__ import annotations

from fastapi import HTTPException

from backend.data.loader import get_alloy_specifications, get_scrap_quality, get_steel_grades
from backend.models.schemas import (
    AlloyAdditionRequired,
    ChemistryValidation,
    ChemistryValidationItem,
    ElementContribution,
    ElementDeficit,
    FinalElementChemistry,
    ScrapChemistryEcho,
    ScrapChemistryInput,
    ScrapChemistryResult,
)
from backend.validation.input_validation import validate_final_chemistry

# Functional unit for this engine, matching the material balance module:
# all calculations are per 1 tonne of finished stainless steel.
_FUNCTIONAL_UNIT_MASS_T = 1.0

_ELEMENTS = ("Cr", "Ni", "Mo", "Fe", "C", "Si", "Mn", "N")
_CRITICAL_ELEMENTS = ("Cr", "Ni", "Mo")

# Which alloy_specifications.json entry supplies each critical element.
_ALLOY_FOR_ELEMENT = {
    "Cr": "FERRO_CHROME",
    "Ni": "NICKEL_METAL",
    "Mo": "FERRO_MOLYBDENUM",
}


def _get_scrap_category(scrap_quality_id: str) -> dict:
    categories = {c["id"]: c for c in get_scrap_quality()["categories"]}
    if scrap_quality_id not in categories:
        valid = ", ".join(sorted(categories.keys()))
        raise HTTPException(
            status_code=422, detail=f"Unknown scrap_quality_id '{scrap_quality_id}'. Valid options: {valid}"
        )
    return categories[scrap_quality_id]


def _get_grade(grade_id: str) -> dict:
    grades = {g["id"]: g for g in get_steel_grades()["grades"]}
    if grade_id not in grades:
        valid = ", ".join(sorted(grades.keys()))
        raise HTTPException(status_code=422, detail=f"Unknown grade_id '{grade_id}'. Valid options: {valid}")
    return grades[grade_id]


def _get_alloy_spec(alloy_id: str) -> dict:
    specs = {s["id"]: s for s in get_alloy_specifications()["specifications"]}
    if alloy_id not in specs:
        raise HTTPException(status_code=500, detail=f"Missing alloy specification '{alloy_id}' in reference data.")
    return specs[alloy_id]


def calculate_scrap_chemistry(payload: ScrapChemistryInput) -> ScrapChemistryResult:
    scrap = _get_scrap_category(payload.scrap_quality_id)
    grade = _get_grade(payload.grade_id)

    recovery = scrap["alloy_recovery"] / 100.0

    # --- Step 1-2: element contribution from scrap ---
    contribution_mass: dict[str, float] = {}
    for element in _ELEMENTS:
        element_fraction = scrap[element] / 100.0
        contribution_mass[element] = payload.scrap_mass * element_fraction * recovery

    scrap_chemistry = ScrapChemistryEcho(
        scrap_quality_id=scrap["id"],
        category_name=scrap["category_name"],
        status=scrap["status"],
        Cr_pct=scrap["Cr"],
        Ni_pct=scrap["Ni"],
        Mo_pct=scrap["Mo"],
        Fe_pct=scrap["Fe"],
        C_pct=scrap["C"],
        Si_pct=scrap["Si"],
        Mn_pct=scrap["Mn"],
        N_pct=scrap["N"],
        yield_pct=scrap["yield"],
        alloy_recovery_pct=scrap["alloy_recovery"],
        source=scrap["source"],
    )

    element_contribution = ElementContribution(
        **{f"{element}_from_scrap": round(contribution_mass[element], 6) for element in _ELEMENTS}
    )

    # --- Step 3: deficits for the critical alloying elements ---
    element_deficits: list[ElementDeficit] = []
    deficit_mass: dict[str, float] = {}
    for element in _CRITICAL_ELEMENTS:
        required_pct = grade.get(f"{element}_min") or 0.0
        required_mass = (required_pct / 100.0) * _FUNCTIONAL_UNIT_MASS_T
        supplied_mass = contribution_mass[element]
        deficit = max(0.0, required_mass - supplied_mass)
        deficit_mass[element] = deficit
        element_deficits.append(
            ElementDeficit(
                element=element,
                required_mass=round(required_mass, 6),
                supplied_mass=round(supplied_mass, 6),
                deficit_mass=round(deficit, 6),
            )
        )

    # --- Step 4: alloy additions required to close each deficit ---
    alloy_additions: list[AlloyAdditionRequired] = []
    alloy_contribution_mass: dict[str, float] = {element: 0.0 for element in _CRITICAL_ELEMENTS}
    for element in _CRITICAL_ELEMENTS:
        spec = _get_alloy_spec(_ALLOY_FOR_ELEMENT[element])
        concentration = spec["concentration_pct"] / 100.0
        alloy_recovery = spec["recovery_pct"] / 100.0
        deficit = deficit_mass[element]

        if deficit <= 0 or concentration <= 0 or alloy_recovery <= 0:
            required_alloy_mass_t = 0.0
        else:
            required_alloy_mass_t = deficit / (concentration * alloy_recovery)

        # The element actually delivered into the melt by this addition
        # (equal to the deficit it was sized to close, when deficit > 0).
        alloy_contribution_mass[element] = required_alloy_mass_t * concentration * alloy_recovery

        alloy_additions.append(
            AlloyAdditionRequired(
                element=element,
                alloy_id=spec["id"],
                alloy_name=spec["name"],
                concentration_pct=spec["concentration_pct"],
                recovery_pct=spec["recovery_pct"],
                required_mass_t=round(required_alloy_mass_t, 6),
                required_mass_kg=round(required_alloy_mass_t * 1000, 4),
            )
        )

    # --- Step 5: final chemistry and validation ---
    final_pct_by_element: dict[str, float] = {}
    final_chemistry: list[FinalElementChemistry] = []
    for element in _ELEMENTS:
        mass = contribution_mass[element]
        if element in _CRITICAL_ELEMENTS:
            mass += alloy_contribution_mass[element]
        pct = (mass / _FUNCTIONAL_UNIT_MASS_T) * 100.0
        final_pct_by_element[element] = pct
        final_chemistry.append(
            FinalElementChemistry(element=element, mass_t=round(mass, 6), pct=round(pct, 4))
        )

    validation_items_raw, overall = validate_final_chemistry(final_pct_by_element, grade)
    chemistry_validation = ChemistryValidation(
        items=[ChemistryValidationItem(**item) for item in validation_items_raw],
        overall=overall,
    )

    return ScrapChemistryResult(
        grade_id=grade["id"],
        scrap_chemistry=scrap_chemistry,
        element_contribution=element_contribution,
        element_deficits=element_deficits,
        alloy_additions=alloy_additions,
        final_chemistry=final_chemistry,
        chemistry_validation=chemistry_validation,
    )
