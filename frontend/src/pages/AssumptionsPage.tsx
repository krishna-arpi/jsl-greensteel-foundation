import { useEffect, useState } from "react";
import Panel from "../components/Panel";
import DemoDataBadge from "../components/DemoDataBadge";
import { fetchReferenceData } from "../services/api";
import type { EmissionFactorEntry, ReferenceDataBundle } from "../types/referenceData";
import { formatNumber } from "../utils/format";

const CATEGORY_LABELS: Record<string, string> = {
  electricity: "Electricity",
  fuel: "Fuel",
  process_route: "Process route",
  alloy_addition: "Alloy addition",
  material_mix: "Scrap / virgin material",
};

const CALCULATION_STEPS: { title: string; body: string }[] = [
  {
    title: "1. Material balance",
    body:
      "Everything is scaled to the functional unit of 1 tonne of finished steel. Because some metal is lost as slag, dust, and fume, the furnace must be charged with slightly more than 1 tonne of material: charge_mass = 1 / yield. At a 92% yield, that's about 1.087 t charged per tonne of finished steel.",
  },
  {
    title: "2. Scrap/virgin calculation",
    body:
      "The charge mass is split between scrap and virgin (ore-based) material according to the chosen scrap percentage: scrap_mass = scrap% × charge_mass, and virgin_mass = (100% − scrap%) × charge_mass.",
  },
  {
    title: "3. Scrap chemistry",
    body:
      "Scrap isn't pure — it carries some Cr, Ni, and Mo from the alloy it used to be. The amount that actually survives into the melt is: element_mass = scrap_mass × element_fraction_in_scrap × recovery_rate. Recovery accounts for the fraction of that element that oxidizes or is lost rather than ending up in the finished steel.",
  },
  {
    title: "4. Alloy deficit",
    body:
      "The target grade specifies a minimum wt% for Cr, Ni, and Mo. If scrap alone doesn't supply enough of an element, the shortfall is a deficit: deficit = max(0, required_mass − supplied_mass). That deficit has to be made up with a purchased alloy addition (ferrochrome, nickel, or ferromolybdenum).",
  },
  {
    title: "5. Material emissions",
    body:
      "Every material entering the charge — scrap, virgin material, and each alloy addition — carries its own embodied emission factor (tCO2e per tonne of that material). Material carbon is simply the sum: CO2_material = Σ(material_quantity × its_emission_factor).",
  },
  {
    title: "6. Energy emissions",
    body:
      "Electricity, natural gas, and coal each have their own emission factor. For a single energy source: CO2_energy = consumption × emission_factor. For a blended energy mix, the factor is the share-weighted average: CO2_energy = consumption × Σ(share_of_source × its_emission_factor).",
  },
  {
    title: "7. Validation",
    body:
      "Before any result is presented, twelve checks confirm the configuration actually makes sense — scrap/virgin percentages sum to 100%, the material balance closes, yield is physically valid, no quantity is negative, energy shares sum to 100%, every required emission factor exists, and the final Cr/Ni/Mo composition satisfies the selected grade's limits. Each check reports PASS, WARNING, or ERROR, and a single ERROR blocks the result from being presented as final.",
  },
  {
    title: "8. Optimization",
    body:
      "An LP/MILP model (solved with PuLP) searches over the scrap/virgin split, the energy-source mix, and the alloy additions to minimize total carbon intensity, subject to the same grade-chemistry, availability, and mix constraints used everywhere else in this application. If no combination satisfies every constraint, it reports that no feasible solution exists rather than returning a number.",
  },
];

