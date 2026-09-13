import { body, json, methodNotAllowed, data, round, evaluateConfiguration } from "../lib/greensteel.js";

export default function handler(req, res) {
  if (req.method !== "POST") return methodNotAllowed(res, ["POST"]);
  try {
    const input = body(req);
    const gradeId = input.grade_id;
    const scrapQualityId = input.scrap_quality_id;
    const yieldFraction = Number(input.yield);
    const energyDemand = Number(input.energy_demand_mwh_equivalent_per_t);
    const processRouteId = input.process_route_id || null;
    const min = Number(input.scrap_pct_min ?? 0);
    const max = Number(input.scrap_pct_max ?? 95);

    const currentScrapPct = Number(input.current_scrap_pct ?? 0);
    const currentEnergyMix = Object.entries(input.current_energy_mix_pct || {}).map(
      ([source_id, share_pct]) => ({ source_id, share_pct: Number(share_pct) })
    );

    const current = evaluateConfiguration({
      gradeId, scrapQualityId, scrapPct: currentScrapPct, yieldFraction,
      energyMix: currentEnergyMix, energyDemand, processRouteId,
    });

    const energySources = data("energy_sources").sources.map((s) => s.id);
    let best = null;
    for (let scrapPct = min; scrapPct <= max; scrapPct += 1) {
      for (const sourceId of energySources) {
        const point = evaluateConfiguration({
          gradeId, scrapQualityId, scrapPct, yieldFraction,
          energyMix: [{ source_id: sourceId, share_pct: 100 }],
          energyDemand, processRouteId,
        });
        if (!point.chemistry_valid) continue;
        if (!best || point.carbon_intensity < best.point.carbon_intensity) {
          best = { scrapPct, sourceId, point };
        }
      }
    }

    if (!best) {
      return json(res, 200, {
        status: "INFEASIBLE",
        message: "No configuration within the supplied scrap % bounds satisfies the grade chemistry limits.",
      });
    }

    const sourceMeta = data("energy_sources").sources.find((s) => s.id === best.sourceId);
    const absoluteReduction = round(current.carbon_intensity - best.point.carbon_intensity, 4);
    const percentageReduction = current.carbon_intensity !== 0
      ? round((absoluteReduction / current.carbon_intensity) * 100, 2)
      : 0;

    return json(res, 200, {
      status: "OPTIMAL",
      message: "Optimal feasible configuration selected from the supplied bounds.",
      optimal_scrap_percentage: round(best.scrapPct, 2),
      optimal_virgin_percentage: round(100 - best.scrapPct, 2),
      optimal_energy_mix: [{ source_id: best.sourceId, label: sourceMeta?.name || best.sourceId, share_pct: 100 }],
      optimal_alloy_additions: best.point.alloy_additions,
      optimized_carbon_intensity: best.point.carbon_intensity,
      current_carbon_intensity: current.carbon_intensity,
      absolute_reduction: absoluteReduction,
      percentage_reduction: percentageReduction,
      current_scenario_chemistry_valid: current.chemistry_valid,
      current_scenario_chemistry_note: current.chemistry_valid
        ? null
        : "The current configuration does not satisfy the grade's chemistry limits at the given scrap quality.",
      binding_constraints: [],
    });
  } catch (error) {
    return json(res, 500, { detail: error.message });
  }
}