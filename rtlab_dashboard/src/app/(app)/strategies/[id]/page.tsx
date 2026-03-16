"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { EquityDrawdownChart } from "@/components/charts/equity-drawdown-chart";
import { ReturnsHistogram } from "@/components/charts/returns-histogram";
import { StackedCostChart } from "@/components/charts/stacked-cost-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiError, apiGet } from "@/lib/client-api";
import { getPlaybook } from "@/lib/playbooks";
import type { BacktestRun, Strategy, StrategyEvidenceResponse, StrategyTruth, Trade } from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>();
  const strategyId = String(params.id);

  const [truth, setTruth] = useState<StrategyTruth | null>(null);
  const [evidence, setEvidence] = useState<StrategyEvidenceResponse | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [allBacktests, setAllBacktests] = useState<BacktestRun[]>([]);
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [compareId, setCompareId] = useState("");
  const [compatibilityNotice, setCompatibilityNotice] = useState("");

  useEffect(() => {
    const load = async () => {
      const [allStrategies, allBacktests, allTrades] = await Promise.all([
        apiGet<Strategy[]>("/api/v1/strategies"),
        apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
        apiGet<Trade[]>(`/api/v1/trades?strategy_id=${strategyId}`),
      ]);
      const fallbackStrategy =
        allStrategies.find((row) => row.id === strategyId) ||
        (await apiGet<Strategy>(`/api/v1/strategies/${strategyId}`).catch(() => null));
      const strategyBacktests = allBacktests
        .filter((row) => row.strategy_id === strategyId)
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

      let truthRes: StrategyTruth;
      let evidenceRes: StrategyEvidenceResponse;
      let legacyNotice = "";

      try {
        truthRes = await apiGet<StrategyTruth>(`/api/v1/strategies/${strategyId}/truth`);
      } catch (err) {
        if (!isMissingRouteError(err) || !fallbackStrategy) throw err;
        truthRes = strategyTruthFromLegacy(fallbackStrategy);
        legacyNotice =
          "Compatibilidad legacy activa: strategy truth/evidence se reconstruyen desde /api/v1/strategies y /api/v1/backtests/runs mientras RTLRESE-14 no este integrado.";
      }

      try {
        evidenceRes = await apiGet<StrategyEvidenceResponse>(`/api/v1/strategies/${strategyId}/evidence?limit=12`);
      } catch (err) {
        if (!isMissingRouteError(err) || !fallbackStrategy) throw err;
        evidenceRes = strategyEvidenceFromLegacy(fallbackStrategy, strategyBacktests);
        legacyNotice =
          "Compatibilidad legacy activa: strategy truth/evidence se reconstruyen desde /api/v1/strategies y /api/v1/backtests/runs mientras RTLRESE-14 no este integrado.";
      }

      setTruth(truthRes);
      setEvidence(evidenceRes);
      setStrategies(allStrategies);
      setCompatibilityNotice(legacyNotice);
      setAllBacktests(
        [...allBacktests].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
      );
      setBacktests(strategyBacktests);
      setTrades(allTrades);
      const compareCandidate =
        allStrategies.find((row) => row.id !== strategyId && row.name === truthRes.name) ||
        allStrategies.find((row) => row.id !== strategyId) ||
        null;
      setCompareId(compareCandidate?.id || "");
    };
    void load();
  }, [strategyId]);

  const latestEvidenceRun = evidence?.latest_run || null;
  const latestEvidenceMetrics = latestEvidenceRun?.metrics || null;
  const latestDetailedBacktest = backtests[0] || null;

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

  const costConfigRows = useMemo(
    () =>
      backtests.slice(0, 8).map((row) => ({
        label: row.id,
        fees: row.costs_model.fees_bps,
        slippage: row.costs_model.slippage_bps,
        funding: row.costs_model.funding_bps,
      })),
    [backtests],
  );

  const evidenceTrendRows = useMemo(
    () =>
      [...(evidence?.items || [])]
        .slice(0, 8)
        .reverse()
        .map((row) => ({
          label: row.created_at ? new Date(row.created_at).toLocaleDateString() : row.run_id,
          mode: row.mode.toUpperCase(),
          sharpe: Number(row.metrics?.sharpe || 0),
          maxDdPct: Number(row.metrics?.max_dd || 0) * 100,
          winratePct: Number(row.metrics?.winrate || 0) * 100,
        })),
    [evidence],
  );

  const compare = strategies.find((row) => row.id === compareId) || null;
  const changedKeys = useMemo(() => {
    if (!truth || !compare) return [];
    const keys = new Set([...Object.keys(truth.params || {}), ...Object.keys(compare.params || {})]);
    return [...keys].filter((key) => truth.params[key] !== compare.params[key]);
  }, [truth, compare]);

  const allBacktestsByStrategy = useMemo(() => {
    const grouped = new Map<string, BacktestRun[]>();
    for (const row of allBacktests) {
      const current = grouped.get(row.strategy_id) || [];
      current.push(row);
      grouped.set(row.strategy_id, current);
    }
    return grouped;
  }, [allBacktests]);

  const latestCurrentBacktest = useMemo(() => {
    const rows = allBacktestsByStrategy.get(strategyId) || [];
    return rows[0] || null;
  }, [allBacktestsByStrategy, strategyId]);

  const latestCompareDetailedBacktest = useMemo(() => {
    if (!compare) return null;
    const rows = allBacktestsByStrategy.get(compare.id) || [];
    return rows[0] || null;
  }, [allBacktestsByStrategy, compare]);

  const evidenceComparisonRows = useMemo(() => {
    if (!latestCurrentBacktest || !latestCompareDetailedBacktest) return [];
    return [
      { label: "CAGR", current: fmtPct(latestCurrentBacktest.metrics.cagr), compare: fmtPct(latestCompareDetailedBacktest.metrics.cagr) },
      { label: "Max DD", current: fmtPct(latestCurrentBacktest.metrics.max_dd), compare: fmtPct(latestCompareDetailedBacktest.metrics.max_dd) },
      { label: "Sharpe", current: fmtNum(latestCurrentBacktest.metrics.sharpe), compare: fmtNum(latestCompareDetailedBacktest.metrics.sharpe) },
      { label: "Sortino", current: fmtNum(latestCurrentBacktest.metrics.sortino), compare: fmtNum(latestCompareDetailedBacktest.metrics.sortino) },
      { label: "Calmar", current: fmtNum(latestCurrentBacktest.metrics.calmar), compare: fmtNum(latestCompareDetailedBacktest.metrics.calmar) },
      { label: "Winrate", current: fmtPct(latestCurrentBacktest.metrics.winrate), compare: fmtPct(latestCompareDetailedBacktest.metrics.winrate) },
      {
        label: "Expectancy / Avg Trade",
        current: `${fmtNum(latestCurrentBacktest.metrics.expectancy)} / ${fmtNum(latestCurrentBacktest.metrics.avg_trade)}`,
        compare: `${fmtNum(latestCompareDetailedBacktest.metrics.expectancy)} / ${fmtNum(latestCompareDetailedBacktest.metrics.avg_trade)}`,
      },
      { label: "Turnover", current: fmtNum(latestCurrentBacktest.metrics.turnover), compare: fmtNum(latestCompareDetailedBacktest.metrics.turnover) },
      {
        label: "Robustness",
        current: fmtNum(latestCurrentBacktest.metrics.robust_score),
        compare: fmtNum(latestCompareDetailedBacktest.metrics.robust_score),
      },
    ];
  }, [latestCompareDetailedBacktest, latestCurrentBacktest]);

  if (!truth) {
    return <p className="text-sm text-slate-400">Cargando estrategia...</p>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle className="flex flex-wrap items-center justify-between gap-3">
          <span className="flex flex-wrap items-center gap-2">
            {truth.name} <span className="text-cyan-300">v{truth.version}</span>
            {truth.primary ? <Badge variant="info">Primaria</Badge> : null}
            {truth.enabled_for_trading ?? truth.enabled ? <Badge variant="success">Trading habilitado</Badge> : <Badge>Trading deshabilitado</Badge>}
            {truth.allow_learning ? <Badge variant="neutral">Pool aprendizaje</Badge> : null}
          </span>
          <Link href="/strategies" className="text-xs text-cyan-300 hover:text-cyan-200">
            Volver a Strategies
          </Link>
        </CardTitle>
        <CardDescription>
          Separacion por dominio: arriba se muestra la definicion de la estrategia (truth) y debajo la evidencia observada que la respalda.
        </CardDescription>
        {compatibilityNotice ? <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">{compatibilityNotice}</p> : null}
      </Card>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Strategy Truth</CardTitle>
          <CardDescription>Definicion declarativa de la estrategia. No incluye KPIs agregados ni evidencia de performance.</CardDescription>
          <CardContent className="space-y-3">
            <div className="grid gap-2 text-xs sm:grid-cols-2">
              <TruthRow label="ID" value={truth.id} />
              <TruthRow label="Source" value={String(truth.source || "-")} />
              <TruthRow label="Status" value={String(truth.status || "-")} />
              <TruthRow label="Primary modes" value={truth.primary_for_modes?.length ? truth.primary_for_modes.join(" / ") : "none"} />
              <TruthRow label="Created" value={truth.created_at ? new Date(truth.created_at).toLocaleString() : "-"} />
              <TruthRow label="Updated" value={truth.updated_at ? new Date(truth.updated_at).toLocaleString() : "-"} />
            </div>
            {truth.description ? (
              <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-sm text-slate-300">{truth.description}</div>
            ) : null}
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Parametros declarativos</p>
              <pre className="overflow-auto text-xs text-slate-200">{JSON.stringify(truth.params, null, 2)}</pre>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Tags / notas</p>
              <div className="flex flex-wrap gap-2">
                {truth.tags?.length ? truth.tags.map((tag) => <Badge key={tag}>{tag}</Badge>) : <Badge variant="neutral">Sin tags</Badge>}
              </div>
              {truth.notes ? <p className="mt-3 text-xs text-slate-300">{truth.notes}</p> : <p className="mt-3 text-xs text-slate-500">Sin notas declarativas.</p>}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Strategy Evidence</CardTitle>
          <CardDescription>Evidence derivada de runs y observacion historica. No forma parte de la verdad base de la estrategia.</CardDescription>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <EvidenceMetric label="Runs observados" value={String(evidence?.run_count || 0)} />
              <EvidenceMetric label="Ultimo run" value={latestEvidenceRun?.created_at ? new Date(latestEvidenceRun.created_at).toLocaleString() : "sin runs"} />
              <EvidenceMetric label="Modo observado" value={latestEvidenceRun?.mode ? latestEvidenceRun.mode.toUpperCase() : "--"} />
              <EvidenceMetric label="WinRate" value={latestEvidenceMetrics ? fmtPct(latestEvidenceMetrics.winrate) : "--"} />
              <EvidenceMetric label="Max DD" value={latestEvidenceMetrics ? fmtPct(latestEvidenceMetrics.max_dd) : "--"} />
              <EvidenceMetric label="Sharpe" value={latestEvidenceMetrics ? fmtNum(latestEvidenceMetrics.sharpe) : "--"} />
            </div>
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              Evidence visible: {latestEvidenceRun ? `run ${latestEvidenceRun.run_id}` : "sin corrida visible"}.
              {" "}Si necesitas series detalladas, los graficos de abajo usan endpoints legacy de backtests/trades pero siguen etiquetados como evidence derivada.
            </div>
            {latestEvidenceRun ? (
              <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-300">
                <p>
                  Validacion: <strong>{latestEvidenceRun.validation_mode || "-"}</strong>
                  {" "}· Tags: <strong>{latestEvidenceRun.tags?.length ? latestEvidenceRun.tags.join(", ") : "none"}</strong>
                </p>
                {latestEvidenceRun.notes ? <p className="mt-2 text-slate-400">{latestEvidenceRun.notes}</p> : null}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-400">
                Todavia no hay evidence visible para esta estrategia.
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Playbook / Truth operativa</CardTitle>
          <CardDescription>Documento humano de la estrategia y parametros declarativos activos.</CardDescription>
          <CardContent className="space-y-3">
            <pre className="whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200">
              {getPlaybook(truth.name)}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Que cambio? (truth vs evidence)</CardTitle>
          <CardDescription>Compara truth declarativa y evidence observada contra otra version de la estrategia.</CardDescription>
          <CardContent className="space-y-3">
            <Select value={compareId} onChange={(e) => setCompareId(e.target.value)}>
              <option value="">Seleccionar version</option>
              {strategies
                .filter((row) => row.id !== truth.id)
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name} v{row.version}
                  </option>
                ))}
            </Select>
            {compare ? (
              <>
                <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Truth: parametros que cambiaron</p>
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
                        <TD>{String(truth.params[key])}</TD>
                        <TD>{String(compare.params[key])}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
                <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence: comparacion del ultimo backtest detallado</p>
                  {evidenceComparisonRows.length ? (
                    <Table>
                      <THead>
                        <TR>
                          <TH>Metrica</TH>
                          <TH>Actual</TH>
                          <TH>Comparado</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {evidenceComparisonRows.map((row) => (
                          <TR key={row.label}>
                            <TD>{row.label}</TD>
                            <TD>{row.current}</TD>
                            <TD>{row.compare}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  ) : (
                    <p className="text-sm text-slate-400">Falta evidence detallada suficiente para comparar la ultima corrida.</p>
                  )}
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-400">Selecciona una version para comparar truth y evidence.</p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Evidence detallada: Equity y Drawdown</CardTitle>
          <CardDescription>Serie detallada del ultimo backtest/run disponible. Se muestra como evidence derivada, no como truth.</CardDescription>
          <CardContent>
            {latestDetailedBacktest ? (
              <EquityDrawdownChart
                data={(latestDetailedBacktest.equity_curve || []).map((point) => ({
                  ...point,
                  label: point.time.slice(5, 10),
                }))}
              />
            ) : (
              <p className="text-sm text-slate-400">Sin backtest detallado para graficar.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Evidence reciente por corrida</CardTitle>
          <CardDescription>Sharpe, Max DD y WinRate sobre las corridas observadas del endpoint de evidence.</CardDescription>
          <CardContent>
            {evidenceTrendRows.length ? (
              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                  <LineChart data={evidenceTrendRows}>
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                    <Legend />
                    <Line type="monotone" dataKey="sharpe" stroke="#22d3ee" strokeWidth={2} dot={false} name="Sharpe" />
                    <Line type="monotone" dataKey="maxDdPct" stroke="#f97316" strokeWidth={2} dot={false} name="Max DD %" />
                    <Line type="monotone" dataKey="winratePct" stroke="#facc15" strokeWidth={2} dot={false} name="WinRate %" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-slate-400">Sin corridas suficientes para mostrar tendencia de evidence.</p>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardTitle>Evidence detallada: Histograma de retornos</CardTitle>
          <CardDescription>Distribucion de trades netos de la estrategia.</CardDescription>
          <CardContent>
            <ReturnsHistogram data={histogram} />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Parametros de costos por corrida</CardTitle>
          <CardDescription>Configuracion de costos usada en las corridas recientes. Es evidence derivada del run, no truth base.</CardDescription>
          <CardContent>
            {costConfigRows.length ? <StackedCostChart data={costConfigRows} /> : <p className="text-sm text-slate-400">Sin corridas para mostrar costos.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Corridas recientes</CardTitle>
          <CardDescription>Resumen rapido de la evidence observada por corrida.</CardDescription>
          <CardContent className="space-y-2">
            {(evidence?.items || []).length ? (
              (evidence?.items || []).slice(0, 6).map((row) => (
                <div key={row.run_id} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold text-slate-100">{row.run_id}</p>
                    <Badge variant="neutral">{row.mode.toUpperCase()}</Badge>
                  </div>
                  <p className="mt-1 text-slate-400">{row.created_at ? new Date(row.created_at).toLocaleString() : "sin fecha"}</p>
                  <p className="mt-2 text-slate-300">
                    Sharpe <strong>{fmtNum(row.metrics?.sharpe || 0)}</strong>
                    {" "}· Max DD <strong>{fmtPct(row.metrics?.max_dd || 0)}</strong>
                    {" "}· WinRate <strong>{fmtPct(row.metrics?.winrate || 0)}</strong>
                  </p>
                  <p className="mt-1 text-slate-500">Validacion: {row.validation_mode || "-"}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-slate-400">Sin corridas recientes.</p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function TruthRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/50 p-2">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm text-slate-200">{value}</p>
    </div>
  );
}

function EvidenceMetric({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardDescription>{label}</CardDescription>
      <CardTitle className="mt-1 text-sm">{value}</CardTitle>
    </Card>
  );
}

function isMissingRouteError(err: unknown) {
  return err instanceof ApiError && err.status === 404;
}

function strategyTruthFromLegacy(strategy: Strategy): StrategyTruth {
  return {
    id: strategy.id,
    name: strategy.name,
    version: strategy.version,
    enabled: strategy.enabled,
    enabled_for_trading: strategy.enabled_for_trading,
    allow_learning: strategy.allow_learning,
    is_primary: strategy.is_primary,
    primary: strategy.primary,
    source: strategy.source,
    status: strategy.status,
    params: strategy.params,
    params_yaml: strategy.defaults_yaml,
    parameters_schema: strategy.schema,
    created_at: strategy.created_at,
    updated_at: strategy.updated_at,
    notes: strategy.notes,
    tags: strategy.tags,
    last_run_at: strategy.last_run_at,
    primary_for_modes: strategy.primary_for_modes,
  };
}

function strategyEvidenceFromLegacy(strategy: Strategy, backtests: BacktestRun[]): StrategyEvidenceResponse {
  const items = backtests.slice(0, 12).map((row) => ({
    run_id: row.id,
    mode: "backtest",
    created_at: row.created_at,
    metrics: row.metrics,
    tags: strategy.tags || [],
    notes: "Evidence derivada desde /api/v1/backtests/runs (legacy fallback).",
    validation_mode: "legacy-backtest",
  }));
  return {
    strategy_id: strategy.id,
    strategy_version: strategy.version,
    last_run_at: strategy.last_run_at,
    run_count: backtests.length,
    last_oos: strategy.last_oos || items[0]?.metrics || null,
    latest_run: items[0] || null,
    items,
  };
}
