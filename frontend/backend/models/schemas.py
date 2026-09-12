"""
Pydantic models (schemas) for JSL GreenSteel Carbon & Energy Optimization Calculator.

NOTE: This models the *shape* of the domain (inputs/outputs for the carbon
calculator). It intentionally does NOT encode any scientific constants -
those live only in /data/*.json and are all marked DEMO_PLACEHOLDER there.
"""
from __future__ import annotations

from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EmissionFactor(BaseModel):
    """A single emission factor with full disclosure metadata.

    Every emission factor surfaced by this application - regardless of
    category (electricity, fuel, process route, alloy addition, material
    mix) - carries all ten of these fields so a reader never has to take a
    number on faith. See data/emission_factors.json for the canonical set.
    """

    name: str
    value: float
    unit: str
    year: Optional[int] = None
    geography: str
    boundary: str
    scope: str
    source: str
    confidence: str
    notes: Optional[str] = None


class EmissionFactorEntry(EmissionFactor):
    """An EmissionFactor plus its catalog id/category, as stored in
    emission_factors.json's 'factors' array."""

    id: str
    category: str


class SteelGrade(BaseModel):
    """Composition bounds for one stainless steel grade. All figures are
    illustrative DEMO values unless status == 'VALIDATED'."""

    id: str
    grade_name: str
    family: str
    status: str
    Cr_min: float
    Cr_max: float
    Ni_min: float
    Ni_max: float
    Mo_min: float
    Mo_max: float
    C_max: float
    Si_max: float
    Mn_max: float
    N_max: Optional[float] = None
    source: str


class ScrapQualityCategory(BaseModel):
    """One scrap quality tier (High / Medium / Low Quality)."""

    id: str
    category_name: str
    status: str
    description: str
    Cr: float
    Ni: float
    Mo: float
    Fe: float
    C: float
    Si: float
    Mn: float
    N: float
    yield_pct: float = Field(..., alias="yield")
    alloy_recovery: float
    source: str

    model_config = ConfigDict(populate_by_name=True)


class EnergySource(BaseModel):
    """One of the four primary energy sources, with its embedded emission factor."""

    id: str
    name: str
    type: str
    description: str
    emission_factor: EmissionFactor


class BaselineScopeFigure(BaseModel):
    value: float
    unit: str
    boundary: str
    source: str
    confidence: str


class BaselineDerivedTotal(BaseModel):
    value: float
    unit: str
    derivation: str
    note: str


class CorporateBenchmark(BaseModel):
    """JSL FY26 corporate carbon-intensity benchmark.

    This is a company-wide reported figure, NOT a scientifically derived,
    product- or grade-specific stainless-steel emission factor. It must
    never be presented as a universal per-tonne product factor.
    """

    label: str
    company: str
    fiscal_year: str
    unit: str
    unit_expanded: str
    scope_1_plus_2: BaselineScopeFigure
    scope_3: BaselineScopeFigure
    derived_reference_total: BaselineDerivedTotal


class AlloyAdditions(BaseModel):
    """kg of alloy added per tonne of liquid steel, keyed by alloy id.

    Keys should match entries in data/emission_factors.json -> alloy_additions.elements
    (e.g. FERRO_CHROME, FERRO_NICKEL, NICKEL_METAL, FERRO_MOLYBDENUM,
    FERRO_MANGANESE, FERRO_SILICON, FERRO_TITANIUM).
    """

    values_kg_per_t: Dict[str, float] = Field(default_factory=dict)


