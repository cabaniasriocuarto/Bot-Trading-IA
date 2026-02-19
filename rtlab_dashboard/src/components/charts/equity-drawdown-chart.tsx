"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function EquityDrawdownChart({
  data,
}: {
  data: Array<{ time: string; equity: number; drawdown: number; label?: string }>;
}) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="eqGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.45} />
              <stop offset="95%" stopColor="#22d3ee" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="ddGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f97316" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#f97316" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <YAxis yAxisId="equity" tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <YAxis yAxisId="drawdown" orientation="right" tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }}
            labelStyle={{ color: "#cbd5e1" }}
          />
          <Legend />
          <Area
            yAxisId="equity"
            type="monotone"
            dataKey="equity"
            stroke="#22d3ee"
            fill="url(#eqGradient)"
            name="Equity"
            strokeWidth={2}
          />
          <Area
            yAxisId="drawdown"
            type="monotone"
            dataKey="drawdown"
            stroke="#f97316"
            fill="url(#ddGradient)"
            name="Drawdown"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}


