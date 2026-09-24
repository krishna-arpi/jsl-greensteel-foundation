// Types mirror backend/models/schemas.py. Keep in sync manually for now
// (a generated client is future scope).

export interface AlloyAdditions {
  values_kg_per_t: Record<string, number>;
}

export interface CarbonCalculationInput {
  scrap_pct: number;
  virgin_material_pct: number;
  grade_id: string;
  scrap_quality_id: string;
  electricity_source_id: string;
  electricity_consumption_mwh_per_t: number;
  fuel_source_id: string;
  fuel_consumption_gj_per_t: number;
  process_route_id: string;
  alloy_additions: AlloyAdditions;
}

export interface EmissionBreakdownItem {
  category: string;
  label: string;
  tco2e_per_t: number;
  is_placeholder: boolean;
  note?: string | null;
}

export interface CarbonCalculationResult {
  status: string;
  warning: string;
  total_tco2e_per_t: number;
  breakdown: EmissionBreakdownItem[];
  input_echo: CarbonCalculationInput;
}

export interface ApiValidationIssue {
  field: string;
  message: string;
  severity: "warning" | "error";
}

// --- Material balance ------------------------------------------------------
// Mirrors backend/models/schemas.py MaterialBalanceInput / MaterialBalanceResult.
// Mass accounting only - no emissions fields here by design.

export interface MaterialBalanceInput {
  scrap_percentage: number;
  yield: number; // fraction, 0 < yield <= 1
}

export interface MaterialBalanceValidationStatus {
  mix_sums_to_100: boolean;
  mass_balance_closes: boolean;
  no_negative_mass: boolean;
  overall: "PASS" | "FAIL";
}

export interface MaterialBalanceResult {
  charge_mass: number;
  scrap_mass: number;
  virgin_mass: number;
  scrap_percentage: number;
  virgin_percentage: number;
  yield: number;
  validation_status: MaterialBalanceValidationStatus;
}

// --- Scrap chemistry ---------------------------------------------------------
// Mirrors backend/models/schemas.py Scrap*/ChemistryValidation models.
// Composition accounting only - no emissions fields here by design.

export interface ScrapChemistryInput {
  scrap_quality_id: string;
  scrap_mass: number; // t, e.g. from MaterialBalanceResult.scrap_mass
  grade_id: string;
}

export interface ScrapChemistryEcho {
  scrap_quality_id: string;
  category_name: string;
  status: string;
  Cr_pct: number;
  Ni_pct: number;
  Mo_pct: number;
  Fe_pct: number;
  C_pct: number;
  Si_pct: number;
  Mn_pct: number;
  N_pct: number;
  yield_pct: number;
  alloy_recovery_pct: number;
  source: string;
}

export interface ElementContribution {
  Cr_from_scrap: number;
  Ni_from_scrap: number;
  Mo_from_scrap: number;
  Fe_from_scrap: number;
  C_from_scrap: number;
  Si_from_scrap: number;
  Mn_from_scrap: number;
  N_from_scrap: number;
}

export interface ElementDeficit {
  element: string;
  required_mass: number;
  supplied_mass: number;
  deficit_mass: number;
}

export interface AlloyAdditionRequired {
  element: string;
  alloy_id: string;
  alloy_name: string;
  concentration_pct: number;
  recovery_pct: number;
  required_mass_t: number;
  required_mass_kg: number;
}

export interface FinalElementChemistry {
  element: string;
  mass_t: number;
  pct: number;
}

export interface ChemistryValidationItem {
  element: string;
  min_required_pct: number | null;
  max_allowed_pct: number | null;
  actual_pct: number;
  status: "PASS" | "FAIL";
}

export interface ChemistryValidation {
  items: ChemistryValidationItem[];
  overall: "PASS" | "FAIL";
}

export interface ScrapChemistryResult {
  status: string;
  warning: string;
  grade_id: string;
  scrap_chemistry: ScrapChemistryEcho;
  element_contribution: ElementContribution;
  element_deficits: ElementDeficit[];
  alloy_additions: AlloyAdditionRequired[];
  final_chemistry: FinalElementChemistry[];
  chemistry_validation: ChemistryValidation;
}

// --- Complete carbon-emission engine ----------------------------------------
// Mirrors backend/models/schemas.py Carbon*/Material*/Electricity*/Fuel*/Process*
// models. Never fabricates a missing factor - see factor_available/notes and
// missing_factor_warnings below.

export interface MaterialQuantityInput {
  material_id: string;
  quantity_t: number;
  label?: string;
}

export interface ElectricityMixComponentInput {
  source_id: string;
  share_pct: number;
}

