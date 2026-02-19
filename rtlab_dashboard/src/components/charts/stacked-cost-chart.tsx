"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function StackedCostChart({
  data,
}: {
  data: Array<{ label: string; fees: number; slippage: number; funding: number }>;
}) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
          <Legend />
          <Bar dataKey="fees" stackId="cost" fill="#22d3ee" />
          <Bar dataKey="slippage" stackId="cost" fill="#f97316" />
          <Bar dataKey="funding" stackId="cost" fill="#facc15" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