class CarbonCalculationInput(BaseModel):
    """All inputs the Problem Statement calls out, as one request payload."""

    # 1 & 2. Scrap vs virgin material split
    scrap_pct: float = Field(..., ge=0, le=100, description="Scrap % of total charge mix")
    virgin_material_pct: float = Field(..., ge=0, le=100, description="Virgin raw material % of total charge mix")

    # 3. Stainless steel grade
    grade_id: str = Field(..., description="ID from steel_grades.json, e.g. SS304")

    # 4. Scrap quality / composition
    scrap_quality_id: str = Field(..., description="ID from scrap_quality.json")

    # 5 & 6. Energy source + electricity consumption
    electricity_source_id: str = Field(..., description="ID from energy_sources.json -> electricity_sources")
    electricity_consumption_mwh_per_t: float = Field(..., ge=0, description="MWh consumed per tonne of liquid steel")

    # 7. Fuel consumption
    fuel_source_id: str = Field(..., description="ID from energy_sources.json -> fuel_sources")
    fuel_consumption_gj_per_t: float = Field(..., ge=0, description="GJ of fuel consumed per tonne of liquid steel")

    # Process route (needed to select a process-emission factor)
    process_route_id: str = Field(..., description="ID from energy_sources.json -> process_routes")

    # 8. Alloy additions
    alloy_additions: AlloyAdditions = Field(default_factory=AlloyAdditions)

    @model_validator(mode="after")
    def check_mix_sums_roughly_to_100(self) -> "CarbonCalculationInput":
        total = self.scrap_pct + self.virgin_material_pct
        if not (99.0 <= total <= 101.0):
            raise ValueError(
                f"scrap_pct + virgin_material_pct should sum to ~100 (got {total:.2f}). "
                "Adjust the charge mix so the two shares are consistent."
            )
        return self


class EmissionBreakdownItem(BaseModel):
    category: str
    label: str
    tco2e_per_t: float
    is_placeholder: bool = True
    note: Optional[str] = None


class CarbonCalculationResult(BaseModel):
    status: str = "DEMO_PLACEHOLDER"
    warning: str = (
        "All emission factors used are unverified placeholders. This result is "
        "illustrative of application behaviour only and must not be used for "
        "real reporting, compliance, or investment decisions."
    )
    total_tco2e_per_t: float
    breakdown: list[EmissionBreakdownItem]
    input_echo: CarbonCalculationInput


class HealthResponse(BaseModel):
    status: str
    service: str
    data_status: str


# --- Material balance ---------------------------------------------------
#
# Functional unit: 1 tonne of finished stainless steel.
# No emissions are calculated here - this is mass accounting only.


class MaterialBalanceInput(BaseModel):
    """Inputs to the material balance engine.

    'yield' is the fraction of charged mass that ends up as finished steel
    (0 < yield <= 1, e.g. 0.92 for a 92% yield). It is exposed as `yield`
    in JSON (a reserved word in Python) via a field alias.
    """

    scrap_percentage: float = Field(..., ge=0, le=100, description="Scrap % of the charge mix")
    yield_fraction: float = Field(
        ...,
        gt=0,
        le=1,
        alias="yield",
        description="Fraction of charged mass recovered as finished steel (0 < yield <= 1)",
    )

    model_config = ConfigDict(populate_by_name=True)


class MaterialBalanceValidationStatus(BaseModel):
    """Explicit pass/fail for each required validation check, plus an
    overall verdict, so a caller never has to infer correctness from the
    numbers alone."""

    mix_sums_to_100: bool
    mass_balance_closes: bool
    no_negative_mass: bool
    overall: str  # "PASS" | "FAIL"


class MaterialBalanceResult(BaseModel):
    charge_mass: float = Field(..., description="Mass charged per tonne of finished steel (t)")
    scrap_mass: float = Field(..., description="Mass of scrap in the charge (t)")
    virgin_mass: float = Field(..., description="Mass of virgin raw material in the charge (t)")
    scrap_percentage: float
    virgin_percentage: float
    yield_fraction: float = Field(..., alias="yield")
    validation_status: MaterialBalanceValidationStatus

    model_config = ConfigDict(populate_by_name=True)


# --- Scrap chemistry -----------------------------------------------------
#
# Functional unit: 1 tonne of finished stainless steel (matches
# MaterialBalanceResult). Determines the approximate element contribution
# from the selected scrap quality, compares it against the selected grade's
# Cr/Ni/Mo requirement, and computes the alloy additions needed to close any
# deficit. Does NOT calculate emissions - that stays in carbon_calculator.py.