export interface CarbonEmissionInput {
  materials: MaterialQuantityInput[];
  electricity_consumption_mwh_per_t: number;
  electricity_mix: ElectricityMixComponentInput[];
  electricity_source_id?: string;
  natural_gas_consumption_gj_per_t: number;
  coal_consumption_gj_per_t: number;
  process_route_id?: string;
  process_emission_override_tco2e_per_t?: number;
}

export interface MaterialEmissionItem {
  material_id: string;
  label: string;
  quantity_t: number;
  emission_factor_tco2e_per_t: number | null;
  tco2e: number;
  factor_available: boolean;
  note: string | null;
}

export interface MaterialEmissions {
  total_tco2e: number;
  items: MaterialEmissionItem[];
}

export interface ElectricityMixItemResult {
  source_id: string;
  label: string;
  share_pct: number;
  emission_factor_tco2e_per_mwh: number | null;
  factor_available: boolean;
  note: string | null;
}

export interface ElectricityEmissions {
  total_tco2e: number;
  consumption_mwh_per_t: number;
  mix: ElectricityMixItemResult[];
  effective_emission_factor_tco2e_per_mwh: number | null;
}

export interface FuelEmissionItem {
  fuel_id: string;
  label: string;
  consumption_gj_per_t: number;
  emission_factor_tco2e_per_gj: number | null;
  tco2e: number;
  factor_available: boolean;
  note: string | null;
}

export interface FuelEmissions {
  total_tco2e: number;
  natural_gas: FuelEmissionItem;
  coal: FuelEmissionItem;
}

export interface ProcessEmissions {
  tco2e_per_t: number;
  source: "override" | "process_route" | "not_configured";
  process_route_id: string | null;
  factor_available: boolean;
  note: string | null;
}

export interface CarbonEmissionResult {
  status: string;
  warning: string;
  carbon_intensity_tCO2e_per_tSS: number;
  carbon_intensity_kgCO2e_per_tSS: number;
  material_emissions: MaterialEmissions;
  electricity_emissions: ElectricityEmissions;
  fuel_emissions: FuelEmissions;
  process_emissions: ProcessEmissions;
  emission_breakdown_by_material: MaterialEmissionItem[];
  missing_factor_warnings: string[];
}

// --- Validation engine -------------------------------------------------------
// Mirrors backend/models/schemas.py Validation* models. Runs the 12 required
// checks across whichever domains are supplied; a domain's checks are simply
// absent from the report when its inputs aren't supplied (no 4th status).

export interface ValidationMaterialInput {
  scrap_percentage: number;
  virgin_percentage?: number;
  yield: number;
}

export interface ValidationRequest {
  material?: ValidationMaterialInput;
  scrap_chemistry?: ScrapChemistryInput;
  carbon_emission?: CarbonEmissionInput;
}

export interface ValidationCheckResult {
  check_id: number;
  name: string;
  status: "PASS" | "WARNING" | "ERROR";
  message: string;
  details: Record<string, unknown> | null;
}

export interface ValidationReport {
  overall_status: "PASS" | "WARNING" | "ERROR";
  blocked: boolean;
  summary: string;
  checks: ValidationCheckResult[];
}

// --- Optimization engine (LP/MILP) ------------------------------------------
// Mirrors backend/models/schemas.py Optimization* models.

export interface OptimizationInput {
  grade_id: string;
  scrap_quality_id: string;
  yield: number;
  scrap_pct_min: number;
  scrap_pct_max: number;
  energy_demand_mwh_equivalent_per_t: number;
  allow_energy_blending: boolean;
  energy_capacity_pct: Record<string, number>;
  scrap_availability_t?: number;
  process_route_id?: string;
  process_emission_override_tco2e_per_t?: number;
  current_scrap_pct: number;
  current_energy_mix_pct: Record<string, number>;
}

export interface EnergyMixShareResult {
  source_id: string;
  label: string;
  share_pct: number;
}

export interface AlloyAdditionOptimalResult {
  element: string;
  alloy_id: string;
  alloy_name: string;
  required_mass_kg: number;
}

export interface BindingConstraintResult {
  name: string;
  description: string;
}

export interface OptimizationResult {
  status: "OPTIMAL" | "INFEASIBLE" | "ERROR";
  message: string;
  warning: string;
  optimal_scrap_percentage: number | null;
  optimal_virgin_percentage: number | null;
  optimal_energy_mix: EnergyMixShareResult[] | null;
  optimal_alloy_additions: AlloyAdditionOptimalResult[] | null;
  optimized_carbon_intensity: number | null;
  current_carbon_intensity: number | null;
  absolute_reduction: number | null;
  percentage_reduction: number | null;
  current_scenario_chemistry_valid: boolean | null;
  current_scenario_chemistry_note: string | null;
  binding_constraints: BindingConstraintResult[];
}

export interface JslBenchmarkRecord {
  financial_year: string;
  parameter: string;
  value: number;
  unit: string;
  scope: string;
  source: string;
  source_url: string;
  data_type: "Official JSL Reported Data";
}

