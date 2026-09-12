"""
Scenario comparison: persistence + CO2 computation.

Functional unit: 1 tonne of finished stainless steel.

A scenario is a named, saved input configuration. Material CO2, Energy CO2,
and Total CO2 are computed here, server-side, via the same
carbon_emissions engine used by /calculate/emissions elsewhere in this
application - never trusted from the client - so every saved scenario's
numbers are authoritative and internally consistent with the rest of the
app. "Energy CO2" combines electricity + natural gas + coal emissions;
process emissions are not part of a scenario's fields and are not included.

Scenarios are persisted to a small JSON file (backend/runtime/scenarios.json)
rather than kept only in memory, so they survive a server restart without
requiring an external database - a lightweight, dependency-free persistence
layer appropriate for this foundation build.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from backend.data.loader import get_energy_sources, get_scrap_quality, get_steel_grades
from backend.models.schemas import (
    CarbonEmissionInput,
    MaterialBalanceInput,
    MaterialQuantityInput,
    ScenarioInput,
    ScenarioRecord,
)
from backend.services.carbon_emissions import calculate_carbon_emissions
from backend.services.material_balance import calculate_material_balance

_STORE_DIR = Path(__file__).resolve().parents[1] / "runtime"
_STORE_PATH = _STORE_DIR / "scenarios.json"


def _load_all() -> list[dict]:
    if not _STORE_PATH.exists():
        return []
    with _STORE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_all(records: list[dict]) -> None:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    with _STORE_PATH.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def _lookup_name(items: list[dict], item_id: str, name_field: str, kind: str) -> str:
    for item in items:
        if item["id"] == item_id:
            return item[name_field]
    raise HTTPException(status_code=422, detail=f"Unknown {kind} '{item_id}'.")


def _compute_co2(payload: ScenarioInput) -> tuple[float, float, float]:
    """Returns (material_co2, energy_co2, total_co2), all tCO2e/t."""
    mb = calculate_material_balance(MaterialBalanceInput(scrap_percentage=payload.scrap_pct, **{"yield": payload.yield_fraction}))

    emissions_input = CarbonEmissionInput(
        materials=[
            MaterialQuantityInput(material_id="SCRAP_EMBODIED", quantity_t=mb.scrap_mass, label="Scrap"),
            MaterialQuantityInput(material_id="VIRGIN_EMBODIED", quantity_t=mb.virgin_mass, label="Virgin iron"),
        ],
        electricity_consumption_mwh_per_t=payload.electricity_consumption_mwh_per_t,
        electricity_mix=[],
        electricity_source_id=payload.energy_source_id,
        natural_gas_consumption_gj_per_t=payload.natural_gas_consumption_gj_per_t,
        coal_consumption_gj_per_t=payload.coal_consumption_gj_per_t,
    )
    result = calculate_carbon_emissions(emissions_input)

    material_co2 = result.material_emissions.total_tco2e
    energy_co2 = result.electricity_emissions.total_tco2e + result.fuel_emissions.total_tco2e
    total_co2 = result.carbon_intensity_tCO2e_per_tSS
    return material_co2, energy_co2, total_co2


def create_scenario(payload: ScenarioInput) -> ScenarioRecord:
    grades = get_steel_grades()["grades"]
    scrap_categories = get_scrap_quality()["categories"]
    energy_sources = get_energy_sources()["sources"]

    grade_name = _lookup_name(grades, payload.grade_id, "grade_name", "grade_id")
    scrap_quality_name = _lookup_name(scrap_categories, payload.scrap_quality_id, "category_name", "scrap_quality_id")
    energy_source_name = _lookup_name(energy_sources, payload.energy_source_id, "name", "energy_source_id")

    material_co2, energy_co2, total_co2 = _compute_co2(payload)

    record = ScenarioRecord(
        id=uuid.uuid4().hex,
        created_at=datetime.now(timezone.utc).isoformat(),
        grade_name=grade_name,
        scrap_quality_name=scrap_quality_name,
        energy_source_name=energy_source_name,
        material_co2_tco2e_per_t=round(material_co2, 6),
        energy_co2_tco2e_per_t=round(energy_co2, 6),
        total_co2_tco2e_per_t=round(total_co2, 6),
        **payload.model_dump(by_alias=True),
    )

    records = _load_all()
    records.append(json.loads(record.model_dump_json(by_alias=True)))
    _save_all(records)

    return record


def list_scenarios() -> list[ScenarioRecord]:
    return [ScenarioRecord(**r) for r in _load_all()]


def delete_scenario(scenario_id: str) -> bool:
    records = _load_all()
    filtered = [r for r in records if r["id"] != scenario_id]
    if len(filtered) == len(records):
        return False
    _save_all(filtered)
    return True
