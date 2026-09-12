import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import KpiCard from "../components/KpiCard";
import CarbonComparisonChart from "../charts/CarbonComparisonChart";
import { ApiError, fetchReferenceData, runOptimization } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { OptimizationResult } from "../types/calculator";
import { formatNumber } from "../utils/format";
import { generateOptimizationExplanation } from "../utils/generateOptimizationExplanation";

export default function CarbonOptimizationPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // --- Current configuration ("Before") ---
  const [gradeId, setGradeId] = useState("");
  const [scrapQualityId, setScrapQualityId] = useState("");
  const [scrapPct, setScrapPct] = useState(65);
  const [energySourceId, setEnergySourceId] = useState("GRID_ELECTRICITY_IN");
  const [energyDemand, setEnergyDemand] = useState(1.0);
  const [yieldPct, setYieldPct] = useState(92);
  const [scrapPctMin, setScrapPctMin] = useState(0);
  const [scrapPctMax, setScrapPctMax] = useState(95);

  const [result, setResult] = useState<OptimizationResult | null>(null);
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

  const energySourceLabel = refData?.energy_sources.sources.find((s) => s.id === energySourceId)?.name ?? energySourceId;
  const gradeName = refData?.steel_grades.grades.find((g) => g.id === gradeId)?.grade_name ?? gradeId;
  const virginPct = 100 - scrapPct;

  async function handleFindLowestCarbon() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await runOptimization({
        grade_id: gradeId,
        scrap_quality_id: scrapQualityId,
        yield: yieldPct / 100,
        scrap_pct_min: scrapPctMin,
        scrap_pct_max: scrapPctMax,
        energy_demand_mwh_equivalent_per_t: energyDemand,
        allow_energy_blending: true,
        energy_capacity_pct: {},
        current_scrap_pct: scrapPct,
        current_energy_mix_pct: { [energySourceId]: 100 },
      });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      } else {
        setError("Could not reach the optimization service.");
      }
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

  const isOptimal = result?.status === "OPTIMAL";
  const explanation = result && isOptimal ? generateOptimizationExplanation(result, { scrapPct, energySourceLabel, gradeName }) : "";

  return (
    <div className="space-y-5">
      <div className="border-b border-base-600 pb-4">
        <p className="text-[11px] uppercase tracking-wider text-steel-400">JSL GreenSteel</p>
        <h1 className="mt-0.5 text-xl font-semibold text-ink-100 sm:text-2xl">Carbon Optimization</h1>
        <p className="mt-1 text-[13px] text-ink-300">
          Finds the scrap/virgin split, energy mix, and alloy additions that minimize carbon intensity while
          satisfying grade chemistry.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Current configuration */}
        <div className="space-y-4 lg:col-span-5 xl:col-span-4">
          <Panel title="Current configuration" eyebrow="Sent to /optimize as the baseline to beat" action={<DemoDataBadge />}>
            <div className="space-y-4">
              <SelectField
                label="Stainless steel grade"
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
                  <span className="text-[12px] text-ink-300">Scrap percentage</span>
                  <span className="font-mono text-[12px] text-ink-100">{formatNumber(scrapPct, 1)}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={0.5}
                  value={scrapPct}
                  onChange={(e) => setScrapPct(parseFloat(e.target.value))}
                  className="w-full accent-steel-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3 rounded border border-base-600 bg-base-800 p-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-ink-400">Scrap %</p>
                  <p className="font-mono text-sm text-ink-100">{formatNumber(scrapPct, 1)}%</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-ink-400">Virgin %</p>
                  <p className="font-mono text-sm text-ink-100">{formatNumber(virginPct, 1)}%</p>
                </div>
              </div>

              <SelectField
                label="Energy source"
                value={energySourceId}
                onChange={setEnergySourceId}
                options={refData.energy_sources.sources.map((s) => ({ id: s.id, name: s.name }))}
              />

              <div className="grid grid-cols-2 gap-3">
                <NumberField label="Energy demand (MWh-equiv/t)" value={energyDemand} onChange={setEnergyDemand} step={0.05} />
                <NumberField label="Yield (%)" value={yieldPct} onChange={setYieldPct} step={0.5} />
              </div>

              <p className="text-[11px] uppercase tracking-wide text-ink-400">Optimizer search bounds</p>
              <div className="grid grid-cols-2 gap-3">
                <NumberField label="Scrap % min" value={scrapPctMin} onChange={setScrapPctMin} step={1} />
                <NumberField label="Scrap % max" value={scrapPctMax} onChange={setScrapPctMax} step={1} />
              </div>
            </div>

            <button
              onClick={handleFindLowestCarbon}
              disabled={running}
              className="mt-5 w-full rounded bg-good-500 py-3 text-sm font-semibold uppercase tracking-wide text-base-900 transition-colors hover:brightness-110 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
            >
              {running ? "Optimizing…" : "Find Lowest Carbon Configuration"}
            </button>
            {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
          </Panel>
        </div>

        {/* Results */}
        <div className="space-y-4 lg:col-span-7 xl:col-span-8">
          {running && (
            <Panel title="Optimizing…">
              <p className="text-sm text-ink-400">Solving the LP/MILP model for the lowest-carbon configuration…</p>
            </Panel>
          )}

          {!running && !result && (
            <Panel title="Result">
              <p className="text-sm text-ink-400">
                Set the current configuration and press "Find Lowest Carbon Configuration" to see results.
              </p>
            </Panel>
          )}

          {!running && result && result.status !== "OPTIMAL" && (
            <Panel title="Optimization status">
              <div className="rounded border border-warn-500/40 bg-warn-500/10 px-4 py-3">
                <p className="text-sm font-medium text-warn-500">
                  {result.status === "INFEASIBLE" ? "✕ No feasible solution" : "✕ Optimization error"}
                </p>
                <p className="mt-1 text-[12px] text-ink-300">{result.message}</p>
              </div>
            </Panel>
          )}

          {!running && result && isOptimal && (
            <>
              <Panel title="Optimization status">
                <div className="rounded border border-good-500/40 bg-good-500/10 px-4 py-3">
                  <p className="text-sm font-medium text-good-500">✓ Optimal solution found</p>
                  <p className="mt-1 text-[12px] text-ink-300">{result.message}</p>
                </div>
              </Panel>

              {result.current_scenario_chemistry_valid === false && (
                <Panel title="Note on the 'Before' figure">
                  <div className="rounded border border-ember-500/40 bg-ember-500/10 px-4 py-3">
                    <p className="text-sm font-medium text-ember-400">⚠ Current configuration is not chemistry-valid</p>
                    <p className="mt-1 text-[12px] leading-relaxed text-ink-300">{result.current_scenario_chemistry_note}</p>
                  </div>
                </Panel>
              )}

              {/* CO2 saved / reduction */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <KpiCard
                  label="CO2 saved"
                  value={formatNumber(result.absolute_reduction!, 2)}
                  unit="tCO2e / tSS"
                  accent={result.absolute_reduction! >= 0 ? "good" : "ember"}
                />
                <KpiCard
                  label="Carbon reduction"
                  value={formatNumber(result.percentage_reduction!, 1)}
                  unit="%"
                  accent={result.percentage_reduction! >= 0 ? "good" : "ember"}
                />
              </div>

              {/* Before vs After */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Panel title="Before" eyebrow="Current configuration">
                  <dl className="space-y-2 text-[13px]">
                    <Row label="Carbon intensity" value={`${formatNumber(result.current_carbon_intensity!, 4)} tCO2e/tSS`} />
                    <Row label="Scrap %" value={`${formatNumber(scrapPct, 1)}%`} />
                    <Row label="Virgin %" value={`${formatNumber(virginPct, 1)}%`} />
                    <Row label="Energy source" value={energySourceLabel} />
                  </dl>
                </Panel>
                <Panel title="After" eyebrow="Optimized configuration">
                  <dl className="space-y-2 text-[13px]">
                    <Row label="Carbon intensity" value={`${formatNumber(result.optimized_carbon_intensity!, 4)} tCO2e/tSS`} highlight />
                    <Row label="Scrap %" value={`${formatNumber(result.optimal_scrap_percentage!, 1)}%`} />
                    <Row label="Virgin %" value={`${formatNumber(result.optimal_virgin_percentage!, 1)}%`} />
                    <div>
                      <dt className="text-ink-400">Energy mix</dt>
                      <dd className="mt-1 space-y-0.5">
                        {result.optimal_energy_mix!
                          .filter((m) => m.share_pct > 0.05)
                          .map((m) => (
                            <div key={m.source_id} className="flex justify-between font-mono text-ink-100">
                              <span className="font-sans text-ink-300">{m.label}</span>
                              <span>{formatNumber(m.share_pct, 1)}%</span>
                            </div>
                          ))}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-ink-400">Alloy additions</dt>
                      <dd className="mt-1 space-y-0.5">
                        {result.optimal_alloy_additions!.filter((a) => a.required_mass_kg > 0.01).length === 0 && (
                          <span className="text-ink-400">None required</span>
                        )}
                        {result.optimal_alloy_additions!
                          .filter((a) => a.required_mass_kg > 0.01)
                          .map((a) => (
                            <div key={a.element} className="flex justify-between font-mono text-ink-100">
                              <span className="font-sans text-ink-300">{a.alloy_name}</span>
                              <span>{formatNumber(a.required_mass_kg, 2)} kg</span>
                            </div>
                          ))}
                      </dd>
                    </div>
                  </dl>
                </Panel>
              </div>

              <Panel title="Current vs. optimized carbon intensity">
                <CarbonComparisonChart currentValue={result.current_carbon_intensity!} optimizedValue={result.optimized_carbon_intensity!} />
              </Panel>

              <Panel title="Why this configuration is better" eyebrow="Generated from the calculated result">
                <p className="text-[13px] leading-relaxed text-ink-200">{explanation}</p>
              </Panel>

              {result.binding_constraints.length > 0 && (
                <Panel title="Binding constraints" eyebrow="Active at the optimum">
                  <ul className="list-inside list-disc space-y-1.5 text-[13px] text-ink-300">
                    {result.binding_constraints.map((b) => (
                      <li key={b.name}>{b.description}</li>
                    ))}
                  </ul>
                </Panel>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-ink-400">{label}</dt>
      <dd className={`font-mono ${highlight ? "text-good-500" : "text-ink-100"}`}>{value}</dd>
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