export interface JslClimateTarget {
  target_id: string;
  baseline_year: string;
  baseline_intensity: number;
  baseline_unit: string;
  target_year: string;
  target_reduction_percent: number;
  derived_target_intensity: number;
  target_description: string;
  source: string;
  source_url: string[];
  data_type: "Model-Derived Target";
}

// --- Sensitivity analysis ---------------------------------------------------
// Mirrors backend/models/schemas.py Sensitivity* models.

export interface SensitivityInput {
  grade_id: string;
  scrap_quality_id: string;
  scrap_pct: number;
  energy_source_id: string;
  yield: number;
  energy_demand_mwh_equivalent_per_t: number;
  process_route_id?: string;
  process_emission_override_tco2e_per_t?: number;
}

export interface SensitivityPoint {
  label: string;
  value_id: string;
  carbon_intensity_tco2e_per_t: number;
  chemistry_valid: boolean;
  is_lowest_feasible: boolean;
}

export interface SensitivitySweep {
  dimension: string;
  baseline_note: string;
  points: SensitivityPoint[];
  insight: string;
}

export interface SensitivityResult {
  status: string;
  warning: string;
  scrap_percentage_sweep: SensitivitySweep;
  energy_source_sweep: SensitivitySweep;
  scrap_quality_sweep: SensitivitySweep;
  grade_sweep: SensitivitySweep;
}

// --- Scenario comparison ------------------------------------------------------
// Mirrors backend/models/schemas.py Scenario* models.

export interface ScenarioInput {
  name: string;
  grade_id: string;
  scrap_pct: number;
  scrap_quality_id: string;
  energy_source_id: string;
  electricity_consumption_mwh_per_t: number;
  natural_gas_consumption_gj_per_t: number;
  coal_consumption_gj_per_t: number;
  yield: number;
}

export interface ScenarioRecord extends ScenarioInput {
  id: string;
  created_at: string;
  grade_name: string;
  scrap_quality_name: string;
  energy_source_name: string;
  material_co2_tco2e_per_t: number;
  energy_co2_tco2e_per_t: number;
  total_co2_tco2e_per_t: number;
}

export interface ScenarioListResponse {
  scenarios: ScenarioRecord[];
}

// --- Uncertainty analysis ------------------------------------------------------
// Mirrors backend/models/schemas.py Uncertainty*/MonteCarlo*/HistogramBin models.

export interface UncertaintyInput {
  grade_id: string;
  scrap_quality_id: string;
  scrap_pct: number;
  energy_source_id: string;
  yield: number;
  energy_demand_mwh_equivalent_per_t: number;
  process_route_id?: string;
  process_emission_override_tco2e_per_t?: number;
  emission_factor_uncertainty_pct: number;
  scrap_composition_uncertainty_pct: number;
  yield_uncertainty_pct: number;
  alloy_recovery_uncertainty_pct: number;
  energy_consumption_uncertainty_pct: number;
  run_monte_carlo: boolean;
  n_simulations: number;
  random_seed?: number;
}

export interface ScenarioCaseResult {
  label: string;
  carbon_intensity_tco2e_per_t: number;
}

export interface HistogramBin {
  bin_start: number;
  bin_end: number;
  count: number;
}

export interface MonteCarloResult {
  n_simulations: number;
  mean_tco2e_per_t: number;
  median_tco2e_per_t: number;
  min_tco2e_per_t: number;
  max_tco2e_per_t: number;
  p5_tco2e_per_t: number;
  p95_tco2e_per_t: number;
  histogram: HistogramBin[];
}

export interface UncertaintyRangesUsed {
  emission_factor_uncertainty_pct: number;
  scrap_composition_uncertainty_pct: number;
  yield_uncertainty_pct: number;
  alloy_recovery_uncertainty_pct: number;
  energy_consumption_uncertainty_pct: number;
}

export interface UncertaintyResult {
  status: string;
  warning: string;
  interpretation_note: string;
  uncertainty_ranges_used: UncertaintyRangesUsed;
  best_case: ScenarioCaseResult;
  base_case: ScenarioCaseResult;
  worst_case: ScenarioCaseResult;
  monte_carlo: MonteCarloResult | null;
}

// --- PDF report ------------------------------------------------------------
// Mirrors backend/models/schemas.py ReportInput.

export interface ReportInput {
  scenario_name: string;
  grade_id: string;
  scrap_quality_id: string;
  scrap_pct: number;
  energy_source_id: string;
  electricity_consumption_mwh_per_t: number;
  natural_gas_consumption_gj_per_t: number;
  coal_consumption_gj_per_t: number;
  yield: number;
  scrap_pct_min: number;
  scrap_pct_max: number;
}
