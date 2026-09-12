"""
Carbon calculation service.

This is the FOUNDATION calculator only: simple, transparent arithmetic that
wires every one of the 8 required inputs into a per-tonne CO2e estimate, so
the application runs end-to-end. It is deliberately NOT a rigorous mass/energy
balance model yet - that is future scope (material balance, alloy chemistry,
and validated emission calculation modules listed in the roadmap).

Every factor pulled from /data is a DEMO_PLACEHOLDER (see emission_factors.json).
The one exception is baseline.json's corporate_benchmark block, which is a
stated JSL FY26 figure (not a per-product emission factor) and is not used
in this per-heat calculation at all.
"""
from __future__ import annotations

from fastapi import HTTPException

from backend.data.loader import get_emission_factors, get_scrap_quality, get_steel_grades
from backend.models.schemas import CarbonCalculationInput, CarbonCalculationResult, EmissionBreakdownItem


def _factor_by_id(factors_list: list[dict], factor_id: str, kind: str) -> dict:
    for entry in factors_list:
        if entry.get("id") == factor_id:
            return entry
    valid = ", ".join(sorted(e["id"] for e in factors_list))
    raise HTTPException(status_code=422, detail=f"Unknown {kind} id '{factor_id}'. Valid options: {valid}")


def calculate_carbon(payload: CarbonCalculationInput) -> CarbonCalculationResult:
    factors_data = get_emission_factors()
    factors_list = factors_data["factors"]

    # Validate reference ids exist (grade, scrap quality) - not yet used
    # numerically beyond scrap/virgin split, but validated so the frontend
    # gets a clear error instead of a silent wrong answer.
    grades = {g["id"] for g in get_steel_grades()["grades"]}
    if payload.grade_id not in grades:
        raise HTTPException(status_code=422, detail=f"Unknown grade_id '{payload.grade_id}'.")

    scrap_qualities = {s["id"] for s in get_scrap_quality()["categories"]}
    if payload.scrap_quality_id not in scrap_qualities:
        raise HTTPException(status_code=422, detail=f"Unknown scrap_quality_id '{payload.scrap_quality_id}'.")

    breakdown: list[EmissionBreakdownItem] = []

    # --- 1 & 2. Scrap vs virgin material embodied emissions ---
    scrap_factor = _factor_by_id(factors_list, "SCRAP_EMBODIED", "material factor")["value"]
    virgin_factor = _factor_by_id(factors_list, "VIRGIN_EMBODIED", "material factor")["value"]
    material_tco2e = (payload.scrap_pct / 100.0) * scrap_factor + (payload.virgin_material_pct / 100.0) * virgin_factor
    breakdown.append(
        EmissionBreakdownItem(
            category="material_mix",
            label="Scrap / virgin material mix",
            tco2e_per_t=round(material_tco2e, 4),
            note="Weighted by scrap_pct / virgin_material_pct against placeholder embodied factors.",
        )
    )

    # --- 5 & 6. Electricity ---
    elec_factor_entry = _factor_by_id(factors_list, payload.electricity_source_id, "electricity_source_id")
    electricity_tco2e = payload.electricity_consumption_mwh_per_t * elec_factor_entry["value"]
    breakdown.append(
        EmissionBreakdownItem(
            category="electricity",
            label="Electricity consumption",
            tco2e_per_t=round(electricity_tco2e, 4),
        )
    )

    # --- 7. Fuel ---
    fuel_factor_entry = _factor_by_id(factors_list, payload.fuel_source_id, "fuel_source_id")
    fuel_tco2e = payload.fuel_consumption_gj_per_t * fuel_factor_entry["value"]
    breakdown.append(
        EmissionBreakdownItem(
            category="fuel",
            label="Fuel consumption",
            tco2e_per_t=round(fuel_tco2e, 4),
        )
    )

    # --- Process route ---
    route_factor_entry = _factor_by_id(factors_list, payload.process_route_id, "process_route_id")
    process_tco2e = route_factor_entry["value"]
    breakdown.append(
        EmissionBreakdownItem(
            category="process_route",
            label="Process route (direct/process emissions)",
            tco2e_per_t=round(process_tco2e, 4),
        )
    )

    # --- 8. Alloy additions ---
    alloy_tco2e = 0.0
    for alloy_id, kg_per_t in payload.alloy_additions.values_kg_per_t.items():
        entry = _factor_by_id(factors_list, alloy_id, "alloy id")
        # entry value is tCO2e per t of alloy; kg_per_t / 1000 -> t of alloy per t steel
        alloy_tco2e += (kg_per_t / 1000.0) * entry["value"]
    breakdown.append(
        EmissionBreakdownItem(
            category="alloy_additions",
            label="Alloy additions",
            tco2e_per_t=round(alloy_tco2e, 4),
        )
    )

    total = sum(item.tco2e_per_t for item in breakdown)

    return CarbonCalculationResult(
        total_tco2e_per_t=round(total, 4),
        breakdown=breakdown,
        input_echo=payload,
    )
