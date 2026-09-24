import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";

const root = process.cwd();
const dataCache = new Map();
export const round = (value, digits = 6) => Number(Number(value).toFixed(digits));

export function json(res, status, body) {
  return res.status(status).json(body);
}

export function methodNotAllowed(res, allowed) {
  res.setHeader("Allow", allowed.join(", "));
  return json(res, 405, { detail: `Method not allowed. Use ${allowed.join(" or ")}.` });
}

export function body(req) {
  if (req.body && typeof req.body === "object") return req.body;
  if (typeof req.body === "string") return JSON.parse(req.body);
  return {};
}

export function data(name) {
  if (!dataCache.has(name)) {
    const file = path.join(root, "data", `${name}.json`);
    if (!fs.existsSync(file)) throw new Error(`Reference data file not found: ${file}`);
    dataCache.set(name, JSON.parse(fs.readFileSync(file, "utf8")));
  }
  return dataCache.get(name);
}

export function allReferenceData() {
  return {
    emission_factors: data("emission_factors"),
    steel_grades: data("steel_grades"),
    scrap_quality: data("scrap_quality"),
    energy_sources: data("energy_sources"),
    baseline: data("baseline"),
    alloy_specifications: data("alloy_specifications"),
    jsl_benchmarks: data("JSL_BENCHMARKS"),
    jsl_climate_targets: data("JSL_CLIMATE_TARGETS"),
  };
}

export function validateReferenceData(reference) {
  const expected = {
    emission_factors: ["DEMO_PLACEHOLDER"],
    steel_grades: ["DEMO_PLACEHOLDER"],
    scrap_quality: ["DEMO_PLACEHOLDER"],
    energy_sources: ["DEMO_PLACEHOLDER"],
    baseline: ["STATED_INPUT", "DEMO_PLACEHOLDER"],
    alloy_specifications: ["DEMO_PLACEHOLDER"],
  };
  const issues = [];
  for (const [key, statuses] of Object.entries(expected)) {
    if (!reference[key]) issues.push({ field: key, message: "Missing reference data section.", severity: "error" });
    else if (!statuses.includes(reference[key]._meta?.status)) {
      issues.push({ field: key, message: `Reference data is missing an explicit status flag from ${statuses.join(", ")}.`, severity: "warning" });
    }
  }
  if (reference.baseline && reference.baseline.demo_scenario?._status !== "DEMO_PLACEHOLDER") {
    issues.push({ field: "baseline.demo_scenario", message: "baseline.json's demo_scenario block is missing its DEMO_PLACEHOLDER flag.", severity: "warning" });
  }
  if (!reference.baseline?.corporate_benchmark) {
    issues.push({ field: "baseline.corporate_benchmark", message: "baseline.json is missing the corporate_benchmark block.", severity: "error" });
  }
  return issues;
}

const factorIndex = () => Object.fromEntries(data("emission_factors").factors.map((item) => [item.id, item]));
const byId = (items, id, kind) => {
  const item = items.find((entry) => entry.id === id);
  if (!item) throw new Error(`Unknown ${kind} '${id}'.`);
  return item;
};
const grade = (id) => byId(data("steel_grades").grades, id, "grade_id");
const scrap = (id) => byId(data("scrap_quality").categories, id, "scrap_quality_id");

export function materialBalance(input) {
  const scrapPercentage = Number(input.scrap_percentage);
  const yieldFraction = Number(input.yield);
  if (!Number.isFinite(scrapPercentage) || !Number.isFinite(yieldFraction) || yieldFraction <= 0 || yieldFraction > 1) {
    throw new Error("scrap_percentage and yield are required; yield must be between 0 and 1.");
  }
  const virginPercentage = 100 - scrapPercentage;
  const chargeMass = 1 / yieldFraction;
  const scrapMass = (scrapPercentage / 100) * chargeMass;
  const virginMass = (virginPercentage / 100) * chargeMass;
  return {
    charge_mass: round(chargeMass), scrap_mass: round(scrapMass), virgin_mass: round(virginMass),
    scrap_percentage: round(scrapPercentage), virgin_percentage: round(virginPercentage),
    yield_fraction: round(yieldFraction),
    validation_status: {
      mix_sums_to_100: Math.abs(scrapPercentage + virginPercentage - 100) <= 1e-6,
      mass_balance_closes: Math.abs(scrapMass + virginMass - chargeMass) <= 1e-6,
      no_negative_mass: chargeMass >= 0 && scrapMass >= -1e-6 && virginMass >= -1e-6,
      overall: "PASS",
    },
  };
}

