interface KpiCardProps {
  label: string;
  value: string;
  unit: string;
  accent?: "steel" | "ember" | "good" | "neutral";
  sublabel?: string;
}

const ACCENT_CLASSES: Record<NonNullable<KpiCardProps["accent"]>, string> = {
  steel: "border-steel-500/40",
  ember: "border-ember-500/40",
  good: "border-good-500/40",
  neutral: "border-base-600",
};

export default function KpiCard({ label, value, unit, accent = "neutral", sublabel }: KpiCardProps) {
  return (
    <div className={`rounded border bg-base-700 p-4 shadow-panel ${ACCENT_CLASSES[accent]}`}>
      <p className="text-[11px] uppercase tracking-wide text-ink-400">{label}</p>
      <p className="mt-1.5 font-mono text-2xl font-semibold leading-none text-ink-100">
        {value}
        <span className="ml-1.5 text-sm font-normal text-ink-400">{unit}</span>
      </p>
      {sublabel && <p className="mt-1.5 text-[11px] text-ink-400">{sublabel}</p>}
    </div>
  );
}
