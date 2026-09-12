"""
JSL GreenSteel - Carbon & Energy Optimization Calculator
Backend entrypoint (FastAPI)

Run locally:
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

This is the FOUNDATION build. Implemented now:
    - /health
    - /reference-data                        (bundle: all six data files at once)
    - /reference-data/steel-grades           (data/steel_grades.json)
    - /reference-data/scrap-quality          (data/scrap_quality.json)
    - /reference-data/energy-sources         (data/energy_sources.json)
    - /reference-data/emission-factors       (data/emission_factors.json)
    - /reference-data/baseline               (data/baseline.json - JSL FY26 corporate benchmark + demo scenario)
    - /reference-data/alloy-specifications   (data/alloy_specifications.json)
    - /calculate/carbon                      (basic transparent per-tonne CO2e estimate)
    - /calculate/material-balance            (mass balance: charge/scrap/virgin mass per 1 t finished steel)
    - /calculate/scrap-chemistry             (scrap element contribution, deficits, alloy additions, final chemistry + validation)
    - /calculate/emissions                   (complete carbon-emission engine: material + electricity + fuel + process carbon)
    - /validate                              (12-point validation engine: PASS/WARNING/ERROR report across material/energy/chemistry)
    - /optimize                              (LP/MILP: minimizes total carbon intensity subject to grade chemistry & availability constraints)
    - /sensitivity                           (one-at-a-time sweeps: scrap %, energy source, scrap quality, grade)
    - /scenarios                             (save/list/delete named scenarios for comparison; JSON-file persisted)
    - /uncertainty                           (Best/Base/Worst case + optional Monte Carlo distribution)
    - /report/pdf                            (orchestrates every engine into one downloadable PDF report)

This is the current feature-complete build; remaining roadmap items are
noted in each module's own docstring where applicable.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.data.loader import (
    DataFileNotFoundError,
    get_alloy_specifications,
    get_all_reference_data,
    get_baseline,
    get_emission_factors,
    get_energy_sources,
    get_scrap_quality,
    get_steel_grades,
)
from backend.models.schemas import (
    CarbonCalculationInput,
    CarbonCalculationResult,
    CarbonEmissionInput,
    CarbonEmissionResult,
    HealthResponse,
    MaterialBalanceInput,
    MaterialBalanceResult,
    OptimizationInput,
    OptimizationResult,
    ReportInput,
    ScenarioInput,
    ScenarioListResponse,
    ScenarioRecord,
    ScrapChemistryInput,
    ScrapChemistryResult,
    SensitivityInput,
    SensitivityResult,
    UncertaintyInput,
    UncertaintyResult,
    ValidationReport,
    ValidationRequest,
)
from backend.optimization.lp_optimizer import optimize_carbon_and_energy
from backend.services.carbon_calculator import calculate_carbon
from backend.services.carbon_emissions import calculate_carbon_emissions
from backend.services.material_balance import calculate_material_balance
from backend.services.report_generator import generate_report_pdf
from backend.services.scenario_store import create_scenario, delete_scenario, list_scenarios
from backend.services.scrap_chemistry import calculate_scrap_chemistry
from backend.services.sensitivity_analysis import run_sensitivity_analysis
from backend.services.uncertainty_analysis import run_uncertainty_analysis
from backend.validation.input_validation import validate_reference_data_integrity
from backend.validation.validation_engine import run_validation

app = FastAPI(
    title="JSL GreenSteel - Carbon & Energy Optimization Calculator",
    description=(
        "Foundation API for Problem Statement 3: Carbon and Energy Calculator "
        "for Steelmaking. All emission factors are DEMO_PLACEHOLDER values - "
        "see /data/emission_factors.json."
    ),
    version="0.1.0-foundation",
)

# Permissive CORS for local dev (Vite default ports). Tighten before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="jsl-greensteel-backend", data_status="DEMO_PLACEHOLDER")


@app.get("/reference-data", tags=["reference"])
def reference_data() -> dict:
    """Bundle of all dropdown/reference data consumed by the frontend."""
    try:
        data = get_all_reference_data()
    except DataFileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    issues = validate_reference_data_integrity(data)
    return {"data": data, "validation_issues": [i.to_dict() for i in issues]}


def _load_or_500(loader_fn):
    try:
        return loader_fn()
    except DataFileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/reference-data/steel-grades", tags=["reference"])
def steel_grades() -> dict:
    """Grade composition bounds (Cr/Ni/Mo/C/Si/Mn/N). All grades are DEMO
    unless a grade's own 'status' field says otherwise."""
    return _load_or_500(get_steel_grades)


