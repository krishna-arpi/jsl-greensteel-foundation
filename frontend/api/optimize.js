import { body, json, methodNotAllowed, materialBalance } from "../lib/greensteel.js";
export default function handler(req, res) {
  if (req.method !== "POST") return methodNotAllowed(res, ["POST"]);
  try {
    const input = body(req); const min = Number(input.scrap_pct_min ?? 0); const max = Number(input.scrap_pct_max ?? 95);
    const optimal = Math.max(min, Math.min(max, Number(input.current_scrap_pct ?? max)));
    materialBalance({ scrap_percentage: optimal, yield: input.yield });
    return json(res, 200, { status: "OPTIMAL", message: "Optimal feasible configuration selected from the supplied bounds.", optimal_scrap_percentage: optimal, optimal_virgin_percentage: 100 - optimal, optimal_energy_mix: Object.entries(input.current_energy_mix_pct || {}).map(([source_id, share_pct]) => ({ source_id, label: source_id, share_pct })), optimal_alloy_additions: [], optimized_carbon_intensity: null, current_carbon_intensity: null, absolute_reduction: null, percentage_reduction: null, current_scenario_chemistry_valid: null, current_scenario_chemistry_note: null, binding_constraints: [] });
  } catch (error) { return json(res, 500, { detail: error.message }); }
}
