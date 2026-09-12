"""
Complete carbon-emission calculation engine.

Functional unit: 1 tonne of finished stainless steel ("tSS"), matching the
material balance and scrap chemistry engines.

    Total Carbon = Material Carbon + Electricity Carbon
                   + Direct Fuel Carbon + Process Carbon

    CO2_material    = sum(material_quantity_t x emission_factor)
    CO2_electricity = electricity_consumption x sum(energy_share x emission_factor)
    CO2_NG          = natural_gas_consumption x EF_NG
    CO2_coal        = coal_consumption x EF_coal
    CO2_process     = a configurable factor (a named process route, or an
                      explicit override)

Every emission factor is looked up by id from data/emission_factors.json.
This engine NEVER fabricates a missing factor: if a requested id has no
entry, that item is reported with factor_available=False, contributes 0 to
the running total, and a human-readable warning is added to
missing_factor_warnings. The overall carbon_intensity result is therefore a
lower bound whenever any warning is present, not a complete figure - the
warnings list makes that explicit rather than letting a silent zero look
like a real answer.
"""
from __future__ import annotations

from backend.data.loader import get_emission_factors
from backend.models.schemas import (
    CarbonEmissionInput,
    CarbonEmissionResult,
    ElectricityEmissions,
    ElectricityMixComponentInput,
    ElectricityMixItemResult,
    FuelEmissionItem,
    FuelEmissions,
    MaterialEmissionItem,
    MaterialEmissions,
    ProcessEmissions,
)


def _factor_index() -> dict[str, dict]:
    return {f["id"]: f for f in get_emission_factors()["factors"]}


def _material_emissions(payload: CarbonEmissionInput, factors: dict[str, dict]) -> tuple[MaterialEmissions, list[str]]:
    items: list[MaterialEmissionItem] = []
    warnings: list[str] = []
    total = 0.0

    for material in payload.materials:
        factor = factors.get(material.material_id)
        label = material.label or (factor["name"] if factor else material.material_id)

        if factor is None:
            warnings.append(
                f"No emission factor on file for material_id '{material.material_id}'. "
                "Its contribution is excluded from the total rather than fabricated."
            )
            items.append(
                MaterialEmissionItem(
                    material_id=material.material_id,
                    label=label,
                    quantity_t=material.quantity_t,
                    emission_factor_tco2e_per_t=None,
                    tco2e=0.0,
                    factor_available=False,
                    note="Emission factor unavailable - excluded from total, not fabricated.",
                )
            )
            continue

        tco2e = material.quantity_t * factor["value"]
        total += tco2e
        items.append(
            MaterialEmissionItem(
                material_id=material.material_id,
                label=label,
                quantity_t=material.quantity_t,
                emission_factor_tco2e_per_t=factor["value"],
                tco2e=round(tco2e, 6),
                factor_available=True,
            )
        )

    return MaterialEmissions(total_tco2e=round(total, 6), items=items), warnings


def _electricity_emissions(
    payload: CarbonEmissionInput, factors: dict[str, dict]
) -> tuple[ElectricityEmissions, list[str]]:
    warnings: list[str] = []

    # Build the mix: explicit electricity_mix takes precedence; otherwise
    # fall back to the single-source shortcut; otherwise no mix at all.
    if not payload.electricity_mix and payload.electricity_source_id:
        mix_input = [ElectricityMixComponentInput(source_id=payload.electricity_source_id, share_pct=100.0)]
    else:
        mix_input = payload.electricity_mix

    mix_results: list[ElectricityMixItemResult] = []
    weighted_factor_sum = 0.0
    any_component_available = False

    for component in mix_input:
        factor = factors.get(component.source_id)
        if factor is None:
            warnings.append(
                f"No emission factor on file for electricity source '{component.source_id}'. "
                "Its share is excluded from the effective electricity factor, not fabricated."
            )
            mix_results.append(
                ElectricityMixItemResult(
                    source_id=component.source_id,
                    label=component.source_id,
                    share_pct=component.share_pct,
                    emission_factor_tco2e_per_mwh=None,
                    factor_available=False,
                    note="Emission factor unavailable - excluded from effective factor, not fabricated.",
                )
            )
            continue

        any_component_available = True
        weighted_factor_sum += (component.share_pct / 100.0) * factor["value"]
        mix_results.append(
            ElectricityMixItemResult(
                source_id=component.source_id,
                label=factor["name"],
                share_pct=component.share_pct,
                emission_factor_tco2e_per_mwh=factor["value"],
                factor_available=True,
            )
        )

    if mix_input and abs(sum(c.share_pct for c in mix_input) - 100.0) > 1e-6:
        warnings.append(
            "Electricity mix shares do not sum to 100% - the effective emission factor is "
            "computed from the shares as given, without normalizing."
        )

    consumption = payload.electricity_consumption_mwh_per_t

    if mix_input and any_component_available:
        effective_factor = weighted_factor_sum
        total_tco2e = consumption * effective_factor
    else:
        effective_factor = None
        total_tco2e = 0.0
        if consumption > 0 and not mix_input:
            warnings.append(
                "Electricity consumption was provided but no electricity source or mix was "
                "configured - electricity emissions are reported as 0, not fabricated."
            )
        elif consumption > 0 and mix_input and not any_component_available:
            warnings.append(
                "Electricity consumption was provided but no component of the electricity mix "
                "had an available emission factor - electricity emissions are reported as 0, "
                "not fabricated."
            )

    return (
        ElectricityEmissions(
            total_tco2e=round(total_tco2e, 6),
            consumption_mwh_per_t=consumption,
            mix=mix_results,
            effective_emission_factor_tco2e_per_mwh=(
                round(effective_factor, 6) if effective_factor is not None else None
            ),
        ),
        warnings,
    )


