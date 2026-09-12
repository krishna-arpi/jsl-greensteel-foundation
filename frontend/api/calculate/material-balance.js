import { body, json, materialBalance, methodNotAllowed } from "../../lib/greensteel.js";
export default function handler(req, res) {
  if (req.method !== "POST") return methodNotAllowed(res, ["POST"]);
  try { return json(res, 200, materialBalance(body(req))); } catch (error) { return json(res, 500, { detail: error.message }); }
}
