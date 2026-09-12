import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface CarbonComparisonChartProps {
  currentValue: number;
  optimizedValue: number;
}

export default function CarbonComparisonChart({ currentValue, optimizedValue }: CarbonComparisonChartProps) {
  const data = [
    { name: "Current", value: currentValue, fill: "#DB8A2C" },
    { name: "Optimized", value: optimizedValue, fill: "#4C9A6A" },
  ];

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }}>
        <CartesianGrid stroke="#2C3540" horizontal={false} />
        <XAxis
          type="number"
          stroke="#8B96A1"
          tick={{ fontSize: 11, fill: "#8B96A1" }}
          label={{ value: "tCO2e / tSS", position: "insideBottom", offset: -2, fill: "#8B96A1", fontSize: 11 }}
        />
        <YAxis type="category" dataKey="name" width={80} stroke="#8B96A1" tick={{ fontSize: 12, fill: "#DCE1E6" }} />
        <Tooltip
          contentStyle={{
            background: "#181D22",
            border: "1px solid #2C3540",
            borderRadius: 4,
            fontSize: 12,
            color: "#F2F4F6",
          }}
          formatter={(value: number) => [`${value.toFixed(4)} tCO2e/tSS`, "Carbon intensity"]}
        />
        <Bar dataKey="value" radius={[0, 3, 3, 0]} barSize={36}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.fill} />
          ))}
          <LabelList dataKey="value" position="right" formatter={(v: number) => v.toFixed(3)} fill="#DCE1E6" fontSize={12} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