_ELEMENTS = ("Cr", "Ni", "Mo", "Fe", "C", "Si", "Mn", "N")
_CRITICAL_ELEMENTS = ("Cr", "Ni", "Mo")


class ScrapChemistryInput(BaseModel):
    scrap_quality_id: str = Field(..., description="ID from scrap_quality.json")
    scrap_mass: float = Field(..., ge=0, description="Mass of scrap charged, in tonnes (e.g. from the material balance result). 0 is valid - it models an all-virgin charge, where every alloying element must come from purchased alloy addition.")
    grade_id: str = Field(..., description="ID from steel_grades.json - the target grade to check against")


class ScrapChemistryEcho(BaseModel):
    """The raw composition/recovery assumptions used for this calculation,
    echoed back so the result is self-contained and auditable."""

    scrap_quality_id: str
    category_name: str
    status: str
    Cr_pct: float
    Ni_pct: float
    Mo_pct: float
    Fe_pct: float
    C_pct: float
    Si_pct: float
    Mn_pct: float
    N_pct: float
    yield_pct: float
    alloy_recovery_pct: float
    source: str


class ElementContribution(BaseModel):
    """Mass (t) of each element contributed by the scrap charge:
    element_mass = scrap_mass x element_fraction x recovery."""

    Cr_from_scrap: float
    Ni_from_scrap: float
    Mo_from_scrap: float
    Fe_from_scrap: float
    C_from_scrap: float
    Si_from_scrap: float
    Mn_from_scrap: float
    N_from_scrap: float


class ElementDeficit(BaseModel):
    element: str
    required_mass: float = Field(..., description="Mass (t) needed to meet the grade's minimum for this element")
    supplied_mass: float = Field(..., description="Mass (t) supplied by scrap alone")
    deficit_mass: float = Field(..., description="max(0, required_mass - supplied_mass)")


class AlloyAdditionRequired(BaseModel):
    element: str
    alloy_id: str
    alloy_name: str
    concentration_pct: float = Field(..., description="wt% of the target element within the alloy addition")
    recovery_pct: float = Field(..., description="% of that element retained in the melt after addition")
    required_mass_t: float = Field(..., description="deficit / (concentration x recovery), in tonnes of alloy")
    required_mass_kg: float


class FinalElementChemistry(BaseModel):
    element: str
    mass_t: float = Field(..., description="Scrap contribution plus any alloy addition, in tonnes")
    pct: float = Field(..., description="mass_t expressed as wt% of the 1 t functional unit")


class ChemistryValidationItem(BaseModel):
    element: str
    min_required_pct: Optional[float] = None
    max_allowed_pct: Optional[float] = None
    actual_pct: float
    status: str  # "PASS" | "FAIL"


class ChemistryValidation(BaseModel):
    items: list[ChemistryValidationItem]
    overall: str  # "PASS" | "FAIL"


class ScrapChemistryResult(BaseModel):
    status: str = "DEMO_PLACEHOLDER"
    warning: str = (
        "Scrap composition and alloy specification figures used here are unverified "
        "placeholders. This result is illustrative of application behaviour only and "
        "must not be used for real charge design, procurement, or compliance decisions."
    )
    grade_id: str
    scrap_chemistry: ScrapChemistryEcho
    element_contribution: ElementContribution
    element_deficits: list[ElementDeficit]
    alloy_additions: list[AlloyAdditionRequired]
    final_chemistry: list[FinalElementChemistry]
    chemistry_validation: ChemistryValidation


# --- Complete carbon-emission calculation engine --------------------------
#
# Functional unit: 1 tonne of finished stainless steel ("tSS"), matching the
# material balance and scrap chemistry engines. This is the "complete"
# emission model:
#     Total Carbon = Material Carbon + Electricity Carbon
#                    + Direct Fuel Carbon + Process Carbon
#
# Every emission factor is looked up from data/emission_factors.json by id.
# If a requested id has no factor on file, this engine does NOT fabricate
# one - it reports the gap explicitly (factor_available=False, a warning
# string, and that item contributing 0 to the total) rather than guessing.


