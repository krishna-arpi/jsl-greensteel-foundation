import { body, json, methodNotAllowed, materialBalance } from "../../lib/greensteel.js";
export default function handler(req, res) {
  if (req.method !== "POST") return methodNotAllowed(res, ["POST"]);
  try {
    const input = body(req);
    return json(res, 200, { status: "DEMO_PLACEHOLDER", format: "json", message: "The report inputs were accepted. Generate the PDF client-side or add a Node PDF renderer for binary report output.", material_balance: input.scrap_pct == null ? null : materialBalance({ scrap_percentage: input.scrap_pct, yield: input.yield }) });
  } catch (error) { return json(res, 500, { detail: error.message }); }
}
