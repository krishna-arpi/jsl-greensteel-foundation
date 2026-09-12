import { useEffect, useState } from "react";
import { fetchHealth } from "../services/api";
import DemoDataBadge from "./DemoDataBadge";

type ConnectionState = "checking" | "connected" | "offline";

export default function TopBar() {
  const [state, setState] = useState<ConnectionState>("checking");

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then(() => {
        if (!cancelled) setState("connected");
      })
      .catch(() => {
        if (!cancelled) setState("offline");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-base-600 bg-base-800 px-4">
      <div className="flex items-center gap-3">
        <DemoDataBadge label="ALL FACTORS ARE PLACEHOLDER" />
      </div>
      <div className="flex items-center gap-2 text-[12px]">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            state === "connected" ? "bg-good-500" : state === "offline" ? "bg-warn-500" : "bg-ink-400"
          }`}
        />
        <span className="text-ink-300">
          {state === "connected" && "Backend connected"}
          {state === "offline" && "Backend unreachable — start the FastAPI server"}
          {state === "checking" && "Checking backend…"}
        </span>
      </div>
    </header>
  );
}