class MaterialQuantityInput(BaseModel):
    """One material or alloy addition entering the charge.

    material_id should match an id in emission_factors.json - e.g.
    SCRAP_EMBODIED, VIRGIN_EMBODIED, FERRO_CHROME, FERRO_NICKEL,
    NICKEL_METAL, FERRO_MOLYBDENUM, FERRO_MANGANESE, FERRO_SILICON,
    FERRO_TITANIUM - or any other id a caller wants priced; unknown ids are
    reported as a missing-factor warning rather than fabricated.
    """

    material_id: str
    quantity_t: float = Field(..., ge=0, description="Mass of this material per tonne of finished steel (t)")
    label: Optional[str] = Field(None, description="Optional display label, e.g. 'Ferrochrome addition'")


class ElectricityMixComponentInput(BaseModel):
    source_id: str = Field(..., description="Electricity-category id from emission_factors.json")
    share_pct: float = Field(..., ge=0, le=100, description="Share of total electricity consumption (%)")


class CarbonEmissionInput(BaseModel):
    """Inputs to the complete carbon-emission engine, functional unit 1 tSS."""

    materials: list[MaterialQuantityInput] = Field(default_factory=list)

    electricity_consumption_mwh_per_t: float = Field(0, ge=0)
    electricity_mix: list[ElectricityMixComponentInput] = Field(
        default_factory=list, description="For a blended grid; overrides electricity_source_id if provided"
    )
    electricity_source_id: Optional[str] = Field(
        None, description="Convenience single-source shortcut, equivalent to a 100% share electricity_mix"
    )

    natural_gas_consumption_gj_per_t: float = Field(0, ge=0)
    coal_consumption_gj_per_t: float = Field(0, ge=0)

    process_route_id: Optional[str] = Field(None, description="process_route-category id from emission_factors.json")
    process_emission_override_tco2e_per_t: Optional[float] = Field(
        None, description="Explicit override for process emissions, taking precedence over process_route_id"
    )


class MaterialEmissionItem(BaseModel):
    material_id: str
    label: str
    quantity_t: float
    emission_factor_tco2e_per_t: Optional[float] = None
    tco2e: float
    factor_available: bool
    note: Optional[str] = None


class MaterialEmissions(BaseModel):
    total_tco2e: float
    items: list[MaterialEmissionItem]


class ElectricityMixItemResult(BaseModel):
    source_id: str
    label: str
    share_pct: float
    emission_factor_tco2e_per_mwh: Optional[float] = None
    factor_available: bool
    note: Optional[str] = None


class ElectricityEmissions(BaseModel):
    total_tco2e: float
    consumption_mwh_per_t: float
    mix: list[ElectricityMixItemResult]
    effective_emission_factor_tco2e_per_mwh: Optional[float] = Field(
        None, description="Weighted average factor across mix components with an available factor"
    )


class FuelEmissionItem(BaseModel):
    fuel_id: str
    label: str
    consumption_gj_per_t: float
    emission_factor_tco2e_per_gj: Optional[float] = None
    tco2e: float
    factor_available: bool
    note: Optional[str] = None


class FuelEmissions(BaseModel):
    total_tco2e: float
    natural_gas: FuelEmissionItem
    coal: FuelEmissionItem


class ProcessEmissions(BaseModel):
    tco2e_per_t: float
    source: str  # "override" | "process_route" | "not_configured"
    process_route_id: Optional[str] = None
    factor_available: bool
    note: Optional[str] = None