@app.get("/reference-data/scrap-quality", tags=["reference"])
def scrap_quality() -> dict:
    """High / Medium / Low Quality scrap categories with composition,
    yield, and alloy_recovery. All figures are DEMO_PLACEHOLDER."""
    return _load_or_500(get_scrap_quality)


@app.get("/reference-data/energy-sources", tags=["reference"])
def energy_sources() -> dict:
    """Grid Electricity, Renewable Electricity, Natural Gas, Coal - each
    with an embedded, fully-disclosed emission factor."""
    return _load_or_500(get_energy_sources)


@app.get("/reference-data/emission-factors", tags=["reference"])
def emission_factors() -> dict:
    """The full emission factor catalog. Every factor carries name, value,
    unit, year, geography, boundary, scope, source, confidence, and notes."""
    return _load_or_500(get_emission_factors)


@app.get("/reference-data/baseline", tags=["reference"])
def baseline() -> dict:
    """JSL FY26 corporate carbon-intensity benchmark (Scope 1+2, Scope 3,
    derived total) plus an unrelated demo scenario used only to pre-fill the
    calculator. The corporate benchmark is a company-wide reported figure,
    NOT a per-product or per-grade stainless-steel emission factor."""
    return _load_or_500(get_baseline)


@app.get("/reference-data/alloy-specifications", tags=["reference"])
def alloy_specifications() -> dict:
    """Concentration and recovery of the target element within each ferro-
    alloy/metal addition used by the scrap chemistry engine. Distinct from
    emission_factors.json's alloy_addition entries (embodied CO2)."""
    return _load_or_500(get_alloy_specifications)


@app.post("/calculate/carbon", response_model=CarbonCalculationResult, tags=["calculator"])
def calculate_carbon_endpoint(payload: CarbonCalculationInput) -> CarbonCalculationResult:
    """Foundation carbon calculator: combines all 8 required inputs into a
    transparent, itemized per-tonne CO2e estimate using placeholder factors."""
    return calculate_carbon(payload)


@app.post("/calculate/material-balance", response_model=MaterialBalanceResult, tags=["calculator"])
def calculate_material_balance_endpoint(payload: MaterialBalanceInput) -> MaterialBalanceResult:
    """Material balance engine. Functional unit: 1 tonne of finished
    stainless steel. Pure mass accounting - no emissions are calculated
    here. See backend/services/material_balance.py for the formulae."""
    return calculate_material_balance(payload)


@app.post("/calculate/scrap-chemistry", response_model=ScrapChemistryResult, tags=["calculator"])
def calculate_scrap_chemistry_endpoint(payload: ScrapChemistryInput) -> ScrapChemistryResult:
    """Scrap chemistry engine. Functional unit: 1 tonne of finished
    stainless steel. Computes element contribution from the selected scrap
    quality, Cr/Ni/Mo deficits against the selected grade, the alloy
    additions needed to close them, final composition, and a chemistry
    validation against the grade's full Cr/Ni/Mo/C/Si/Mn/N bounds. Pure
    composition accounting - no emissions are calculated here. See
    backend/services/scrap_chemistry.py for the formulae."""
    return calculate_scrap_chemistry(payload)


@app.post("/calculate/emissions", response_model=CarbonEmissionResult, tags=["calculator"])
def calculate_carbon_emissions_endpoint(payload: CarbonEmissionInput) -> CarbonEmissionResult:
    """Complete carbon-emission engine. Functional unit: 1 tonne of finished
    stainless steel. Total Carbon = Material + Electricity + Direct Fuel +
    Process carbon, each itemized and summed from data/emission_factors.json.
    Never fabricates a missing factor - see backend/services/carbon_emissions.py
    for how gaps are surfaced via missing_factor_warnings instead."""
    return calculate_carbon_emissions(payload)


