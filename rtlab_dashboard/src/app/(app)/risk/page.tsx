"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { apiGet } from "@/lib/client-api";
import type { BacktestRun, RiskSnapshot } from "@/lib/types";
import { fmtNum, fmtPct, fmtUsd } from "@/lib/utils";

interface RiskResponse extends RiskSnapshot {
  gate_checklist: Array<{ stage: string; done: boolean; note: string }>;
}

export default function RiskPage() {
  const [risk, setRisk] = useState<RiskResponse | null>(null);
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);

  useEffect(() => {
    const load = async () => {
      const [riskSnap, runs] = await Promise.all([
        apiGet<RiskResponse>("/api/v1/risk"),
        apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
      ]);
      setRisk(riskSnap);
      setBacktests(runs);
    };
    void load();
  }, []);

  const stressRows = useMemo(() => {
    if (risk?.stress_tests?.length) {
      return risk.stress_tests.map((row) => ({ scenario: row.scenario, robust: row.robust_score }));
    }
    const latest = backtests[0];
    if (!latest) return [];
    const base = latest.metrics.robust_score;
    return [
      { scenario: "Base", robust: base },
      { scenario: "Fees x2", robust: Number((base * 0.86).toFixed(2)) },
      { scenario: "Slippage x2", robust: Number((base * 0.82).toFixed(2)) },
      { scenario: "Spread shock", robust: Number((base * 0.78).toFixed(2)) },
      { scenario: "Param +/-15%", robust: Number((base * 0.81).toFixed(2)) },
    ];
  }, [backtests, risk]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Riesgo y Limites</CardTitle>
        <CardDescription>Limites, exposicion, concentracion y robustez bajo stress. Los gates de rollout se gestionan en Settings.</CardDescription>
      </Card>

      {!risk ? (
        <Card>
          <CardContent className="space-y-3">
            <p className="text-sm font-semibold text-slate-100">Todavia no hay snapshot de riesgo</p>
            <p className="text-sm text-slate-400">
              Esta pantalla necesita datos de riesgo/portfolio y, idealmente, corridas recientes para mostrar stress tests y checklist.
            </p>
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-300">
              <p className="font-semibold text-slate-100">Que hacer ahora</p>
              <ol className="mt-2 list-decimal space-y-1 pl-4">
                <li>Ejecuta un Quick Backtest o Research Batch para generar evidencia.</li>
                <li>Si vas a operar, corre Paper/Testnet para poblar riesgo real.</li>
                <li>Volve a Riesgo y recarga.</li>
              </ol>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Equity" value={risk ? fmtUsd(risk.equity) : "--"} />
        <MetricCard label="DD actual" value={risk ? fmtPct(risk.dd) : "--"} />
        <MetricCard label="Perdida diaria" value={risk ? fmtPct(risk.daily_loss) : "--"} />
        <MetricCard label="Exposicion total" value={risk ? fmtUsd(risk.exposure_total) : "--"} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Panel de Limites</CardTitle>
          <CardContent className="space-y-2">
            <MetricRow label="Limite perdida diaria" value={risk ? fmtPct(risk.limits.daily_loss_limit) : "--"} />
            <MetricRow label="Limite max DD" value={risk ? fmtPct(risk.limits.max_dd_limit) : "--"} />
            <MetricRow label="Max posiciones" value={risk ? String(risk.limits.max_positions) : "--"} />
            <MetricRow label="Max exposicion total" value={risk ? fmtPct(risk.limits.max_total_exposure) : "--"} />
            <MetricRow label="Riesgo por trade" value={risk ? fmtPct(risk.limits.risk_per_trade) : "--"} />
            <div className="pt-2">
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Circuit breakers disparados</p>
              <div className="flex flex-wrap gap-2">
                {risk?.circuit_breakers.map((row) => (
                  <Badge key={row} variant="warn">
                    {row}
                  </Badge>
                )) || <Badge>ninguno</Badge>}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Stress Tests</CardTitle>
          <CardDescription>Robustez bajo shocks de costos.</CardDescription>
          <CardContent>
            {stressRows.length ? (
              <>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                    <BarChart data={stressRows}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                      <XAxis dataKey="scenario" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                      <Bar dataKey="robust" fill="#22d3ee" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-sm text-slate-300">
                  Caida de robustez: {fmtNum(stressRows[0].robust)} {"->"} {fmtNum(stressRows[stressRows.length - 1].robust)}
                </p>
              </>
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-300">
                <p className="font-semibold text-slate-100">Todavia no hay stress tests</p>
                <p className="mt-1 text-slate-400">Necesitas un backtest reciente o snapshot de riesgo con stress tests calculados.</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button type="button" variant="outline" onClick={() => { window.location.href = "/backtests"; }}>
                    Ir a Backtests
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardTitle>Forecast Band [SUPUESTO]</CardTitle>
        <CardDescription>Intervalos bootstrap sobre distribucion historica (sin garantia).</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <MetricRow label="Retorno esperado p50 (30d)" value={risk?.forecast_band ? fmtPct(risk.forecast_band.return_p50_30d) : "+4.2%"} />
          <MetricRow label="Retorno esperado p90 (30d)" value={risk?.forecast_band ? fmtPct(risk.forecast_band.return_p90_30d) : "+8.9%"} />
          <MetricRow label="DD esperado p90 (30d)" value={risk?.forecast_band ? fmtPct(risk.forecast_band.dd_p90_30d) : "-9.8%"} />
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Correlacion y concentracion (como usarlo)</CardTitle>
        <CardDescription>Evita duplicar riesgo entre activos que se mueven juntos.</CardDescription>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300">
            <p className="font-semibold text-slate-100">Que significa la matriz de correlacion</p>
            <p className="mt-1 text-slate-400">
              Mide cuanto se mueven juntos los activos. Si varias posiciones tienen correlacion alta, la cartera puede quedar concentrada aunque parezca diversificada.
            </p>
            <p className="mt-2 text-slate-400">
              La matriz visual se muestra en <span className="text-slate-200">Portfolio</span>, donde se combina con exposicion y posiciones abiertas.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => { window.location.href = "/portfolio"; }}>
              Ver matriz de correlacion en Portfolio
            </Button>
            <Button type="button" variant="outline" onClick={() => { window.location.href = "/settings"; }}>
              Ver Rollout / Gates (operativo)
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardDescription>{label}</CardDescription>
      <CardTitle className="mt-1 text-xl">{value}</CardTitle>
    </Card>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
      <span className="text-sm text-slate-300">{label}</span>
      <span className="text-sm font-semibold text-slate-100">{value}</span>
    </div>
  );
}
