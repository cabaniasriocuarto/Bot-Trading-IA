"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Line, LineChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet, apiPost } from "@/lib/client-api";
import type { BacktestRun, Strategy } from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

type RunForm = {
  strategy_id: string;
  start: string;
  end: string;
  symbols: string;
  fees_bps: string;
  spread_bps: string;
  slippage_bps: string;
  funding_bps: string;
  validation_mode: "walk-forward" | "purged-cv" | "cpcv";
};

const chartColors = ["#22d3ee", "#f97316", "#facc15", "#4ade80", "#f472b6"];

export default function BacktestsPage() {
  const { role } = useSession();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);

  const [form, setForm] = useState<RunForm>({
    strategy_id: "",
    start: "2024-01-01",
    end: "2024-12-31",
    symbols: "BTC/USDT,ETH/USDT",
    fees_bps: "5.5",
    spread_bps: "4.0",
    slippage_bps: "3.0",
    funding_bps: "1.0",
    validation_mode: "walk-forward",
  });

  const refresh = useCallback(async () => {
    const [stg, bt] = await Promise.all([
      apiGet<Strategy[]>("/api/v1/strategies"),
      apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
    ]);
    setStrategies(stg);
    setRuns(bt);
    if (!form.strategy_id && stg[0]) {
      setForm((prev) => ({ ...prev, strategy_id: stg[0].id }));
    }
  }, [form.strategy_id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const launchRun = async (event: FormEvent) => {
    event.preventDefault();
    setRunning(true);
    try {
      await apiPost("/api/v1/backtests/run", {
        strategy_id: form.strategy_id,
        period: { start: form.start, end: form.end },
        universe: form.symbols.split(",").map((x) => x.trim()),
        costs_model: {
          fees_bps: Number(form.fees_bps),
          spread_bps: Number(form.spread_bps),
          slippage_bps: Number(form.slippage_bps),
          funding_bps: Number(form.funding_bps),
        },
        validation_mode: form.validation_mode,
      });
      await refresh();
    } finally {
      setRunning(false);
    }
  };

  const toggleRun = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 5) return prev;
      return [...prev, id];
    });
  };

  const selectedRuns = runs.filter((run) => selected.includes(run.id)).slice(0, 5);

  const consistency = useMemo(() => {
    if (selectedRuns.length < 2) return null;
    const periods = new Set(selectedRuns.map((run) => `${run.period.start}|${run.period.end}`));
    const universes = new Set(selectedRuns.map((run) => [...run.universe].sort().join(",")));
    const costs = new Set(
      selectedRuns.map(
        (run) =>
          `${run.costs_model.fees_bps}|${run.costs_model.spread_bps}|${run.costs_model.slippage_bps}|${run.costs_model.funding_bps}`,
      ),
    );
    return {
      samePeriod: periods.size === 1,
      sameUniverse: universes.size === 1,
      sameCosts: costs.size === 1,
    };
  }, [selectedRuns]);

  const overlayData = useMemo(() => {
    if (!selectedRuns.length) return [];
    const map = new Map<number, Record<string, number | string>>();
    selectedRuns.forEach((run) => {
      run.equity_curve.forEach((point, idx) => {
        const row = map.get(idx) || { index: idx };
        row[run.id] = point.equity;
        map.set(idx, row);
      });
    });
    return [...map.values()];
  }, [selectedRuns]);

  const overlayDDData = useMemo(() => {
    if (!selectedRuns.length) return [];
    const map = new Map<number, Record<string, number | string>>();
    selectedRuns.forEach((run) => {
      run.equity_curve.forEach((point, idx) => {
        const row = map.get(idx) || { index: idx };
        row[run.id] = point.drawdown;
        map.set(idx, row);
      });
    });
    return [...map.values()];
  }, [selectedRuns]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Laboratorio de Estrategias</CardTitle>
        <CardDescription>Corre backtests y compara 2 a 5 corridas con misma ventana/universo/costos.</CardDescription>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" onSubmit={launchRun}>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Estrategia</label>
              <Select value={form.strategy_id} onChange={(e) => setForm((prev) => ({ ...prev, strategy_id: e.target.value }))}>
                {strategies.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name} v{row.version}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Desde</label>
              <Input type="date" value={form.start} onChange={(e) => setForm((prev) => ({ ...prev, start: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Hasta</label>
              <Input type="date" value={form.end} onChange={(e) => setForm((prev) => ({ ...prev, end: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Universo</label>
              <Input value={form.symbols} onChange={(e) => setForm((prev) => ({ ...prev, symbols: e.target.value }))} />
            </div>

            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Fees bps</label>
              <Input value={form.fees_bps} onChange={(e) => setForm((prev) => ({ ...prev, fees_bps: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Spread bps</label>
              <Input value={form.spread_bps} onChange={(e) => setForm((prev) => ({ ...prev, spread_bps: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Slippage bps</label>
              <Input value={form.slippage_bps} onChange={(e) => setForm((prev) => ({ ...prev, slippage_bps: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Funding bps</label>
              <Input value={form.funding_bps} onChange={(e) => setForm((prev) => ({ ...prev, funding_bps: e.target.value }))} />
            </div>

            <div className="space-y-1 xl:col-span-2">
              <label className="text-xs uppercase tracking-wide text-slate-400">Validacion</label>
              <Select
                value={form.validation_mode}
                onChange={(e) => setForm((prev) => ({ ...prev, validation_mode: e.target.value as RunForm["validation_mode"] }))}
              >
                <option value="walk-forward">Walk-Forward</option>
                <option value="purged-cv">Purged CV</option>
                <option value="cpcv">CPCV</option>
              </Select>
            </div>
            <div className="xl:col-span-2 flex items-end">
              <Button disabled={role !== "admin" || running}>{running ? "Corriendo..." : "Correr Backtest"}</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Corridas de Backtest</CardTitle>
        <CardDescription>Estado, duracion, hash de dataset, commit y export de artefactos.</CardDescription>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Comparar</TH>
                <TH>ID</TH>
                <TH>Estado</TH>
                <TH>Duracion</TH>
                <TH>Dataset Hash</TH>
                <TH>Commit</TH>
                <TH>Metricas</TH>
                <TH>Exportar</TH>
              </TR>
            </THead>
            <TBody>
              {runs.map((run) => (
                <TR key={run.id}>
                  <TD>
                    <input type="checkbox" checked={selected.includes(run.id)} onChange={() => toggleRun(run.id)} />
                  </TD>
                  <TD>{run.id}</TD>
                  <TD>
                    <Badge variant={run.status === "completed" ? "success" : run.status === "failed" ? "danger" : "warn"}>{run.status}</Badge>
                  </TD>
                  <TD>{run.duration_sec}s</TD>
                  <TD className="font-mono text-xs">{run.dataset_hash}</TD>
                  <TD className="font-mono text-xs">{run.git_commit}</TD>
                  <TD>
                    S:{fmtNum(run.metrics.sharpe)} D:{fmtPct(run.metrics.max_dd)} R:{fmtNum(run.metrics.robust_score)}
                  </TD>
                  <TD>
                    <div className="flex flex-col gap-1 text-xs text-cyan-300">
                      <a href={run.artifacts_links.report_json} className="underline">
                        report.json
                      </a>
                      <a href={run.artifacts_links.trades_csv} className="underline">
                        trades.csv
                      </a>
                      <a href={run.artifacts_links.equity_curve_csv} className="underline">
                        equity_curve.csv
                      </a>
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Overlay de Equity</CardTitle>
          <CardDescription>Superposicion de corridas seleccionadas (2 a 5).</CardDescription>
          <CardContent>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart data={overlayData}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="index" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  {selectedRuns.map((run, idx) => (
                    <Line key={run.id} type="monotone" dataKey={run.id} stroke={chartColors[idx % chartColors.length]} strokeWidth={2} dot={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Overlay de Drawdown</CardTitle>
          <CardDescription>Comparacion del perfil de riesgo entre corridas.</CardDescription>
          <CardContent>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart data={overlayDDData}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="index" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  {selectedRuns.map((run, idx) => (
                    <Line key={run.id} type="monotone" dataKey={run.id} stroke={chartColors[idx % chartColors.length]} strokeWidth={2} dot={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardTitle>Comparador de Metricas</CardTitle>
        <CardDescription>KPIs por corrida con chequeo de robustez y consistencia.</CardDescription>
        <CardContent className="space-y-3">
          {consistency ? (
            <div className="flex flex-wrap gap-2">
              <Badge variant={consistency.samePeriod ? "success" : "warn"}>Periodo {consistency.samePeriod ? "alineado" : "diferente"}</Badge>
              <Badge variant={consistency.sameUniverse ? "success" : "warn"}>Universo {consistency.sameUniverse ? "alineado" : "diferente"}</Badge>
              <Badge variant={consistency.sameCosts ? "success" : "warn"}>Costos {consistency.sameCosts ? "alineado" : "diferente"}</Badge>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Selecciona al menos 2 corridas para activar comparacion.</p>
          )}
          <Table>
            <THead>
              <TR>
                <TH>Run</TH>
                <TH>CAGR</TH>
                <TH>Max DD</TH>
                <TH>Sharpe</TH>
                <TH>Sortino</TH>
                <TH>Calmar</TH>
                <TH>Winrate</TH>
                <TH>Expectancy</TH>
                <TH>Avg Trade</TH>
                <TH>Turnover</TH>
                <TH>Robustez</TH>
              </TR>
            </THead>
            <TBody>
              {selectedRuns.map((run) => (
                <TR key={`cmp-${run.id}`}>
                  <TD>{run.id}</TD>
                  <TD>{fmtPct(run.metrics.cagr)}</TD>
                  <TD>{fmtPct(run.metrics.max_dd)}</TD>
                  <TD>{fmtNum(run.metrics.sharpe)}</TD>
                  <TD>{fmtNum(run.metrics.sortino)}</TD>
                  <TD>{fmtNum(run.metrics.calmar)}</TD>
                  <TD>{fmtPct(run.metrics.winrate)}</TD>
                  <TD>{fmtNum(run.metrics.expectancy)}</TD>
                  <TD>{fmtNum(run.metrics.avg_trade)}</TD>
                  <TD>{fmtNum(run.metrics.turnover)}</TD>
                  <TD>{fmtNum(run.metrics.robust_score)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
