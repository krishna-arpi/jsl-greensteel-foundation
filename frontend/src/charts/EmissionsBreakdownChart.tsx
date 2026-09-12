import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EmissionBreakdownItem } from "../types/calculator";

interface EmissionsBreakdownChartProps {
  breakdown: EmissionBreakdownItem[];
}

export default function EmissionsBreakdownChart({ breakdown }: EmissionsBreakdownChartProps) {
  const chartData = breakdown.map((item) => ({
    name: item.label,
    value: item.tco2e_per_t,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
        <CartesianGrid stroke="#2C3540" horizontal={false} />
        <XAxis
          type="number"
          stroke="#8B96A1"
          tick={{ fontSize: 11, fill: "#8B96A1" }}
          label={{ value: "tCO2e / t steel", position: "insideBottom", offset: -2, fill: "#8B96A1", fontSize: 11 }}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={170}
          stroke="#8B96A1"
          tick={{ fontSize: 11, fill: "#DCE1E6" }}
        />
        <Tooltip
          contentStyle={{
            background: "#181D22",
            border: "1px solid #2C3540",
            borderRadius: 4,
            fontSize: 12,
            color: "#F2F4F6",
          }}
          formatter={(value: number) => [`${value.toFixed(3)} tCO2e/t`, "Emissions"]}
        />
        <Bar dataKey="value" fill="#4C82AA" radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
