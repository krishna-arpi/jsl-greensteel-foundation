import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Panel from "./Panel";
import KpiCard from "./KpiCard";
import { ApiError, fetchJslBenchmarks, fetchJslClimateTargets } from "../services/api";
import type { JslBenchmarkRecord, JslClimateTarget, OptimizationResult } from "../types/calculator";
import { formatNumber } from "../utils/format";

const OFFICIAL_BADGE = "OFFICIAL JSL DATA";
const DERIVED_BADGE = "MODEL-DERIVED";
const CALCULATED_BADGE = "CALCULATED";

interface Props {
  optimizationResult: OptimizationResult | null;
}

export default function JSLDecarbonizationTracker({ optimizationResult }: Props) {
  const [benchmarks, setBenchmarks] = useState<JslBenchmarkRecord[]>([]);
  const [targets, setTargets] = useState<JslClimateTarget[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchJslBenchmarks(), fetchJslClimateTargets()])
      .then(([benchmarkResponse, targetResponse]) => {
        setBenchmarks(benchmarkResponse.records);
        setTargets(targetResponse.records);
      })
      .catch((reason) => {
        setError(reason instanceof ApiError ? reason.message : "Could not load JSL benchmark data.");
      });
  }, []);

  const intensityRecords = useMemo(
    () => benchmarks.filter((record) => record.parameter === "Scope 1+2 GHG intensity"),
    [benchmarks]
  );
  const actual = intensityRecords.find((record) => record.financial_year === "FY2026");
  const target = targets[0];
  const absoluteGap = actual && target ? actual.value - target.derived_target_intensity : null;
  const remainingReduction =
    actual && target ? ((actual.value - target.derived_target_intensity) / actual.value) * 100 : null;
  const modelUsesTss = true;
  const distanceToTarget =
    !modelUsesTss && optimizationResult?.optimized_carbon_intensity != null && target
      ? optimizationResult.optimized_carbon_intensity - target.derived_target_intensity
      : null;

  const trend = [
    ...intensityRecords.map((record) => ({
      year: record.financial_year,
      intensity: record.value,
      kind: OFFICIAL_BADGE,
      source: record.source_url,
    })),
    ...(target
      ? [{ year: target.target_year, intensity: target.derived_target_intensity, kind: DERIVED_BADGE, source: target.source_url[0] }]
      : []),
  ];

  if (error) {
    return (
      <Panel title="JSL Decarbonization Target Tracker">
        <p className="text-sm text-warn-500">{error}</p>
      </Panel>
    );
  }

  if (!actual || !target) {
    return <Panel title="JSL Decarbonization Target Tracker">Loading official benchmarks and derived target…</Panel>;
  }

  return (
    <div className="space-y-4">
      <Panel title="JSL Decarbonization Target Tracker" eyebrow="Corporate benchmark context · tCO2e/tcs">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <KpiCard
            label="FY2026 Actual"
            value={formatNumber(actual.value, 2)}
            unit="tCO2e/tcs"
            accent="steel"
            sublabel={`FY2026 Official JSL Reported · ${OFFICIAL_BADGE} · ESG Factsheet`}
          />
          <KpiCard
            label="FY2035 Derived Target"
            value={formatNumber(target.derived_target_intensity, 2)}
            unit="tCO2e/tcs"
            accent="good"
            sublabel={`FY2035 Model-Derived Target · ${DERIVED_BADGE} · Annual Report / TCFD`}
          />
          <KpiCard
            label="Remaining Reduction"
            value={`${formatNumber(remainingReduction ?? 0, 2)}%`}
            unit=""
            accent="ember"
            sublabel={`Calculated Remaining Reduction · ${CALCULATED_BADGE}`}
          />
        </div>
        <p className="mt-3 text-[11px] text-ink-400">
          Actual source: <a className="text-steel-400 underline" href={actual.source_url} target="_blank" rel="noreferrer">JSL ESG Factsheet</a> ·
          Target source: <a className="text-steel-400 underline" href={target.source_url[0]} target="_blank" rel="noreferrer">JSL Integrated Annual Report</a>
        </p>
        <p className="mt-3 text-[12px] text-ink-300">
          Absolute gap: <span className="font-mono text-ink-100">{formatNumber(absoluteGap ?? 0, 2)} tCO2e/tcs</span>{" "}
          <Badge label={CALCULATED_BADGE} />
        </p>
        <p className="mt-2 text-[11px] text-ink-400">
          Baseline: <span className="font-mono text-ink-100">{formatNumber(target.baseline_intensity, 2)} {target.baseline_unit}</span>{" "}
          <Badge label={OFFICIAL_BADGE} /> · Reduction: <span className="font-mono text-ink-100">{formatNumber(target.target_reduction_percent, 0)}%</span>{" "}
          <Badge label={DERIVED_BADGE} /> ·{" "}
          <a className="text-steel-400 underline" href={target.source_url[0]} target="_blank" rel="noreferrer">target source</a>
        </p>
      </Panel>

      <Panel title="Reported intensity trend" eyebrow="Official reported series with derived FY2035 target">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={trend} margin={{ top: 8, right: 18, bottom: 8, left: 4 }}>
            <CartesianGrid stroke="#2C3540" />
            <XAxis dataKey="year" stroke="#8B96A1" tick={{ fontSize: 11, fill: "#8B96A1" }} />
            <YAxis
              stroke="#8B96A1"
              tick={{ fontSize: 11, fill: "#8B96A1" }}
              label={{ value: "tCO2e/tcs", angle: -90, position: "insideLeft", fill: "#8B96A1", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ background: "#181D22", border: "1px solid #2C3540", borderRadius: 4, fontSize: 12 }}
              formatter={(value: number, _name, item) => [
                `${value.toFixed(2)} tCO2e/tcs · ${item.payload.kind} · ${item.payload.source}`,
                "Intensity",
              ]}
            />
            <Line type="monotone" dataKey="intensity" stroke="#6FA6C9" strokeWidth={2} dot={{ r: 4 }} />
            <ReferenceDot
              x={target.target_year}
              y={target.derived_target_intensity}
              r={7}
              fill="#4C9A6A"
              stroke="#F2F4F6"
              strokeDasharray="3 3"
            />
          </LineChart>
        </ResponsiveContainer>
        <p className="text-[11px] text-ink-400">
          FY2022–FY2026 points: <Badge label={OFFICIAL_BADGE} /> · FY2035 point: <Badge label={DERIVED_BADGE} /> ·{" "}
          Sources are listed in each record below.
        </p>
      </Panel>

      <Panel title="JSL benchmark records" eyebrow="Official JSL reported data">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-[12px]">
            <thead className="border-b border-base-600 text-ink-400">
              <tr>
                <th className="px-2 py-2 font-medium">Financial year</th>
                <th className="px-2 py-2 font-medium">Parameter</th>
                <th className="px-2 py-2 font-medium">Value</th>
                <th className="px-2 py-2 font-medium">Scope</th>
                <th className="px-2 py-2 font-medium">Data class</th>
                <th className="px-2 py-2 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map((record) => (
                <tr key={`${record.financial_year}-${record.parameter}`} className="border-b border-base-600/60">
                  <td className="px-2 py-2 text-ink-200">{record.financial_year}</td>
                  <td className="px-2 py-2 text-ink-200">{record.parameter}</td>
                  <td className="px-2 py-2 font-mono text-ink-100">
                    {formatNumber(record.value, record.unit.includes("%") ? 2 : 2)} {record.unit}
                  </td>
                  <td className="px-2 py-2 text-ink-300">{record.scope}</td>
                  <td className="px-2 py-2"><Badge label={OFFICIAL_BADGE} /></td>
                  <td className="px-2 py-2">
                    <a className="text-steel-400 underline" href={record.source_url} target="_blank" rel="noreferrer">
                      {record.source}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[11px] text-ink-400">
          Confirmed: FY2026 Scope 1+2 intensity = <span className="font-mono text-ink-100">1.76 tCO2e/tcs</span>{" "}
          <Badge label={OFFICIAL_BADGE} />.
        </p>
      </Panel>

      <Panel title="Target comparison" eyebrow="Baseline → Optimized → Target">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ComparisonValue label="JSL FY2026" value={actual.value} unit="tCO2e/tcs" badge={OFFICIAL_BADGE} sourceUrl={actual.source_url} />
          <ComparisonValue
            label="Model Baseline"
            value={optimizationResult?.current_carbon_intensity}
            unit="tCO2e/tSS"
            badge="Scenario-level model result"
          />
          <ComparisonValue
            label="Model Optimized"
            value={optimizationResult?.optimized_carbon_intensity}
            unit="tCO2e/tSS"
            badge="Scenario-level model result"
          />
          <ComparisonValue
            label="FY2035 Derived Target"
            value={target.derived_target_intensity}
            unit="tCO2e/tcs"
            badge="Derived JSL target benchmark"
            sourceUrl={target.source_url[0]}
          />
        </div>
        {modelUsesTss ? (
          <p className="mt-4 rounded border border-warn-500/40 bg-warn-500/10 px-3 py-2 text-[12px] leading-relaxed text-warn-500">
            JSL benchmark is reported per tonne of crude steel (tcs). Align the system boundary and functional unit before direct comparison.
          </p>
        ) : (
          <p className="mt-4 text-[12px] text-ink-300">
            {distanceToTarget != null && distanceToTarget > 0
              ? "Additional reduction required to reach derived FY2035 target"
              : "Model scenario reaches or exceeds the derived target intensity"}
            {" · "}
            <Badge label={CALCULATED_BADGE} />
          </p>
        )}
      </Panel>

      <Panel title="Benchmark Sources">
        <ul className="space-y-2 text-[12px] text-ink-300">
          <li><SourceLink label="Jindal Stainless FY2025-26 ESG Factsheet (Official JSL reported data)" url="https://www.jindalstainless.com/esg-reports/" /></li>
          <li><SourceLink label="Jindal Stainless FY2025-26 Integrated Annual Report (Official JSL strategy and climate targets)" url="https://www.jindalstainless.com/annualreport/2025-2026/strategy.php" /></li>
          <li><SourceLink label="Jindal Stainless Climate Action Report (FY2022 baseline and 2035 target)" url="https://www.jindalstainless.com/wp-content/uploads/2025/10/JSL-TCFD-Report-2025.pdf" /></li>
        </ul>
      </Panel>
    </div>
  );
}

function ComparisonValue({
  label,
  value,
  unit,
  badge,
  sourceUrl,
}: {
  label: string;
  value?: number | null;
  unit: string;
  badge: string;
  sourceUrl?: string;
}) {
  return (
    <div className="rounded border border-base-600 bg-base-800 p-3">
      <p className="text-[10px] uppercase tracking-wide text-ink-400">{label}</p>
      <p className="mt-1 font-mono text-lg text-ink-100">{value == null ? "—" : formatNumber(value, 2)} <span className="text-[11px] text-ink-400">{unit}</span></p>
      <p className="mt-1 text-[10px] text-ink-400">{badge}</p>
      {sourceUrl && <a className="text-[10px] text-steel-400 underline" href={sourceUrl} target="_blank" rel="noreferrer">Source</a>}
    </div>
  );
}

function Badge({ label }: { label: string }) {
  return <span className="rounded-sm border border-base-600 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-ink-300">{label}</span>;
}

function SourceLink({ label, url }: { label: string; url: string }) {
  return <a className="text-steel-400 underline" href={url} target="_blank" rel="noreferrer">{label}</a>;
}
