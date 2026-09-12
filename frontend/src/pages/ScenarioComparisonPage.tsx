import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import { ApiError, createScenario, deleteScenario, fetchReferenceData, fetchScenarios } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { ScenarioRecord } from "../types/calculator";
import { formatNumber } from "../utils/format";

type SortMode = "lowest_carbon" | "highest_scrap" | "lowest_energy";

const SORT_LABELS: Record<SortMode, string> = {
  lowest_carbon: "Lowest Carbon",
  highest_scrap: "Highest Scrap",
  lowest_energy: "Lowest Energy Emissions",
};

export default function ScenarioComparisonPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [scenarios, setScenarios] = useState<ScenarioRecord[]>([]);
  const [sortMode, setSortMode] = useState<SortMode>("lowest_carbon");

  const [name, setName] = useState("");
  const [gradeId, setGradeId] = useState("");
  const [scrapPct, setScrapPct] = useState(65);
  const [scrapQualityId, setScrapQualityId] = useState("");
  const [energySourceId, setEnergySourceId] = useState("");
  const [electricityConsumption, setElectricityConsumption] = useState(0.55);
  const [naturalGasConsumption, setNaturalGasConsumption] = useState(0.9);
  const [coalConsumption, setCoalConsumption] = useState(0.1);
  const [yieldPct, setYieldPct] = useState(92);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchReferenceData(), fetchScenarios()])
      .then(([ref, scenarioList]) => {
        setRefData(ref.data);
        setScenarios(scenarioList.scenarios);
        setGradeId(ref.data.steel_grades.grades[0]?.id ?? "");
        setScrapQualityId(ref.data.scrap_quality.categories[0]?.id ?? "");
        const firstElectricity = ref.data.energy_sources.sources.find((s) => s.type === "electricity");
        setEnergySourceId(firstElectricity?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load data."));
  }, []);

  async function handleSave() {
    if (!name.trim()) {
      setError("Give the scenario a name before saving.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const record = await createScenario({
        name: name.trim(),
        grade_id: gradeId,
        scrap_pct: scrapPct,
        scrap_quality_id: scrapQualityId,
        energy_source_id: energySourceId,
        electricity_consumption_mwh_per_t: electricityConsumption,
        natural_gas_consumption_gj_per_t: naturalGasConsumption,
        coal_consumption_gj_per_t: coalConsumption,
        yield: yieldPct / 100,
      });
      setScenarios((prev) => [...prev, record]);
      setName("");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      } else {
        setError("Could not reach the scenario service.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteScenario(id);
      setScenarios((prev) => prev.filter((s) => s.id !== id));
    } catch {
      setError("Could not delete that scenario - it may already be gone.");
    }
  }

  if (loadError) {
    return (
      <Panel title="Could not load data">
        <p className="text-sm text-warn-500">{loadError}</p>
      </Panel>
    );
  }

  if (!refData) {
    return <Panel title="Loading…">Fetching reference data and saved scenarios.</Panel>;
  }

  const sorted = [...scenarios].sort((a, b) => {
    if (sortMode === "lowest_carbon") return a.total_co2_tco2e_per_t - b.total_co2_tco2e_per_t;
    if (sortMode === "highest_scrap") return b.scrap_pct - a.scrap_pct;
    return a.energy_co2_tco2e_per_t - b.energy_co2_tco2e_per_t;
  });

  const worstTotal = scenarios.length > 0 ? Math.max(...scenarios.map((s) => s.total_co2_tco2e_per_t)) : 0;
  const bestId = scenarios.length > 0 ? scenarios.reduce((a, b) => (b.total_co2_tco2e_per_t < a.total_co2_tco2e_per_t ? b : a)).id : null;

  return (
    <div className="space-y-5">
      <div className="border-b border-base-600 pb-4">
        <p className="text-[11px] uppercase tracking-wider text-steel-400">JSL GreenSteel</p>
        <h1 className="mt-0.5 text-xl font-semibold text-ink-100 sm:text-2xl">Scenario Comparison</h1>
        <p className="mt-1 text-[13px] text-ink-300">
          Save named configurations and compare their carbon performance side by side.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-4 xl:col-span-3">
          <Panel title="Save a scenario" action={<DemoDataBadge />}>
            <div className="space-y-3">
              <label className="block">
                <span className="mb-1.5 block text-[12px] text-ink-300">Scenario name</span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Renewable + high scrap"
                  className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 text-[13px] text-ink-100 outline-none placeholder:text-ink-400 focus:border-steel-500"
                />
              </label>

              <SelectField
                label="Steel grade"
                value={gradeId}
                onChange={setGradeId}
                options={refData.steel_grades.grades.map((g) => ({ id: g.id, name: g.grade_name }))}
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
                label="Scrap quality"
                value={scrapQualityId}
                onChange={setScrapQualityId}
                options={refData.scrap_quality.categories.map((c) => ({ id: c.id, name: c.category_name }))}
              />
              <SelectField
                label="Energy source"
                value={energySourceId}
                onChange={setEnergySourceId}
                options={refData.energy_sources.sources.filter((s) => s.type === "electricity").map((s) => ({ id: s.id, name: s.name }))}
              />

              <NumberField label="Electricity (MWh/t)" value={electricityConsumption} onChange={setElectricityConsumption} step={0.01} />
              <NumberField label="Natural gas (GJ/t)" value={naturalGasConsumption} onChange={setNaturalGasConsumption} step={0.01} />
              <NumberField label="Coal (GJ/t)" value={coalConsumption} onChange={setCoalConsumption} step={0.01} />
              <NumberField label="Yield (%)" value={yieldPct} onChange={setYieldPct} step={0.5} />
            </div>

            <button
              onClick={handleSave}
              disabled={saving}
              className="mt-4 w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
            >
              {saving ? "Saving…" : "Save Scenario"}
            </button>
            {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
          </Panel>
        </div>

        <div className="space-y-4 lg:col-span-8 xl:col-span-9">
          <Panel
            title="Saved scenarios"
            eyebrow={`${scenarios.length} scenario${scenarios.length === 1 ? "" : "s"} saved`}
            action={
              <div className="flex items-center gap-1.5">
                {(Object.keys(SORT_LABELS) as SortMode[]).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setSortMode(mode)}
                    className={`rounded-sm px-2 py-1 text-[11px] transition-colors ${
                      sortMode === mode ? "bg-steel-600/30 text-ink-100" : "text-ink-400 hover:bg-base-700"
                    }`}
                  >
                    {SORT_LABELS[mode]}
                  </button>
                ))}
              </div>
            }
          >
            {scenarios.length === 0 ? (
              <p className="text-sm text-ink-400">No scenarios saved yet. Use the form to save your first one.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-[12px]">
                  <thead>
                    <tr className="border-b border-base-600 text-ink-400">
                      <th className="py-1.5 pr-3 font-normal">Scenario</th>
                      <th className="py-1.5 pr-3 font-normal">Grade</th>
                      <th className="py-1.5 pr-3 font-normal">Scrap %</th>
                      <th className="py-1.5 pr-3 font-normal">Energy</th>
                      <th className="py-1.5 pr-3 font-normal">Material CO2</th>
                      <th className="py-1.5 pr-3 font-normal">Energy CO2</th>
                      <th className="py-1.5 pr-3 font-normal">Total CO2</th>
                      <th className="py-1.5 pr-3 font-normal">Reduction %</th>
                      <th className="py-1.5 font-normal" />
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((s) => {
                      const isBest = s.id === bestId;
                      const reductionPct = worstTotal > 0 ? ((worstTotal - s.total_co2_tco2e_per_t) / worstTotal) * 100 : 0;
                      return (
                        <tr
                          key={s.id}
                          className={`border-b border-base-600/60 ${isBest ? "bg-good-500/10" : ""}`}
                        >
                          <td className="py-1.5 pr-3 text-ink-100">
                            {isBest && <span className="mr-1 text-good-500">★</span>}
                            {s.name}
                          </td>
                          <td className="py-1.5 pr-3 text-ink-300">{s.grade_name}</td>
                          <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(s.scrap_pct, 1)}%</td>
                          <td className="py-1.5 pr-3 text-ink-300">{s.energy_source_name}</td>
                          <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(s.material_co2_tco2e_per_t, 3)}</td>
                          <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(s.energy_co2_tco2e_per_t, 3)}</td>
                          <td className={`py-1.5 pr-3 font-mono ${isBest ? "text-good-500" : "text-ink-100"}`}>
                            {formatNumber(s.total_co2_tco2e_per_t, 3)}
                          </td>
                          <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(reductionPct, 1)}%</td>
                          <td className="py-1.5">
                            <button onClick={() => handleDelete(s.id)} className="text-[11px] text-warn-500 hover:underline">
                              Delete
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {scenarios.length > 0 && (
              <p className="mt-3 text-[11px] text-ink-400">
                Reduction % is relative to the highest-carbon scenario currently saved ({formatNumber(worstTotal, 3)}{" "}
                tCO2e/t). ★ marks the lowest-carbon scenario.
              </p>
            )}
          </Panel>
        </div>
      </div>
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
