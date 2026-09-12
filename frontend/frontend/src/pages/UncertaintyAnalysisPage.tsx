import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import KpiCard from "../components/KpiCard";
import UncertaintyHistogramChart from "../charts/UncertaintyHistogramChart";
import { ApiError, fetchReferenceData, runUncertaintyAnalysis } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { UncertaintyResult } from "../types/calculator";
import { formatNumber } from "../utils/format";

export default function UncertaintyAnalysisPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [gradeId, setGradeId] = useState("");
  const [scrapQualityId, setScrapQualityId] = useState("");
  const [scrapPct, setScrapPct] = useState(65);
  const [energySourceId, setEnergySourceId] = useState("GRID_ELECTRICITY_IN");
  const [yieldPct, setYieldPct] = useState(92);
  const [energyDemand, setEnergyDemand] = useState(1.0);

  const [efPct, setEfPct] = useState(15);
  const [compPct, setCompPct] = useState(10);
  const [yieldUncertaintyPct, setYieldUncertaintyPct] = useState(3);
  const [recoveryPct, setRecoveryPct] = useState(5);
  const [energyUncertaintyPct, setEnergyUncertaintyPct] = useState(10);

  const [runMonteCarlo, setRunMonteCarlo] = useState(true);
  const [nSimulations, setNSimulations] = useState(1000);

  const [result, setResult] = useState<UncertaintyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    fetchReferenceData()
      .then((res) => {
        setRefData(res.data);
        setGradeId(res.data.steel_grades.grades[0]?.id ?? "");
        setScrapQualityId(res.data.scrap_quality.categories[0]?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load reference data."));
  }, []);

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      const res = await runUncertaintyAnalysis({
        grade_id: gradeId,
        scrap_quality_id: scrapQualityId,
        scrap_pct: scrapPct,
        energy_source_id: energySourceId,
        yield: yieldPct / 100,
        energy_demand_mwh_equivalent_per_t: energyDemand,
        emission_factor_uncertainty_pct: efPct,
        scrap_composition_uncertainty_pct: compPct,
        yield_uncertainty_pct: yieldUncertaintyPct,
        alloy_recovery_uncertainty_pct: recoveryPct,
        energy_consumption_uncertainty_pct: energyUncertaintyPct,
        run_monte_carlo: runMonteCarlo,
        n_simulations: nSimulations,
      });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      } else {
        setError("Could not reach the uncertainty analysis service.");
      }
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

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

  return (
    <div className="space-y-5">
      <div className="border-b border-base-600 pb-4">
        <p className="text-[11px] uppercase tracking-wider text-steel-400">JSL GreenSteel</p>
        <h1 className="mt-0.5 text-xl font-semibold text-ink-100 sm:text-2xl">Uncertainty Analysis</h1>
        <p className="mt-1 text-[13px] text-ink-300">
          Explores how much carbon intensity could plausibly move given assumed ranges on emission factors,
          scrap composition, yield, alloy recovery, and energy consumption.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-4 xl:col-span-3">
          <Panel title="Baseline configuration" action={<DemoDataBadge />}>
            <div className="space-y-3">
              <SelectField
                label="Grade"
                value={gradeId}
                onChange={setGradeId}
                options={refData.steel_grades.grades.map((g) => ({ id: g.id, name: g.grade_name }))}
              />
              <SelectField
                label="Scrap quality"
                value={scrapQualityId}
                onChange={setScrapQualityId}
                options={refData.scrap_quality.categories.map((c) => ({ id: c.id, name: c.category_name }))}
              />
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-[12px] text-ink-300">Scrap % (fixed, not uncertain)</span>
                  <span className="font-mono text-[12px] text-ink-100">{formatNumber(scrapPct, 1)}%</span>
                </div>
                <input type="range" min={0} max={100} step={1} value={scrapPct} onChange={(e) => setScrapPct(parseFloat(e.target.value))} className="w-full accent-steel-500" />
              </div>
              <SelectField
                label="Energy source"
                value={energySourceId}
                onChange={setEnergySourceId}
                options={refData.energy_sources.sources.map((s) => ({ id: s.id, name: s.name }))}
              />
              <NumberField label="Yield (%, nominal)" value={yieldPct} onChange={setYieldPct} step={0.5} />
              <NumberField label="Energy demand (MWh-equiv/t, nominal)" value={energyDemand} onChange={setEnergyDemand} step={0.05} />
            </div>
          </Panel>

          <Panel title="Uncertainty ranges" eyebrow="Assumed +/- spread around nominal values">
            <div className="space-y-3">
              <NumberField label="Emission factors (%)" value={efPct} onChange={setEfPct} step={1} />
              <NumberField label="Scrap composition (%)" value={compPct} onChange={setCompPct} step={1} />
              <NumberField label="Yield (%)" value={yieldUncertaintyPct} onChange={setYieldUncertaintyPct} step={0.5} />
              <NumberField label="Alloy recovery (%)" value={recoveryPct} onChange={setRecoveryPct} step={1} />
              <NumberField label="Energy consumption (%)" value={energyUncertaintyPct} onChange={setEnergyUncertaintyPct} step={1} />
            </div>
          </Panel>

          <Panel title="Monte Carlo">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={runMonteCarlo} onChange={(e) => setRunMonteCarlo(e.target.checked)} className="accent-steel-500" />
              <span className="text-[12px] text-ink-300">Run Monte Carlo simulation</span>
            </label>
            {runMonteCarlo && (
              <div className="mt-3">
                <NumberField label="Number of simulations" value={nSimulations} onChange={setNSimulations} step={100} />
              </div>
            )}
            <button
              onClick={handleRun}
              disabled={running}
              className="mt-4 w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
            >
              {running ? "Running…" : "Run uncertainty analysis"}
            </button>
            {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
          </Panel>
        </div>

        <div className="space-y-4 lg:col-span-8 xl:col-span-9">
          {!result && (
            <Panel title="Result">
              <p className="text-sm text-ink-400">Run the analysis to see Best/Base/Worst case and the distribution here.</p>
            </Panel>
          )}

          {result && (
            <>
              <Panel title="Model uncertainty, not measurement uncertainty" eyebrow="Read this before interpreting anything below">
                <p className="text-[13px] leading-relaxed text-ink-200">{result.interpretation_note}</p>
              </Panel>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <KpiCard label="Best Case" value={formatNumber(result.best_case.carbon_intensity_tco2e_per_t, 3)} unit="tCO2e / tSS" accent="good" />
                <KpiCard label="Base Case" value={formatNumber(result.base_case.carbon_intensity_tco2e_per_t, 3)} unit="tCO2e / tSS" accent="steel" />
                <KpiCard label="Worst Case" value={formatNumber(result.worst_case.carbon_intensity_tco2e_per_t, 3)} unit="tCO2e / tSS" accent="ember" />
              </div>

              {result.monte_carlo && (
                <>
                  <Panel title="Carbon intensity distribution" eyebrow={`${result.monte_carlo.n_simulations} Monte Carlo simulations`}>
                    <UncertaintyHistogramChart
                      histogram={result.monte_carlo.histogram}
                      mean={result.monte_carlo.mean_tco2e_per_t}
                      p5={result.monte_carlo.p5_tco2e_per_t}
                      p95={result.monte_carlo.p95_tco2e_per_t}
                    />
                  </Panel>

                  <Panel title="Distribution summary">
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                      <MiniStat label="Mean" value={result.monte_carlo.mean_tco2e_per_t} highlight />
                      <MiniStat label="Median" value={result.monte_carlo.median_tco2e_per_t} />
                      <MiniStat label="Min" value={result.monte_carlo.min_tco2e_per_t} />
                      <MiniStat label="Max" value={result.monte_carlo.max_tco2e_per_t} />
                      <MiniStat label="P5" value={result.monte_carlo.p5_tco2e_per_t} highlight />
                      <MiniStat label="P95" value={result.monte_carlo.p95_tco2e_per_t} highlight />
                    </div>
                    <p className="mt-3 text-[12px] text-ink-300">
                      P5–P95 range:{" "}
                      <span className="font-mono text-ink-100">
                        {formatNumber(result.monte_carlo.p5_tco2e_per_t, 3)} – {formatNumber(result.monte_carlo.p95_tco2e_per_t, 3)} tCO2e/tSS
                      </span>
                    </p>
                  </Panel>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, highlight = false }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-ink-400">{label}</p>
      <p className={`font-mono text-sm ${highlight ? "text-good-500" : "text-ink-100"}`}>{formatNumber(value, 3)}</p>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
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