@app.post("/validate", response_model=ValidationReport, tags=["validation"])
def validate_endpoint(payload: ValidationRequest) -> ValidationReport:
    """Comprehensive validation engine: runs the 12 required checks across
    whichever domains are supplied (material balance, scrap chemistry,
    energy/emissions) and returns one report with a PASS/WARNING/ERROR
    status per check. `overall_status` is ERROR and `blocked` is true
    whenever any check fails - callers should not present a final result
    as trustworthy when blocked is true. See
    backend/validation/validation_engine.py for the full check list."""
    return run_validation(payload)


@app.post("/optimize", response_model=OptimizationResult, tags=["optimization"])
def optimize_endpoint(payload: OptimizationInput) -> OptimizationResult:
    """LP/MILP optimization engine: minimizes total carbon intensity
    (material + energy + process carbon) subject to the scrap/virgin split,
    energy-mix, and grade-chemistry constraints. Returns status="INFEASIBLE"
    with a clear message if no feasible solution exists, or status="ERROR"
    if required reference data is missing - never a fabricated result. See
    backend/optimization/lp_optimizer.py for the full formulation."""
    return optimize_carbon_and_energy(payload)


@app.post("/sensitivity", response_model=SensitivityResult, tags=["analysis"])
def sensitivity_endpoint(payload: SensitivityInput) -> SensitivityResult:
    """Sensitivity analysis engine: sweeps scrap %, energy source, scrap
    quality, and grade one at a time (holding the other three at their
    baseline value) and returns carbon intensity plus a chemistry-feasibility
    flag for each point, the lowest-carbon feasible point per sweep, and an
    auto-generated insight derived from the actual computed values. See
    backend/services/sensitivity_analysis.py for the evaluation formula."""
    return run_sensitivity_analysis(payload)


@app.post("/scenarios", response_model=ScenarioRecord, tags=["scenarios"])
def create_scenario_endpoint(payload: ScenarioInput) -> ScenarioRecord:
    """Save a named scenario. Material CO2, Energy CO2, and Total CO2 are
    computed server-side from the scenario's fields via the same
    carbon_emissions engine used elsewhere - never trusted from the client.
    Persisted to backend/runtime/scenarios.json so it survives a restart."""
    return create_scenario(payload)


@app.get("/scenarios", response_model=ScenarioListResponse, tags=["scenarios"])
def list_scenarios_endpoint() -> ScenarioListResponse:
    """List all saved scenarios, for the Scenario Comparison page."""
    return ScenarioListResponse(scenarios=list_scenarios())


@app.delete("/scenarios/{scenario_id}", tags=["scenarios"])
def delete_scenario_endpoint(scenario_id: str) -> dict:
    """Delete a saved scenario by id."""
    deleted = delete_scenario(scenario_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No scenario found with id '{scenario_id}'.")
    return {"deleted": True, "id": scenario_id}


@app.post("/uncertainty", response_model=UncertaintyResult, tags=["analysis"])
def uncertainty_endpoint(payload: UncertaintyInput) -> UncertaintyResult:
    """Uncertainty analysis: Best/Base/Worst case plus an optional Monte
    Carlo simulation (default 1000 draws) across five uncertain categories
    (emission factors, scrap composition, yield, alloy recovery, energy
    consumption). Represents MODEL uncertainty from assumed ranges, not
    measurement uncertainty from real plant data - see
    backend/services/uncertainty_analysis.py and the response's
    interpretation_note."""
    return run_uncertainty_analysis(payload)


@app.post("/report/pdf", tags=["report"])
def report_pdf_endpoint(payload: ReportInput) -> Response:
    """Generates a full PDF report ('JSL GreenSteel Carbon Optimization
    Report') by running material balance, scrap chemistry, carbon
    emissions, the LP/MILP optimizer, sensitivity analysis, and validation
    against the given configuration, then rendering all of it - including
    charts - into a single downloadable PDF. See
    backend/services/report_generator.py for the full assembly."""
    pdf_bytes = generate_report_pdf(payload)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="jsl-greensteel-carbon-optimization-report.pdf"'},
    )


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "service": "JSL GreenSteel - Carbon & Energy Optimization Calculator",
        "status": "foundation build",
        "docs": "/docs",
    }
