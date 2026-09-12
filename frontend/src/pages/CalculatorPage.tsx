import { useEffect, useMemo, useRef, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import KpiCard from "../components/KpiCard";
import EmissionBreakdownDonutChart from "../charts/EmissionBreakdownDonutChart";
import MaterialEmissionBarChart from "../charts/MaterialEmissionBarChart";
import { ApiError, calculateCarbonEmissions, fetchReferenceData } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { CarbonEmissionResult } from "../types/calculator";
import { formatNumber } from "../utils/format";

export default function CalculatorPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // --- Inputs (the 8 required fields) ---
  const [gradeId, setGradeId] = useState("");
  const [scrapPct, setScrapPct] = useState(65);
  const [scrapQualityId, setScrapQualityId] = useState("");
  const [electricitySourceId, setElectricitySourceId] = useState("");
  const [electricityConsumption, setElectricityConsumption] = useState(0.55);
  const [naturalGasConsumption, setNaturalGasConsumption] = useState(0.9);
  const [coalConsumption, setCoalConsumption] = useState(0.1);
  const [yieldPct, setYieldPct] = useState(92);

  const [result, setResult] = useState<CarbonEmissionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetchReferenceData()
      .then((res) => {
        setRefData(res.data);
        setGradeId(res.data.steel_grades.grades[0]?.id ?? "");
        setScrapQualityId(res.data.scrap_quality.categories[0]?.id ?? "");
        const firstElectricity = res.data.energy_sources.sources.find((s) => s.type === "electricity");
        setElectricitySourceId(firstElectricity?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load reference data."));
  }, []);

  // Virgin % and the underlying mass balance are derived automatically
  // whenever scrap % or yield change - shown live, no calculation needed.
  const virginPct = 100 - scrapPct;
  const yieldFraction = yieldPct / 100;
  const yieldValid = yieldFraction > 0 && yieldFraction <= 1;
  const chargeMass = yieldValid ? 1 / yieldFraction : null;
  const scrapMass = chargeMass != null ? (scrapPct / 100) * chargeMass : null;
  const virginMass = chargeMass != null ? (virginPct / 100) * chargeMass : null;

  async function handleCalculate() {
    if (!yieldValid || scrapMass == null || virginMass == null || !electricitySourceId) return;
    setCalculating(true);
    setError(null);
    try {
      const res = await calculateCarbonEmissions({
        materials: [
          { material_id: "SCRAP_EMBODIED", quantity_t: scrapMass, label: "Scrap" },
          { material_id: "VIRGIN_EMBODIED", quantity_t: virginMass, label: "Virgin iron" },
        ],
        electricity_consumption_mwh_per_t: electricityConsumption,
        electricity_mix: [],
        electricity_source_id: electricitySourceId,
        natural_gas_consumption_gj_per_t: naturalGasConsumption,
        coal_consumption_gj_per_t: coalConsumption,
      });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      } else {
        setError("Could not reach the calculation service.");
      }
      setResult(null);
    } finally {
      setCalculating(false);
    }
  }

  // Recalculate automatically whenever an input changes (debounced), so the
  // explicit button is a convenience, not the only way to trigger a result.
  useEffect(() => {
    if (!refData) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      handleCalculate();
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    refData,
    scrapPct,
    electricitySourceId,
    electricityConsumption,
    naturalGasConsumption,
    coalConsumption,
    yieldPct,
  ]);

  const donutSlices = useMemo(() => {
    if (!result) return [];
    return [
      { name: "Material", value: result.material_emissions.total_tco2e, color: "#4C82AA" },
      { name: "Electricity", value: result.electricity_emissions.total_tco2e, color: "#DB8A2C" },
      { name: "Fuel", value: result.fuel_emissions.total_tco2e, color: "#8A97A3" },
      { name: "Process", value: result.process_emissions.tco2e_per_t, color: "#4C9A6A" },
    ];
  }, [result]);

  const materialBars = useMemo(() => {
    if (!result) return [];
    return result.emission_breakdown_by_material.map((item) => ({
      label: item.label,
      tco2e: item.tco2e,
      factorAvailable: item.factor_available,
    }));
  }, [result]);

  if (loadError) {
    return (
      <Panel title="Could not load reference data">
        <p className="text-sm text-warn-500">{loadError}</p>
        <p className="mt-2 text-sm text-ink-300">
          Make sure the backend is running:{" "}
          <code className="rounded bg-base-800 px-1.5 py-0.5 font-mono text-xs">
            cd backend &amp;&amp; uvicorn main:app --reload --port 8000
          </code>
        </p>
      </Panel>
    );
  }

  if (!refData) {
    return <Panel title="Loading reference data…">Fetching grades, scrap quality, and energy sources.</Panel>;
  }

  const electricitySources = refData.energy_sources.sources.filter((s) => s.type === "electricity");

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="border-b border-base-600 pb-4">
        <p className="text-[11px] uppercase tracking-wider text-steel-400">JSL GreenSteel</p>
        <h1 className="mt-0.5 text-xl font-semibold text-ink-100 sm:text-2xl">
          Carbon &amp; Energy Optimization Calculator
        </h1>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Input section */}
        <div className="space-y-4 lg:col-span-5 xl:col-span-4">
          <Panel title="Inputs" eyebrow="Recalculates automatically as you adjust these" action={<DemoDataBadge />}>
            <div className="space-y-4">
              <SelectField
                label="1. Stainless steel grade"
                value={gradeId}
                onChange={setGradeId}
                options={refData.steel_grades.grades.map((g) => ({ id: g.id, name: g.grade_name }))}
              />

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-[12px] text-ink-300">2. Scrap percentage</span>
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

              {/* Automatically-shown Scrap % / Virgin % */}
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
                label="3. Scrap quality"
                value={scrapQualityId}
                onChange={setScrapQualityId}
                options={refData.scrap_quality.categories.map((c) => ({ id: c.id, name: c.category_name }))}
              />
              <p className="-mt-3 text-[11px] text-ink-400">
                Feeds the Alloy Chemistry module; this page's emission total uses mass only.
              </p>

              <SelectField
                label="4. Energy source (electricity)"
                value={electricitySourceId}
                onChange={setElectricitySourceId}
                options={electricitySources}
              />

              <NumberField
                label="5. Electricity consumption"
                unit="MWh / t steel"
                value={electricityConsumption}
                onChange={setElectricityConsumption}
                step={0.01}
              />
              <NumberField
                label="6. Natural gas consumption"
                unit="GJ / t steel"
                value={naturalGasConsumption}
                onChange={setNaturalGasConsumption}
                step={0.01}
              />
              <NumberField
                label="7. Coal consumption"
                unit="GJ / t steel"
                value={coalConsumption}
                onChange={setCoalConsumption}
                step={0.01}
              />
              <NumberField
                label="8. Production yield"
                unit="%"
                value={yieldPct}
                onChange={setYieldPct}
                step={0.5}
                error={!yieldValid ? "Yield must be greater than 0% and at most 100%." : undefined}
              />
            </div>

            <button
              onClick={handleCalculate}
              disabled={calculating || !yieldValid || !electricitySourceId}
              className="mt-5 w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
            >
              {calculating ? "Calculating…" : "Calculate Carbon Footprint"}
            </button>
            {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
          </Panel>
        </div>

        {/* Results section */}
        <div className="space-y-4 lg:col-span-7 xl:col-span-8">
          {!result && (
            <Panel title="Result">
              <p className="text-sm text-ink-400">
                {calculating ? "Calculating…" : "Adjust an input or press Calculate Carbon Footprint to see results."}
              </p>
            </Panel>
          )}

          {result && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <KpiCard
                  label="Carbon Intensity"
                  value={formatNumber(result.carbon_intensity_tCO2e_per_tSS, 3)}
                  unit="tCO2e / tSS"
                  accent="steel"
                  sublabel={`${formatNumber(result.carbon_intensity_kgCO2e_per_tSS, 0)} kgCO2e / tSS`}
                />
                <KpiCard
                  label="Material Emissions"
                  value={formatNumber(result.material_emissions.total_tco2e, 3)}
                  unit="tCO2e / tSS"
                />
                <KpiCard
                  label="Energy Emissions"
                  value={formatNumber(result.electricity_emissions.total_tco2e, 3)}
                  unit="tCO2e / tSS"
                  sublabel="Electricity only"
                />
                <KpiCard
                  label="Fuel Emissions"
                  value={formatNumber(result.fuel_emissions.total_tco2e, 3)}
                  unit="tCO2e / tSS"
                  sublabel="Natural gas + coal"
                />
              </div>

              {result.missing_factor_warnings.length > 0 && (
                <div className="rounded border border-ember-500/40 bg-ember-500/10 p-3">
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ember-400">
                    Missing factor warnings — not fabricated
                  </p>
                  <ul className="list-inside list-disc space-y-1 text-[12px] text-ember-400">
                    {result.missing_factor_warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <Panel title="Emission breakdown" eyebrow="By category · tCO2e / tSS">
                  <EmissionBreakdownDonutChart
                    slices={donutSlices}
                    centerLabel={`${formatNumber(result.carbon_intensity_tCO2e_per_tSS, 2)}`}
                    centerSubLabel="tCO2e / tSS"
                  />
                </Panel>
                <Panel title="Material emissions" eyebrow="Scrap vs. virgin · tCO2e">
                  <MaterialEmissionBarChart items={materialBars} />
                </Panel>
              </div>

              <Panel title="Mass balance used for this calculation" eyebrow="Derived automatically from scrap % and yield">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <MiniStat label="Charge mass" value={chargeMass} unit="t" />
                  <MiniStat label="Scrap mass" value={scrapMass} unit="t" />
                  <MiniStat label="Virgin mass" value={virginMass} unit="t" />
                  <MiniStat label="Yield" value={yieldFraction * 100} unit="%" />
                </div>
              </Panel>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, unit }: { label: string; value: number | null; unit: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-ink-400">{label}</p>
      <p className="font-mono text-sm text-ink-100">
        {value != null ? formatNumber(value, 4) : "—"} <span className="text-ink-400">{unit}</span>
      </p>
    </div>
  );
}

function NumberField({
  label,
  unit,
  value,
  onChange,
  step = 1,
  error,
}: {
  label: string;
  unit: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  error?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline justify-between text-[12px] text-ink-300">
        <span>{label}</span>
        <span className="text-[10px] text-ink-400">{unit}</span>
      </span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className={`w-full rounded border bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500 ${
          error ? "border-warn-500" : "border-base-600"
        }`}
      />
      {error && <span className="mt-1 block text-[11px] text-warn-500">{error}</span>}
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
