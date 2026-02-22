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
  market: "crypto" | "forex" | "equities";
  symbol: string;
  timeframe: "5m" | "10m" | "15m";
  start: string;
  end: string;
  fees_bps: string;
  spread_bps: string;
  slippage_bps: string;
  funding_bps: string;
  rollover_bps: string;
  validation_mode: "walk-forward" | "purged-cv" | "cpcv";
};

const chartColors = ["#22d3ee", "#f97316", "#facc15", "#4ade80", "#f472b6"];
const MARKET_OPTIONS: Record<RunForm["market"], string[]> = {
  crypto: ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"],
  forex: ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
  equities: ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA"],
};

type MetricGrade = "muy_malo" | "malo" | "aceptable" | "bueno" | "excelente";

const GRADE_CLASS: Record<MetricGrade, string> = {
  muy_malo: "bg-violet-600/25 text-violet-100 border border-violet-500/40",
  malo: "bg-red-600/25 text-red-100 border border-red-500/40",
  aceptable: "bg-orange-600/25 text-orange-100 border border-orange-500/40",
  bueno: "bg-yellow-500/25 text-yellow-50 border border-yellow-400/40",
  excelente: "bg-green-600/25 text-green-100 border border-green-500/40",
};

function gradeMetric(key: string, rawValue: number | undefined): MetricGrade | null {
  if (typeof rawValue !== "number" || Number.isNaN(rawValue)) return null;
  const value = key === "max_dd" ? Math.abs(rawValue) * 100 : ["cagr", "winrate"].includes(key) ? rawValue * 100 : rawValue;
  switch (key) {
    case "cagr":
      if (value < 0) return "muy_malo";
      if (value <= 10) return "malo";
      if (value <= 20) return "aceptable";
      if (value <= 40) return "bueno";
      return "excelente";
    case "max_dd":
      if (value > 50) return "muy_malo";
      if (value >= 30) return "malo";
      if (value >= 15) return "aceptable";
      if (value >= 8) return "bueno";
      return "excelente";
    case "sharpe":
      if (value < 0) return "muy_malo";
      if (value <= 0.5) return "malo";
      if (value <= 1.0) return "aceptable";
      if (value <= 2.0) return "bueno";
      return "excelente";
    case "sortino":
      if (value < 0) return "muy_malo";
      if (value <= 0.7) return "malo";
      if (value <= 1.5) return "aceptable";
      if (value <= 3.0) return "bueno";
      return "excelente";
    case "calmar":
      if (value < 0) return "muy_malo";
      if (value <= 0.5) return "malo";
      if (value <= 1.0) return "aceptable";
      if (value <= 3.0) return "bueno";
      return "excelente";
    case "winrate":
      if (value < 35) return "muy_malo";
      if (value <= 45) return "malo";
      if (value <= 55) return "aceptable";
      if (value <= 65) return "bueno";
      return "excelente";
    case "turnover":
      if (value > 10) return "muy_malo";
      if (value >= 5) return "malo";
      if (value >= 2) return "aceptable";
      if (value >= 0.8) return "bueno";
      return "excelente";
    case "robustness":
      if (value < 40) return "muy_malo";
      if (value <= 55) return "malo";
      if (value <= 70) return "aceptable";
      if (value <= 85) return "bueno";
      return "excelente";
    default:
      return null;
  }
}

function gradeCellClass(key: string, value: number | undefined): string {
  const grade = gradeMetric(key, value);
  return grade ? GRADE_CLASS[grade] : "";
}

