import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SensitivityPoint } from "../types/calculator";

interface SensitivityBarChartProps {
  points: SensitivityPoint[];
}

export default function SensitivityBarChart({ points }: SensitivityBarChartProps) {
  const chartData = points.map((p) => ({
    name: p.label,
    value: p.carbon_intensity_tco2e_per_t,
    chemistryValid: p.chemistry_valid,
    isLowest: p.is_lowest_feasible,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 4 }}>
        <CartesianGrid stroke="#2C3540" vertical={false} />
        <XAxis dataKey="name" stroke="#8B96A1" tick={{ fontSize: 11, fill: "#8B96A1" }} />
        <YAxis
          stroke="#8B96A1"
          tick={{ fontSize: 11, fill: "#8B96A1" }}
          label={{ value: "tCO2e/t", angle: -90, position: "insideLeft", fill: "#8B96A1", fontSize: 11 }}
        />
        <Tooltip
          contentStyle={{
            background: "#181D22",
            border: "1px solid #2C3540",
            borderRadius: 4,
            fontSize: 12,
            color: "#F2F4F6",
          }}
          formatter={(value: number, _name: string, item) => [
            `${value.toFixed(4)} tCO2e/t${item.payload.chemistryValid ? "" : " (infeasible - fails grade chemistry)"}`,
            item.payload.isLowest ? "Lowest feasible" : "Carbon intensity",
          ]}
        />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>
          {chartData.map((entry, i) => (
            <Cell
              key={i}
              fill={!entry.chemistryValid ? "#5C6975" : entry.isLowest ? "#4C9A6A" : "#4C82AA"}
              fillOpacity={!entry.chemistryValid ? 0.4 : 1}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
