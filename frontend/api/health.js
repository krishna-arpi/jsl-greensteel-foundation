import { json, methodNotAllowed } from "../lib/greensteel.js";

export default function handler(req, res) {
  if (req.method !== "GET") return methodNotAllowed(res, ["GET"]);
  return json(res, 200, { status: "ok", service: "jsl-greensteel-backend", data_status: "DEMO_PLACEHOLDER" });
}
