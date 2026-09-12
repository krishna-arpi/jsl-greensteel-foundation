import { useState } from "react";
import Panel from "../components/Panel";
import { ApiError, calculateMaterialBalance } from "../services/api";
import type { MaterialBalanceResult } from "../types/calculator";
import { formatNumber } from "../utils/format";

export default function MaterialBalancePage() {
  const [scrapPercentage, setScrapPercentage] = useState(65);
  const [yieldPct, setYieldPct] = useState(92); // shown to the user as a %, sent to the API as a fraction

  const [result, setResult] = useState<MaterialBalanceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);

  const virginPercentage = 100 - scrapPercentage;

  async function handleCalculate() {
    setCalculating(true);
    setError(null);
    try {
      const res = await calculateMaterialBalance({
        scrap_percentage: scrapPercentage,
        yield: yieldPct / 100,
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

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
      <div className="space-y-4 xl:col-span-2">
        <Panel title="Material balance" eyebrow="Functional unit: 1 tonne of finished stainless steel">
          <p className="mb-4 text-[13px] leading-relaxed text-ink-300">
            Pure mass accounting — computes how much scrap and virgin material must be charged
            to net 1 tonne of finished steel once furnace yield is accounted for. No emissions
            are calculated here.
          </p>

          <label className="block">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[12px] text-ink-300">Scrap percentage</span>
              <span className="font-mono text-[12px] text-ink-100">{formatNumber(scrapPercentage, 1)}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={0.5}
              value={scrapPercentage}
              onChange={(e) => setScrapPercentage(parseFloat(e.target.value))}
              className="w-full accent-steel-500"
            />
          </label>

          <p className="mt-1.5 text-[12px] text-ink-400">
            Virgin percentage (derived): <span className="font-mono text-ink-200">{formatNumber(virginPercentage, 1)}%</span>
          </p>

          <label className="mt-4 block">
            <span className="mb-1.5 block text-[12px] text-ink-300">Yield (%)</span>
            <input
              type="number"
              value={yieldPct}
              step={0.1}
              min={0.1}
              max={100}
              onChange={(e) => setYieldPct(parseFloat(e.target.value) || 0)}
              className="w-full rounded border border-base-600 bg-base-800 px-2.5 py-2 font-mono text-[13px] text-ink-100 outline-none focus:border-steel-500"
            />
          </label>
          <p className="mt-1 text-[11px] text-ink-400">
            Fraction of charged mass recovered as finished steel. Sent to the API as{" "}
            <code className="font-mono">{(yieldPct / 100).toFixed(4)}</code>.
          </p>

          <button
            onClick={handleCalculate}
            disabled={calculating || yieldPct <= 0 || yieldPct > 100}
            className="mt-4 w-full rounded bg-steel-500 py-2.5 text-sm font-medium text-base-900 transition-colors hover:bg-steel-400 disabled:cursor-not-allowed disabled:bg-base-600 disabled:text-ink-400"
          >
            {calculating ? "Calculating…" : "Calculate material balance"}
          </button>
          {error && <p className="mt-2 text-sm text-warn-500">{error}</p>}
        </Panel>
      </div>

      <div className="space-y-4 xl:col-span-3">
        <Panel title="Result" eyebrow="Mass per tonne of finished steel">
          {!result && <p className="text-sm text-ink-400">Run the calculator to see results here.</p>}
          {result && (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <MassFigure label="Charge mass" value={result.charge_mass} highlight />
                <MassFigure label="Scrap mass" value={result.scrap_mass} />
                <MassFigure label="Virgin mass" value={result.virgin_mass} />
              </div>

              <div className="mt-4 h-3 w-full overflow-hidden rounded-sm bg-base-800">
                <div className="flex h-full w-full">
                  <div
                    className="h-full bg-good-500"
                    style={{ width: `${result.scrap_percentage}%` }}
                    title={`Scrap ${result.scrap_percentage}%`}
                  />
                  <div
                    className="h-full bg-ember-500"
                    style={{ width: `${result.virgin_percentage}%` }}
                    title={`Virgin ${result.virgin_percentage}%`}
                  />
                </div>
              </div>
              <div className="mt-1.5 flex justify-between text-[11px] text-ink-400">
                <span>
                  <span className="mr-1 inline-block h-2 w-2 rounded-full bg-good-500" />
                  Scrap {formatNumber(result.scrap_percentage, 1)}%
                </span>
                <span>
                  <span className="mr-1 inline-block h-2 w-2 rounded-full bg-ember-500" />
                  Virgin {formatNumber(result.virgin_percentage, 1)}%
                </span>
              </div>

              <ul className="mt-4 space-y-1.5 border-t border-base-600 pt-3 text-[13px]">
                <li className="flex justify-between">
                  <span className="text-ink-300">Yield</span>
                  <span className="font-mono text-ink-100">{formatNumber(result.yield * 100, 2)}%</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-ink-300">Scrap %</span>
                  <span className="font-mono text-ink-100">{formatNumber(result.scrap_percentage, 2)}%</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-ink-300">Virgin %</span>
                  <span className="font-mono text-ink-100">{formatNumber(result.virgin_percentage, 2)}%</span>
                </li>
              </ul>

              <div className="mt-4 border-t border-base-600 pt-3">
                <p className="mb-2 text-[11px] uppercase tracking-wide text-ink-400">Validation status</p>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
                  <ValidationRow label="Mix sums to 100%" pass={result.validation_status.mix_sums_to_100} />
                  <ValidationRow label="Mass balance closes" pass={result.validation_status.mass_balance_closes} />
                  <ValidationRow label="No negative mass" pass={result.validation_status.no_negative_mass} />
                </div>
                <p
                  className={`mt-3 inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-[12px] font-medium ${
                    result.validation_status.overall === "PASS"
                      ? "bg-good-500/10 text-good-500"
                      : "bg-warn-500/10 text-warn-500"
                  }`}
                >
                  Overall: {result.validation_status.overall}
                </p>
              </div>
            </>
          )}
        </Panel>

        <Panel title="Formulae" eyebrow="How this is computed">
          <pre className="whitespace-pre-wrap rounded bg-base-800 p-3 font-mono text-[12px] leading-relaxed text-ink-300">
{`virgin_percentage = 100 - scrap_percentage
charge_mass       = 1 / yield
scrap_mass        = (scrap_percentage / 100) * charge_mass
virgin_mass       = (virgin_percentage / 100) * charge_mass`}
          </pre>
        </Panel>
      </div>
    </div>
  );
}

function MassFigure({ label, value, highlight = false }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`rounded border p-3 ${highlight ? "border-steel-500 bg-steel-600/10" : "border-base-600 bg-base-800"}`}>
      <p className="text-[11px] text-ink-400">{label}</p>
      <p className="mt-0.5 font-mono text-xl font-semibold text-ink-100">
        {formatNumber(value, 4)} <span className="text-xs font-normal text-ink-400">t</span>
      </p>
    </div>
  );
}

function ValidationRow({ label, pass }: { label: string; pass: boolean }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span className={`h-1.5 w-1.5 rounded-full ${pass ? "bg-good-500" : "bg-warn-500"}`} />
      <span className="text-ink-300">{label}</span>
    </div>
  );
}
