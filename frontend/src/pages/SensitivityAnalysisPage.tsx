import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import SensitivityBarChart from "../charts/SensitivityBarChart";
import { ApiError, fetchReferenceData, runSensitivityAnalysis } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { SensitivityResult, SensitivitySweep } from "../types/calculator";
import { formatNumber } from "../utils/format";

export default function SensitivityAnalysisPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [gradeId, setGradeId] = useState("");
  const [scrapQualityId, setScrapQualityId] = useState("");
  const [scrapPct, setScrapPct] = useState(65);
  const [energySourceId, setEnergySourceId] = useState("GRID_ELECTRICITY_IN");
  const [yieldPct, setYieldPct] = useState(92);
  const [energyDemand, setEnergyDemand] = useState(1.0);

  const [result, setResult] = useState<SensitivityResult | null>(null);
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
      const res = await runSensitivityAnalysis({
        grade_id: gradeId,
        scrap_quality_id: scrapQualityId,
        scrap_pct: scrapPct,
        energy_source_id: energySourceId,
        yield: yieldPct / 100,
        energy_demand_mwh_equivalent_per_t: energyDemand,
      });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      } else {
        setError("Could not reach the sensitivity analysis service.");
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
        <h1 className="mt-0.5 text-xl font-semibold text-ink-100 sm:text-2xl">Sensitivity Analysis</h1>
        <p className="mt-1 text-[13px] text-ink-300">
          Sweeps one variable at a time — scrap %, energy source, scrap quality, and grade — while holding
          the others fixed at the baseline below.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-4 xl:col-span-3">
          <Panel title="Baseline configuration" eyebrow="Held fixed for whichever dimension isn't being swept" action={<DemoDataBadge />}>
            <div className="space-y-4">
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
                  <span className="text-[12px] text-ink-300">Scrap %</span>
                  <span className="font-mono text-[12px] text-ink-100">{formatNumber(scrapPct, 1)}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={scrapPct}
                  onChange={(e) => setScrapPct(parseFloat(e.target.value))}
                  className="w-full accent-steel-500"
                />
              </div>
              <SelectField
                label="Energy source"
                value={energySourceId}
                onChange={setEnergySourceId}
                options={refData.energy_sources.sources.map((s) => ({ id: s.id, name: s.name }))}
              />
              <NumberField label="Yield (%)" value={yieldPct} onChange={setYieldPct} step={0.5} />
              <NumberField label="Energy demand (MWh-equiv/t)" value={energyDemand} onChange={setEnergyDemand} step={0.05} />
            </div>

            <button
              onClick={handleRun}
              disabled={running}
              className="mt-5 w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
            >
              {running ? "Running…" : "Run sensitivity analysis"}
            </button>
            {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
          </Panel>

          <Panel title="Legend">
            <ul className="space-y-1.5 text-[12px] text-ink-300">
              <li className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-sm bg-good-500" /> Lowest-carbon feasible scenario
              </li>
              <li className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-sm bg-steel-500" /> Feasible
              </li>
              <li className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-sm bg-carbon-500 opacity-40" /> Infeasible (fails grade chemistry)
              </li>
            </ul>
          </Panel>
        </div>

        <div className="space-y-4 lg:col-span-8 xl:col-span-9">
          {!result && (
            <Panel title="Result">
              <p className="text-sm text-ink-400">Run the analysis to see the four sweep charts here.</p>
            </Panel>
          )}

          {result && (
            <>
              <SweepPanel title="1. Scrap % vs. Carbon Intensity" sweep={result.scrap_percentage_sweep} />
              <SweepPanel title="2. Energy Source vs. Carbon Intensity" sweep={result.energy_source_sweep} />
              <SweepPanel title="3. Scrap Quality vs. Carbon Intensity" sweep={result.scrap_quality_sweep} />
              <SweepPanel title="4. Grade vs. Carbon Intensity" sweep={result.grade_sweep} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SweepPanel({ title, sweep }: { title: string; sweep: SensitivitySweep }) {
  return (
    <Panel title={title} eyebrow={sweep.baseline_note}>
      <SensitivityBarChart points={sweep.points} />
      <p className="mt-3 rounded border border-base-600 bg-base-800 p-3 text-[13px] leading-relaxed text-ink-200">
        {sweep.insight}
      </p>
    </Panel>
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