export function calculateCarbon(input) {
  const factors = factorIndex();
  grade(input.grade_id);
  scrap(input.scrap_quality_id);
  const find = (id, kind) => {
    if (!factors[id]) throw new Error(`Unknown ${kind} '${id}'.`);
    return factors[id];
  };
  const breakdown = [];
  const material = (Number(input.scrap_pct) / 100) * find("SCRAP_EMBODIED", "material factor").value +
    (Number(input.virgin_material_pct) / 100) * find("VIRGIN_EMBODIED", "material factor").value;
  breakdown.push({ category: "material_mix", label: "Scrap / virgin material mix", tco2e_per_t: round(material, 4), is_placeholder: true, note: "Weighted by scrap_pct / virgin_material_pct against placeholder embodied factors." });
  const electricity = Number(input.electricity_consumption_mwh_per_t) * find(input.electricity_source_id, "electricity_source_id").value;
  breakdown.push({ category: "electricity", label: "Electricity consumption", tco2e_per_t: round(electricity, 4), is_placeholder: true });
  const fuel = Number(input.fuel_consumption_gj_per_t) * find(input.fuel_source_id, "fuel_source_id").value;
  breakdown.push({ category: "fuel", label: "Fuel consumption", tco2e_per_t: round(fuel, 4), is_placeholder: true });
  const process = find(input.process_route_id, "process_route_id").value;
  breakdown.push({ category: "process_route", label: "Process route (direct/process emissions)", tco2e_per_t: round(process, 4), is_placeholder: true });
  const alloy = Object.entries(input.alloy_additions?.values_kg_per_t || {}).reduce((sum, [id, kg]) => sum + (Number(kg) / 1000) * find(id, "alloy id").value, 0);
  breakdown.push({ category: "alloy_additions", label: "Alloy additions", tco2e_per_t: round(alloy, 4), is_placeholder: true });
  return {
    status: "DEMO_PLACEHOLDER",
    warning: "All emission factors used are unverified placeholders.",
    total_tco2e_per_t: round(breakdown.reduce((sum, item) => sum + item.tco2e_per_t, 0), 4),
    breakdown, input_echo: input,
  };
}

const bounds = { Cr: ["Cr_min", "Cr_max"], Ni: ["Ni_min", "Ni_max"], Mo: ["Mo_min", "Mo_max"], C: [null, "C_max"], Si: [null, "Si_max"], Mn: [null, "Mn_max"], N: [null, "N_max"] };
export function chemistryValidation(values, target) {
  const items = Object.entries(bounds).map(([element, [minKey, maxKey]]) => {
    const actual = Number(values[element] || 0);
    const min = minKey ? target[minKey] ?? null : null;
    const max = maxKey ? target[maxKey] ?? null : null;
    const pass = (min === null || actual >= min - 1e-6) && (max === null || actual <= max + 1e-6);
    return { element, min_required_pct: min, max_allowed_pct: max, actual_pct: round(actual, 4), status: pass ? "PASS" : "FAIL" };
  });
  return { items, overall: items.every((item) => item.status === "PASS") ? "PASS" : "FAIL" };
}

const alloyFor = { Cr: "FERRO_CHROME", Ni: "NICKEL_METAL", Mo: "FERRO_MOLYBDENUM" };

