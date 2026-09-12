import { allReferenceData, json, methodNotAllowed, validateReferenceData } from "../../lib/greensteel.js";

export default function handler(req, res) {
  if (req.method !== "GET") return methodNotAllowed(res, ["GET"]);
  try { const data = allReferenceData(); return json(res, 200, { data, validation_issues: validateReferenceData(data) }); }
  catch (error) { return json(res, 500, { detail: error.message }); }
}
