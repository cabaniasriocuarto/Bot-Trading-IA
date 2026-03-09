"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet, apiPost } from "@/lib/client-api";
import type {
  BotBrainItem,
  BotBrainResponse,
  BotDecisionLogResponse,
  BotInstance,
  BotLiveEligibilityResponse,
  ExecutionRealityResponse,
} from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

function normalizeList(value: unknown): string[] {
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

function summarizeReason(value: Record<string, unknown> | undefined): string {
  if (!value) return "Sin detalle";
  const selectedBy = typeof value.selected_by === "string" ? value.selected_by : "";
  const selected = typeof value.selected_strategy_id === "string" ? value.selected_strategy_id : "";
  if (selectedBy || selected) return [selectedBy, selected].filter(Boolean).join(" - ");
  return Object.entries(value)
    .slice(0, 2)
    .map(([key, item]) => `${key}: ${String(item)}`)
    .join(" - ");
}

function modeBadge(mode: string | undefined) {
  const normalized = String(mode || "").toLowerCase();
  if (normalized === "live") return "warn" as const;
  if (normalized === "testnet") return "info" as const;
  if (normalized === "paper") return "neutral" as const;
  if (normalized === "mock" || normalized === "shadow") return "warn" as const;
  return "neutral" as const;
}

function BotsPageContent() {
  const searchParams = useSearchParams();
  const requestedBotId = searchParams.get("bot_id") || "";

  const [bots, setBots] = useState<BotInstance[]>([]);
  const [selectedBotId, setSelectedBotId] = useState("");
  const [brain, setBrain] = useState<BotBrainResponse | null>(null);
  const [decisionLog, setDecisionLog] = useState<BotDecisionLogResponse | null>(null);
  const [eligibility, setEligibility] = useState<BotLiveEligibilityResponse | null>(null);
  const [reality, setReality] = useState<ExecutionRealityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [recomputeBusy, setRecomputeBusy] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");

  const loadBots = useCallback(async () => {
    const payload = await apiGet<{ items: BotInstance[] }>("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0");
    const items = Array.isArray(payload?.items) ? payload.items : [];
    setBots(items);
    setSelectedBotId((current) => {
      if (requestedBotId && items.some((item) => item.id === requestedBotId)) return requestedBotId;
      if (current && items.some((item) => item.id === current)) return current;
      return items[0]?.id || "";
    });
  }, [requestedBotId]);

  const loadBotDetails = useCallback(async (botId: string) => {
    if (!botId) {
      setBrain(null);
      setDecisionLog(null);
      setEligibility(null);
      setReality(null);
      setDetailError("");
      return;
    }
    setDetailLoading(true);
    setDetailError("");
    try {
      const [brainPayload, decisionPayload, eligibilityPayload, realityPayload] = await Promise.all([
        apiGet<BotBrainResponse>(`/api/v1/bots/${encodeURIComponent(botId)}/brain`),
        apiGet<BotDecisionLogResponse>(`/api/v1/bots/${encodeURIComponent(botId)}/decision-log`),
        apiGet<BotLiveEligibilityResponse>(`/api/v1/bots/${encodeURIComponent(botId)}/live-eligibility`),
        apiGet<ExecutionRealityResponse>(`/api/v1/execution/reality?bot_id=${encodeURIComponent(botId)}`),
      ]);
      setBrain(brainPayload);
      setDecisionLog(decisionPayload);
      setEligibility(eligibilityPayload);
      setReality(realityPayload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "No se pudo cargar el detalle del bot.";
      setDetailError(message);
      setBrain(null);
      setDecisionLog(null);
      setEligibility(null);
      setReality(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      try {
        setLoading(true);
        await loadBots();
        setError("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "No se pudieron cargar los bots.");
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [loadBots]);

  useEffect(() => {
    if (!bots.length && !selectedBotId) return;
    void loadBotDetails(selectedBotId);
  }, [bots.length, loadBotDetails, selectedBotId]);

  const selectedBot = useMemo(
    () => bots.find((item) => item.id === selectedBotId) || null,
    [bots, selectedBotId],
  );

  const sourceRows = useMemo(
    () =>
      Object.entries(brain?.source_summary?.sources || {}).sort(
        (left, right) => Number(right[1]?.weight_sum || 0) - Number(left[1]?.weight_sum || 0),
      ),
    [brain],
  );

  const refreshAll = async () => {
    try {
      setLoading(true);
      await loadBots();
      await loadBotDetails(selectedBotId || requestedBotId);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo refrescar la pantalla de bots.");
    } finally {
      setLoading(false);
    }
  };

  const recomputeBrain = async () => {
    if (!selectedBotId) return;
    try {
      setRecomputeBusy(true);
      await apiPost(`/api/v1/bots/${encodeURIComponent(selectedBotId)}/recompute-brain`, {});
      await loadBotDetails(selectedBotId);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "No se pudo recomputar el cerebro.");
    } finally {
      setRecomputeBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Bots / Cerebro del Bot</CardTitle>
        <CardDescription>
          Dominio exclusivo de bots: pool, policy, decision log, elegibilidad live y realidad de ejecución. La operativa sigue en Ejecución.
        </CardDescription>
      </Card>

      <Card>
        <CardTitle>Taxonomía de modos</CardTitle>
        <CardDescription>
          El cerebro pondera distinto la evidencia según el modo. Mock y Shadow son simulación propia; Paper usa mercado real con fills simulados; Testnet valida contra el exchange de prueba; Live usa cuenta real.
        </CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <ModeExplainer title="Mock / Shadow" badge="mock" text="Sirve para probar policy, UI y eventos sin tocar un exchange real." />
          <ModeExplainer title="Paper" badge="paper" text="Usa mercado real, pero fills y capital simulados con nuestro execution model." />
          <ModeExplainer title="Testnet" badge="testnet" text="Usa la API oficial de prueba para validar payloads, restricciones y errores reales." />
          <ModeExplainer title="Live" badge="live" text="Cuenta real. Requiere elegibilidad, riesgo, pre-flight y monitoreo operativo." />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-[minmax(260px,360px)_1fr_auto]">
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Bot seleccionado</label>
              <Select value={selectedBotId} onChange={(event) => setSelectedBotId(event.target.value)} disabled={!bots.length}>
                {!bots.length ? <option value="">Sin bots disponibles</option> : null}
                {bots.map((bot) => (
                  <option key={bot.id} value={bot.id}>
                    {bot.name} · {bot.id}
                  </option>
                ))}
              </Select>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
              {selectedBot ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-slate-100">{selectedBot.name}</span>
                    <Badge variant={modeBadge(selectedBot.mode)}>{selectedBot.mode}</Badge>
                    <Badge variant={selectedBot.status === "active" ? "success" : selectedBot.status === "paused" ? "warn" : "neutral"}>
                      {selectedBot.status}
                    </Badge>
                    <span className="text-slate-400">{selectedBot.engine}</span>
                  </div>
                  <p className="mt-2">
                    Pool actual: <strong>{selectedBot.pool_strategy_ids.length}</strong> estrategias
                    {selectedBot.universe?.length ? ` · Universo: ${selectedBot.universe.join(", ")}` : ""}
                  </p>
                </>
              ) : (
                <p>Seleccioná un bot para ver el cerebro y la trazabilidad operativa.</p>
              )}
            </div>
            <div className="flex items-end gap-2">
              <Button variant="outline" onClick={() => void refreshAll()} disabled={loading || detailLoading}>
                Refrescar
              </Button>
              <Button onClick={() => void recomputeBrain()} disabled={!selectedBotId || recomputeBusy || detailLoading}>
                {recomputeBusy ? "Recalculando..." : "Recalcular cerebro"}
              </Button>
            </div>
          </div>
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
          {detailError ? <p className="text-sm text-rose-300">{detailError}</p> : null}
        </CardContent>
      </Card>

      {loading ? <p className="text-sm text-slate-400">Cargando bots...</p> : null}
      {!loading && !selectedBot ? <p className="text-sm text-slate-400">No hay bots disponibles todavía.</p> : null}

      {selectedBot ? (
        <>
          <section className="grid gap-4 lg:grid-cols-4">
            <MetricCard label="Estrategia elegida" value={brain?.selected_strategy_id || "Sin seleccion"} />
            <MetricCard label="Régimen actual" value={brain?.regime_label || "--"} />
            <MetricCard label="Trades con evidencia" value={String(brain?.source_summary?.trades_total ?? 0)} />
            <MetricCard label="Peso efectivo total" value={fmtNum(brain?.source_summary?.weight_sum_total ?? 0)} />
          </section>

          {brain?.warnings?.length ? (
            <Card>
              <CardTitle>Warnings del cerebro</CardTitle>
              <CardContent className="flex flex-wrap gap-2">
                {brain.warnings.map((warning) => (
                  <Badge key={warning} variant="warn">
                    {warning}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          ) : null}

          <section className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardTitle>Policy del bot por estrategia</CardTitle>
              <CardDescription>Score bot-first con prior global, pesos objetivo/live y confidence por estrategia del pool.</CardDescription>
              <CardContent className="space-y-4 overflow-x-auto">
                <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                  <MetricCard label="Decisiones" value={String(decisionLog?.summary?.count ?? 0)} compact />
                  <MetricCard label="Con selección" value={String(decisionLog?.summary?.with_selection ?? 0)} compact />
                  <MetricCard label="Hold / Skip" value={String(decisionLog?.summary?.hold_or_skip ?? 0)} compact />
                  <MetricCard label="Candidatas" value={String(decisionLog?.summary?.candidate_total ?? 0)} compact />
                  <MetricCard label="Rechazadas" value={String(decisionLog?.summary?.rejected_total ?? 0)} compact />
                  <MetricCard
                    label="Última decisión"
                    value={decisionLog?.summary?.latest_timestamp ? new Date(decisionLog.summary.latest_timestamp).toLocaleString() : "--"}
                    compact
                  />
                </div>
                {(decisionLog?.summary?.regime_breakdown && Object.keys(decisionLog.summary.regime_breakdown).length) ||
                (decisionLog?.summary?.selected_breakdown && Object.keys(decisionLog.summary.selected_breakdown).length) ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-xs uppercase tracking-wide text-slate-400">Régimen observado</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {Object.entries(decisionLog?.summary?.regime_breakdown || {}).map(([regime, count]) => (
                          <Badge key={regime} variant="neutral">
                            {regime}: {count}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <p className="text-xs uppercase tracking-wide text-slate-400">Selecciones más frecuentes</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {Object.entries(decisionLog?.summary?.selected_breakdown || {}).length ? (
                          Object.entries(decisionLog?.summary?.selected_breakdown || {}).map(([strategyId, count]) => (
                            <Badge key={strategyId} variant="info">
                              {strategyId}: {count}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-sm text-slate-400">Solo hubo hold/skip en esta ventana.</span>
                        )}
                      </div>
                    </div>
                  </div>
                ) : null}
                <Table className="text-xs">
                  <THead>
                    <TR>
                      <TH>Estrategia</TH>
                      <TH>Exact bot</TH>
                      <TH>Pool</TH>
                      <TH>Truth</TH>
                      <TH>Final</TH>
                      <TH>Weight target</TH>
                      <TH>Weight live</TH>
                      <TH>Confidence</TH>
                      <TH>Historial exacto</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {(brain?.items || []).map((item) => (
                      <TR key={item.strategy_id}>
                        <TD>
                          <div className="space-y-1">
                            <Link href={`/strategies/${encodeURIComponent(item.strategy_id)}`} className="font-semibold text-cyan-300 hover:underline">
                              {item.strategy_name}
                            </Link>
                            <div className="flex flex-wrap gap-1 text-[10px]">
                              <Badge variant="neutral">{item.truth?.family || "sin familia"}</Badge>
                              <Badge variant="neutral">{item.truth?.timeframe || "sin TF"}</Badge>
                              <Badge variant="neutral">{item.source_scope}</Badge>
                            </div>
                          </div>
                        </TD>
                        <TD>{fmtNum(item.score_exact_bot)}</TD>
                        <TD>{fmtNum(item.score_pool_context)}</TD>
                        <TD>{fmtNum(item.score_global_truth)}</TD>
                        <TD className="font-semibold text-cyan-300">{fmtNum(item.score_final)}</TD>
                        <TD>{fmtPct(item.weight_target)}</TD>
                        <TD>{fmtPct(item.weight_live)}</TD>
                        <TD>{fmtPct(item.confidence)}</TD>
                        <TD>
                          <Badge variant={item.exact_history_sufficient ? "success" : "warn"}>
                            {item.exact_history_sufficient ? "Suficiente" : "Insuficiente"}
                          </Badge>
                        </TD>
                      </TR>
                    ))}
                    {!brain?.items?.length ? (
                      <TR>
                        <TD colSpan={9} className="text-slate-400">
                          No hay estrategias atribuibles al bot o el pool todavía está vacío.
                        </TD>
                      </TR>
                    ) : null}
                  </TBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardTitle>Fuentes de evidencia</CardTitle>
              <CardDescription>Resumen agregado de trades y peso efectivo por fuente para este bot/pool.</CardDescription>
              <CardContent className="space-y-3">
                {sourceRows.length ? (
                  sourceRows.map(([source, summary]) => (
                    <div key={source} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <Badge variant="info">{source}</Badge>
                        <span className="text-slate-400">{fmtNum(summary.count)} episodios</span>
                      </div>
                      <div className="mt-2 grid gap-2 md:grid-cols-2">
                        <p className="text-slate-300">Peso efectivo: <strong>{fmtNum(summary.weight_sum)}</strong></p>
                        <p className="text-slate-300">Trades: <strong>{fmtNum(summary.trades)}</strong></p>
                        <p className="text-slate-400">Exacto del bot: {fmtNum(summary.exact_bot_count)} episodios / {fmtNum(summary.exact_bot_trades)} trades</p>
                        <p className="text-slate-400">Contexto del pool/global: {fmtNum(summary.pool_context_count)} episodios / {fmtNum(summary.pool_context_trades)} trades</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-slate-400">Todavía no hay evidencia ponderable para este bot.</p>
                )}
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardTitle>Decision log del bot</CardTitle>
              <CardDescription>Historial auditable de candidatas, elegida, vetos y razón de la policy.</CardDescription>
              <CardContent className="overflow-x-auto">
                <Table className="text-xs">
                  <THead>
                    <TR>
                      <TH>Fecha</TH>
                      <TH>Régimen</TH>
                      <TH>Elegida</TH>
                      <TH>Candidatas</TH>
                      <TH>Rechazadas</TH>
                      <TH>Motivo</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {(decisionLog?.items || []).map((row) => (
                      <TR key={row.decision_id}>
                        <TD>{row.timestamp ? new Date(row.timestamp).toLocaleString() : "--"}</TD>
                        <TD>{row.regime_label || "--"}</TD>
                        <TD>{row.selected_strategy_id || "hold/skip"}</TD>
                        <TD>{Array.isArray(row.candidate_strategies_json) ? row.candidate_strategies_json.length : 0}</TD>
                        <TD>{Array.isArray(row.rejected_strategies_json) ? row.rejected_strategies_json.length : 0}</TD>
                        <TD className="max-w-[260px] truncate" title={summarizeReason(row.reason_json)}>
                          {summarizeReason(row.reason_json)}
                        </TD>
                      </TR>
                    ))}
                    {!decisionLog?.items?.length ? (
                      <TR>
                        <TD colSpan={6} className="text-slate-400">
                          No hay decisiones persistidas todavía para este bot.
                        </TD>
                      </TR>
                    ) : null}
                  </TBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardTitle>Live eligibility y execution reality</CardTitle>
              <CardDescription>Estado real del bot para live y resumen de ejecución reciente del ledger operativo.</CardDescription>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                  <MetricCard label="Instrumentos elegibles" value={String(eligibility?.summary?.eligible_instruments ?? 0)} compact />
                  <MetricCard label="Parity ready" value={String(eligibility?.summary?.parity_ready ?? 0)} compact />
                  <MetricCard label="Exec rows" value={String(reality?.summary?.count ?? 0)} compact />
                  <MetricCard label="Símbolos activos" value={String(reality?.summary?.symbols_count ?? 0)} compact />
                  <MetricCard
                    label="Última ejecución"
                    value={reality?.summary?.latest_timestamp ? new Date(reality.summary.latest_timestamp).toLocaleString() : "--"}
                    compact
                  />
                  <MetricCard label="Partial fill prom." value={fmtPct(reality?.summary?.avg_partial_fill_ratio ?? 0)} compact />
                </div>
                <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
                  <MetricCard label="Slippage promedio" value={`${fmtNum(reality?.summary?.avg_realized_slippage_bps ?? 0)} bps`} compact />
                  <MetricCard label="Latencia promedio" value={`${fmtNum(reality?.summary?.avg_latency_ms ?? 0)} ms`} compact />
                  <MetricCard label="Spread promedio" value={`${fmtNum(reality?.summary?.avg_spread_bps ?? 0)} bps`} compact />
                  <MetricCard label="Impacto promedio" value={`${fmtNum(reality?.summary?.avg_impact_bps_est ?? 0)} bps`} compact />
                  <MetricCard label="Maker / Taker" value={`${fmtPct(reality?.summary?.maker_ratio ?? 0)} / ${fmtPct(reality?.summary?.taker_ratio ?? 0)}`} compact />
                </div>

                {Object.keys(reality?.summary?.reconciliation_breakdown || {}).length ? (
                  <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Estado de reconciliación</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {Object.entries(reality?.summary?.reconciliation_breakdown || {}).map(([status, count]) => (
                        <Badge key={status} variant={status === "ok" || status === "matched" ? "success" : "warn"}>
                          {status}: {count}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                {eligibility?.blocked_reasons?.length ? (
                  <div className="rounded-lg border border-rose-900/50 bg-rose-950/30 p-3 text-sm text-rose-200">
                    <p className="font-semibold">Bloqueos live</p>
                    <ul className="mt-2 list-disc space-y-1 pl-4">
                      {eligibility.blocked_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 p-3 text-sm text-emerald-200">
                    Sin bloqueos live críticos para este bot.
                  </div>
                )}

                {eligibility?.warnings?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {eligibility.warnings.map((warning) => (
                      <Badge key={warning} variant="warn">
                        {warning}
                      </Badge>
                    ))}
                  </div>
                ) : null}

                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Instrumentos live elegibles</p>
                  <div className="flex flex-wrap gap-2">
                    {(eligibility?.eligible_instruments || []).slice(0, 10).map((instrument) => (
                      <Badge key={instrument.instrument_id} variant={instrument.eligible_live ? "success" : "neutral"}>
                        {instrument.provider_market}:{instrument.provider_symbol}
                      </Badge>
                    ))}
                    {!eligibility?.eligible_instruments?.length ? <span className="text-sm text-slate-400">Sin instrumentos elegibles.</span> : null}
                  </div>
                </div>

                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Últimas ejecuciones</p>
                  <div className="space-y-2">
                    {(reality?.items || []).slice(0, 5).map((row) => (
                      <div key={row.execution_id} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="info">{row.symbol || "sin símbolo"}</Badge>
                          <Badge variant="neutral">{row.side || "sin lado"}</Badge>
                          <Badge variant="neutral">{row.maker_taker || "n/a"}</Badge>
                          <span>{row.timestamp ? new Date(row.timestamp).toLocaleString() : "--"}</span>
                        </div>
                        <p className="mt-2">
                          Slippage: <strong>{fmtNum(row.realized_slippage_bps ?? 0)} bps</strong> ·
                          Latencia: <strong>{fmtNum(row.latency_ms ?? 0)} ms</strong> ·
                          Spread: <strong>{fmtNum(row.spread_bps ?? 0)} bps</strong>
                        </p>
                      </div>
                    ))}
                    {!reality?.items?.length ? <p className="text-sm text-slate-400">No hay ejecuciones recientes para este bot.</p> : null}
                  </div>
                </div>
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            {(brain?.items || []).slice(0, 2).map((item) => (
              <StrategyTruthCard key={item.strategy_id} item={item} />
            ))}
          </section>
        </>
      ) : null}
    </div>
  );
}

function ModeExplainer({ title, badge, text }: { title: string; badge: string; text: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant={modeBadge(badge)}>{title}</Badge>
      </div>
      <p>{text}</p>
    </div>
  );
}

function MetricCard({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
  return (
    <Card>
      <CardDescription>{label}</CardDescription>
      <CardTitle className={compact ? "mt-1 text-lg" : "mt-1 text-xl"}>{value}</CardTitle>
    </Card>
  );
}

function StrategyTruthCard({ item }: { item: BotBrainItem }) {
  const intended = normalizeList(item.truth?.intended_regimes);
  const forbidden = normalizeList(item.truth?.forbidden_regimes);
  return (
    <Card>
      <CardTitle>Truth / evidencia: {item.strategy_name}</CardTitle>
      <CardDescription>Truth científica + evidencia agregada que el bot usa para decidir.</CardDescription>
      <CardContent className="space-y-3 text-sm">
        <div className="grid gap-3 sm:grid-cols-2">
          <MetricCard label="Confidence base" value={fmtPct(item.truth?.current_confidence ?? 0)} compact />
          <MetricCard label="Status" value={String(item.truth?.current_status || "sin estado")} compact />
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Tesis</p>
          <p className="mt-2 text-slate-200">{item.truth?.thesis_summary || item.truth?.thesis_detail || "Sin tesis documentada."}</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Regímenes aptos</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {intended.length ? intended.map((regime) => <Badge key={regime} variant="success">{regime}</Badge>) : <span className="text-slate-400">No documentados.</span>}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Regímenes prohibidos</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {forbidden.length ? forbidden.map((regime) => <Badge key={regime} variant="danger">{regime}</Badge>) : <span className="text-slate-400">No documentados.</span>}
            </div>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <MetricCard label="Expectancy net exacta" value={fmtNum(item.exact_bot.metrics.expectancy_net ?? 0)} compact />
          <MetricCard label="Sharpe truth" value={fmtNum(item.global_truth.metrics.sharpe ?? 0)} compact />
          <MetricCard label="Max DD truth" value={fmtPct(item.global_truth.metrics.max_dd ?? 0)} compact />
        </div>
      </CardContent>
    </Card>
  );
}

export default function BotsPage() {
  return (
    <Suspense fallback={<div className="space-y-4"><p className="text-sm text-slate-400">Cargando vista de bots...</p></div>}>
      <BotsPageContent />
    </Suspense>
  );
}