class CarbonEmissionResult(BaseModel):
    status: str = "DEMO_PLACEHOLDER"
    warning: str = (
        "All emission factors used are unverified placeholders. This result is "
        "illustrative of application behaviour only and must not be used for "
        "real reporting, compliance, or investment decisions."
    )
    carbon_intensity_tCO2e_per_tSS: float
    carbon_intensity_kgCO2e_per_tSS: float
    material_emissions: MaterialEmissions
    electricity_emissions: ElectricityEmissions
    fuel_emissions: FuelEmissions
    process_emissions: ProcessEmissions
    emission_breakdown_by_material: list[MaterialEmissionItem]
    missing_factor_warnings: list[str] = Field(default_factory=list)


# --- Validation engine -----------------------------------------------------
#
# Runs the 12 required checks across whichever domains the caller supplies
# (material balance, scrap chemistry, energy/emissions) and returns a single
# detailed report with a PASS/WARNING/ERROR status per check plus an overall
# verdict. Each sub-payload is optional: a domain's checks only appear in the
# report when its inputs are supplied, so the three-status contract stays
# clean (there is deliberately no fourth "not applicable" status).
#
# Inputs here are intentionally permissive (no ge/le bounds) where the
# equivalent field is tightly bounded on its own calculation endpoint - the
# whole point of this engine is to accept an out-of-range value and report
# *why* it fails, rather than let FastAPI reject it before this engine ever
# sees it.


class ValidationMaterialInput(BaseModel):
    """Permissive echo of the material-balance inputs, deliberately
    unbounded so checks 1-6 can evaluate and report on out-of-range values
    instead of the request being rejected before reaching them."""

    scrap_percentage: float
    virgin_percentage: Optional[float] = Field(
        None, description="If supplied, checked against 100 - scrap_percentage; otherwise derived"
    )
    yield_fraction: float = Field(..., alias="yield")

    model_config = ConfigDict(populate_by_name=True)


class ValidationRequest(BaseModel):
    material: Optional[ValidationMaterialInput] = None
    scrap_chemistry: Optional[ScrapChemistryInput] = None
    carbon_emission: Optional[CarbonEmissionInput] = None


class ValidationCheckResult(BaseModel):
    check_id: int
    name: str
    status: str  # "PASS" | "WARNING" | "ERROR"
    message: str
    details: Optional[dict] = None


class ValidationReport(BaseModel):
    overall_status: str  # "PASS" | "WARNING" | "ERROR"
    blocked: bool = Field(..., description="True when overall_status is ERROR - results should not be shown as final")
    summary: str
    checks: list[ValidationCheckResult]


# --- LP/MILP optimization engine --------------------------------------------
#
# Functional unit: 1 tonne of finished stainless steel, matching every other
# engine in this application. Minimizes total carbon intensity subject to
# grade chemistry and availability constraints.
#
# Modeling note on the energy term: the objective's energy component is
# E_total x sum(EF_j x share_j) - a single blended energy demand across up to
# four sources (grid electricity, renewable electricity, natural gas, coal).
# Natural gas and coal's native factors are tCO2e/GJ while electricity's are
# tCO2e/MWh; to blend them in one linear term this engine converts GJ-based
# factors to a MWh-equivalent basis using the standard conversion
# 1 MWh = 3.6 GJ. This is a deliberate simplification for a solvable single-
# commodity energy-mix optimization, distinct from the richer, unit-separated
# electricity/NG/coal accounting used by /calculate/emissions elsewhere in
# this application - it is documented here so the two are never confused.


