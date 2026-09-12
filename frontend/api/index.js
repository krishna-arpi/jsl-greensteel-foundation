import { json, methodNotAllowed } from "../lib/greensteel.js";

export default function handler(req, res) {
  if (req.method !== "GET") return methodNotAllowed(res, ["GET"]);
  return json(res, 200, { service: "JSL GreenSteel - Carbon & Energy Optimization Calculator", status: "foundation build", docs: "/docs" });
}
