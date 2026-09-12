import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  implemented: boolean;
}

const navItems: NavItem[] = [
  { to: "/", label: "Executive Dashboard", implemented: true },
  { to: "/calculator", label: "Carbon Calculator", implemented: true },
  { to: "/material-balance", label: "Material Balance", implemented: true },
  { to: "/alloy-chemistry", label: "Alloy Chemistry", implemented: true },
  { to: "/emissions", label: "Emission Calculation", implemented: true },
  { to: "/optimization", label: "Carbon Optimization", implemented: true },
  { to: "/sensitivity", label: "Sensitivity Analysis", implemented: true },
  { to: "/scenarios", label: "Scenario Comparison", implemented: true },
  { to: "/validation", label: "Validation", implemented: true },
  { to: "/uncertainty", label: "Uncertainty Analysis", implemented: true },
  { to: "/assumptions", label: "Methodology & Sources", implemented: true },
];

export default function Sidebar() {
  return (
    <nav className="flex h-full w-60 shrink-0 flex-col border-r border-base-600 bg-base-800">
      <div className="border-b border-base-600 px-4 py-4">
        <p className="text-[11px] uppercase tracking-wider text-steel-400">JSL GreenSteel</p>
        <h1 className="mt-0.5 text-[15px] font-semibold leading-tight text-ink-100">
          Carbon &amp; Energy Optimization Calculator
        </h1>
      </div>
      <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {navItems.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `flex items-center justify-between rounded px-2.5 py-2 text-[13px] transition-colors ${
                  isActive
                    ? "bg-steel-600/20 text-ink-100"
                    : "text-ink-300 hover:bg-base-700 hover:text-ink-100"
                }`
              }
            >
              <span>{item.label}</span>
              {!item.implemented && (
                <span className="rounded-sm bg-base-600 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-ink-400">
                  Planned
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="border-t border-base-600 px-4 py-3 text-[11px] leading-snug text-ink-400">
        Problem Statement 3 — Carbon and Energy Calculator for Steelmaking. Foundation build.
      </div>
    </nav>
  );
}