export function evaluateConfiguration({ gradeId, scrapQualityId, scrapPct, yieldFraction, energyMix, energyDemand, processRouteId }) {
  const factors = factorIndex();
  const target = grade(gradeId);
  const selectedScrap = scrap(scrapQualityId);
  const charge = 1 / yieldFraction;
  const scrapMass = (scrapPct / 100) * charge;
  const virginMass = (1 - scrapPct / 100) * charge;

  let material = scrapMass * factors.SCRAP_EMBODIED.value + virginMass * factors.VIRGIN_EMBODIED.value;
  const finalPct = {};
  const alloyAdditions = [];

  for (const element of ["Cr", "Ni", "Mo"]) {
    const alloy = data("alloy_specifications").specifications.find((item) => item.id === alloyFor[element]);
    const supplied = (scrapMass * selectedScrap[element]) / 100 * (selectedScrap.alloy_recovery / 100);
    const required = (target[`${element}_min`] || 0) / 100;
    const deficit = Math.max(0, required - supplied);
    const massT = deficit / ((alloy.concentration_pct / 100) * (alloy.recovery_pct / 100));
    material += massT * factors[alloy.id].value;
    finalPct[element] = (supplied + massT * (alloy.concentration_pct / 100) * (alloy.recovery_pct / 100)) * 100;
    alloyAdditions.push({
      element,
      alloy_id: alloy.id,
      alloy_name: alloy.name,
      required_mass_t: round(massT),
      required_mass_kg: round(massT * 1000, 4),
    });
  }
  for (const element of ["C", "Si", "Mn", "N"]) {
    finalPct[element] = (scrapMass * selectedScrap[element]) / 100 * selectedScrap.alloy_recovery;
  }

  const chemistry = chemistryValidation(finalPct, target);

  let effectiveFactor = 0;
  for (const component of energyMix) {
    const factor = factors[component.source_id];
    if (!factor) continue;
    const value = factor.unit?.endsWith("/GJ") ? factor.value * 3.6 : factor.value;
    effectiveFactor += (component.share_pct / 100) * value;
  }
  const energyEmissions = energyDemand * effectiveFactor;
  const processEmissions = processRouteId ? factors[processRouteId]?.value || 0 : 0;
  const total = material + energyEmissions + processEmissions;

  return {
    carbon_intensity: round(total, 6),
    chemistry_valid: chemistry.overall === "PASS",
    alloy_additions: alloyAdditions,
  };
}

export function scrapChemistry(input) {
  const selectedScrap = scrap(input.scrap_quality_id);
  const target = grade(input.grade_id);
  const recovery = selectedScrap.alloy_recovery / 100;
  const elements = ["Cr", "Ni", "Mo", "Fe", "C", "Si", "Mn", "N"];
  const contribution = Object.fromEntries(elements.map((element) => [element, Number(input.scrap_mass) * selectedScrap[element] / 100 * recovery]));
  const specs = Object.fromEntries(data("alloy_specifications").specifications.map((item) => [item.id, item]));
  const alloyFor = { Cr: "FERRO_CHROME", Ni: "NICKEL_METAL", Mo: "FERRO_MOLYBDENUM" };
  const deficits = []; const additions = []; const alloyContribution = { Cr: 0, Ni: 0, Mo: 0 };
  for (const element of ["Cr", "Ni", "Mo"]) {
    const required = (target[`${element}_min`] || 0) / 100;
    const deficit = Math.max(0, required - contribution[element]);
    const spec = specs[alloyFor[element]];
    const mass = deficit / ((spec.concentration_pct / 100) * (spec.recovery_pct / 100));
    deficits.push({ element, required_mass: round(required), supplied_mass: round(contribution[element]), deficit_mass: round(deficit) });
    additions.push({ element, alloy_id: spec.id, alloy_name: spec.name, concentration_pct: spec.concentration_pct, recovery_pct: spec.recovery_pct, required_mass_t: round(mass), required_mass_kg: round(mass * 1000, 4) });
    alloyContribution[element] = mass * spec.concentration_pct / 100 * spec.recovery_pct / 100;
  }
  const final = Object.fromEntries(elements.map((element) => [element, contribution[element] + (alloyContribution[element] || 0)]));
  return {
    status: "DEMO_PLACEHOLDER", warning: "Scrap composition and alloy specification figures are unverified placeholders.",
    grade_id: target.id,
    scrap_chemistry: { scrap_quality_id: selectedScrap.id, category_name: selectedScrap.category_name, status: selectedScrap.status, ...Object.fromEntries(elements.map((e) => [`${e}_pct`, selectedScrap[e]])), yield_pct: selectedScrap.yield, alloy_recovery_pct: selectedScrap.alloy_recovery, source: selectedScrap.source },
    element_contribution: Object.fromEntries(elements.map((e) => [`${e}_from_scrap`, round(contribution[e])])),
    element_deficits: deficits, alloy_additions: additions,
    final_chemistry: elements.map((element) => ({ element, mass_t: round(final[element]), pct: round(final[element] * 100, 4) })),
    chemistry_validation: chemistryValidation(Object.fromEntries(elements.map((e) => [e, final[e] * 100])), target),
  };
}

