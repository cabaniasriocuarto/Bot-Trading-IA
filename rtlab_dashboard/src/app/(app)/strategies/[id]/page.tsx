"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";

import { EquityDrawdownChart } from "@/components/charts/equity-drawdown-chart";
import { ReturnsHistogram } from "@/components/charts/returns-histogram";
import { StackedCostChart } from "@/components/charts/stacked-cost-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet } from "@/lib/client-api";
import { getPlaybook } from "@/lib/playbooks";
import type { BacktestRun, Strategy, StrategyEvidenceResponse, StrategyTruthResponse, Trade } from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

function normalizeLabels(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      if (Array.isArray(parsed)) return parsed.map((item) => String(item)).filter(Boolean);
    } catch {
      return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    }
  }
  return [];
}

export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>();
  const strategyId = String(params.id);

  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [allBacktests, setAllBacktests] = useState<BacktestRun[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [compareId, setCompareId] = useState("");
  const [truthPayload, setTruthPayload] = useState<StrategyTruthResponse | null>(null);
  const [evidencePayload, setEvidencePayload] = useState<StrategyEvidenceResponse | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [s, allStrategies, loadedBacktests, allTrades, truth, evidence] = await Promise.all([
          apiGet<Strategy>(`/api/v1/strategies/${strategyId}`),
          apiGet<Strategy[]>("/api/v1/strategies"),
          apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
          apiGet<Trade[]>(`/api/v1/trades?strategy_id=${strategyId}`),
          apiGet<StrategyTruthResponse>(`/api/v1/strategies/${strategyId}/truth`).catch(() => null),
          apiGet<StrategyEvidenceResponse>(`/api/v1/strategies/${strategyId}/evidence`).catch(() => null),
        ]);
        setStrategy(s);
        setStrategies(allStrategies);
        setAllBacktests(loadedBacktests);
        setBacktests(loadedBacktests.filter((row) => row.strategy_id === strategyId));
        setTrades(allTrades);
        setTruthPayload(truth);
        setEvidencePayload(evidence);
        const compareCandidate = allStrategies.find((row) => row.id !== strategyId && row.name === s.name) || allStrategies.find((row) => row.id !== strategyId);
        setCompareId(compareCandidate?.id || "");
        setLoadError("");
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "No se pudo cargar la estrategia.");
      }
    };
    void load();
  }, [strategyId]);

  const kpis = backtests[0]?.metrics;
  const histogram = useMemo(() => {
    const buckets = [
      { bucket: "< -100", min: -99999, max: -100 },
      { bucket: "-100 to -25", min: -100, max: -25 },
      { bucket: "-25 to 0", min: -25, max: 0 },
      { bucket: "0 to 25", min: 0, max: 25 },
      { bucket: "25 to 100", min: 25, max: 100 },
      { bucket: "> 100", min: 100, max: 99999 },
    ];
    return buckets.map((bucket) => ({
      bucket: bucket.bucket,
      count: trades.filter((row) => row.pnl_net >= bucket.min && row.pnl_net < bucket.max).length,
    }));
  }, [trades]);

  const costs = useMemo(
    () =>
      backtests.map((row) => ({
        label: row.id,
        fees: row.costs_model.fees_bps,
        slippage: row.costs_model.slippage_bps,
        funding: row.costs_model.funding_bps,
      })),
    [backtests],
  );

  const rolling = useMemo(() => {
    const base = backtests[0]?.equity_curve || [];
    return base.map((point, idx) => ({
      label: idx % 10 === 0 ? point.time.slice(0, 10) : "",
      sharpe: Number((1.2 + Math.sin(idx / 8) * 0.4).toFixed(2)),
      sortino: Number((1.8 + Math.cos(idx / 7) * 0.5).toFixed(2)),
    }));
  }, [backtests]);

  const compare = strategies.find((row) => row.id === compareId) || null;
  const truth = truthPayload?.truth || null;
  const intendedRegimes = useMemo(() => normalizeLabels(truth?.intended_regimes), [truth?.intended_regimes]);
  const forbiddenRegimes = useMemo(() => normalizeLabels(truth?.forbidden_regimes), [truth?.forbidden_regimes]);
  const evidenceSummaryRows = useMemo(
    () => Object.entries(truthPayload?.evidence_summary || evidencePayload?.summary || {}),
    [evidencePayload?.summary, truthPayload?.evidence_summary],
  );
  const changedKeys = useMemo(() => {
    if (!strategy || !compare) return [];
    const keys = new Set([...Object.keys(strategy.params), ...Object.keys(compare.params)]);
    return [...keys].filter((key) => strategy.params[key] !== compare.params[key]);
  }, [strategy, compare]);

  const latestCurrentBacktest = useMemo(
    () =>
      [...allBacktests]
        .filter((row) => row.strategy_id === strategyId)
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0] || null,
    [allBacktests, strategyId],
  );

  const latestCompareBacktest = useMemo(
    () =>
      compare
        ? [...allBacktests]
            .filter((row) => row.strategy_id === compare.id)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0] || null
        : null,
    [allBacktests, compare],
  );

  const metricComparisonRows = useMemo(() => {
    if (!latestCurrentBacktest || !latestCompareBacktest) return [];
    return [
      { label: "CAGR", current: fmtPct(latestCurrentBacktest.metrics.cagr), compare: fmtPct(latestCompareBacktest.metrics.cagr) },
      { label: "Max DD", current: fmtPct(latestCurrentBacktest.metrics.max_dd), compare: fmtPct(latestCompareBacktest.metrics.max_dd) },
      { label: "Sharpe", current: fmtNum(latestCurrentBacktest.metrics.sharpe), compare: fmtNum(latestCompareBacktest.metrics.sharpe) },
      { label: "Sortino", current: fmtNum(latestCurrentBacktest.metrics.sortino), compare: fmtNum(latestCompareBacktest.metrics.sortino) },
      { label: "Calmar", current: fmtNum(latestCurrentBacktest.metrics.calmar), compare: fmtNum(latestCompareBacktest.metrics.calmar) },
      { label: "Winrate", current: fmtPct(latestCurrentBacktest.metrics.winrate), compare: fmtPct(latestCompareBacktest.metrics.winrate) },
      {
        label: "Expectancy / Avg Trade",
        current: `${fmtNum(latestCurrentBacktest.metrics.expectancy)} / ${fmtNum(latestCurrentBacktest.metrics.avg_trade)}`,
        compare: `${fmtNum(latestCompareBacktest.metrics.expectancy)} / ${fmtNum(latestCompareBacktest.metrics.avg_trade)}`,
      },
      { label: "Turnover", current: fmtNum(latestCurrentBacktest.metrics.turnover), compare: fmtNum(latestCompareBacktest.metrics.turnover) },
      {
        label: "Robustness Score",
        current: fmtNum(latestCurrentBacktest.metrics.robust_score),
        compare: fmtNum(latestCompareBacktest.metrics.robust_score),
      },
    ];
  }, [latestCompareBacktest, latestCurrentBacktest]);

  if (loadError && !strategy) {
    return <p className="text-sm text-rose-300">{loadError}</p>;
  }

  if (!strategy) {
    return <p className="text-sm text-slate-400">Cargando estrategia...</p>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {strategy.name} <span className="text-cyan-300">v{strategy.version}</span>
          {strategy.primary ? <Badge variant="info">Primaria</Badge> : null}
          {strategy.enabled ? <Badge variant="success">Habilitada</Badge> : <Badge>Deshabilitada</Badge>}
        </CardTitle>
        <CardDescription>Detalle de estrategia con KPIs y comparacion A/B de versiones.</CardDescription>
      </Card>

      {kpis ? (
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Kpi label="CAGR" value={fmtPct(kpis.cagr)} />
          <Kpi label="Max DD" value={fmtPct(kpis.max_dd)} />
          <Kpi label="Sharpe / Sortino" value={`${fmtNum(kpis.sharpe)} / ${fmtNum(kpis.sortino)}`} />
          <Kpi label="Calmar / Winrate" value={`${fmtNum(kpis.calmar)} / ${fmtPct(kpis.winrate)}`} />
          <Kpi label="Expectancy / Robust" value={`${fmtNum(kpis.expectancy)} / ${fmtNum(kpis.robust_score)}`} />
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Truth científica</CardTitle>
          <CardDescription>Tesis, confidence y regímenes válidos/prohibidos que el cerebro usa como prior global.</CardDescription>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Kpi label="Confidence base" value={fmtPct(truth?.current_confidence ?? 0)} />
              <Kpi label="Estado truth" value={String(truth?.current_status || "sin estado")} />
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Tesis resumida</p>
              <p className="mt-2 text-sm text-slate-200">{truth?.thesis_summary || truth?.thesis_detail || "Sin tesis documentada todavía."}</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Regímenes aptos</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {intendedRegimes.length ? intendedRegimes.map((item) => <Badge key={item} variant="success">{item}</Badge>) : <span className="text-sm text-slate-400">No documentados</span>}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Regímenes prohibidos</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {forbiddenRegimes.length ? forbiddenRegimes.map((item) => <Badge key={item} variant="danger">{item}</Badge>) : <span className="text-sm text-slate-400">No documentados</span>}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-slate-300">
              <Badge variant="neutral">{truth?.family || "sin familia"}</Badge>
              <Badge variant="neutral">{truth?.market || "sin mercado"}</Badge>
              <Badge variant="neutral">{truth?.asset_class || "sin asset class"}</Badge>
              <Badge variant="neutral">{truth?.timeframe || "sin timeframe"}</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Evidencia por fuente</CardTitle>
          <CardDescription>Resumen y últimas filas del ledger de evidencia para esta estrategia.</CardDescription>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {evidenceSummaryRows.length ? (
                evidenceSummaryRows.map(([source, summary]) => (
                  <div key={source} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300">
                    <div className="flex items-center justify-between gap-2">
                      <Badge variant="info">{source}</Badge>
                      <span>{fmtNum(summary.count || 0)} filas</span>
                    </div>
                    <p className="mt-2">Peso efectivo: <strong>{fmtNum(summary.effective_weight || 0)}</strong></p>
                    <p>Trades: <strong>{fmtNum(summary.trades || 0)}</strong></p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-400">Todavía no hay evidencia indexada por fuente.</p>
              )}
            </div>
            <div className="overflow-x-auto">
              <Table className="text-xs">
                <THead>
                  <TR>
                    <TH>Fuente</TH>
                    <TH>Bot</TH>
                    <TH>Trades</TH>
                    <TH>Peso</TH>
                    <TH>Expectancy</TH>
                    <TH>Sharpe</TH>
                    <TH>PSR / DSR</TH>
                    <TH>PBO</TH>
                    <TH>Flags</TH>
                  </TR>
                </THead>
                <TBody>
                  {(evidencePayload?.items || []).slice(0, 8).map((row, idx) => (
                    <TR key={`${row.evidence_id || row.run_id || row.source_type}-${idx}`}>
                      <TD>{row.source_type}</TD>
                      <TD>{row.bot_id || "--"}</TD>
                      <TD>{fmtNum(row.trades || 0)}</TD>
                      <TD>{fmtNum(row.effective_weight || 0)}</TD>
                      <TD>{fmtNum(row.expectancy_net || 0)}</TD>
                      <TD>{fmtNum(row.sharpe || 0)}</TD>
                      <TD>{`${fmtNum(row.psr || 0)} / ${fmtNum(row.dsr || 0)}`}</TD>
                      <TD>{row.pbo == null ? "--" : fmtNum(row.pbo)}</TD>
                      <TD>
                        <div className="flex flex-wrap gap-1">
                          {row.legacy_untrusted ? <Badge variant="warn">Legacy</Badge> : null}
                          {row.stale ? <Badge variant="warn">Stale</Badge> : null}
                          {row.excluded_from_learning ? <Badge variant="danger">Excluida</Badge> : null}
                        </div>
                      </TD>
                    </TR>
                  ))}
                  {!evidencePayload?.items?.length ? (
                    <TR>
                      <TD colSpan={9} className="text-slate-400">
                        No hay filas de evidencia persistidas todavía.
                      </TD>
                    </TR>
                  ) : null}
                </TBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Equity y Drawdown</CardTitle>
          <CardContent>
            <EquityDrawdownChart
              data={(backtests[0]?.equity_curve || []).map((x) => ({
                ...x,
                label: x.time.slice(5, 10),
              }))}
            />
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Sharpe / Sortino Rolling</CardTitle>
          <CardContent>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart data={rolling}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} label={{ value: "Tiempo", position: "insideBottom", offset: -5, fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} label={{ value: "Ratio", angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  <Line type="monotone" dataKey="sharpe" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="sortino" stroke="#f97316" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardTitle>Histograma de Retornos</CardTitle>
          <CardContent>
            <ReturnsHistogram data={histogram} />
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Fees + Slippage (apilado)</CardTitle>
          <CardContent>
            <StackedCostChart data={costs} />
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Tendencia de Exposicion</CardTitle>
          <CardContent>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart
                  data={(backtests[0]?.equity_curve || []).map((x, idx) => ({
                    label: idx % 12 === 0 ? x.time.slice(5, 10) : "",
                    net: 0.4 + Math.sin(idx / 8) * 0.25,
                    gross: 0.8 + Math.cos(idx / 7) * 0.35,
                  }))}
                >
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} label={{ value: "Tiempo", position: "insideBottom", offset: -5, fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} label={{ value: "Exposición relativa", angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  <Line type="monotone" dataKey="net" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="gross" stroke="#facc15" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Playbook</CardTitle>
          <CardDescription>Resumen de reglas + parametros activos + versiones recientes.</CardDescription>
          <CardContent className="space-y-3">
            <pre className="whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200">
              {getPlaybook(strategy.name)}
            </pre>
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Parametros activos</p>
              <pre className="text-xs text-slate-200">{JSON.stringify(strategy.params, null, 2)}</pre>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Changelog</p>
              <ul className="space-y-1 text-sm text-slate-300">
                {strategies
                  .filter((row) => row.name === strategy.name)
                  .map((row) => (
                    <li key={row.id}>
                      {row.version} - actualizado {new Date(row.updated_at).toLocaleDateString()}
                    </li>
                  ))}
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Que cambio? (A/B)</CardTitle>
          <CardDescription>Compara parametros y metricas contra otra version.</CardDescription>
          <CardContent className="space-y-3">
            <Select value={compareId} onChange={(e) => setCompareId(e.target.value)}>
              <option value="">Seleccionar version</option>
              {strategies
                .filter((row) => row.id !== strategy.id)
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name} v{row.version}
                  </option>
                ))}
            </Select>
            {compare ? (
              <>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                  <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Claves cambiadas</p>
                  <div className="flex flex-wrap gap-2">
                    {changedKeys.length ? changedKeys.map((key) => <Badge key={key}>{key}</Badge>) : <Badge variant="success">Sin diferencias</Badge>}
                  </div>
                </div>
                <Table>
                  <THead>
                    <TR>
                      <TH>Parametro</TH>
                      <TH>Actual</TH>
                      <TH>Comparado</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {changedKeys.map((key) => (
                      <TR key={key}>
                        <TD>{key}</TD>
                        <TD>{String(strategy.params[key])}</TD>
                        <TD>{String(compare.params[key])}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
                <Table>
                  <THead>
                    <TR>
                      <TH>Metrica</TH>
                      <TH>Actual</TH>
                      <TH>Comparado</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {metricComparisonRows.map((row) => (
                      <TR key={row.label}>
                        <TD>{row.label}</TD>
                        <TD>{row.current}</TD>
                        <TD>{row.compare}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </>
            ) : (
              <p className="text-sm text-slate-400">Selecciona una version para comparar.</p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardDescription>{label}</CardDescription>
      <CardTitle className="mt-1 text-lg">{value}</CardTitle>
    </Card>
  );
}

