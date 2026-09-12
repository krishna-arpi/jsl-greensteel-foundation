import type { OptimizationResult } from "../types/calculator";

interface BeforeConfig {
  scrapPct: number;
  energySourceLabel: string;
  gradeName: string;
}

/**
 * Builds a plain-language explanation of why the optimized configuration is
 * better, entirely from the numbers in `result` and the caller-supplied
 * "before" state - no canned conclusion is asserted that isn't backed by an
 * actual computed delta.
 */
export function generateOptimizationExplanation(result: OptimizationResult, before: BeforeConfig): string {
  if (
    result.status !== "OPTIMAL" ||
    result.optimal_scrap_percentage == null ||
    result.optimal_energy_mix == null ||
    result.optimal_alloy_additions == null ||
    result.absolute_reduction == null ||
    result.percentage_reduction == null
  ) {
    return "";
  }

  const sentences: string[] = [];

  // --- Scrap/virgin mix change ---
  const scrapDelta = result.optimal_scrap_percentage - before.scrapPct;
  if (Math.abs(scrapDelta) > 0.5) {
    if (scrapDelta > 0) {
      sentences.push(
        `Increasing scrap from ${before.scrapPct.toFixed(1)}% to ${result.optimal_scrap_percentage.toFixed(1)}% reduced the requirement for carbon-intensive virgin material.`
      );
    } else {
      sentences.push(
        `Reducing scrap from ${before.scrapPct.toFixed(1)}% to ${result.optimal_scrap_percentage.toFixed(1)}% was necessary to keep the final composition within the grade's chemistry limits.`
      );
    }
  } else {
    sentences.push(`The scrap share (${result.optimal_scrap_percentage.toFixed(1)}%) was already close to optimal and did not change materially.`);
  }

  // --- Energy source change ---
  const dominant = [...result.optimal_energy_mix].sort((a, b) => b.share_pct - a.share_pct)[0];
  if (dominant) {
    const sameSource = dominant.label === before.energySourceLabel;
    if (!sameSource && dominant.share_pct > 0.5) {
      const coverage = dominant.share_pct < 99.5 ? ` covering ${dominant.share_pct.toFixed(0)}% of demand` : "";
      sentences.push(
        `The optimizer also selected a lower-carbon electricity source, switching from ${before.energySourceLabel} to ${dominant.label}${coverage}.`
      );
    } else if (sameSource) {
      sentences.push(`${before.energySourceLabel} was retained as the energy source since it was already the lowest-carbon option available under the current constraints.`);
    }
  }

  // --- Alloy additions ---
  const additions = result.optimal_alloy_additions.filter((a) => a.required_mass_kg > 0.01);
  if (additions.length > 0) {
    const list = additions.map((a) => `${a.required_mass_kg.toFixed(2)} kg of ${a.alloy_name}`).join(", ");
    sentences.push(`To maintain ${before.gradeName} chemistry at this composition, the optimizer added ${list} per tonne of steel.`);
  } else {
    sentences.push(`No additional alloy was required to satisfy ${before.gradeName}'s chemistry limits at this composition.`);
  }

  // --- Binding constraints ---
  if (result.binding_constraints.length > 0) {
    const descriptions = result.binding_constraints.map((b) => b.description).join(" ");
    sentences.push(`The solution is limited by the following active constraints: ${descriptions}`);
  }

  // --- Overall result ---
  if (result.absolute_reduction >= 0) {
    sentences.push(
      `Overall, these changes cut carbon intensity by ${result.absolute_reduction.toFixed(3)} tCO2e/tSS (${result.percentage_reduction.toFixed(1)}%) while maintaining grade chemistry and production constraints.`
    );
  } else {
    sentences.push(
      `The fully grade-compliant configuration carries a carbon intensity ${Math.abs(result.absolute_reduction).toFixed(3)} tCO2e/tSS higher than the stated current scenario, because the current scenario does not itself satisfy the grade's chemistry limits (see the note above) - it is not a like-for-like reduction.`
    );
  }

  return sentences.join(" ");
}