export function emissions(input) {
  const factors = factorIndex(); const warnings = [];
  const materialItems = (input.materials || []).map((item) => {
    const factor = factors[item.material_id]; const label = item.label || factor?.name || item.material_id;
    if (!factor) { warnings.push(`No emission factor on file for material_id '${item.material_id}'.`); return { material_id: item.material_id, label, quantity_t: item.quantity_t, emission_factor_tco2e_per_t: null, tco2e: 0, factor_available: false, note: "Emission factor unavailable - excluded from total." }; }
    return { material_id: item.material_id, label, quantity_t: item.quantity_t, emission_factor_tco2e_per_t: factor.value, tco2e: round(item.quantity_t * factor.value), factor_available: true };
  });
  const mix = input.electricity_mix?.length ? input.electricity_mix : (input.electricity_source_id ? [{ source_id: input.electricity_source_id, share_pct: 100 }] : []);
  let effective = 0; const mixResults = mix.map((component) => {
    const factor = factors[component.source_id];
    if (!factor) { warnings.push(`No emission factor on file for electricity source '${component.source_id}'.`); return { source_id: component.source_id, label: component.source_id, share_pct: component.share_pct, emission_factor_tco2e_per_mwh: null, factor_available: false }; }
    effective += component.share_pct / 100 * factor.value;
    return { source_id: component.source_id, label: factor.name, share_pct: component.share_pct, emission_factor_tco2e_per_mwh: factor.value, factor_available: true };
  });
  const electricity = Number(input.electricity_consumption_mwh_per_t || 0) * effective;
  const fuelItem = (id, label, value) => factors[id] ? { fuel_id: id, label: factors[id].name, consumption_gj_per_t: value, emission_factor_tco2e_per_gj: factors[id].value, tco2e: round(value * factors[id].value), factor_available: true } : { fuel_id: id, label, consumption_gj_per_t: value, emission_factor_tco2e_per_gj: null, tco2e: 0, factor_available: false };
  const naturalGas = fuelItem("NATURAL_GAS", "Natural Gas", Number(input.natural_gas_consumption_gj_per_t || 0));
  const coal = fuelItem("COAL", "Coal", Number(input.coal_consumption_gj_per_t || 0));
  const process = input.process_emission_override_tco2e_per_t != null ? { tco2e_per_t: input.process_emission_override_tco2e_per_t, source: "override", process_route_id: null, factor_available: true } : { tco2e_per_t: factors[input.process_route_id]?.value || 0, source: "process_route", process_route_id: input.process_route_id || null, factor_available: Boolean(factors[input.process_route_id]) };
  const materialTotal = materialItems.reduce((sum, item) => sum + item.tco2e, 0);
  const fuelTotal = naturalGas.tco2e + coal.tco2e; const total = materialTotal + electricity + fuelTotal + process.tco2e_per_t;
  return { carbon_intensity_tCO2e_per_tSS: round(total), carbon_intensity_kgCO2e_per_tSS: round(total * 1000, 3), material_emissions: { total_tco2e: round(materialTotal), items: materialItems }, electricity_emissions: { total_tco2e: round(electricity), consumption_mwh_per_t: input.electricity_consumption_mwh_per_t || 0, mix: mixResults, effective_emission_factor_tco2e_per_mwh: mix.length ? round(effective) : null }, fuel_emissions: { total_tco2e: round(fuelTotal), natural_gas: naturalGas, coal }, process_emissions: process, emission_breakdown_by_material: materialItems, missing_factor_warnings: warnings };
}

