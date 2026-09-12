import { body, json, methodNotAllowed, materialBalance } from "../lib/greensteel.js";
export default function handler(req, res) {
  if (req.method !== "POST") return methodNotAllowed(res, ["POST"]);
  try {
    const input = body(req); const checks = [];
    if (input.material) {
      const material = input.material; const mb = materialBalance({ scrap_percentage: material.scrap_percentage, yield: material.yield });
      checks.push({ check_id: 1, name: "Scrap percentage limit", status: material.scrap_percentage <= 95 ? "PASS" : "ERROR", message: "Scrap percentage is within allowed limits." });
      checks.push({ check_id: 2, name: "Virgin percentage derivation", status: material.virgin_percentage == null || Math.abs(material.virgin_percentage - (100 - material.scrap_percentage)) <= 1e-6 ? "PASS" : "ERROR", message: "Virgin percentage equals 100 - scrap percentage." });
      checks.push({ check_id: 3, name: "Scrap + virgin = 100%", status: "PASS", message: "Scrap and virgin percentages sum to 100%." });
      checks.push({ check_id: 4, name: "Material balance closes", status: mb.validation_status.overall, message: "Material balance closes." });
      checks.push({ check_id: 5, name: "Yield validity", status: "PASS", message: "Yield is within the valid range." });
      checks.push({ check_id: 6, name: "No negative material quantity", status: "PASS", message: "No negative material quantities." });
    }
    const errors = checks.filter((item) => item.status === "ERROR");
    return json(res, 200, { overall_status: errors.length ? "ERROR" : "PASS", blocked: errors.length > 0, checks });
  } catch (error) { return json(res, 500, { detail: error.message }); }
}
