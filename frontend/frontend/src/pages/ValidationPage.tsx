import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import { ApiError, fetchReferenceData, runValidation } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { ValidationReport } from "../types/calculator";

export default function ValidationPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [scrapPercentage, setScrapPercentage] = useState(65);
  const [yieldPct, setYieldPct] = useState(92);

  const [scrapQualityId, setScrapQualityId] = useState("");
  const [gradeId, setGradeId] = useState("");
  const [scrapMass, setScrapMass] = useState(0.7);

  const [electricityConsumption, setElectricityConsumption] = useState(0.55);
  const [gridSharePct, setGridSharePct] = useState(80);
  const [renewableSharePct, setRenewableSharePct] = useState(20);
  const [processRouteId, setProcessRouteId] = useState("");

  const [report, setReport] = useState<ValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    fetchReferenceData()
      .then((res) => {
        setRefData(res.data);
        setScrapQualityId(res.data.scrap_quality.categories[0]?.id ?? "");
        setGradeId(res.data.steel_grades.grades[0]?.id ?? "");
        setProcessRouteId(res.data.energy_sources.process_routes[0]?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load reference data."));
  }, []);

  async function handleRunValidation() {
    setRunning(true);
    setError(null);
    try {
      const electricity_mix = [
        ...(gridSharePct > 0 ? [{ source_id: "GRID_ELECTRICITY_IN", share_pct: gridSharePct }] : []),
        ...(renewableSharePct > 0 ? [{ source_id: "RENEWABLE_ELECTRICITY_IN", share_pct: renewableSharePct }] : []),
      ];

      const res = await runValidation({
        material: { scrap_percentage: scrapPercentage, yield: yieldPct / 100 },
        scrap_chemistry:
          scrapQualityId && gradeId
            ? { scrap_quality_id: scrapQualityId, scrap_mass: scrapMass, grade_id: gradeId }
            : undefined,
        carbon_emission: {
          materials: [],
          electricity_consumption_mwh_per_t: electricityConsumption,
          electricity_mix,
          natural_gas_consumption_gj_per_t: 0,
          coal_consumption_gj_per_t: 0,
          process_route_id: processRouteId || undefined,
        },
      });
      setReport(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
      } else {
        setError("Could not reach the validation service.");
      }
      setReport(null);
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
    return <Panel title="Loading reference data…">Fetching grades, scrap quality, and process routes.</Panel>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
      <div className="space-y-4 xl:col-span-2">
        <Panel title="Validation engine" eyebrow="Runs the 12 required checks across every domain below">
          <p className="mb-4 text-[13px] leading-relaxed text-ink-300">
            Every check reports PASS, WARNING, or ERROR. If any check is an ERROR, the overall
            result is blocked — an invalid configuration should never silently produce a final
            answer.
          </p>

          <p className="mb-2 text-[11px] uppercase tracking-wide text-ink-400">Material balance</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Scrap %</span>
              <input
                type="number"
                value={scrapPercentage}
                step={1}
                onChange={(e) => setScrapPercentage(parseFloat(e.target.value) || 0)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Yield %</span>
              <input
                type="number"
                value={yieldPct}
                step={1}
                onChange={(e) => setYieldPct(parseFloat(e.target.value) || 0)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
              />
            </label>
          </div>
          <p className="mt-1.5 text-[11px] text-ink-400">
            Try 150 (scrap %) or 0 (yield %) to see the checks fail on purpose.
          </p>

          <p className="mb-2 mt-4 text-[11px] uppercase tracking-wide text-ink-400">Scrap chemistry</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Scrap quality</span>
              <select
                value={scrapQualityId}
                onChange={(e) => setScrapQualityId(e.target.value)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 text-[13px] text-ink-100 outline-none focus:border-steel-500"
              >
                {refData.scrap_quality.categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.category_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-ink-300">Grade</span>
              <select
                value={gradeId}
                onChange={(e) => setGradeId(e.target.value)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 text-[13px] text-ink-100 outline-none focus:border-steel-500"
              >
                {refData.steel_grades.grades.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.grade_name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="mt-3 block">
            <span className="mb-1.5 block text-[12px] text-ink-300">Scrap mass charged (t)</span>
            <input
              type="number"
              value={scrapMass}
              step={0.05}
              onChange={(e) => setScrapMass(parseFloat(e.target.value) || 0)}
              className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
            />
          </label>
          <p className="mt-1 text-[11px] text-ink-400">
            Try SS304 + High Quality scrap to see the grade chemistry check fail (trace Mo).
          </p>

          <p className="mb-2 mt-4 text-[11px] uppercase tracking-wide text-ink-400">Energy</p>
          <label className="block">
            <span className="mb-1.5 block text-[12px] text-ink-300">Electricity consumption (MWh/t)</span>
            <input
              type="number"
              value={electricityConsumption}
              step={0.01}
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
                onChange={(e) => setRenewableSharePct(parseFloat(e.target.value) || 0)}
                className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
              />
            </label>
          </div>
          <p className="mt-1 text-[11px] text-ink-400">Try 80/50 (sums to 130%) to see the energy-mix check fail.</p>

          <label className="mt-3 block">
            <span className="mb-1.5 block text-[12px] text-ink-300">Process route</span>
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
          </label>

          <button
            onClick={handleRunValidation}
            disabled={running}
            className="mt-4 w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
          >
            {running ? "Validating…" : "Run validation"}
          </button>
          {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
        </Panel>
      </div>

      <div className="space-y-4 xl:col-span-3">
        {!report && (
          <Panel title="Validation report">
            <p className="text-sm text-ink-400">Run the validation engine to see the report here.</p>
          </Panel>
        )}

        {report && (
          <Panel title="Validation report" eyebrow={report.summary}>
            <OverallBanner report={report} />

            <ul className="mt-4 space-y-2">
              {report.checks.map((check) => (
                <li
                  key={check.check_id}
                  className={`flex items-start gap-2.5 rounded border px-3 py-2 ${
                    check.status === "PASS"
                      ? "border-good-500/30 bg-good-500/5"
                      : check.status === "WARNING"
                        ? "border-ember-500/30 bg-ember-500/5"
                        : "border-warn-500/30 bg-warn-500/5"
                  }`}
                >
                  <StatusIcon status={check.status} />
                  <div>
                    <p className="text-[13px] text-ink-100">{check.name}</p>
                    <p className="text-[12px] text-ink-300">{check.message}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

function OverallBanner({ report }: { report: ValidationReport }) {
  if (report.blocked) {
    return (
      <div className="rounded border border-warn-500/40 bg-warn-500/10 px-4 py-3">
        <p className="text-sm font-medium text-warn-500">✕ Invalid configuration — results are blocked</p>
        <p className="mt-1 text-[12px] text-ink-300">
          One or more checks failed. Fix the errors below before trusting any downstream
          calculation for this configuration.
        </p>
      </div>
    );
  }
  if (report.overall_status === "WARNING") {
    return (
      <div className="rounded border border-ember-500/40 bg-ember-500/10 px-4 py-3">
        <p className="text-sm font-medium text-ember-400">⚠ Passed with warnings</p>
        <p className="mt-1 text-[12px] text-ink-300">
          No blocking errors, but review the warnings below before relying on the result.
        </p>
      </div>
    );
  }
  return (
    <div className="rounded border border-good-500/40 bg-good-500/10 px-4 py-3">
      <p className="text-sm font-medium text-good-500">✓ All checks passed</p>
    </div>
  );
}

function StatusIcon({ status }: { status: "PASS" | "WARNING" | "ERROR" }) {
  if (status === "PASS") return <span className="mt-0.5 shrink-0 text-good-500">✓</span>;
  if (status === "WARNING") return <span className="mt-0.5 shrink-0 text-ember-400">⚠</span>;
  return <span className="mt-0.5 shrink-0 text-warn-500">✕</span>;
}
