import { allReferenceData, data, json, methodNotAllowed, validateReferenceData } from "../lib/greensteel.js";

function route(req) {
  const queryRoute = req.query?.route;
  if (typeof queryRoute === "string") return queryRoute;
  const pathname = new URL(req.url || "", "http://localhost").pathname;
  return pathname.split("/").filter(Boolean).pop();
}

export default function handler(req, res) {
  if (req.method !== "GET") return methodNotAllowed(res, ["GET"]);
  try {
    switch (route(req)) {
      case "index":
      case "reference-data":
        {
          const referenceData = allReferenceData();
          return json(res, 200, {
            data: referenceData,
            validation_issues: validateReferenceData(referenceData),
          });
        }
      case "alloy-specifications":
        return json(res, 200, data("alloy_specifications"));
      case "jsl-benchmarks":
        return json(res, 200, data("JSL_BENCHMARKS"));
      case "jsl-climate-targets":
        return json(res, 200, data("JSL_CLIMATE_TARGETS"));
      case "baseline":
        return json(res, 200, data("baseline"));
      case "emission-factors":
        return json(res, 200, data("emission_factors"));
      case "energy-sources":
        return json(res, 200, data("energy_sources"));
      case "scrap-quality":
        return json(res, 200, data("scrap_quality"));
      case "steel-grades":
        return json(res, 200, data("steel_grades"));
      default:
        return json(res, 404, { detail: "Not found" });
    }
  } catch (error) {
    return json(res, 500, { detail: error.message });
  }
}
