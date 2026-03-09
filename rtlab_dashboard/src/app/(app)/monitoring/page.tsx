"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet } from "@/lib/client-api";
import type {
  MonitoringAlertsResponse,
  MonitoringHealthResponse,
  MonitoringKillSwitchesResponse,
  MonitoringMetricsSummary,
} from "@/lib/types";

function scoreVariant(score: number): "success" | "warn" | "danger" | "info" {
  if (score >= 80) return "success";
  if (score >= 60) return "warn";
  if (score >= 40) return "info";
  return "danger";
}

function statusVariant(active: boolean): "success" | "danger" {
  return active ? "success" : "danger";
}

function scoreLabel(score: number) {
  if (score >= 85) return "Solido";
  if (score >= 70) return "Aceptable";
  if (score >= 50) return "Fragil";
  return "Critico";
}

function fmtTs(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

const SCORE_CARDS: Array<{ key: keyof MonitoringHealthResponse; title: string; description: string }> = [
  { key: "global_health_score", title: "Salud global", description: "Vista consolidada del estado operativo actual." },
  { key: "data_health_score", title: "Datos", description: "Paridad live, estado de mercado y frescura de metadata." },
  { key: "research_health_score", title: "Research", description: "Backtests/runs recientes y estabilidad del funnel." },
  { key: "brain_health_score", title: "Cerebro", description: "Drift, propuestas pendientes y consistencia de policy." },
  { key: "execution_health_score", title: "Ejecucion", description: "Latencia, slippage, errores y rate limits." },
  { key: "live_health_score", title: "Live", description: "Elegibilidad operativa y parity por instrumento." },
  { key: "risk_health_score", title: "Riesgo", description: "Safe mode, kill switch e integridad de breakers." },
  { key: "observability_health_score", title: "Observabilidad", description: "Alertas operativas y trazabilidad disponible." },
];

export default function MonitoringPage() {
  const [health, setHealth] = useState<MonitoringHealthResponse | null>(null);
  const [metrics, setMetrics] = useState<MonitoringMetricsSummary | null>(null);
  const [alerts, setAlerts] = useState<MonitoringAlertsResponse | null>(null);
  const [killSwitches, setKillSwitches] = useState<MonitoringKillSwitchesResponse | null>(null);
  const [drift, setDrift] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [healthPayload, metricsPayload, alertsPayload, killPayload, driftPayload] = await Promise.all([
        apiGet<MonitoringHealthResponse>("/api/v1/monitoring/health"),
        apiGet<MonitoringMetricsSummary>("/api/v1/monitoring/metrics-summary"),
        apiGet<MonitoringAlertsResponse>("/api/v1/monitoring/alerts"),
        apiGet<MonitoringKillSwitchesResponse>("/api/v1/monitoring/kill-switches"),
        apiGet<Record<string, unknown>>("/api/v1/monitoring/drift"),
      ]);
      setHealth(healthPayload);
      setMetrics(metricsPayload);
      setAlerts(alertsPayload);
      setKillSwitches(killPayload);
      setDrift(driftPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar Monitoring / Salud.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const scoreRows = useMemo(() => {
    if (!health) return [];
    return SCORE_CARDS.map((row) => ({
      ...row,
      value: Number(health[row.key] || 0),
    }));
  }, [health]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Monitoring / Salud</CardTitle>
        <CardDescription>
          Estado consolidado del sistema: salud, parity, drift, kill switches y alertas operativas. Esta pantalla resume; el drilldown fino sigue en Alertas y Logs.
        </CardDescription>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {metrics ? (
              <>
                <Badge variant={statusVariant(metrics.status.runtime_ready_for_live)}>Live {metrics.status.runtime_ready_for_live ? "listo" : "bloqueado"}</Badge>
                <Badge variant={statusVariant(!metrics.status.safe_mode)}>Safe mode {metrics.status.safe_mode ? "activo" : "off"}</Badge>
                <Badge variant={statusVariant(!metrics.status.killed)}>Kill switch {metrics.status.killed ? "activo" : "off"}</Badge>
                <Badge variant="info">{String(metrics.status.runtime_mode || "paper").toUpperCase()}</Badge>
                <Badge variant="info">{String(metrics.status.runtime_engine || "simulated")}</Badge>
              </>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {health ? <span className="text-sm text-slate-400">Actualizado: {fmtTs(health.generated_at)}</span> : null}
            <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
              {loading ? "Actualizando..." : "Refrescar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Card>
          <CardContent className="py-4 text-sm text-rose-300">{error}</CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-4">
        {scoreRows.map((row) => (
          <Card key={row.key}>
            <CardTitle className="flex items-center justify-between">
              <span>{row.title}</span>
              <Badge variant={scoreVariant(row.value)}>{scoreLabel(row.value)}</Badge>
            </CardTitle>
            <CardDescription>{row.description}</CardDescription>
            <CardContent className="space-y-2">
              <div className="text-3xl font-semibold text-slate-100">{row.value.toFixed(1)}</div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-900">
                <div className="h-full rounded-full bg-cyan-400" style={{ width: `${Math.max(0, Math.min(100, row.value))}%` }} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardTitle>Por que bajo la salud</CardTitle>
          <CardDescription>Motivos actuales y acciones sugeridas para recuperar estabilidad.</CardDescription>
          <CardContent className="grid gap-4 lg:grid-cols-2">
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Motivos</p>
              <ul className="space-y-2 text-sm text-slate-300">
                {(health?.reasons?.length ? health.reasons : ["Sin alertas estructurales activas."]).map((row) => (
                  <li key={row} className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
                    {row}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Acciones sugeridas</p>
              <ul className="space-y-2 text-sm text-slate-300">
                {(health?.suggested_actions || []).map((row) => (
                  <li key={row} className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
                    {row}
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Resumen de modos y bots</CardTitle>
          <CardDescription>Estado operativo actual, distribuido por modo y status.</CardDescription>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Bots por modo</p>
                <div className="mt-2 space-y-1 text-sm text-slate-300">
                  {Object.entries(metrics?.bots.by_mode || {}).map(([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <span>{key}</span>
                      <span>{value}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Bots por estado</p>
                <div className="mt-2 space-y-1 text-sm text-slate-300">
                  {Object.entries(metrics?.bots.by_status || {}).map(([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <span>{key}</span>
                      <span>{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Research</p>
                <div className="mt-2 space-y-1 text-sm text-slate-300">
                  <div className="flex justify-between"><span>Runs totales</span><span>{metrics?.research_health.runs_total || 0}</span></div>
                  <div className="flex justify-between"><span>Fallidos</span><span>{metrics?.research_health.failed_runs || 0}</span></div>
                  <div className="flex justify-between"><span>En curso</span><span>{metrics?.research_health.running_runs || 0}</span></div>
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Cerebro</p>
                <div className="mt-2 space-y-1 text-sm text-slate-300">
                  <div className="flex justify-between"><span>Drift</span><span>{metrics?.brain_health.drift_detected ? "Si" : "No"}</span></div>
                  <div className="flex justify-between"><span>Propuestas pendientes</span><span>{metrics?.brain_health.pending_proposals || 0}</span></div>
                  <div className="flex justify-between"><span>Needs validation</span><span>{metrics?.brain_health.needs_validation_proposals || 0}</span></div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card>
          <CardTitle>Salud de datos y live parity</CardTitle>
          <CardDescription>Lo minimo para confiar en datos, elegibilidad operativa y metadata del catalogo.</CardDescription>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Paridad live</p>
              <div className="mt-2 text-2xl font-semibold">{metrics?.data_health.parity_ready || 0} / {metrics?.data_health.live_parity_total || 0}</div>
              <p className="mt-1 text-sm text-slate-400">Instrumentos listos para evaluacion live.</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Stale market state</p>
              <div className="mt-2 text-2xl font-semibold">{metrics?.data_health.stale_market_state || 0}</div>
              <p className="mt-1 text-sm text-slate-400">Instrumentos con estado de mercado vencido.</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Referencia vencida</p>
              <div className="mt-2 text-2xl font-semibold">{metrics?.data_health.stale_reference_data || 0}</div>
              <p className="mt-1 text-sm text-slate-400">Metadata de simbolos a resincronizar.</p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 md:col-span-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Distribucion por mercado</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {Object.entries(metrics?.data_health.provider_markets || {}).map(([market, value]) => (
                  <div key={market} className="rounded-md border border-slate-800 px-3 py-2 text-sm text-slate-300">
                    <div className="font-medium text-slate-200">{market}</div>
                    <div>{value} instrumentos</div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Ejecucion y costos</CardTitle>
          <CardDescription>Metricas operativas recientes del runtime actual.</CardDescription>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Latencia p95</p>
              <div className="mt-2 text-2xl font-semibold">{metrics?.execution_health.latency_ms_p95?.toFixed(0) || "0"} ms</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Slippage p95</p>
              <div className="mt-2 text-2xl font-semibold">{metrics?.execution_health.p95_slippage?.toFixed(2) || "0.00"} bps</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Spread p95</p>
              <div className="mt-2 text-2xl font-semibold">{metrics?.execution_health.p95_spread?.toFixed(2) || "0.00"} bps</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Errores API</p>
              <div className="mt-2 text-2xl font-semibold">{metrics?.execution_health.api_errors || 0}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardTitle>Alertas operativas</CardTitle>
          <CardDescription>Alertas derivadas de drift, slippage, errores de API e integridad de breaker events.</CardDescription>
          <CardContent className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Timestamp</TH>
                  <TH>Tipo</TH>
                  <TH>Modulo</TH>
                  <TH>Severidad</TH>
                  <TH>Mensaje</TH>
                </TR>
              </THead>
              <TBody>
                {(alerts?.alerts || []).map((row) => (
                  <TR key={row.id}>
                    <TD>{fmtTs(row.ts)}</TD>
                    <TD>{row.type || "-"}</TD>
                    <TD>{row.module || "-"}</TD>
                    <TD><Badge variant={row.severity === "error" ? "danger" : "warn"}>{row.severity}</Badge></TD>
                    <TD>{row.message}</TD>
                  </TR>
                ))}
                {!alerts?.alerts?.length ? (
                  <TR>
                    <TD colSpan={5} className="text-center text-slate-400">
                      Sin alertas operativas activas.
                    </TD>
                  </TR>
                ) : null}
              </TBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Kill switches e incidentes recientes</CardTitle>
          <CardDescription>Estado del kill switch, safe mode e historial reciente de breakers.</CardDescription>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge variant={statusVariant(!(killSwitches?.safe_mode || false))}>Safe mode {killSwitches?.safe_mode ? "activo" : "off"}</Badge>
              <Badge variant={statusVariant(!(killSwitches?.killed || false))}>Kill switch {killSwitches?.killed ? "activo" : "off"}</Badge>
              <Badge variant={(killSwitches?.breaker_integrity.ok ?? true) ? "success" : "warn"}>
                Breaker integrity {killSwitches?.breaker_integrity.status || "SIN_DATO"}
              </Badge>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Timestamp</TH>
                    <TH>Bot</TH>
                    <TH>Modo</TH>
                    <TH>Reason</TH>
                    <TH>Simbolo</TH>
                  </TR>
                </THead>
                <TBody>
                  {(killSwitches?.recent_events || []).slice(0, 10).map((row) => (
                    <TR key={`${row.id}-${row.ts}`}>
                      <TD>{fmtTs(row.ts)}</TD>
                      <TD>{row.bot_id}</TD>
                      <TD>{row.mode}</TD>
                      <TD>{row.reason}</TD>
                      <TD>{row.symbol || "-"}</TD>
                    </TR>
                  ))}
                  {!killSwitches?.recent_events?.length ? (
                    <TR>
                      <TD colSpan={5} className="text-center text-slate-400">
                        No hay eventos recientes de breakers.
                      </TD>
                    </TR>
                  ) : null}
                </TBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardTitle>Drift</CardTitle>
          <CardDescription>Resumen simple para decidir si el cerebro necesita revalidacion.</CardDescription>
          <CardContent className="space-y-3 text-sm text-slate-300">
            <div className="flex flex-wrap gap-2">
              <Badge variant={Boolean(drift?.drift) ? "warn" : "success"}>{Boolean(drift?.drift) ? "Drift detectado" : "Sin drift fuerte"}</Badge>
              <Badge variant="info">Algoritmo: {String(drift?.algo || "unknown")}</Badge>
              <Badge variant={Boolean(drift?.research_loop_triggered) ? "warn" : "info"}>
                Research loop {Boolean(drift?.research_loop_triggered) ? "activado" : "sin activar"}
              </Badge>
            </div>
            <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
              {JSON.stringify(drift || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Logs recientes relevantes</CardTitle>
          <CardDescription>Ultimos eventos crudos para contexto rapido antes de ir al drilldown completo.</CardDescription>
          <CardContent className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Timestamp</TH>
                  <TH>Tipo</TH>
                  <TH>Modulo</TH>
                  <TH>Severidad</TH>
                  <TH>Mensaje</TH>
                </TR>
              </THead>
              <TBody>
                {(metrics?.observability_health.recent_logs || []).slice(0, 10).map((row) => (
                  <TR key={row.id}>
                    <TD>{fmtTs(row.ts)}</TD>
                    <TD>{row.type}</TD>
                    <TD>{row.module}</TD>
                    <TD>
                      <Badge variant={row.severity === "error" ? "danger" : row.severity === "warn" ? "warn" : "info"}>{row.severity}</Badge>
                    </TD>
                    <TD>{row.message}</TD>
                  </TR>
                ))}
                {!metrics?.observability_health.recent_logs?.length ? (
                  <TR>
                    <TD colSpan={5} className="text-center text-slate-400">
                      Sin logs recientes.
                    </TD>
                  </TR>
                ) : null}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