class OptimizationInput(BaseModel):
    grade_id: str = Field(..., description="ID from steel_grades.json")
    scrap_quality_id: str = Field(..., description="ID from scrap_quality.json")
    yield_fraction: float = Field(..., gt=0, le=1, alias="yield", description="Fixed production yield (0, 1]")

    scrap_pct_min: float = Field(0, ge=0, le=100, description="S_min")
    scrap_pct_max: float = Field(95, ge=0, le=100, description="S_max")

    energy_demand_mwh_equivalent_per_t: float = Field(
        ..., gt=0, description="Total energy demand per t steel, MWh-equivalent (GJ figures converted at 1 MWh = 3.6 GJ)"
    )
    allow_energy_blending: bool = Field(
        True, description="True: continuous 0<=x_j<=1 blend. False: exactly one source selected (binary MILP)."
    )
    energy_capacity_pct: dict[str, float] = Field(
        default_factory=dict, description="Optional max share (%) per energy-source id, e.g. {'RENEWABLE_ELECTRICITY_IN': 30}"
    )

    scrap_availability_t: Optional[float] = Field(None, gt=0, description="Optional cap on scrap mass available (t)")

    process_route_id: Optional[str] = Field(None, description="process_route-category id from emission_factors.json")
    process_emission_override_tco2e_per_t: Optional[float] = Field(None, description="Explicit process emissions override")

    current_scrap_pct: float = Field(..., ge=0, le=100, description="Baseline scrap % for the current_carbon_intensity comparison")
    current_energy_mix_pct: dict[str, float] = Field(
        ..., description="Baseline energy mix shares (%) by source id, for the current-scenario comparison"
    )

    model_config = ConfigDict(populate_by_name=True)


class EnergyMixShareResult(BaseModel):
    source_id: str
    label: str
    share_pct: float


class AlloyAdditionOptimalResult(BaseModel):
    element: str
    alloy_id: str
    alloy_name: str
    required_mass_kg: float


class BindingConstraintResult(BaseModel):
    name: str
    description: str


class OptimizationResult(BaseModel):
    status: str  # "OPTIMAL" | "INFEASIBLE" | "ERROR"
    message: str
    warning: str = (
        "Emission factors, alloy specifications, and scrap composition used here are "
        "unverified DEMO_PLACEHOLDER values, and the energy term uses a simplified "
        "single-commodity blend (see module docstring). Illustrative of application "
        "behaviour only - not for real production or investment decisions."
    )

    optimal_scrap_percentage: Optional[float] = None
    optimal_virgin_percentage: Optional[float] = None
    optimal_energy_mix: Optional[list[EnergyMixShareResult]] = None
    optimal_alloy_additions: Optional[list[AlloyAdditionOptimalResult]] = None

    optimized_carbon_intensity: Optional[float] = None
    current_carbon_intensity: Optional[float] = None
    absolute_reduction: Optional[float] = None
    percentage_reduction: Optional[float] = None

    current_scenario_chemistry_valid: Optional[bool] = Field(
        None,
        description=(
            "Whether the caller's current scrap%/energy scenario, after closing any Cr/Ni/Mo "
            "deficit against the grade minimum, also satisfies the grade's maximum limits. "
            "False means current_carbon_intensity reflects a composition that would not "
            "actually pass grade chemistry - e.g. the scrap quality contaminates the melt "
            "with more of an element than the grade allows, regardless of alloy additions."
        ),
    )
    current_scenario_chemistry_note: Optional[str] = None

    binding_constraints: list[BindingConstraintResult] = Field(default_factory=list)


# --- Sensitivity analysis ---------------------------------------------------
#
# Functional unit: 1 tonne of finished stainless steel, matching every other
# engine. Sweeps one dimension at a time (scrap %, energy source, scrap
# quality, grade) while holding the other three at their baseline value,
# using the same deterministic "close the deficit to the grade minimum, then
# validate against the full min/max envelope" evaluation as the optimizer's
# current-scenario check - so a swept point that would fail grade chemistry
# is marked infeasible rather than silently included as if it were usable.


class SensitivityInput(BaseModel):
    grade_id: str = Field(..., description="Baseline grade - held fixed for the energy/quality/scrap-% sweeps")
    scrap_quality_id: str = Field(..., description="Baseline scrap quality - held fixed for the scrap-%/energy/grade sweeps")
    scrap_pct: float = Field(..., ge=0, le=100, description="Baseline scrap % - held fixed for the energy/quality/grade sweeps")
    energy_source_id: str = Field(..., description="Baseline single energy source - held fixed for the scrap-%/quality/grade sweeps")
    yield_fraction: float = Field(..., gt=0, le=1, alias="yield")
    energy_demand_mwh_equivalent_per_t: float = Field(..., gt=0)
    process_route_id: Optional[str] = None
    process_emission_override_tco2e_per_t: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True)