export function saveScenario(input) {
  const record = { id: randomUUID().replaceAll("-", ""), created_at: new Date().toISOString(), ...input,
    grade_name: grade(input.grade_id).grade_name, scrap_quality_name: scrap(input.scrap_quality_id).category_name,
    energy_source_name: byId(data("energy_sources").sources, input.energy_source_id, "energy_source_id").name };
  const mb = materialBalance({ scrap_percentage: input.scrap_pct, yield: input.yield });
  const result = emissions({ materials: [{ material_id: "SCRAP_EMBODIED", quantity_t: mb.scrap_mass, label: "Scrap" }, { material_id: "VIRGIN_EMBODIED", quantity_t: mb.virgin_mass, label: "Virgin iron" }], electricity_consumption_mwh_per_t: input.electricity_consumption_mwh_per_t, electricity_source_id: input.energy_source_id, natural_gas_consumption_gj_per_t: input.natural_gas_consumption_gj_per_t, coal_consumption_gj_per_t: input.coal_consumption_gj_per_t });
  record.material_co2_tco2e_per_t = result.material_emissions.total_tco2e;
  record.energy_co2_tco2e_per_t = result.electricity_emissions.total_tco2e + result.fuel_emissions.total_tco2e;
  record.total_co2_tco2e_per_t = result.carbon_intensity_tCO2e_per_tSS;
  globalThis.__greensteelScenarios ||= []; globalThis.__greensteelScenarios.push(record); return record;
}
export const listScenarios = () => globalThis.__greensteelScenarios || [];
export function deleteScenario(id) { const before = listScenarios().length; globalThis.__greensteelScenarios = listScenarios().filter((item) => item.id !== id); return before !== globalThis.__greensteelScenarios.length; }

function simplifiedPoint({ gradeId, scrapQualityId, scrapPct, energySourceId, yieldFraction, energyDemand, processRouteId }) {
  const factors = factorIndex();
  const target = grade(gradeId);
  const selectedScrap = scrap(scrapQualityId);
  const charge = 1 / yieldFraction;
  const scrapMass = scrapPct / 100 * charge;
  const virginMass = (1 - scrapPct / 100) * charge;
  let material = scrapMass * factors.SCRAP_EMBODIED.value + virginMass * factors.VIRGIN_EMBODIED.value;
  const final = {};
  const alloyFor = { Cr: "FERRO_CHROME", Ni: "NICKEL_METAL", Mo: "FERRO_MOLYBDENUM" };
  for (const element of ["Cr", "Ni", "Mo"]) {
    const alloy = data("alloy_specifications").specifications.find((item) => item.id === alloyFor[element]);
    const supplied = scrapMass * selectedScrap[element] / 100 * selectedScrap.alloy_recovery / 100;
    const required = (target[`${element}_min`] || 0) / 100;
    const deficit = Math.max(0, required - supplied);
    const addition = deficit / (alloy.concentration_pct / 100 * alloy.recovery_pct / 100);
    material += addition * factors[alloy.id].value;
    final[element] = (supplied + addition * alloy.concentration_pct / 100 * alloy.recovery_pct / 100) * 100;
  }
  for (const element of ["C", "Si", "Mn", "N"]) final[element] = scrapMass * selectedScrap[element] / 100 * selectedScrap.alloy_recovery;
  const chemistry = chemistryValidation(final, target).overall === "PASS";
  const energyFactor = factors[energySourceId]?.value ?? 0;
  const normalizedEnergy = factors[energySourceId]?.unit?.endsWith("/GJ") ? energyFactor * 3.6 : energyFactor;
  const process = processRouteId ? (factors[processRouteId]?.value || 0) : 0;
  return { carbon: material + energyDemand * normalizedEnergy + process, chemistry };
}

function sensitivityAnalysis(input) {
  const base = {
    gradeId: input.grade_id, scrapQualityId: input.scrap_quality_id, scrapPct: Number(input.scrap_pct),
    energySourceId: input.energy_source_id, yieldFraction: Number(input.yield),
    energyDemand: Number(input.energy_demand_mwh_equivalent_per_t), processRouteId: input.process_route_id,
  };
  const make = (dimension, values, select) => {
    const points = values.map((value) => {
      const result = simplifiedPoint({ ...base, ...select(value) });
      return { label: String(value), value_id: String(value), carbon_intensity_tco2e_per_t: round(result.carbon, 6), chemistry_valid: result.chemistry, is_lowest_feasible: false };
    });
    const feasible = points.filter((point) => point.chemistry_valid);
    if (feasible.length) {
      const lowest = feasible.reduce((a, b) => a.carbon_intensity_tco2e_per_t < b.carbon_intensity_tco2e_per_t ? a : b);
      lowest.is_lowest_feasible = true;
    }
    return {
      dimension, baseline_note: "Other inputs are held at the supplied baseline.",
      points, insight: feasible.length ? `${feasible.length} of ${points.length} tested options satisfy the grade chemistry limits.` : "None of the tested options satisfy the grade chemistry limits.",
    };
  };
  const sources = ["GRID_ELECTRICITY_IN", "RENEWABLE_ELECTRICITY_IN", "NATURAL_GAS", "COAL"];
  return {
    status: "DEMO_PLACEHOLDER", warning: "Emission factors and compositions are illustrative DEMO_PLACEHOLDER values.",
    scrap_percentage_sweep: make("scrap_percentage", [0, 10, 20, 30, 40, 50, 60, 70, 80, 90], (value) => ({ scrapPct: value })),
    energy_source_sweep: make("energy_source", sources, (value) => ({ energySourceId: value })),
    scrap_quality_sweep: make("scrap_quality", data("scrap_quality").categories.map((item) => item.id), (value) => ({ scrapQualityId: value })),
    grade_sweep: make("grade", data("steel_grades").grades.map((item) => item.id), (value) => ({ gradeId: value })),
  };
}

