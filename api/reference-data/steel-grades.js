import { data, json, methodNotAllowed } from "../../lib/greensteel.js";
export default function handler(req, res) {
  if (req.method !== "GET") return methodNotAllowed(res, ["GET"]);
  try { return json(res, 200, data("steel_grades")); } catch (error) { return json(res, 500, { detail: error.message }); }
}