export default function BacktestsPage() {
  const { role } = useSession();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);

  const [form, setForm] = useState<RunForm>({
    strategy_id: "",
    market: "crypto",
    symbol: "BTCUSDT",
    timeframe: "5m",
    start: "2024-01-01",
    end: "2024-12-31",
    fees_bps: "5.5",
    spread_bps: "4.0",
    slippage_bps: "3.0",
    funding_bps: "1.0",
    rollover_bps: "0.0",
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

  useEffect(() => {
    const symbols = MARKET_OPTIONS[form.market];
    if (!symbols.includes(form.symbol)) {
      setForm((prev) => ({ ...prev, symbol: symbols[0] }));
    }
  }, [form.market, form.symbol]);

  const launchRun = async (event: FormEvent) => {
    event.preventDefault();
    setRunning(true);
    try {
      await apiPost("/api/v1/backtests/run", {
        strategy_id: form.strategy_id,
        market: form.market,
        symbol: form.symbol,
        timeframe: form.timeframe,
        start: form.start,
        end: form.end,
        period: { start: form.start, end: form.end },
        universe: [form.symbol],
        costs: {
          fees_bps: Number(form.fees_bps),
          spread_bps: Number(form.spread_bps),
          slippage_bps: Number(form.slippage_bps),
          funding_bps: Number(form.funding_bps),
          rollover_bps: Number(form.rollover_bps),
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
  const focusRun = selectedRuns[0] || runs[0] || null;

  const tradeStatsForRun = (run: BacktestRun | null) => {
    if (!run) {
      return { totalEntries: 0, totalExits: 0, totalRoundtrips: 0, tradeCount: 0 };
    }
    const fallbackCount = run.trades?.length || 0;
    const totalEntries = run.metrics.total_entries ?? fallbackCount;
    const totalExits = run.metrics.total_exits ?? fallbackCount;
    const totalRoundtrips = run.metrics.total_roundtrips ?? Math.min(totalEntries, totalExits);
    const tradeCount = run.metrics.trade_count ?? fallbackCount;
    return { totalEntries, totalExits, totalRoundtrips, tradeCount };
  };

  const focusTradeStats = tradeStatsForRun(focusRun);

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
              <label className="text-xs uppercase tracking-wide text-slate-400">Mercado</label>
              <Select value={form.market} onChange={(e) => setForm((prev) => ({ ...prev, market: e.target.value as RunForm["market"] }))}>
                <option value="crypto">crypto</option>
                <option value="forex">forex</option>
                <option value="equities">equities</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Simbolo</label>
              <Select value={form.symbol} onChange={(e) => setForm((prev) => ({ ...prev, symbol: e.target.value }))}>
                {MARKET_OPTIONS[form.market].map((sym) => (
                  <option key={sym} value={sym}>
                    {sym}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Timeframe</label>
              <Select value={form.timeframe} onChange={(e) => setForm((prev) => ({ ...prev, timeframe: e.target.value as RunForm["timeframe"] }))}>
                <option value="5m">5m</option>
                <option value="10m">10m</option>
                <option value="15m">15m</option>
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
              <label className="text-xs uppercase tracking-wide text-slate-400">Rollover bps</label>
              <Input value={form.rollover_bps} onChange={(e) => setForm((prev) => ({ ...prev, rollover_bps: e.target.value }))} />
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
                <TH>Mercado</TH>
                <TH>Simbolo</TH>
                <TH>TF</TH>
                <TH>Entradas/Salidas</TH>
                <TH>Fuente</TH>
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
                  <TD>{run.market || "-"}</TD>
                  <TD>{run.symbol || run.universe?.[0] || "-"}</TD>
                  <TD>{run.timeframe || "-"}</TD>
                  <TD className="text-xs">
                    {tradeStatsForRun(run).totalEntries}/{tradeStatsForRun(run).totalExits} (RT {tradeStatsForRun(run).totalRoundtrips})
                  </TD>
                  <TD className="text-xs">{run.data_source || "-"}</TD>
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

      <Card>
        <CardTitle>Detalle de Corrida</CardTitle>
        <CardDescription>{focusRun ? `Run ${focusRun.id}` : "Sin corridas disponibles."}</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 md:col-span-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">Dataset</p>
            <p className="text-sm text-slate-200">
              {(focusRun?.market || "-")}/{(focusRun?.symbol || focusRun?.universe?.[0] || "-")} @ {focusRun?.timeframe || "-"} | fuente{" "}
              {focusRun?.data_source || "-"}
            </p>
            <p className="text-xs font-mono text-slate-400 break-all">{focusRun?.dataset_hash || "-"}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Cantidad de entradas</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.totalEntries}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Salidas</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.totalExits}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Roundtrips</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.totalRoundtrips}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Trade Count</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.tradeCount}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 md:col-span-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">Costos (del formulario)</p>
            <p className="text-sm text-slate-200">
              Fees {fmtNum(focusRun?.costs_breakdown?.fees_total ?? 0)} | Spread {fmtNum(focusRun?.costs_breakdown?.spread_total ?? 0)} | Slippage{" "}
              {fmtNum(focusRun?.costs_breakdown?.slippage_total ?? 0)} | Funding {fmtNum(focusRun?.costs_breakdown?.funding_total ?? 0)} | Rollover{" "}
              {fmtNum(focusRun?.costs_breakdown?.rollover_total ?? 0)}
            </p>
            <p className="text-xs text-slate-400">
              % sobre PnL bruto: fees {fmtPct(focusRun?.costs_breakdown?.fees_pct_of_gross_pnl ?? 0)} | spread{" "}
              {fmtPct(focusRun?.costs_breakdown?.spread_pct_of_gross_pnl ?? 0)} | slippage{" "}
              {fmtPct(focusRun?.costs_breakdown?.slippage_pct_of_gross_pnl ?? 0)} | funding{" "}
              {fmtPct(focusRun?.costs_breakdown?.funding_pct_of_gross_pnl ?? 0)} | rollover{" "}
              {fmtPct(focusRun?.costs_breakdown?.rollover_pct_of_gross_pnl ?? 0)}
            </p>
          </div>
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
          <div className="flex flex-wrap gap-2 text-xs text-slate-300">
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.muy_malo}`}>Violeta: Muy malo</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.malo}`}>Rojo: Malo</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.aceptable}`}>Naranja: Aceptable</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.bueno}`}>Amarillo: Bueno</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.excelente}`}>Verde: Excelente</span>
          </div>
          <Table>
            <THead>
              <TR>
                <TH>Run</TH>
                <TH>Cant. entradas</TH>
                <TH>CAGR</TH>
                <TH>Max DD</TH>
                <TH>Sharpe</TH>
                <TH>Sortino</TH>
                <TH>Calmar</TH>
                <TH>Winrate</TH>
                <TH>Expectancy USD</TH>
                <TH>Avg Trade</TH>
                <TH>Turnover</TH>
                <TH>Robustez</TH>
              </TR>
            </THead>
            <TBody>
              {selectedRuns.map((run) => (
                <TR key={`cmp-${run.id}`}>
                  <TD>{run.id}</TD>
                  <TD>{tradeStatsForRun(run).totalEntries}</TD>
                  <TD className={gradeCellClass("cagr", run.metrics.cagr)}>{fmtPct(run.metrics.cagr)}</TD>
                  <TD className={gradeCellClass("max_dd", run.metrics.max_dd)}>{fmtPct(run.metrics.max_dd)}</TD>
                  <TD className={gradeCellClass("sharpe", run.metrics.sharpe)}>{fmtNum(run.metrics.sharpe)}</TD>
                  <TD className={gradeCellClass("sortino", run.metrics.sortino)}>{fmtNum(run.metrics.sortino)}</TD>
                  <TD className={gradeCellClass("calmar", run.metrics.calmar)}>{fmtNum(run.metrics.calmar)}</TD>
                  <TD className={gradeCellClass("winrate", run.metrics.winrate)}>{fmtPct(run.metrics.winrate)}</TD>
                  <TD>{fmtNum(run.metrics.expectancy)}</TD>
                  <TD>{fmtNum(run.metrics.avg_trade)}</TD>
                  <TD className={gradeCellClass("turnover", run.metrics.turnover)}>{fmtNum(run.metrics.turnover)}</TD>
                  <TD className={gradeCellClass("robustness", run.metrics.robustness_score ?? run.metrics.robust_score)}>
                    {fmtNum(run.metrics.robustness_score ?? run.metrics.robust_score)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
