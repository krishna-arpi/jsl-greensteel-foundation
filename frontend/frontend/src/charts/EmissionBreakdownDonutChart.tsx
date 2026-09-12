import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

export interface DonutSlice {
  name: string;
  value: number;
  color: string;
}

interface EmissionBreakdownDonutChartProps {
  slices: DonutSlice[];
  /** Total shown in the center of the donut, e.g. "1.474 tCO2e/t". */
  centerLabel?: string;
  centerSubLabel?: string;
}

export default function EmissionBreakdownDonutChart({
  slices,
  centerLabel,
  centerSubLabel,
}: EmissionBreakdownDonutChartProps) {
  const hasData = slices.some((s) => s.value > 0);

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={hasData ? slices : [{ name: "No data", value: 1, color: "#2C3540" }]}
            dataKey="value"
            nameKey="name"
            innerRadius="60%"
            outerRadius="85%"
            paddingAngle={hasData ? 2 : 0}
            stroke="none"
          >
            {(hasData ? slices : [{ name: "No data", value: 1, color: "#2C3540" }]).map((slice, i) => (
              <Cell key={i} fill={slice.color} />
            ))}
          </Pie>
          {hasData && (
            <Tooltip
              contentStyle={{
                background: "#181D22",
                border: "1px solid #2C3540",
                borderRadius: 4,
                fontSize: 12,
                color: "#F2F4F6",
              }}
              formatter={(value: number, name: string) => [`${value.toFixed(4)} tCO2e/t`, name]}
            />
          )}
          <Legend
            verticalAlign="bottom"
            height={36}
            iconSize={9}
            wrapperStyle={{ fontSize: 11, color: "#8B96A1" }}
          />
        </PieChart>
      </ResponsiveContainer>
      {centerLabel && (
        <div className="pointer-events-none absolute inset-x-0 top-[42%] -translate-y-1/2 text-center">
          <p className="font-mono text-lg font-semibold text-ink-100">{centerLabel}</p>
          {centerSubLabel && <p className="text-[10px] text-ink-400">{centerSubLabel}</p>}
        </div>
      )}
    </div>
  );
}