class SensitivityPoint(BaseModel):
    label: str
    value_id: str
    carbon_intensity_tco2e_per_t: float
    chemistry_valid: bool
    is_lowest_feasible: bool


class SensitivitySweep(BaseModel):
    dimension: str
    baseline_note: str
    points: list[SensitivityPoint]
    insight: str


class SensitivityResult(BaseModel):
    status: str = "DEMO_PLACEHOLDER"
    warning: str = (
        "Emission factors, alloy specifications, and scrap composition used here are "
        "unverified DEMO_PLACEHOLDER values, and the energy term uses the same simplified "
        "single-commodity MWh-equivalent blend as the optimizer. Illustrative of application "
        "behaviour only - not for real production or investment decisions."
    )
    scrap_percentage_sweep: SensitivitySweep
    energy_source_sweep: SensitivitySweep
    scrap_quality_sweep: SensitivitySweep
    grade_sweep: SensitivitySweep


# --- Scenario comparison -----------------------------------------------------
#
# Functional unit: 1 tonne of finished stainless steel. A scenario is a named,
# saved input configuration (grade, scrap %, scrap quality, energy source,
# electricity/NG/coal consumption, yield). Material CO2, Energy CO2, and
# Total CO2 (= carbon intensity) are computed server-side at save time via
# the same carbon_emissions engine used elsewhere - never trusted from the
# client - so every saved scenario's numbers are authoritative and
# consistent with the rest of the application. Persisted to a small JSON
# file store (backend/runtime/scenarios.json) so scenarios survive a server
# restart without requiring an external database.


class ScenarioInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    grade_id: str
    scrap_pct: float = Field(..., ge=0, le=100)
    scrap_quality_id: str
    energy_source_id: str = Field(..., description="Electricity source id, e.g. GRID_ELECTRICITY_IN")
    electricity_consumption_mwh_per_t: float = Field(..., ge=0)
    natural_gas_consumption_gj_per_t: float = Field(..., ge=0)
    coal_consumption_gj_per_t: float = Field(..., ge=0)
    yield_fraction: float = Field(..., gt=0, le=1, alias="yield")

    model_config = ConfigDict(populate_by_name=True)


class ScenarioRecord(ScenarioInput):
    id: str
    created_at: str
    grade_name: str
    scrap_quality_name: str
    energy_source_name: str
    material_co2_tco2e_per_t: float
    energy_co2_tco2e_per_t: float
    total_co2_tco2e_per_t: float


class ScenarioListResponse(BaseModel):
    scenarios: list[ScenarioRecord]


# --- Uncertainty analysis ----------------------------------------------------
#
# Functional unit: 1 tonne of finished stainless steel. Explores how much
# total carbon intensity could plausibly move given uncertainty in five
# categories: emission factors, scrap composition, yield, alloy recovery,
# and energy consumption. scrap_pct itself is a user-chosen configuration,
# not an uncertain input, and is held fixed at its given value throughout.
#
# IMPORTANT INTERPRETATION NOTE: every uncertainty_pct here is an assumed
# spread around this application's DEMO_PLACEHOLDER nominal values, not a
# measured statistical uncertainty from any real process or lab. This
# analysis characterizes MODEL uncertainty (how sensitive the calculation
# is to the ranges we assumed) - it is NOT a measurement-uncertainty
# analysis, and should not be presented as one unless the ranges are
# replaced with real, plant-derived variability data.