function uncertaintyAnalysis(input) {
  const percentages = {
    emission_factor_uncertainty_pct: Number(input.emission_factor_uncertainty_pct ?? 15),
    scrap_composition_uncertainty_pct: Number(input.scrap_composition_uncertainty_pct ?? 10),
    yield_uncertainty_pct: Number(input.yield_uncertainty_pct ?? 3),
    alloy_recovery_uncertainty_pct: Number(input.alloy_recovery_uncertainty_pct ?? 5),
    energy_consumption_uncertainty_pct: Number(input.energy_consumption_uncertainty_pct ?? 10),
  };
  const nominal = simplifiedPoint({ gradeId: input.grade_id, scrapQualityId: input.scrap_quality_id, scrapPct: Number(input.scrap_pct), energySourceId: input.energy_source_id, yieldFraction: Number(input.yield), energyDemand: Number(input.energy_demand_mwh_equivalent_per_t), processRouteId: input.process_route_id }).carbon;
  const factorSpread = percentages.emission_factor_uncertainty_pct / 100;
  const energySpread = percentages.energy_consumption_uncertainty_pct / 100;
  const yieldSpread = percentages.yield_uncertainty_pct / 100;
  const best = nominal * (1 - factorSpread) * (1 - energySpread) * (1 - yieldSpread);
  const worst = nominal * (1 + factorSpread) * (1 + energySpread) * (1 + yieldSpread);
  let monteCarlo = null;
  if (input.run_monte_carlo !== false) {
    const count = Math.max(100, Math.min(20000, Number(input.n_simulations || 1000)));
    let seed = Number(input.random_seed || 12345);
    const random = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
    const values = Array.from({ length: count }, () => nominal * (1 - factorSpread + random() * factorSpread * 2) * (1 - energySpread + random() * energySpread * 2));
    values.sort((a, b) => a - b);
    const percentile = (pct) => values[Math.min(values.length - 1, Math.floor(values.length * pct))];
    const min = values[0], max = values[values.length - 1], binCount = 10, width = (max - min || 1) / binCount;
    const histogram = Array.from({ length: binCount }, (_, index) => ({ bin_start: round(min + index * width), bin_end: round(min + (index + 1) * width), count: values.filter((value) => value >= min + index * width && (index === binCount - 1 || value < min + (index + 1) * width)).length }));
    monteCarlo = { n_simulations: count, mean_tco2e_per_t: round(values.reduce((sum, value) => sum + value, 0) / count), median_tco2e_per_t: round(percentile(0.5)), min_tco2e_per_t: round(min), max_tco2e_per_t: round(max), p5_tco2e_per_t: round(percentile(0.05)), p95_tco2e_per_t: round(percentile(0.95)), histogram };
  }
  return { status: "DEMO_PLACEHOLDER", warning: "Uncertainty ranges are assumed spreads, not measured plant variability.", interpretation_note: "This represents model uncertainty, not measurement uncertainty.", uncertainty_ranges_used: percentages, best_case: { label: "Best Case", carbon_intensity_tco2e_per_t: round(best) }, base_case: { label: "Base Case", carbon_intensity_tco2e_per_t: round(nominal) }, worst_case: { label: "Worst Case", carbon_intensity_tco2e_per_t: round(worst) }, monte_carlo: monteCarlo };
}

export function genericAnalysis(input, kind) {
  return kind === "uncertainty" ? uncertaintyAnalysis(input) : sensitivityAnalysis(input);
}
