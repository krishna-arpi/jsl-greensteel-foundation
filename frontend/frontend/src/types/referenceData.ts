// Mirrors the shape of /data/*.json as returned by GET /reference-data and
// its per-file endpoints. All of this data is DEMO_PLACEHOLDER unless a
// record's own status/confidence fields say otherwise (see baseline's
// corporate_benchmark, which is a stated figure, not a placeholder).

export interface DataMeta {
  status: string;
  warning?: string;
  [key: string]: unknown;
}

// --- Emission factors -------------------------------------------------

export interface EmissionFactor {
  name: string;
  value: number;
  unit: string;
  year: number | null;
  geography: string;
  boundary: string;
  scope: string;
  source: string;
  confidence: string;
  notes?: string | null;
}

export interface EmissionFactorEntry extends EmissionFactor {
  id: string;
  category: "electricity" | "fuel" | "process_route" | "alloy_addition" | "material_mix" | string;
}

export interface EmissionFactorsFile {
  _meta: DataMeta;
  factors: EmissionFactorEntry[];
}

// --- Steel grades -------------------------------------------------------

export interface SteelGrade {
  id: string;
  grade_name: string;
  family: string;
  status: string;
  Cr_min: number;
  Cr_max: number;
  Ni_min: number;
  Ni_max: number;
  Mo_min: number;
  Mo_max: number;
  C_max: number;
  Si_max: number;
  Mn_max: number;
  N_max: number | null;
  source: string;
}

export interface SteelGradesFile {
  _meta: DataMeta;
  grades: SteelGrade[];
}

// --- Scrap quality --------------------------------------------------------

export interface ScrapQualityCategory {
  id: string;
  category_name: "High Quality" | "Medium Quality" | "Low Quality" | string;
  status: string;
  description: string;
  Cr: number;
  Ni: number;
  Mo: number;
  Fe: number;
  C: number;
  Si: number;
  Mn: number;
  N: number;
  yield: number;
  alloy_recovery: number;
  source: string;
}

export interface ScrapQualityFile {
  _meta: DataMeta;
  categories: ScrapQualityCategory[];
}

// --- Energy sources -------------------------------------------------------

export interface EnergySource {
  id: string;
  name: string;
  type: "electricity" | "fuel";
  description: string;
  emission_factor: EmissionFactor;
}

export interface ProcessRouteOption {
  id: string;
  name: string;
}

export interface EnergySourcesFile {
  _meta: DataMeta;
  sources: EnergySource[];
  process_routes: ProcessRouteOption[];
}

// --- Baseline ---------------------------------------------------------------

export interface BaselineScopeFigure {
  value: number;
  unit: string;
  boundary: string;
  source: string;
  confidence: string;
}

export interface BaselineDerivedTotal {
  value: number;
  unit: string;
  derivation: string;
  note: string;
}

export interface CorporateBenchmark {
  label: string;
  company: string;
  fiscal_year: string;
  unit: string;
  unit_expanded: string;
  scope_1_plus_2: BaselineScopeFigure;
  scope_3: BaselineScopeFigure;
  derived_reference_total: BaselineDerivedTotal;
}

export interface DemoScenario {
  _status: string;
  scenario_name: string;
  note: string;
  inputs: Record<string, unknown>;
  source: string;
}

export interface BaselineFile {
  _meta: DataMeta;
  corporate_benchmark: CorporateBenchmark;
  demo_scenario: DemoScenario;
}

// --- Bundle ---------------------------------------------------------------

export interface ReferenceDataBundle {
  emission_factors: EmissionFactorsFile;
  steel_grades: SteelGradesFile;
  scrap_quality: ScrapQualityFile;
  energy_sources: EnergySourcesFile;
  baseline: BaselineFile;
}

export interface ReferenceDataResponse {
  data: ReferenceDataBundle;
  validation_issues: { field: string; message: string; severity: string }[];
}
