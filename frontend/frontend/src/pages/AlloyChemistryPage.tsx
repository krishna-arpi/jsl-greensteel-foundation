import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import { ApiError, calculateScrapChemistry, fetchReferenceData } from "../services/api";
import type { ReferenceDataBundle } from "../types/referenceData";
import type { ScrapChemistryResult } from "../types/calculator";
import { formatNumber } from "../utils/format";

const ELEMENT_ORDER = ["Cr", "Ni", "Mo", "Fe", "C", "Si", "Mn", "N"] as const;

export default function AlloyChemistryPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [scrapQualityId, setScrapQualityId] = useState("");
  const [gradeId, setGradeId] = useState("");
  const [scrapMass, setScrapMass] = useState(0.7);

  const [result, setResult] = useState<ScrapChemistryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);

  useEffect(() => {
    fetchReferenceData()
      .then((res) => {
        setRefData(res.data);
        setScrapQualityId(res.data.scrap_quality.categories[0]?.id ?? "");
        setGradeId(res.data.steel_grades.grades[0]?.id ?? "");
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load reference data."));
  }, []);

  async function handleCalculate() {
    setCalculating(true);
    setError(null);
    try {
      const res = await calculateScrapChemistry({
        scrap_quality_id: scrapQualityId,
        scrap_mass: scrapMass,
        grade_id: gradeId,
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
    return <Panel title="Loading reference data…">Fetching grades and scrap quality categories.</Panel>;
  }

  const contribution = result ? (result.element_contribution as unknown as Record<string, number>) : null;

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
      <div className="space-y-4 xl:col-span-2">
        <Panel
          title="Scrap chemistry"
          eyebrow="Functional unit: 1 tonne of finished stainless steel"
          action={<DemoDataBadge />}
        >
          <p className="mb-4 text-[13px] leading-relaxed text-ink-300">
            Determines the element contribution from the selected scrap quality, compares it
            against the selected grade's Cr/Ni/Mo requirement, and computes the alloy additions
            needed to close any deficit. No emissions are calculated here.
          </p>

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

          <label className="mt-4 block">
            <span className="mb-1.5 block text-[12px] text-ink-300">Target grade</span>
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

          <label className="mt-4 block">
            <span className="mb-1.5 block text-[12px] text-ink-300">Scrap mass charged (t)</span>
            <input
              type="number"
              value={scrapMass}
              step={0.05}
              min={0}
              onChange={(e) => setScrapMass(parseFloat(e.target.value) || 0)}
              className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
            />
          </label>
          <p className="mt-1 text-[11px] text-ink-400">
            Typically the scrap_mass output from the Material Balance page. 0 t is a valid input — it models an
            all-virgin charge, where every alloying element must come from purchased alloy addition.
          </p>

          <button
            onClick={handleCalculate}
            disabled={calculating || !scrapQualityId || !gradeId || scrapMass < 0}
            className="mt-4 w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
          >
            {calculating ? "Calculating…" : "Calculate scrap chemistry"}
          </button>
          {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
        </Panel>

        {result && (
          <Panel title="Scrap composition used" eyebrow={result.scrap_chemistry.category_name}>
            <table className="w-full text-left text-[12px]">
              <tbody>
                {ELEMENT_ORDER.map((el) => (
                  <tr key={el} className="border-b border-base-600/60">
                    <td className="py-1 pr-3 text-ink-300">{el}</td>
                    <td className="py-1 font-mono text-ink-100">
                      {formatNumber((result.scrap_chemistry as unknown as Record<string, number>)[`${el}_pct`], 2)}%
                    </td>
                  </tr>
                ))}
                <tr>
                  <td className="pt-2 text-ink-300">Yield</td>
                  <td className="pt-2 font-mono text-ink-100">{result.scrap_chemistry.yield_pct}%</td>
                </tr>
                <tr>
                  <td className="text-ink-300">Alloy recovery</td>
                  <td className="font-mono text-ink-100">{result.scrap_chemistry.alloy_recovery_pct}%</td>
                </tr>
              </tbody>
            </table>
          </Panel>
        )}
      </div>

      <div className="space-y-4 xl:col-span-3">
        {!result && (
          <Panel title="Result">
            <p className="text-sm text-ink-400">Run the calculator to see results here.</p>
          </Panel>
        )}

        {result && (
          <>
            <Panel title="Element contribution from scrap" eyebrow="element_mass = scrap_mass × element_fraction × recovery">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-b border-base-600 text-ink-400">
                    <th className="py-1.5 pr-3 font-normal">Element</th>
                    <th className="py-1.5 font-normal">Mass supplied (t)</th>
                  </tr>
                </thead>
                <tbody>
                  {ELEMENT_ORDER.map((el) => (
                    <tr key={el} className="border-b border-base-600/60">
                      <td className="py-1.5 pr-3 text-ink-200">{el}</td>
                      <td className="py-1.5 font-mono text-ink-100">{formatNumber(contribution![`${el}_from_scrap`], 6)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <Panel title="Element deficits" eyebrow="Cr, Ni, Mo only · deficit = max(0, required − supplied)">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-b border-base-600 text-ink-400">
                    <th className="py-1.5 pr-3 font-normal">Element</th>
                    <th className="py-1.5 pr-3 font-normal">Required (t)</th>
                    <th className="py-1.5 pr-3 font-normal">Supplied (t)</th>
                    <th className="py-1.5 font-normal">Deficit (t)</th>
                  </tr>
                </thead>
                <tbody>
                  {result.element_deficits.map((d) => (
                    <tr key={d.element} className="border-b border-base-600/60">
                      <td className="py-1.5 pr-3 text-ink-200">{d.element}</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(d.required_mass, 6)}</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(d.supplied_mass, 6)}</td>
                      <td className={`py-1.5 font-mono ${d.deficit_mass > 0 ? "text-ember-400" : "text-good-500"}`}>
                        {formatNumber(d.deficit_mass, 6)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <Panel title="Alloy additions required" eyebrow="alloy_required = deficit / (concentration × recovery)">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-b border-base-600 text-ink-400">
                    <th className="py-1.5 pr-3 font-normal">Element</th>
                    <th className="py-1.5 pr-3 font-normal">Alloy</th>
                    <th className="py-1.5 pr-3 font-normal">Concentration</th>
                    <th className="py-1.5 pr-3 font-normal">Recovery</th>
                    <th className="py-1.5 font-normal">Required</th>
                  </tr>
                </thead>
                <tbody>
                  {result.alloy_additions.map((a) => (
                    <tr key={a.element} className="border-b border-base-600/60">
                      <td className="py-1.5 pr-3 text-ink-200">{a.element}</td>
                      <td className="py-1.5 pr-3 text-ink-300">{a.alloy_name}</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">{a.concentration_pct}%</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">{a.recovery_pct}%</td>
                      <td className="py-1.5 font-mono text-ink-100">{formatNumber(a.required_mass_kg, 2)} kg</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <Panel title="Final chemistry vs. grade validation" eyebrow={`Target grade: ${result.grade_id}`}>
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-b border-base-600 text-ink-400">
                    <th className="py-1.5 pr-3 font-normal">Element</th>
                    <th className="py-1.5 pr-3 font-normal">Final %</th>
                    <th className="py-1.5 pr-3 font-normal">Min</th>
                    <th className="py-1.5 pr-3 font-normal">Max</th>
                    <th className="py-1.5 font-normal">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {result.chemistry_validation.items.map((item) => (
                    <tr key={item.element} className="border-b border-base-600/60">
                      <td className="py-1.5 pr-3 text-ink-200">{item.element}</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-100">{formatNumber(item.actual_pct, 3)}%</td>
                      <td className="py-1.5 pr-3 font-mono text-ink-400">
                        {item.min_required_pct != null ? `${item.min_required_pct}%` : "—"}
                      </td>
                      <td className="py-1.5 pr-3 font-mono text-ink-400">
                        {item.max_allowed_pct != null ? `${item.max_allowed_pct}%` : "—"}
                      </td>
                      <td className="py-1.5">
                        <span
                          className={`rounded-sm px-1.5 py-0.5 text-[11px] font-medium ${
                            item.status === "PASS" ? "bg-good-500/10 text-good-500" : "bg-warn-500/10 text-warn-500"
                          }`}
                        >
                          {item.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p
                className={`mt-3 inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-[12px] font-medium ${
                  result.chemistry_validation.overall === "PASS"
                    ? "bg-good-500/10 text-good-500"
                    : "bg-warn-500/10 text-warn-500"
                }`}
              >
                Overall: {result.chemistry_validation.overall}
              </p>
            </Panel>
          </>
        )}
      </div>
    </div>
  );
}
