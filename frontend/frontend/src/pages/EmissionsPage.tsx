import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import { ApiError, calculateCarbonEmissions, fetchReferenceData } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { CarbonEmissionResult, MaterialQuantityInput } from "../types/calculator";
import { formatNumber, titleCase } from "../utils/format";

const KNOWN_MATERIAL_IDS = [
  "SCRAP_EMBODIED",
  "VIRGIN_EMBODIED",
  "FERRO_CHROME",
  "FERRO_NICKEL",
  "NICKEL_METAL",
  "FERRO_MOLYBDENUM",
  "FERRO_MANGANESE",
  "FERRO_SILICON",
  "FERRO_TITANIUM",
];

interface CustomMaterialRow {
  key: string;
  material_id: string;
  quantity_t: number;
}

export default function EmissionsPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [materialQuantities, setMaterialQuantities] = useState<Record<string, number>>({
    SCRAP_EMBODIED: 0.7,
    VIRGIN_EMBODIED: 0.3,
    FERRO_CHROME: 0.15,
  });
  const [customMaterials, setCustomMaterials] = useState<CustomMaterialRow[]>([]);

  const [electricityConsumption, setElectricityConsumption] = useState(0.55);
  const [gridSharePct, setGridSharePct] = useState(80);
  const [renewableSharePct, setRenewableSharePct] = useState(20);

  const [naturalGasConsumption, setNaturalGasConsumption] = useState(0.9);
  const [coalConsumption, setCoalConsumption] = useState(0.1);

  const [processRouteId, setProcessRouteId] = useState("");

  const [result, setResult] = useState<CarbonEmissionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);

  useEffect(() => {
    fetchReferenceData()
      .then((res) => {
        setRefData(res.data);
        setProcessRouteId(res.data.energy_sources.process_routes[0]?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load reference data."));
  }, []);

  function addCustomMaterial() {
    setCustomMaterials((prev) => [...prev, { key: crypto.randomUUID(), material_id: "", quantity_t: 0.01 }]);
  }

  function updateCustomMaterial(key: string, patch: Partial<CustomMaterialRow>) {
    setCustomMaterials((prev) => prev.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function removeCustomMaterial(key: string) {
    setCustomMaterials((prev) => prev.filter((row) => row.key !== key));
  }

  async function handleCalculate() {
    setCalculating(true);
    setError(null);
    try {
      const materials: MaterialQuantityInput[] = [
        ...Object.entries(materialQuantities)
          .filter(([, qty]) => qty > 0)
          .map(([material_id, quantity_t]) => ({ material_id, quantity_t })),
        ...customMaterials
          .filter((row) => row.material_id.trim() !== "" && row.quantity_t > 0)
          .map((row) => ({ material_id: row.material_id.trim(), quantity_t: row.quantity_t })),
      ];

      const electricity_mix = [
        ...(gridSharePct > 0 ? [{ source_id: "GRID_ELECTRICITY_IN", share_pct: gridSharePct }] : []),
        ...(renewableSharePct > 0 ? [{ source_id: "RENEWABLE_ELECTRICITY_IN", share_pct: renewableSharePct }] : []),
      ];

      const res = await calculateCarbonEmissions({
        materials,
        electricity_consumption_mwh_per_t: electricityConsumption,
        electricity_mix,
        natural_gas_consumption_gj_per_t: naturalGasConsumption,
        coal_consumption_gj_per_t: coalConsumption,
        process_route_id: processRouteId || undefined,
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

  if (loadError) {
    return (
      <Panel title="Could not load reference data">
        <p className="text-sm text-warn-500">{loadError}</p>
      </Panel>
    );
  }

  if (!refData) {
    return <Panel title="Loading reference data…">Fetching process routes and factors.</Panel>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
      <div className="space-y-4 xl:col-span-2">
        <Panel
          title="Complete carbon-emission engine"
          eyebrow="Total = Material + Electricity + Direct Fuel + Process"
          action={<DemoDataBadge />}
        >
          <p className="mb-4 text-[13px] leading-relaxed text-ink-300">
            Every factor is looked up by id. If a factor is missing, that item is excluded from
            the total and reported as a warning — never fabricated.
          </p>

          <p className="mb-2 text-[11px] uppercase tracking-wide text-ink-400">Materials (t per t steel)</p>
          <div className="space-y-2">
            {KNOWN_MATERIAL_IDS.map((id) => (
              <label key={id} className="flex items-center justify-between gap-3">
                <span className="text-[12px] text-ink-300">{titleCase(id)}</span>
                <input
                  type="number"
                  value={materialQuantities[id] ?? 0}
                  step={0.01}
                  min={0}
                  onChange={(e) =>
                    setMaterialQuantities((prev) => ({ ...prev, [id]: parseFloat(e.target.value) || 0 }))
                  }
                  className="w-28 rounded border border-base-600 bg-base-800 px-2 py-1 font-mono text-[12px] text-ink-100 outline-none focus:border-steel-500"
                />
              </label>
            ))}
          </div>

          {customMaterials.map((row) => (
            <div key={row.key} className="mt-2 flex items-center gap-2">
              <input
                type="text"
                placeholder="material_id (e.g. UNKNOWN_ALLOY)"
                value={row.material_id}
                onChange={(e) => updateCustomMaterial(row.key, { material_id: e.target.value })}
                className="flex-1 rounded border border-base-600 bg-base-800 px-2 py-1 font-mono text-[12px] text-ink-100 outline-none focus:border-steel-500"
              />
              <input
                type="number"
                value={row.quantity_t}
                step={0.01}
                min={0}
                onChange={(e) => updateCustomMaterial(row.key, { quantity_t: parseFloat(e.target.value) || 0 })}
                className="w-20 rounded border border-base-600 bg-base-800 px-2 py-1 font-mono text-[12px] text-ink-100 outline-none focus:border-steel-500"
              />
              <button onClick={() => removeCustomMaterial(row.key)} className="text-[11px] text-warn-500">
                Remove
              </button>
            </div>
          ))}
          <button onClick={addCustomMaterial} className="mt-2 text-[11px] text-steel-400 hover:text-steel-300">
            + Add custom material (test a missing factor)
          </button>
        </Panel>

        <Panel title="Electricity" eyebrow="CO2_electricity = consumption × Σ(share × factor)">
          <label className="block">
            <span className="mb-1.5 block text-[12px] text-ink-300">Consumption (MWh/t)</span>
            <input
              type="number"
              value={electricityConsumption}
              step={0.01}
              min={0}
              onChange={(e) => setElectricityConsumption(parseFloat(e.target.value) || 0)}
              className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
            />
          </label>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Grid share (%)</span>
              <input
                type="number"
                value={gridSharePct}
                step={1}
                min={0}
                max={100}
                onChange={(e) => setGridSharePct(parseFloat(e.target.value) || 0)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Renewable share (%)</span>
              <input
                type="number"
                value={renewableSharePct}
                step={1}
                min={0}
                max={100}
                onChange={(e) => setRenewableSharePct(parseFloat(e.target.value) || 0)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
              />
            </label>
          </div>
          <p className={`mt-1.5 text-[11px] ${gridSharePct + renewableSharePct === 100 ? "text-ink-400" : "text-ember-400"}`}>
            Shares sum to {gridSharePct + renewableSharePct}%
          </p>
        </Panel>

        <Panel title="Direct fuel" eyebrow="CO2_NG = NG × EF_NG · CO2_coal = coal × EF_coal">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Natural gas (GJ/t)</span>
              <input
                type="number"
                value={naturalGasConsumption}
                step={0.01}
                min={0}
                onChange={(e) => setNaturalGasConsumption(parseFloat(e.target.value) || 0)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Coal (GJ/t)</span>
              <input
                type="number"
                value={coalConsumption}
                step={0.01}
                min={0}
                onChange={(e) => setCoalConsumption(parseFloat(e.target.value) || 0)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
              />
            </label>
          </div>
        </Panel>

        <Panel title="Process (configurable)" eyebrow="Named route, or leave unset to see the warning">
          <select
            value={processRouteId}
            onChange={(e) => setProcessRouteId(e.target.value)}
            className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 text-[13px] text-ink-100 outline-none focus:border-steel-500"
          >
            <option value="">Not configured</option>
            {refData.energy_sources.process_routes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </Panel>

        <button
          onClick={handleCalculate}
          disabled={calculating}
          className="w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
        >
          {calculating ? "Calculating…" : "Calculate total carbon intensity"}
        </button>
        {error && <p className="text-sm text-warn-500">{error}</p>}
      </div>

      <div className="space-y-4 xl:col-span-3">
        {!result && (
          <Panel title="Result">
            <p className="text-sm text-ink-400">Run the calculator to see results here.</p>
          </Panel>
        )}

        {result && (
          <>
            <Panel title="Carbon intensity" eyebrow="Total = Material + Electricity + Direct Fuel + Process">
              <div className="mb-1 font-mono text-3xl font-semibold text-ink-100">
                {formatNumber(result.carbon_intensity_tCO2e_per_tSS, 4)}
                <span className="ml-1.5 text-base font-normal text-ink-400">tCO2e / tSS</span>
              </div>
              <p className="mb-3 text-[12px] text-ink-400">
                = {formatNumber(result.carbon_intensity_kgCO2e_per_tSS, 1)} kgCO2e / tSS
              </p>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <ComponentFigure label="Material" value={result.material_emissions.total_tco2e} />
                <ComponentFigure label="Electricity" value={result.electricity_emissions.total_tco2e} />
                <ComponentFigure label="Fuel" value={result.fuel_emissions.total_tco2e} />
                <ComponentFigure label="Process" value={result.process_emissions.tco2e_per_t} />
              </div>

              {result.missing_factor_warnings.length > 0 && (
                <div className="mt-4 rounded border border-ember-500/40 bg-ember-500/10 p-3">
                  <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ember-400">
                    Missing factor warnings — not fabricated
                  </p>
                  <ul className="list-inside list-disc space-y-1 text-[12px] text-ember-400">
                    {result.missing_factor_warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Panel>

            <Panel title="Emission breakdown by material">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-b border-base-600 text-ink-400">
                    <th className="py-1.5 pr-3 font-normal">Material</th>
                    <th className="py-1.5 pr-3 font-normal">Quantity (t)</th>
                    <th className="py-1.5 pr-3 font-normal">Factor</th>
                    <th className="py-1.5 font-normal">tCO2e</th>
                  </tr>
                </thead>
                <tbody>
                  {result.emission_breakdown_by_material.map((item) => (
                    <tr key={item.material_id} className="border-b border-base-600/60">
                      <td className="py-1.5 pr-3 text-ink-200">{item.label}</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(item.quantity_t, 4)}</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">
                        {item.factor_available ? (
                          `${item.emission_factor_tco2e_per_t} tCO2e/t`
                        ) : (
                          <span className="text-warn-500">unavailable</span>
                        )}
                      </td>
                      <td className="py-1.5 font-mono text-ink-100">{formatNumber(item.tco2e, 4)}</td>
                    </tr>
                  ))}
                  {result.emission_breakdown_by_material.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-2 text-ink-400">
                        No materials supplied.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </Panel>

            <Panel title="Electricity mix detail">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-b border-base-600 text-ink-400">
                    <th className="py-1.5 pr-3 font-normal">Source</th>
                    <th className="py-1.5 pr-3 font-normal">Share</th>
                    <th className="py-1.5 font-normal">Factor</th>
                  </tr>
                </thead>
                <tbody>
                  {result.electricity_emissions.mix.map((m) => (
                    <tr key={m.source_id} className="border-b border-base-600/60">
                      <td className="py-1.5 pr-3 text-ink-200">{m.label}</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">{m.share_pct}%</td>
                      <td className="py-1.5 font-mono text-ink-100">
                        {m.factor_available ? (
                          `${m.emission_factor_tco2e_per_mwh} tCO2e/MWh`
                        ) : (
                          <span className="text-warn-500">unavailable</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.electricity_emissions.effective_emission_factor_tco2e_per_mwh != null && (
                <p className="mt-2 text-[12px] text-ink-300">
                  Effective factor:{" "}
                  <span className="font-mono text-ink-100">
                    {formatNumber(result.electricity_emissions.effective_emission_factor_tco2e_per_mwh, 4)} tCO2e/MWh
                  </span>
                </p>
              )}
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}

function ComponentFigure({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-base-600 bg-base-800 p-3">
      <p className="text-[11px] text-ink-400">{label}</p>
      <p className="mt-0.5 font-mono text-lg font-semibold text-ink-100">{formatNumber(value, 4)}</p>
    </div>
  );
}
