import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import KpiCard from "../components/KpiCard";
import CarbonIntensityGauge from "../charts/CarbonIntensityGauge";
import EmissionBreakdownDonutChart from "../charts/EmissionBreakdownDonutChart";
import MaterialEmissionBarChart from "../charts/MaterialEmissionBarChart";
import CarbonComparisonChart from "../charts/CarbonComparisonChart";
import SensitivityBarChart from "../charts/SensitivityBarChart";
import {
  ApiError,
  calculateCarbonEmissions,
  createScenario,
  fetchReferenceData,
  generateReportPdf,
  runOptimization,
  runSensitivityAnalysis,
  runValidation,
} from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { CarbonEmissionResult, OptimizationResult, SensitivityResult, ValidationReport } from "../types/calculator";
import { formatNumber } from "../utils/format";

const GJ_PER_MWH = 3.6;

export default function ExecutiveDashboardPage() {
  const navigate = useNavigate();
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // --- Scenario inputs (LEFT panel) ---
  const [gradeId, setGradeId] = useState("");
  const [scrapPct, setScrapPct] = useState(65);
  const [scrapQualityId, setScrapQualityId] = useState("");
  const [energySourceId, setEnergySourceId] = useState("GRID_ELECTRICITY_IN");
  const [electricityConsumption, setElectricityConsumption] = useState(0.55);
  const [naturalGasConsumption, setNaturalGasConsumption] = useState(0.9);
  const [coalConsumption, setCoalConsumption] = useState(0.1);
  const [yieldPct, setYieldPct] = useState(92);
  const [scenarioName, setScenarioName] = useState("");

  // --- Results ---
  const [calcResult, setCalcResult] = useState<CarbonEmissionResult | null>(null);
  const [optResult, setOptResult] = useState<OptimizationResult | null>(null);
  const [sensResult, setSensResult] = useState<SensitivityResult | null>(null);
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);

  const [calculating, setCalculating] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchReferenceData()
      .then((res) => {
        setRefData(res.data);
        setGradeId(res.data.steel_grades.grades[0]?.id ?? "");
        setScrapQualityId(res.data.scrap_quality.categories[0]?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load reference data."));
  }, []);

  const virginPct = 100 - scrapPct;
  const yieldFraction = yieldPct / 100;
  const yieldValid = yieldFraction > 0 && yieldFraction <= 1;
  const chargeMass = yieldValid ? 1 / yieldFraction : null;
  const scrapMass = chargeMass != null ? (scrapPct / 100) * chargeMass : null;
  const virginMass = chargeMass != null ? (virginPct / 100) * chargeMass : null;
  const energyDemandMwhEquivalent = electricityConsumption + (naturalGasConsumption + coalConsumption) / GJ_PER_MWH;

  async function handleCalculate() {
    if (!yieldValid || scrapMass == null || virginMass == null) return;
    setCalculating(true);
    setError(null);
    try {
      const [emissions, validation, sensitivity] = await Promise.all([
        calculateCarbonEmissions({
          materials: [
            { material_id: "SCRAP_EMBODIED", quantity_t: scrapMass, label: "Scrap" },
            { material_id: "VIRGIN_EMBODIED", quantity_t: virginMass, label: "Virgin iron" },
          ],
          electricity_consumption_mwh_per_t: electricityConsumption,
          electricity_mix: [],
          electricity_source_id: energySourceId,
          natural_gas_consumption_gj_per_t: naturalGasConsumption,
          coal_consumption_gj_per_t: coalConsumption,
        }),
        runValidation({
          material: { scrap_percentage: scrapPct, yield: yieldFraction },
          carbon_emission: {
            materials: [],
            electricity_consumption_mwh_per_t: electricityConsumption,
            electricity_mix: [],
            electricity_source_id: energySourceId,
            natural_gas_consumption_gj_per_t: naturalGasConsumption,
            coal_consumption_gj_per_t: coalConsumption,
          },
        }),
        runSensitivityAnalysis({
          grade_id: gradeId,
          scrap_quality_id: scrapQualityId,
          scrap_pct: scrapPct,
          energy_source_id: energySourceId,
          yield: yieldFraction,
          energy_demand_mwh_equivalent_per_t: energyDemandMwhEquivalent || 0.1,
        }),
      ]);
      setCalcResult(emissions);
      setValidationReport(validation);
      setSensResult(sensitivity);
    } catch (err) {
      setError(err instanceof ApiError ? (typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail)) : "Could not reach the calculation service.");
    } finally {
      setCalculating(false);
    }
  }

  async function handleOptimize() {
    if (!yieldValid) return;
    setOptimizing(true);
    setError(null);
    try {
      const res = await runOptimization({
        grade_id: gradeId,
        scrap_quality_id: scrapQualityId,
        yield: yieldFraction,
        scrap_pct_min: 0,
        scrap_pct_max: 95,
        energy_demand_mwh_equivalent_per_t: energyDemandMwhEquivalent || 0.1,
        allow_energy_blending: true,
        energy_capacity_pct: {},
        current_scrap_pct: scrapPct,
        current_energy_mix_pct: { [energySourceId]: 100 },
      });
      setOptResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? (typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail)) : "Could not reach the optimization service.");
    } finally {
      setOptimizing(false);
    }
  }

  async function handleSaveScenario() {
    if (!scenarioName.trim()) {
      setError("Give the scenario a name before saving.");
      return;
    }
    setSaving(true);
    setError(null);
    setSaveMessage(null);
    try {
      const record = await createScenario({
        name: scenarioName.trim(),
        grade_id: gradeId,
        scrap_pct: scrapPct,
        scrap_quality_id: scrapQualityId,
        energy_source_id: energySourceId,
        electricity_consumption_mwh_per_t: electricityConsumption,
        natural_gas_consumption_gj_per_t: naturalGasConsumption,
        coal_consumption_gj_per_t: coalConsumption,
        yield: yieldFraction,
      });
      setSaveMessage(`Saved "${record.name}" (${formatNumber(record.total_co2_tco2e_per_t, 3)} tCO2e/tSS).`);
      setScenarioName("");
    } catch (err) {
      setError(err instanceof ApiError ? (typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail)) : "Could not save the scenario.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDownloadReport() {
    if (!yieldValid) {
      setError("Fix the yield value before generating a report.");
      return;
    }
    setDownloadingReport(true);
    setError(null);
    try {
      const blob = await generateReportPdf({
        scenario_name: scenarioName.trim() || "Untitled Scenario",
        grade_id: gradeId,
        scrap_quality_id: scrapQualityId,
        scrap_pct: scrapPct,
        energy_source_id: energySourceId,
        electricity_consumption_mwh_per_t: electricityConsumption,
        natural_gas_consumption_gj_per_t: naturalGasConsumption,
        coal_consumption_gj_per_t: coalConsumption,
        yield: yieldFraction,
        scrap_pct_min: 0,
        scrap_pct_max: 95,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "jsl-greensteel-carbon-optimization-report.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? typeof err.detail === "string"
            ? err.detail
            : JSON.stringify(err.detail)
          : "Could not generate the report."
      );
    } finally {
      setDownloadingReport(false);
    }
  }

  const donutSlices = useMemo(() => {
    if (!calcResult) return [];
    return [
      { name: "Material", value: calcResult.material_emissions.total_tco2e, color: "#4C82AA" },
      { name: "Electricity", value: calcResult.electricity_emissions.total_tco2e, color: "#DB8A2C" },
      { name: "Fuel", value: calcResult.fuel_emissions.total_tco2e, color: "#8A97A3" },
      { name: "Process", value: calcResult.process_emissions.tco2e_per_t, color: "#4C9A6A" },
    ];
  }, [calcResult]);

  const materialBars = useMemo(() => {
    if (!calcResult) return [];
    return calcResult.emission_breakdown_by_material.map((item) => ({
      label: item.label,
      tco2e: item.tco2e,
      factorAvailable: item.factor_available,
    }));
  }, [calcResult]);

  if (loadError) {
    return (
      <Panel title="Could not load reference data">
        <p className="text-sm text-warn-500">{loadError}</p>
      </Panel>
    );
  }

  if (!refData) {
    return <Panel title="Loading reference data…">Fetching grades, scrap quality, and energy sources.</Panel>;
  }

  const energyEmissionsTotal = calcResult ? calcResult.electricity_emissions.total_tco2e + calcResult.fuel_emissions.total_tco2e : null;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="border-b border-base-600 pb-4">
        <p className="text-[11px] uppercase tracking-wider text-steel-400">JSL GreenSteel</p>
        <h1 className="mt-0.5 text-xl font-semibold text-ink-100 sm:text-2xl">Carbon &amp; Energy Optimization Dashboard</h1>
        <p className="mt-1 text-[13px] italic text-ink-300">
          "Data-driven decision support for lower-carbon stainless steelmaking"
        </p>
      </div>

      {/* Top KPI cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Carbon Intensity"
          value={calcResult ? formatNumber(calcResult.carbon_intensity_tCO2e_per_tSS, 3) : "—"}
          unit="tCO2e / tSS"
          accent="steel"
        />
        <KpiCard label="Scrap Utilization" value={formatNumber(scrapPct, 1)} unit="%" />
        <KpiCard
          label="Energy Emissions"
          value={energyEmissionsTotal != null ? formatNumber(energyEmissionsTotal, 3) : "—"}
          unit="tCO2e / tSS"
        />
        <KpiCard
          label="Potential CO2 Reduction"
          value={optResult?.status === "OPTIMAL" ? formatNumber(optResult.percentage_reduction!, 1) : "—"}
          unit="%"
          accent="good"
        />
      </div>

      {/* Status indicators */}
      <div className="flex flex-wrap gap-2">
        <StatusPill label="Current Scenario" status={calcResult ? "PASS" : "PENDING"} text={calcResult ? "Calculated" : "Not calculated"} />
        <StatusPill
          label="Optimized Scenario"
          status={optResult ? (optResult.status === "OPTIMAL" ? "PASS" : "ERROR") : "PENDING"}
          text={optResult ? optResult.status : "Not run"}
        />
        <StatusPill
          label="Validation Status"
          status={validationReport ? validationReport.overall_status : "PENDING"}
          text={validationReport ? validationReport.overall_status : "Not run"}
        />
      </div>

      {/* Main layout: LEFT inputs / CENTER gauge / RIGHT recommendation */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="xl:col-span-4">
          <Panel title="Scenario inputs" action={<DemoDataBadge />}>
            <div className="space-y-3">
              <SelectField label="Grade" value={gradeId} onChange={setGradeId} options={refData.steel_grades.grades.map((g) => ({ id: g.id, name: g.grade_name }))} />
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-[12px] text-ink-300">Scrap %</span>
                  <span className="font-mono text-[12px] text-ink-100">{formatNumber(scrapPct, 1)}%</span>
                </div>
                <input type="range" min={0} max={100} step={0.5} value={scrapPct} onChange={(e) => setScrapPct(parseFloat(e.target.value))} className="w-full accent-steel-500" />
                <p className="mt-1 text-[11px] text-ink-400">Virgin: {formatNumber(virginPct, 1)}%</p>
              </div>
              <SelectField label="Scrap quality" value={scrapQualityId} onChange={setScrapQualityId} options={refData.scrap_quality.categories.map((c) => ({ id: c.id, name: c.category_name }))} />
              <SelectField
                label="Energy source"
                value={energySourceId}
                onChange={setEnergySourceId}
                options={refData.energy_sources.sources.map((s) => ({ id: s.id, name: s.name }))}
              />
              <NumberField label="Electricity (MWh/t)" value={electricityConsumption} onChange={setElectricityConsumption} step={0.01} />
              <NumberField label="Natural gas (GJ/t)" value={naturalGasConsumption} onChange={setNaturalGasConsumption} step={0.01} />
              <NumberField label="Coal (GJ/t)" value={coalConsumption} onChange={setCoalConsumption} step={0.01} />
              <NumberField label="Yield (%)" value={yieldPct} onChange={setYieldPct} step={0.5} />
            </div>
          </Panel>
        </div>

        <div className="flex flex-col items-center justify-center xl:col-span-4">
          <Panel title="Carbon intensity" className="w-full">
            <div className="flex justify-center py-2">
              <CarbonIntensityGauge value={calcResult?.carbon_intensity_tCO2e_per_tSS ?? 0} />
            </div>
          </Panel>
        </div>

        <div className="xl:col-span-4">
          <Panel title="Optimization recommendation">
            {!optResult && <p className="text-sm text-ink-400">Press Optimize to generate a recommendation.</p>}
            {optResult && optResult.status !== "OPTIMAL" && (
              <div className="rounded border border-warn-500/40 bg-warn-500/10 p-3">
                <p className="text-sm font-medium text-warn-500">{optResult.status === "INFEASIBLE" ? "No feasible solution" : "Error"}</p>
                <p className="mt-1 text-[12px] text-ink-300">{optResult.message}</p>
              </div>
            )}
            {optResult && optResult.status === "OPTIMAL" && (
              <div className="space-y-2 text-[13px]">
                <Row label="Optimal scrap %" value={`${formatNumber(optResult.optimal_scrap_percentage!, 1)}%`} />
                <Row
                  label="Top energy source"
                  value={[...optResult.optimal_energy_mix!].sort((a, b) => b.share_pct - a.share_pct)[0]?.label ?? "—"}
                />
                <Row label="CO2 saved" value={`${formatNumber(optResult.absolute_reduction!, 3)} tCO2e/tSS`} highlight />
                <Row label="Reduction" value={`${formatNumber(optResult.percentage_reduction!, 1)}%`} highlight />
              </div>
            )}
          </Panel>
        </div>
      </div>

      {/* Buttons */}
      <div className="flex flex-wrap gap-2">
        <ActionButton onClick={handleCalculate} disabled={calculating} primary>
          {calculating ? "Calculating…" : "Calculate"}
        </ActionButton>
        <ActionButton onClick={handleOptimize} disabled={optimizing}>
          {optimizing ? "Optimizing…" : "Optimize"}
        </ActionButton>
        <input
          type="text"
          value={scenarioName}
          onChange={(e) => setScenarioName(e.target.value)}
          placeholder="Scenario name"
          className="rounded border border-base-600 bg-base-800 px-2.5 py-1.5 text-[13px] text-ink-100 outline-none placeholder:text-ink-400 focus:border-steel-500"
        />
        <ActionButton onClick={handleSaveScenario} disabled={saving}>
          {saving ? "Saving…" : "Save Scenario"}
        </ActionButton>
        <ActionButton onClick={() => navigate("/scenarios")}>Compare</ActionButton>
        <ActionButton onClick={handleDownloadReport} disabled={downloadingReport}>
          {downloadingReport ? "Generating PDF…" : "Download Report"}
        </ActionButton>
      </div>
      {error && <p className="text-sm text-warn-500">{error}</p>}
      {saveMessage && <p className="text-sm text-good-500">{saveMessage}</p>}

      {/* Charts */}
      {calcResult && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Panel title="1. Emission breakdown" eyebrow="By category · tCO2e/tSS">
            <EmissionBreakdownDonutChart slices={donutSlices} centerLabel={formatNumber(calcResult.carbon_intensity_tCO2e_per_tSS, 2)} centerSubLabel="tCO2e/tSS" />
          </Panel>
          <Panel title="2. Material contribution" eyebrow="Scrap vs. virgin · tCO2e">
            <MaterialEmissionBarChart items={materialBars} />
          </Panel>
        </div>
      )}

      {optResult && optResult.status === "OPTIMAL" && (
        <Panel title="3. Current vs. optimized">
          <CarbonComparisonChart currentValue={optResult.current_carbon_intensity!} optimizedValue={optResult.optimized_carbon_intensity!} />
        </Panel>
      )}

      {sensResult && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Panel title="4. Scrap sensitivity" eyebrow={sensResult.scrap_percentage_sweep.baseline_note}>
            <SensitivityBarChart points={sensResult.scrap_percentage_sweep.points} />
            <p className="mt-3 rounded border border-base-600 bg-base-800 p-3 text-[12px] leading-relaxed text-ink-200">
              {sensResult.scrap_percentage_sweep.insight}
            </p>
          </Panel>
          <Panel title="5. Energy source comparison" eyebrow={sensResult.energy_source_sweep.baseline_note}>
            <SensitivityBarChart points={sensResult.energy_source_sweep.points} />
            <p className="mt-3 rounded border border-base-600 bg-base-800 p-3 text-[12px] leading-relaxed text-ink-200">
              {sensResult.energy_source_sweep.insight}
            </p>
          </Panel>
        </div>
      )}
    </div>
  );
}

