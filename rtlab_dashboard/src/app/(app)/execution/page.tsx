"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { apiGet } from "@/lib/client-api";
import type { ExecutionStats } from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

export default function ExecutionPage() {
  const [stats, setStats] = useState<ExecutionStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const exec = await apiGet<ExecutionStats>("/api/v1/execution/metrics");
        setStats(exec);
        setError("");
      } catch (err) {
        const message = err instanceof Error ? err.message : "No se pudo cargar ejecucion.";
        setError(message);
      }
    };
    void load();
  }, []);

  const latencySeries = useMemo(
    () =>
      (stats?.series || []).map((row, idx) => ({
        label: idx % 8 === 0 ? new Date(row.ts).toLocaleTimeString() : "",
        latency: row.latency_ms_p95,
        spread: row.spread_bps,
      })),
    [stats],
  );

  const qualityBars = useMemo(
    () => [
      { metric: "maker_ratio", value: (stats?.maker_ratio || 0) * 100 },
      { metric: "fill_ratio", value: (stats?.fill_ratio || 0) * 100 },
      { metric: "p95_slippage", value: stats?.p95_slippage || 0 },
      { metric: "p95_spread", value: stats?.p95_spread || 0 },
    ],
    [stats],
  );

  const hasData = Boolean(stats && stats.series.length > 0);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Ejecucion / Microestructura</CardTitle>
        <CardDescription>Calidad de fills, spread/slippage, latencia y salud operativa.</CardDescription>
      </Card>

      {error ? <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-300">{error}</p> : null}

      {!hasData ? (
        <Card>
          <CardContent>
            <p className="text-sm text-slate-300">Sin datos aun (ejecuta paper/testnet o backtest).</p>
          </CardContent>
        </Card>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Maker Ratio" value={stats ? fmtPct(stats.maker_ratio) : "--"} />
        <Metric label="Fill Ratio" value={stats ? fmtPct(stats.fill_ratio) : "--"} />
        <Metric label="Requotes / Cancels" value={stats ? `${stats.requotes} / ${stats.cancels}` : "--"} />
        <Metric label="Rate limits / API errors" value={stats ? `${stats.rate_limit_hits} / ${stats.api_errors}` : "--"} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Snapshot de Calidad de Ejecucion</CardTitle>
          <CardContent>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <BarChart data={qualityBars}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="metric" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Bar dataKey="value" fill="#22d3ee" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Traza de Latencia y Spread</CardTitle>
          <CardContent>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart data={latencySeries}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis yAxisId="left" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Line yAxisId="left" type="monotone" dataKey="latency" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="spread" stroke="#f97316" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardTitle>Notas Operativas</CardTitle>
        <CardContent className="space-y-2 text-sm text-slate-300">
          <p>
            Slippage real vs estimada: <strong>{stats ? `${fmtNum(stats.avg_slippage)} / ${fmtNum(stats.p95_slippage)} bps (avg/p95)` : "--"}</strong>
          </p>
          <p>
            Spread promedio y p95: <strong>{stats ? `${fmtNum(stats.avg_spread)} / ${fmtNum(stats.p95_spread)} bps` : "--"}</strong>
          </p>
          <p>
            Errores por endpoint/rate-limit: <strong>{stats ? `${stats.api_errors} errores API, ${stats.rate_limit_hits} rate-limit hits` : "--"}</strong>
          </p>
          {stats?.notes?.map((row, idx) => (
            <p key={`${row}-${idx}`}>- {row}</p>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardDescription>{label}</CardDescription>
      <CardTitle className="mt-1 text-lg">{value}</CardTitle>
    </Card>
  );
}
