import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";

interface CarbonIntensityGaugeProps {
  value: number;
  /** Illustrative reference scale, not an industry-standard threshold. */
  maxScale?: number;
}

function zoneColor(value: number, maxScale: number): string {
  const ratio = value / maxScale;
  if (ratio <= 0.4) return "#4C9A6A"; // good
  if (ratio <= 0.7) return "#DB8A2C"; // ember
  return "#C4502A"; // warn
}

export default function CarbonIntensityGauge({ value, maxScale = 5 }: CarbonIntensityGaugeProps) {
  const clamped = Math.min(value, maxScale);
  const data = [{ name: "Carbon Intensity", value: clamped, fill: zoneColor(value, maxScale) }];

  return (
    <div className="relative flex flex-col items-center">
      <RadialBarChart
        width={220}
        height={150}
        cx={110}
        cy={130}
        innerRadius={80}
        outerRadius={110}
        barSize={16}
        data={data}
        startAngle={180}
        endAngle={0}
      >
        <PolarAngleAxis type="number" domain={[0, maxScale]} angleAxisId={0} tick={false} />
        <RadialBar background={{ fill: "#222931" }} dataKey="value" cornerRadius={8} angleAxisId={0} />
      </RadialBarChart>
      <div className="pointer-events-none absolute inset-x-0 top-[70px] text-center">
        <p className="font-mono text-2xl font-semibold text-ink-100">{value.toFixed(3)}</p>
        <p className="text-[10px] text-ink-400">tCO2e / tSS</p>
      </div>
      <p className="mt-1 text-[10px] text-ink-400">Illustrative 0–{maxScale} reference scale, not an industry threshold</p>
    </div>
  );
}
