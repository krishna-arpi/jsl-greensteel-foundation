import {
  body,
  deleteScenario,
  json,
  listScenarios,
  methodNotAllowed,
  saveScenario,
} from "../lib/greensteel.js";

function route(req) {
  const queryRoute = req.query?.route;
  if (typeof queryRoute === "string") return queryRoute;
  if (req.query?.scenario_id) return "detail";
  return "list";
}

export default function handler(req, res) {
  if (route(req) === "detail") {
    if (req.method !== "DELETE") return methodNotAllowed(res, ["DELETE"]);
    try {
      const id = req.query?.scenario_id;
      if (!deleteScenario(id)) return json(res, 500, { detail: `No scenario found with id '${id}'.` });
      return json(res, 200, { deleted: true, id });
    } catch (error) {
      return json(res, 500, { detail: error.message });
    }
  }

  try {
    if (req.method === "GET") return json(res, 200, { scenarios: listScenarios() });
    if (req.method === "POST") return json(res, 200, saveScenario(body(req)));
    return methodNotAllowed(res, ["GET", "POST"]);
  } catch (error) {
    return json(res, 500, { detail: error.message });
  }
}
