import type {
  CarbonCalculationInput,
  CarbonCalculationResult,
  CarbonEmissionInput,
  CarbonEmissionResult,
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
  JslBenchmarkRecord,
  JslClimateTarget,
} from "../types/calculator";
import type {
  BaselineFile,
  EmissionFactorsFile,
  EnergySourcesFile,
  ReferenceDataResponse,
  ScrapQualityFile,
  SteelGradesFile,
} from "../types/referenceData";

// Vercel serves the FastAPI function under /api; local development uses the
// standalone backend unless an explicit API URL is provided.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://localhost:8000" : "/api");

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `API error (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail: unknown;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export function fetchHealth() {
  return request<{ status: string; service: string; data_status: string }>("/health");
}

export function fetchReferenceData() {
  return request<ReferenceDataResponse>("/reference-data");
}

// Per-file endpoints, in case a page only needs one slice of reference data.
export function fetchSteelGrades() {
  return request<SteelGradesFile>("/reference-data/steel-grades");
}

export function fetchScrapQuality() {
  return request<ScrapQualityFile>("/reference-data/scrap-quality");
}

export function fetchEnergySources() {
  return request<EnergySourcesFile>("/reference-data/energy-sources");
}

export function fetchEmissionFactors() {
  return request<EmissionFactorsFile>("/reference-data/emission-factors");
}

export function fetchBaseline() {
  return request<BaselineFile>("/reference-data/baseline");
}

export function fetchJslBenchmarks() {
  return request<{ records: JslBenchmarkRecord[] }>("/reference-data/jsl-benchmarks");
}

export function fetchJslClimateTargets() {
  return request<{ records: JslClimateTarget[] }>("/reference-data/jsl-climate-targets");
}

export function calculateCarbon(payload: CarbonCalculationInput) {
  return request<CarbonCalculationResult>("/calculate/carbon", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateMaterialBalance(payload: MaterialBalanceInput) {
  return request<MaterialBalanceResult>("/calculate/material-balance", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateScrapChemistry(payload: ScrapChemistryInput) {
  return request<ScrapChemistryResult>("/calculate/scrap-chemistry", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function calculateCarbonEmissions(payload: CarbonEmissionInput) {
  return request<CarbonEmissionResult>("/calculate/emissions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runValidation(payload: ValidationRequest) {
  return request<ValidationReport>("/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runOptimization(payload: OptimizationInput) {
  return request<OptimizationResult>("/optimize", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runSensitivityAnalysis(payload: SensitivityInput) {
  return request<SensitivityResult>("/sensitivity", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createScenario(payload: ScenarioInput) {
  return request<ScenarioRecord>("/scenarios", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchScenarios() {
  return request<ScenarioListResponse>("/scenarios");
}

export function deleteScenario(scenarioId: string) {
  return request<{ deleted: boolean; id: string }>(`/scenarios/${scenarioId}`, {
    method: "DELETE",
  });
}

export function runUncertaintyAnalysis(payload: UncertaintyInput) {
  return request<UncertaintyResult>("/uncertainty", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Generates the PDF report. Unlike every other call in this file, the
 * response is a binary PDF, not JSON - so this bypasses the generic
 * `request` helper and returns a Blob the caller can turn into a download.
 */
export async function generateReportPdf(payload: ReportInput): Promise<Blob> {
  const res = await fetch(`${API_BASE_URL}/report/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let detail: unknown;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }

  return res.blob();
}