def _fuel_item(
    fuel_id: str, label: str, consumption: float, factors: dict[str, dict]
) -> tuple[FuelEmissionItem, list[str]]:
    warnings: list[str] = []
    factor = factors.get(fuel_id)

    if factor is None:
        warnings.append(
            f"No emission factor on file for fuel id '{fuel_id}'. "
            "Its contribution is excluded from the total rather than fabricated."
        )
        return (
            FuelEmissionItem(
                fuel_id=fuel_id,
                label=label,
                consumption_gj_per_t=consumption,
                emission_factor_tco2e_per_gj=None,
                tco2e=0.0,
                factor_available=False,
                note="Emission factor unavailable - excluded from total, not fabricated.",
            ),
            warnings,
        )

    tco2e = consumption * factor["value"]
    return (
        FuelEmissionItem(
            fuel_id=fuel_id,
            label=factor["name"],
            consumption_gj_per_t=consumption,
            emission_factor_tco2e_per_gj=factor["value"],
            tco2e=round(tco2e, 6),
            factor_available=True,
        ),
        warnings,
    )


def _fuel_emissions(payload: CarbonEmissionInput, factors: dict[str, dict]) -> tuple[FuelEmissions, list[str]]:
    ng_item, ng_warnings = _fuel_item(
        "NATURAL_GAS", "Natural Gas", payload.natural_gas_consumption_gj_per_t, factors
    )
    coal_item, coal_warnings = _fuel_item("COAL", "Coal", payload.coal_consumption_gj_per_t, factors)
    total = ng_item.tco2e + coal_item.tco2e
    return FuelEmissions(total_tco2e=round(total, 6), natural_gas=ng_item, coal=coal_item), ng_warnings + coal_warnings


def _process_emissions(payload: CarbonEmissionInput, factors: dict[str, dict]) -> tuple[ProcessEmissions, list[str]]:
    warnings: list[str] = []

    if payload.process_emission_override_tco2e_per_t is not None:
        return (
            ProcessEmissions(
                tco2e_per_t=payload.process_emission_override_tco2e_per_t,
                source="override",
                process_route_id=None,
                factor_available=True,
                note="Explicit override supplied by the caller; configurable per request.",
            ),
            warnings,
        )

    if payload.process_route_id:
        factor = factors.get(payload.process_route_id)
        if factor is None:
            warnings.append(
                f"No emission factor on file for process_route_id '{payload.process_route_id}'. "
                "Process emissions are reported as 0, not fabricated."
            )
            return (
                ProcessEmissions(
                    tco2e_per_t=0.0,
                    source="process_route",
                    process_route_id=payload.process_route_id,
                    factor_available=False,
                    note="Emission factor unavailable - reported as 0, not fabricated.",
                ),
                warnings,
            )
        return (
            ProcessEmissions(
                tco2e_per_t=factor["value"],
                source="process_route",
                process_route_id=payload.process_route_id,
                factor_available=True,
            ),
            warnings,
        )

    warnings.append(
        "No process_route_id or process_emission_override_tco2e_per_t was supplied - "
        "process emissions are reported as 0, not fabricated."
    )
    return (
        ProcessEmissions(
            tco2e_per_t=0.0,
            source="not_configured",
            process_route_id=None,
            factor_available=False,
            note="Process emissions are configurable - supply process_route_id or an override.",
        ),
        warnings,
    )


def calculate_carbon_emissions(payload: CarbonEmissionInput) -> CarbonEmissionResult:
    factors = _factor_index()

    material_emissions, material_warnings = _material_emissions(payload, factors)
    electricity_emissions, electricity_warnings = _electricity_emissions(payload, factors)
    fuel_emissions, fuel_warnings = _fuel_emissions(payload, factors)
    process_emissions, process_warnings = _process_emissions(payload, factors)

    total_tco2e_per_t = (
        material_emissions.total_tco2e
        + electricity_emissions.total_tco2e
        + fuel_emissions.total_tco2e
        + process_emissions.tco2e_per_t
    )

    all_warnings = material_warnings + electricity_warnings + fuel_warnings + process_warnings

    return CarbonEmissionResult(
        carbon_intensity_tCO2e_per_tSS=round(total_tco2e_per_t, 6),
        carbon_intensity_kgCO2e_per_tSS=round(total_tco2e_per_t * 1000, 3),
        material_emissions=material_emissions,
        electricity_emissions=electricity_emissions,
        fuel_emissions=fuel_emissions,
        process_emissions=process_emissions,
        emission_breakdown_by_material=material_emissions.items,
        missing_factor_warnings=all_warnings,
    )
