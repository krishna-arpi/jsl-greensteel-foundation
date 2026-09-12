import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface MaterialEmissionBar {
  label: string;
  tco2e: number;
  factorAvailable: boolean;
}

interface MaterialEmissionBarChartProps {
  items: MaterialEmissionBar[];
}

export default function MaterialEmissionBarChart({ items }: MaterialEmissionBarChartProps) {
  if (items.length === 0) {
    return <p className="py-8 text-center text-[13px] text-ink-400">No materials to show yet.</p>;
  }

  const chartData = items.map((item) => ({
    name: item.label,
    value: item.tco2e,
    factorAvailable: item.factorAvailable,
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(160, items.length * 44)}>
      <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
        <CartesianGrid stroke="#2C3540" horizontal={false} />
        <XAxis
          type="number"
          stroke="#8B96A1"
          tick={{ fontSize: 11, fill: "#8B96A1" }}
          label={{ value: "tCO2e", position: "insideBottom", offset: -2, fill: "#8B96A1", fontSize: 11 }}
        />
        <YAxis type="category" dataKey="name" width={130} stroke="#8B96A1" tick={{ fontSize: 11, fill: "#DCE1E6" }} />
        <Tooltip
          contentStyle={{
            background: "#181D22",
            border: "1px solid #2C3540",
            borderRadius: 4,
            fontSize: 12,
            color: "#F2F4F6",
          }}
          formatter={(value: number, _name: string, item) => [
            `${value.toFixed(4)} tCO2e${item.payload.factorAvailable ? "" : " (factor unavailable)"}`,
            "Emissions",
          ]}
        />
        <Bar dataKey="value" radius={[0, 2, 2, 0]}>
          {chartData.map((entry, i) => (
            <Cell key={i} fill={entry.factorAvailable ? "#4C82AA" : "#5C6975"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