class UncertaintyInput(BaseModel):
    grade_id: str
    scrap_quality_id: str
    scrap_pct: float = Field(..., ge=0, le=100, description="Fixed configuration, not treated as uncertain")
    energy_source_id: str
    yield_fraction: float = Field(..., gt=0, le=1, alias="yield", description="Nominal (base-case) yield")
    energy_demand_mwh_equivalent_per_t: float = Field(..., gt=0, description="Nominal energy demand")
    process_route_id: Optional[str] = None
    process_emission_override_tco2e_per_t: Optional[float] = None

    emission_factor_uncertainty_pct: float = Field(15.0, ge=0, le=100)
    scrap_composition_uncertainty_pct: float = Field(10.0, ge=0, le=100)
    yield_uncertainty_pct: float = Field(3.0, ge=0, le=100)
    alloy_recovery_uncertainty_pct: float = Field(5.0, ge=0, le=100)
    energy_consumption_uncertainty_pct: float = Field(10.0, ge=0, le=100)

    run_monte_carlo: bool = True
    n_simulations: int = Field(1000, ge=100, le=20000)
    random_seed: Optional[int] = Field(None, description="Set for reproducible simulations, e.g. in tests")

    model_config = ConfigDict(populate_by_name=True)


class ScenarioCaseResult(BaseModel):
    label: str  # "Best Case" | "Base Case" | "Worst Case"
    carbon_intensity_tco2e_per_t: float


class HistogramBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class MonteCarloResult(BaseModel):
    n_simulations: int
    mean_tco2e_per_t: float
    median_tco2e_per_t: float
    min_tco2e_per_t: float
    max_tco2e_per_t: float
    p5_tco2e_per_t: float
    p95_tco2e_per_t: float
    histogram: list[HistogramBin]


class UncertaintyRangesUsed(BaseModel):
    emission_factor_uncertainty_pct: float
    scrap_composition_uncertainty_pct: float
    yield_uncertainty_pct: float
    alloy_recovery_uncertainty_pct: float
    energy_consumption_uncertainty_pct: float


class UncertaintyResult(BaseModel):
    status: str = "DEMO_PLACEHOLDER"
    warning: str = (
        "Emission factors, scrap composition, and alloy specifications used here are "
        "unverified DEMO_PLACEHOLDER values, and the uncertainty ranges applied to them are "
        "assumed spreads, not measured variability. This is illustrative of application "
        "behaviour only - not for real production or investment decisions."
    )
    interpretation_note: str = (
        "This analysis represents MODEL uncertainty - how much the calculated result could "
        "move given the assumed input ranges - not MEASUREMENT uncertainty from real plant "
        "data. Treat it as a measurement-uncertainty analysis only if the ranges above are "
        "replaced with variability actually observed at a plant (e.g. from repeated lab "
        "assays of scrap composition or metered energy consumption)."
    )
    uncertainty_ranges_used: UncertaintyRangesUsed
    best_case: ScenarioCaseResult
    base_case: ScenarioCaseResult
    worst_case: ScenarioCaseResult
    monte_carlo: Optional[MonteCarloResult] = None


# --- PDF report -------------------------------------------------------------
#
# Assembles a full scenario report by running material_balance,
# scrap_chemistry, carbon_emissions, the LP/MILP optimizer, sensitivity
# analysis, and validation together against one configuration, then renders
# the result as a PDF. No new calculation logic lives here - it is pure
# orchestration plus presentation of numbers already computed elsewhere.


class ReportInput(BaseModel):
    scenario_name: str = Field("Untitled Scenario", min_length=1, max_length=100)
    grade_id: str
    scrap_quality_id: str
    scrap_pct: float = Field(..., ge=0, le=100)
    energy_source_id: str
    electricity_consumption_mwh_per_t: float = Field(..., ge=0)
    natural_gas_consumption_gj_per_t: float = Field(..., ge=0)
    coal_consumption_gj_per_t: float = Field(..., ge=0)
    yield_fraction: float = Field(..., gt=0, le=1, alias="yield")
    scrap_pct_min: float = Field(0, ge=0, le=100)
    scrap_pct_max: float = Field(95, ge=0, le=100)

    model_config = ConfigDict(populate_by_name=True)
