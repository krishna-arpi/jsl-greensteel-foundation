import {
  body,
  calculateCarbon,
  emissions,
  json,
  materialBalance,
  methodNotAllowed,
  scrapChemistry,
} from "../lib/greensteel.js";

function route(req) {
  const queryRoute = req.query?.route;
  if (typeof queryRoute === "string") return queryRoute;
  const pathname = new URL(req.url || "", "http://localhost").pathname;
  return pathname.split("/").filter(Boolean).pop();
}

export default function handler(req, res) {
  if (req.method !== "POST") return methodNotAllowed(res, ["POST"]);
  try {
    switch (route(req)) {
      case "carbon":
        return json(res, 200, calculateCarbon(body(req)));
      case "emissions":
        return json(res, 200, emissions(body(req)));
      case "material-balance":
        return json(res, 200, materialBalance(body(req)));
      case "scrap-chemistry":
        return json(res, 200, scrapChemistry(body(req)));
      default:
        return json(res, 404, { detail: "Not found" });
    }
  } catch (error) {
    return json(res, 500, { detail: error.message });
  }
}
