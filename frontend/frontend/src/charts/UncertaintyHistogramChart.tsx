import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HistogramBin } from "../types/calculator";

interface UncertaintyHistogramChartProps {
  histogram: HistogramBin[];
  mean: number;
  p5: number;
  p95: number;
}

export default function UncertaintyHistogramChart({ histogram, mean, p5, p95 }: UncertaintyHistogramChartProps) {
  const data = histogram.map((b) => ({
    name: `${b.bin_start.toFixed(2)}`,
    midpoint: (b.bin_start + b.bin_end) / 2,
    count: b.count,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid stroke="#2C3540" vertical={false} />
        <XAxis
          dataKey="name"
          stroke="#8B96A1"
          tick={{ fontSize: 10, fill: "#8B96A1" }}
          interval={Math.max(0, Math.floor(data.length / 8))}
          label={{ value: "tCO2e/t (bin start)", position: "insideBottom", offset: -2, fill: "#8B96A1", fontSize: 11 }}
        />
        <YAxis stroke="#8B96A1" tick={{ fontSize: 11, fill: "#8B96A1" }} label={{ value: "Count", angle: -90, position: "insideLeft", fill: "#8B96A1", fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            background: "#181D22",
            border: "1px solid #2C3540",
            borderRadius: 4,
            fontSize: 12,
            color: "#F2F4F6",
          }}
          formatter={(value: number) => [`${value} simulations`, "Count"]}
          labelFormatter={(label) => `~${label} tCO2e/t`}
        />
        <Bar dataKey="count" fill="#4C82AA" radius={[2, 2, 0, 0]} />
        <ReferenceLine x={data.find((d) => d.midpoint >= mean)?.name} stroke="#4C9A6A" strokeWidth={2} label={{ value: "Mean", position: "top", fill: "#4C9A6A", fontSize: 11 }} />
        <ReferenceLine x={data.find((d) => d.midpoint >= p5)?.name} stroke="#DB8A2C" strokeDasharray="4 3" label={{ value: "P5", position: "top", fill: "#DB8A2C", fontSize: 10 }} />
        <ReferenceLine x={data.find((d) => d.midpoint >= p95)?.name} stroke="#DB8A2C" strokeDasharray="4 3" label={{ value: "P95", position: "top", fill: "#DB8A2C", fontSize: 10 }} />
      </BarChart>
    </ResponsiveContainer>
  );
}
