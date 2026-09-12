import { body, json, listScenarios, methodNotAllowed, saveScenario } from "../../lib/greensteel.js";
export default function handler(req, res) {
  try {
    if (req.method === "GET") return json(res, 200, { scenarios: listScenarios() });
    if (req.method === "POST") return json(res, 200, saveScenario(body(req)));
    return methodNotAllowed(res, ["GET", "POST"]);
  } catch (error) { return json(res, 500, { detail: error.message }); }
}