export default function AssumptionsPage() {
  const [refData, setRefData] = useState<ReferenceDataBundle | null>(null);

  useEffect(() => {
    fetchReferenceData()
      .then((res) => setRefData(res.data))
      .catch(() => setRefData(null));
  }, []);

  const factorsByCategory = groupByCategory(refData?.emission_factors.factors ?? []);

  return (
    <div className="space-y-4">
      <div className="border-b border-base-600 pb-4">
        <p className="text-[11px] uppercase tracking-wider text-steel-400">JSL GreenSteel</p>
        <h1 className="mt-0.5 text-xl font-semibold text-ink-100 sm:text-2xl">Methodology &amp; Sources</h1>
        <p className="mt-1 text-[13px] text-ink-300">
          What this application actually calculates, in plain engineering language — and exactly which
          numbers behind it are real versus illustrative.
        </p>
      </div>

      <Panel title="Data status" eyebrow="Read this before trusting any number in this app" action={<DemoDataBadge />}>
        <p className="text-[13px] leading-relaxed text-ink-300">
          Every emission factor used by the calculator — electricity, fuel, process route, alloy
          additions, and the scrap-vs-virgin embodied-emissions gap — is an illustrative
          placeholder, not a scientifically validated value. Each factor below discloses its
          own name, value, unit, year, scope, boundary, source, and confidence, so nothing here has
          to be taken on faith. Replace every value before using this tool for real reporting,
          target-setting, or investment decisions.
        </p>
      </Panel>

      <Panel title="Functional unit" eyebrow="Everything in this application is scaled to this">
        <p className="font-mono text-lg text-ink-100">1 tonne of finished stainless steel</p>
        <p className="mt-1 text-[13px] text-ink-300">
          Abbreviated tSS in results. All masses, energy figures, and emission totals are per tonne of
          finished steel unless stated otherwise.
        </p>
      </Panel>

      <Panel title="The model" eyebrow="What every calculator in this application ultimately computes">
        <pre className="whitespace-pre-wrap rounded bg-base-800 p-4 font-mono text-[13px] leading-relaxed text-ink-100">
{`Total Carbon =
    Material Carbon
  + Energy Carbon
  + Process Carbon`}
        </pre>
        <p className="mt-2 text-[12px] text-ink-400">
          Process Carbon is a configurable, exogenous term (a named process route's factor, or an
          explicit override) — it isn't derived from a decision variable the way material and energy
          carbon are.
        </p>
      </Panel>

      <Panel title="How each part is calculated" eyebrow="8 steps, from charge mix to optimization">
        <div className="space-y-4">
          {CALCULATION_STEPS.map((step) => (
            <div key={step.title}>
              <p className="text-[13px] font-medium text-ink-100">{step.title}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-300">{step.body}</p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Emission factor table" eyebrow="/data/emission_factors.json — every factor, fully disclosed">
        {refData ? (
          <div className="space-y-5">
            {Object.entries(factorsByCategory).map(([category, factors]) => (
              <div key={category}>
                <p className="mb-2 text-[11px] uppercase tracking-wide text-ink-400">
                  {CATEGORY_LABELS[category] ?? category}
                </p>
                <FactorTable factors={factors} />
              </div>
            ))}
          </div>
        ) : (
          <LoadingNote />
        )}
      </Panel>

      <Panel title="Three different kinds of benchmark — do not conflate them" eyebrow="Each has a different boundary and a different level of verification">
        {refData ? (
          <div className="space-y-4">
            <div className="rounded border border-steel-500/40 bg-steel-600/10 p-3">
              <p className="text-[13px] font-medium text-ink-100">1. JSL corporate benchmark</p>
              <p className="mt-1 text-[12px] leading-relaxed text-ink-300">
                A stated, company-wide reported figure — Scope 1+2 = {refData.baseline.corporate_benchmark.scope_1_plus_2.value}{" "}
                {refData.baseline.corporate_benchmark.unit}, Scope 3 = {refData.baseline.corporate_benchmark.scope_3.value}{" "}
                {refData.baseline.corporate_benchmark.unit}, derived total ={" "}
                {refData.baseline.corporate_benchmark.derived_reference_total.value} {refData.baseline.corporate_benchmark.unit} for{" "}
                {refData.baseline.corporate_benchmark.company}, {refData.baseline.corporate_benchmark.fiscal_year}. This is a
                company-wide figure, not a per-product or per-grade emission factor, and it is not used in the
                per-heat calculators elsewhere in this application.
              </p>
            </div>

            <div className="rounded border border-ember-500/40 bg-ember-500/10 p-3">
              <p className="text-[13px] font-medium text-ink-100">2. Stainless-steel LCA benchmark</p>
              <p className="mt-1 text-[12px] leading-relaxed text-ink-300">
                <strong>Not currently included in this application's dataset.</strong> A real implementation
                would source this from a stainless-specific life-cycle inventory — e.g. the International
                Stainless Steel Forum (ISSF) or a stainless-grade-specific EPD — since stainless production
                (with its Cr/Ni/Mo alloying and higher-recycled-content routes) has a materially different
                emissions profile from generic carbon steel. No such figure is fabricated here.
              </p>
            </div>

            <div className="rounded border border-carbon-500/40 bg-carbon-500/10 p-3">
              <p className="text-[13px] font-medium text-ink-100">3. Generic steel-route benchmark</p>
              <p className="mt-1 text-[12px] leading-relaxed text-ink-300">
                <strong>Not currently included in this application's dataset.</strong> A real implementation
                would cite a generic (crude carbon steel) benchmark here — e.g. worldsteel's LCI data for EAF or
                BOF routes. The DEMO_PLACEHOLDER material and process-route factors used by this application's
                calculators are illustrative numbers only: they are <em>not</em> sourced from worldsteel or any
                other published generic-steel dataset, and must never be presented as if they were — and,
                per the point above, they must never be presented as stainless-steel-specific either.
              </p>
            </div>
          </div>
        ) : (
          <LoadingNote />
        )}
      </Panel>

      <Panel title="Steel grades" eyebrow="/data/steel_grades.json">
        {refData ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {refData.steel_grades.grades.map((g) => (
              <div key={g.id} className="rounded border border-base-600 bg-base-800 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-medium text-ink-100">{g.grade_name}</span>
                  <span className="text-[10px] text-ink-400">
                    {g.family} · {g.status}
                  </span>
                </div>
                <p className="mt-1.5 font-mono text-[11px] text-ink-300">
                  Cr {g.Cr_min}–{g.Cr_max} · Ni {g.Ni_min}–{g.Ni_max} · Mo {g.Mo_min}–{g.Mo_max} · C ≤{g.C_max} · Si ≤
                  {g.Si_max} · Mn ≤{g.Mn_max}
                  {g.N_max != null ? ` · N ≤${g.N_max}` : ""}
                </p>
                <p className="mt-1 text-[11px] text-ink-400">{g.source}</p>
              </div>
            ))}
          </div>
        ) : (
          <LoadingNote />
        )}
      </Panel>

      <Panel title="Scrap quality categories" eyebrow="/data/scrap_quality.json">
        {refData ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {refData.scrap_quality.categories.map((s) => (
              <div key={s.id} className="rounded border border-base-600 bg-base-800 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-medium text-ink-100">{s.category_name}</span>
                  <span className="text-[10px] text-ink-400">{s.status}</span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-ink-400">{s.description}</p>
                <p className="mt-1.5 font-mono text-[11px] text-ink-300">
                  Cr {s.Cr} · Ni {s.Ni} · Mo {s.Mo} · Fe {s.Fe} · C {s.C} · Si {s.Si} · Mn {s.Mn} · N {s.N}
                </p>
                <p className="mt-1 text-[11px] text-ink-300">
                  Yield {formatNumber(s.yield, 0)}% · Alloy recovery {formatNumber(s.alloy_recovery, 0)}%
                </p>
              </div>
            ))}
          </div>
        ) : (
          <LoadingNote />
        )}
      </Panel>

      <Panel title="Model limitations" eyebrow="What this tool does not (yet) account for">
        <ul className="list-inside list-disc space-y-1.5 text-[13px] leading-relaxed text-ink-300">
          <li>Scrap composition varies — a real scrap lot's Cr/Ni/Mo content is a distribution, not a fixed number.</li>
          <li>Emission factors vary by geography and technology — a grid factor in one region or year is not another's.</li>
          <li>Energy consumption varies by operating conditions — furnace practice, campaign length, and equipment condition all matter.</li>
          <li>Alloy recovery varies — furnace practice and alloy form (lump, briquette, fines) affect how much of an addition actually reports to the melt.</li>
          <li>LCA allocation methodology affects scrap emissions — how upstream burden is allocated to scrap (cut-off vs. substitution vs. shared) changes its embodied factor.</li>
          <li>Corporate carbon intensity and product carbon footprint have different boundaries — a company-wide Scope 1+2+3 figure is not the same measurement as a per-tonne product footprint, and the two should never be swapped for each other.</li>
          <li>This is a decision-support prototype, not a verified ISO product carbon footprint.</li>
        </ul>
      </Panel>
    </div>
  );
}

function groupByCategory(factors: EmissionFactorEntry[]): Record<string, EmissionFactorEntry[]> {
  return factors.reduce<Record<string, EmissionFactorEntry[]>>((acc, f) => {
    (acc[f.category] ??= []).push(f);
    return acc;
  }, {});
}

function LoadingNote() {
  return <p className="text-[13px] text-ink-400">Loading…</p>;
}

function FactorTable({ factors }: { factors: EmissionFactorEntry[] }) {
  return (
    <table className="w-full text-left text-[12px]">
      <thead>
        <tr className="border-b border-base-600 text-ink-400">
          <th className="py-1.5 pr-3 font-normal">Parameter</th>
          <th className="py-1.5 pr-3 font-normal">Value</th>
          <th className="py-1.5 pr-3 font-normal">Unit</th>
          <th className="py-1.5 pr-3 font-normal">Year</th>
          <th className="py-1.5 pr-3 font-normal">Scope</th>
          <th className="py-1.5 pr-3 font-normal">Boundary</th>
          <th className="py-1.5 pr-3 font-normal">Source</th>
          <th className="py-1.5 font-normal">Confidence</th>
        </tr>
      </thead>
      <tbody>
        {factors.map((f) => (
          <tr key={f.id} className="border-b border-base-600/60 align-top">
            <td className="py-1.5 pr-3 text-ink-200">{f.name}</td>
            <td className="py-1.5 pr-3 whitespace-nowrap font-mono text-ink-100">{f.value}</td>
            <td className="py-1.5 pr-3 whitespace-nowrap text-ink-300">{f.unit}</td>
            <td className="py-1.5 pr-3 font-mono text-ink-300">{f.year ?? "—"}</td>
            <td className="py-1.5 pr-3 text-ink-300">{f.scope}</td>
            <td className="py-1.5 pr-3 text-ink-300">{f.boundary}</td>
            <td className="py-1.5 pr-3 text-ember-400">{f.source}</td>
            <td className="py-1.5 text-ink-300">{f.confidence}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