function StatusPill({ label, status, text }: { label: string; status: string; text: string }) {
  const colorClass =
    status === "PASS"
      ? "border-good-500/40 bg-good-500/10 text-good-500"
      : status === "WARNING"
        ? "border-ember-500/40 bg-ember-500/10 text-ember-400"
        : status === "ERROR"
          ? "border-warn-500/40 bg-warn-500/10 text-warn-500"
          : "border-base-600 bg-base-800 text-ink-400";
  return (
    <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-[12px] ${colorClass}`}>
      <span className="font-medium">{label}:</span>
      <span>{text}</span>
    </div>
  );
}

function Row({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-400">{label}</span>
      <span className={`font-mono ${highlight ? "text-good-500" : "text-ink-100"}`}>{value}</span>
    </div>
  );
}

function ActionButton({
  children,
  onClick,
  disabled = false,
  primary = false,
}: {
  children: React.ReactNode;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-4 py-2 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400 ${
        primary ? "bg-steel-500 text-base-900 hover:bg-steel-400" : "border border-base-600 bg-base-800 text-ink-100 hover:bg-base-700"
      }`}
    >
      {children}
    </button>
  );
}

function NumberField({ label, value, onChange, step = 1 }: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] text-ink-300">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { id: string; name: string }[];
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] text-ink-300">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 text-[13px] text-ink-100 outline-none focus:border-steel-500"
      >
        {options.map((opt) => (
          <option key={opt.id} value={opt.id}>
            {opt.name}
          </option>
        ))}
      </select>
    </label>
  );
}
