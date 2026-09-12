import { deleteScenario, json, methodNotAllowed } from "../../lib/greensteel.js";
export default function handler(req, res) {
  if (req.method !== "DELETE") return methodNotAllowed(res, ["DELETE"]);
  try {
    const id = req.query?.scenario_id;
    if (!deleteScenario(id)) return json(res, 500, { detail: `No scenario found with id '${id}'.` });
    return json(res, 200, { deleted: true, id });
  } catch (error) { return json(res, 500, { detail: error.message }); }
}
