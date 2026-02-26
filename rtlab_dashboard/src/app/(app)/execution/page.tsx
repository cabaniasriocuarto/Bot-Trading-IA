"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { apiGet, apiPost } from "@/lib/client-api";
import type { BotStatusResponse, ExchangeDiagnoseResponse, ExecutionStats, HealthResponse, SettingsResponse, TradingMode } from "@/lib/types";
import { fmtNum, fmtPct, fmtUsd } from "@/lib/utils";

type GatesResponse = {
  overall_status: "PASS" | "FAIL" | "WARN" | "UNKNOWN";
  gates: Array<{ id: string; status: "PASS" | "FAIL" | "WARN"; reason?: string }>;
};

type RolloutStatusLite = {
  state?: string;
  pending_live_approval?: boolean;
  pending_live_approval_target?: string | null;
  live_stable_100_requires_approve?: boolean;
  routing?: { mode?: string; phase?: string; phase_type?: string; shadow_only?: boolean } | null;
};

type ControlActionPath =
  | "/api/v1/bot/start"
  | "/api/v1/bot/stop"
  | "/api/v1/control/pause"
  | "/api/v1/control/resume"
  | "/api/v1/control/safe-mode"
  | "/api/v1/control/kill"
  | "/api/v1/control/close-all";

const CONNECTOR_OPTIONS = ["binance", "bybit", "oanda", "alpaca"] as const;

export default function ExecutionPage() {
  const { role } = useSession();
  const [stats, setStats] = useState<ExecutionStats | null>(null);
  const [error, setError] = useState("");
  const [botStatus, setBotStatus] = useState<BotStatusResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [gates, setGates] = useState<GatesResponse | null>(null);
  const [rollout, setRollout] = useState<RolloutStatusLite | null>(null);
  const [exchangeDiag, setExchangeDiag] = useState<ExchangeDiagnoseResponse | null>(null);
  const [exchangeDiagError, setExchangeDiagError] = useState("");
  const [panelLoading, setPanelLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [controlError, setControlError] = useState("");
  const [modeDraft, setModeDraft] = useState<TradingMode>("PAPER");
  const [modeBusy, setModeBusy] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState<number>(0);

  useEffect(() => {
    const load = async () => {
      try {
        setPanelLoading(true);
        await Promise.all([loadExecutionMetrics(), loadTradingPanel(false)]);
      } catch (err) {
        const message = err instanceof Error ? err.message : "No se pudo cargar ejecucion.";
        setError(message);
      } finally {
        setPanelLoading(false);
      }
    };
    void load();
  }, []);

  const loadExecutionMetrics = async () => {
    const exec = await apiGet<ExecutionStats>("/api/v1/execution/metrics");
    setStats(exec);
    setError("");
  };

  const loadTradingPanel = async (forceExchange: boolean) => {
    const [status, currentSettings, healthPayload, gatesPayload, rolloutPayload] = await Promise.all([
      apiGet<BotStatusResponse>("/api/v1/bot/status"),
      apiGet<SettingsResponse>("/api/v1/settings"),
      apiGet<HealthResponse>("/api/v1/health"),
      apiGet<GatesResponse>("/api/v1/gates"),
      apiGet<RolloutStatusLite>("/api/v1/rollout/status"),
    ]);
    setBotStatus(status);
    setSettings(currentSettings);
    setHealth(healthPayload);
    setGates(gatesPayload);
    setRollout(rolloutPayload);
    setModeDraft(currentSettings.mode);

    const mode = (currentSettings.mode || "PAPER").toLowerCase();
    try {
      const diag = await apiGet<ExchangeDiagnoseResponse>(`/api/v1/exchange/diagnose?force=${forceExchange ? "true" : "false"}&mode=${encodeURIComponent(mode)}`);
      setExchangeDiag(diag);
      setExchangeDiagError("");
    } catch (err) {
      setExchangeDiag(null);
      setExchangeDiagError(err instanceof Error ? err.message : "No se pudo diagnosticar el exchange.");
    }
  };

  const refreshAll = async (forceExchange = false) => {
    setRefreshing(true);
    setMessage("");
    setControlError("");
    try {
      await Promise.all([loadExecutionMetrics(), loadTradingPanel(forceExchange)]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "No se pudo actualizar la pantalla.";
      setError(msg);
    } finally {
      setRefreshing(false);
    }
  };

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
  const onCooldown = Date.now() < cooldownUntil;
  const selectedExchange = settings?.exchange || health?.exchange.name || "binance";
  const connectorRows = (settings?.exchange_plugin_options?.length ? settings.exchange_plugin_options : [...CONNECTOR_OPTIONS]).map((name) => {
    const isSelected = name === selectedExchange;
    if (!isSelected) {
      return { name, variant: "neutral" as const, label: "No seleccionado", detail: "Disponible para configurar en Settings." };
    }
    if (exchangeDiagError) {
      return { name, variant: "danger" as const, label: "Error", detail: exchangeDiagError };
    }
    if (!exchangeDiag) {
      return { name, variant: "neutral" as const, label: "Sin diagnostico", detail: "Ejecuta 'Refrescar panel' o 'Probar exchange'." };
    }
    if (exchangeDiag.ok) {
      return {
        name,
        variant: "success" as const,
        label: `OK (${exchangeDiag.mode})`,
        detail: exchangeDiag.order_ok ? "Conector y orden de prueba OK." : exchangeDiag.connector_reason || "Conector OK",
      };
    }
    if (!exchangeDiag.has_keys) {
      return {
        name,
        variant: "warn" as const,
        label: "Faltan keys",
        detail: exchangeDiag.missing?.length ? `Faltan: ${exchangeDiag.missing.join(", ")}` : "Configura keys en variables de entorno.",
      };
    }
    return {
      name,
      variant: "danger" as const,
      label: "Error",
      detail: exchangeDiag.last_error || exchangeDiag.order_reason || exchangeDiag.connector_reason || "Diagnostico con fallo.",
    };
  });

  const liveReadyItems = [
    {
      key: "keys",
      label: "Credenciales del exchange",
      status: exchangeDiag?.has_keys || settings?.credentials.exchange_configured ? "pass" : "fail",
      help:
        exchangeDiag?.has_keys || settings?.credentials.exchange_configured
          ? "Hay credenciales detectadas para el exchange seleccionado."
          : "Carga API key/secret en Railway/VPS y redeploya el backend.",
    },
    {
      key: "perms",
      label: "Permisos minimos (Read + Trade, sin Withdraw)",
      status: "manual",
      help: "Chequeo manual en el panel del exchange. Requisito obligatorio antes de LIVE.",
    },
    {
      key: "connector",
      label: "Conector y orden de prueba",
      status: exchangeDiag?.ok ? "pass" : exchangeDiag ? "fail" : "pending",
      help: exchangeDiag
        ? exchangeDiag.ok
          ? "Diagnostico del exchange OK para el modo actual."
          : exchangeDiag.last_error || exchangeDiag.order_reason || exchangeDiag.connector_reason || "Revisar diagnostico."
        : "Ejecuta diagnostico del exchange para validar conectividad.",
    },
    {
      key: "gates",
      label: "Gates LIVE",
      status: gates?.overall_status === "PASS" ? "pass" : gates ? "fail" : "pending",
      help:
        gates?.overall_status === "PASS"
          ? "Los gates LIVE estan en PASS."
          : "Revisa Settings > Rollout / Gates y corrige FAIL antes de pasar a LIVE.",
    },
    {
      key: "approve",
      label: "Aprobacion humana (Opcion B)",
      status: rollout?.live_stable_100_requires_approve ? "pass" : "fail",
      help:
        rollout?.live_stable_100_requires_approve
          ? "La promocion a STABLE_100 requiere approve manual."
          : "Debe quedar habilitado el approve manual para LIVE.",
    },
    {
      key: "rollout",
      label: "Rollout / Canary",
      status: rollout?.pending_live_approval ? "warn" : "pending",
      help: rollout?.pending_live_approval
        ? `Hay aprobacion pendiente${rollout.pending_live_approval_target ? ` para ${rollout.pending_live_approval_target}` : ""}.`
        : "Inicia un rollout (shadow/canary) desde Settings para poblar telemetria y validar antes de LIVE.",
    },
  ] as const;

  const canTradeLiveNow =
    modeDraft === "LIVE" &&
    liveReadyItems.find((row) => row.key === "keys")?.status === "pass" &&
    liveReadyItems.find((row) => row.key === "connector")?.status === "pass" &&
    liveReadyItems.find((row) => row.key === "gates")?.status === "pass";

  const statusVariant = botStatus
    ? botStatus.bot_status === "RUNNING"
      ? "success"
      : botStatus.bot_status === "SAFE_MODE"
        ? "warn"
        : botStatus.bot_status === "KILLED"
          ? "danger"
          : "neutral"
    : "neutral";

  const runControlAction = async (path: ControlActionPath, body?: Record<string, unknown>, opts?: { confirm?: string; cooldownMs?: number; successMessage?: string }) => {
    if (opts?.confirm) {
      const ok = window.confirm(opts.confirm);
      if (!ok) return;
    }
    setActionLoading(path);
    setControlError("");
    setMessage("");
    try {
      await apiPost(path, body);
      setMessage(opts?.successMessage || "Accion ejecutada.");
      if (opts?.cooldownMs) setCooldownUntil(Date.now() + opts.cooldownMs);
      await refreshAll(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : "No se pudo ejecutar la accion.");
    } finally {
      setActionLoading(null);
    }
  };

  const applyMode = async () => {
    setModeBusy(true);
    setControlError("");
    setMessage("");
    try {
      const mode = modeDraft.toLowerCase();
      if (mode === "live") {
        const ok = window.confirm("Vas a cambiar el modo operativo a LIVE. Esto no inicia trading, pero habilita controles de live. Continuar?");
        if (!ok) return;
      }
      await apiPost("/api/v1/bot/mode", mode === "live" ? { mode, confirm: "ENABLE_LIVE" } : { mode });
      setMessage(`Modo operativo actualizado a ${modeLabel(modeDraft)}.`);
      await refreshAll(true);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : "No se pudo cambiar el modo operativo.");
    } finally {
      setModeBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Trading en Vivo (Paper / Testnet / Live) + Diagnostico</CardTitle>
        <CardDescription>
          Pantalla operativa para ejecutar, pausar y validar conectores. Incluye checklist Live Ready y metricas de ejecucion.
        </CardDescription>
      </Card>

      {error ? <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-300">{error}</p> : null}
      {controlError ? <p className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">{controlError}</p> : null}
      {message ? <p className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-300">{message}</p> : null}

      <section className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardTitle className="flex items-center justify-between gap-3">
            <span>Trading en Vivo (panel operativo)</span>
            <Badge variant={statusVariant as "neutral" | "success" | "warn" | "danger"}>
              {botStatus?.bot_status ? statusLabel(botStatus.bot_status) : panelLoading ? "Cargando..." : "Sin datos"}
            </Badge>
          </CardTitle>
          <CardDescription>
            Elegi modo, valida conectores y ejecuta controles admin. Para viewer queda en solo lectura.
          </CardDescription>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <Metric title="Modo runtime" value={health ? modeLabel(health.exchange.mode) : settings ? modeLabel(settings.mode) : "--"} compact />
              <Metric title="Exchange activo" value={selectedExchange.toUpperCase()} compact />
              <Metric title="WS/SSE backend" value={health ? (health.ws.connected ? "conectado" : "desconectado") : "--"} compact />
              <Metric title="Estado bot" value={botStatus ? statusLabel(botStatus.bot_status) : "--"} compact />
              <Metric title="PnL diario" value={botStatus ? fmtUsd(botStatus.pnl.daily) : "--"} compact />
              <Metric title="Max DD / Limite" value={botStatus ? `${fmtPct(botStatus.max_dd.value)} / ${fmtPct(botStatus.max_dd.limit)}` : "--"} compact />
            </div>

            <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Modo operativo</label>
                <Select value={modeDraft} onChange={(e) => setModeDraft(e.target.value as TradingMode)} disabled={modeBusy || role !== "admin"}>
                  <option value="MOCK">Mock (sin ordenes reales)</option>
                  <option value="PAPER">Paper</option>
                  <option value="TESTNET">Testnet</option>
                  <option value="LIVE">Live</option>
                </Select>
                <p className="mt-1 text-xs text-slate-400">
                  Cambia el modo runtime del bot. Para LIVE, el backend exige gates PASS y confirmacion explicita.
                </p>
              </div>
              <div className="flex items-end">
                <Button
                  variant="outline"
                  disabled={role !== "admin" || modeBusy || refreshing}
                  onClick={() => {
                    void applyMode();
                  }}
                  title="Aplica el modo operativo en el backend (no inicia trading por si solo)."
                >
                  {modeBusy ? "Aplicando..." : "Aplicar modo"}
                </Button>
              </div>
              <div className="flex items-end">
                <Button
                  variant="secondary"
                  disabled={refreshing}
                  onClick={() => {
                    void refreshAll(true);
                  }}
                  title="Refresca estado del bot, health, gates, rollout y diagnostico del exchange."
                >
                  {refreshing ? "Refrescando..." : "Refrescar panel"}
                </Button>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <ActionButton
                label={actionLoading === "/api/v1/bot/start" ? "Iniciando..." : "Iniciar"}
                help="Inicia el bot con la estrategia principal configurada para el modo actual."
                disabled={role !== "admin" || !!actionLoading}
                onClick={() => void runControlAction("/api/v1/bot/start", undefined, { successMessage: "Bot iniciado." })}
              />
              <ActionButton
                label={actionLoading === "/api/v1/bot/stop" ? "Deteniendo..." : "Detener"}
                help="Detiene el bot (estado PAUSED) sin ejecutar kill switch."
                variant="secondary"
                disabled={role !== "admin" || !!actionLoading}
                onClick={() => void runControlAction("/api/v1/bot/stop", undefined, { successMessage: "Bot detenido." })}
              />
              <ActionButton
                label={actionLoading === "/api/v1/control/pause" ? "Pausando..." : "Pausar"}
                help="Pausa la operativa. Equivalente a stop suave."
                variant="secondary"
                disabled={role !== "admin" || !!actionLoading}
                onClick={() => void runControlAction("/api/v1/control/pause", undefined, { successMessage: "Bot pausado." })}
              />
              <ActionButton
                label={actionLoading === "/api/v1/control/resume" ? "Reanudando..." : "Reanudar"}
                help="Reanuda la operativa usando la estrategia principal del modo actual."
                disabled={role !== "admin" || !!actionLoading}
                onClick={() => void runControlAction("/api/v1/control/resume", undefined, { successMessage: "Bot reanudado." })}
              />
              <ActionButton
                label="Modo seguro ON"
                help="Reduce riesgo operativo. Usalo cuando el mercado esta inestable o en observacion."
                variant="outline"
                disabled={role !== "admin" || !!actionLoading || onCooldown}
                onClick={() => void runControlAction("/api/v1/control/safe-mode", { enabled: true }, { successMessage: "Modo seguro activado." })}
              />
              <ActionButton
                label="Modo seguro OFF"
                help="Vuelve al modo normal. Verifica riesgo/gates antes de apagarlo."
                variant="secondary"
                disabled={role !== "admin" || !!actionLoading || onCooldown}
                onClick={() => void runControlAction("/api/v1/control/safe-mode", { enabled: false }, { successMessage: "Modo seguro desactivado." })}
              />
              <ActionButton
                label="Cerrar posiciones"
                help="Solicitud de cierre de todas las posiciones (soft action). Revisa logs y confirmacion del exchange."
                variant="outline"
                disabled={role !== "admin" || !!actionLoading || onCooldown}
                onClick={() =>
                  void runControlAction("/api/v1/control/close-all", undefined, {
                    confirm: "Confirmar solicitud de cierre de todas las posiciones?",
                    successMessage: "Solicitud de cierre enviada.",
                  })
                }
              />
              <ActionButton
                label="Kill switch"
                help="Interruptor de emergencia: detiene trading y activa safe mode. Requiere doble confirmacion."
                variant="danger"
                disabled={role !== "admin" || !!actionLoading || onCooldown}
                onClick={() => {
                  const ok = window.confirm("Confirmar Kill switch (emergencia). Esto detiene el trading.");
                  if (!ok) return;
                  const ok2 = window.confirm("Segunda confirmacion: ejecutar Kill switch ahora?");
                  if (!ok2) return;
                  void runControlAction("/api/v1/control/kill", undefined, {
                    successMessage: "Kill switch ejecutado.",
                    cooldownMs: 10_000,
                  });
                }}
              />
            </div>

            {onCooldown ? (
              <p className="text-xs text-amber-300">
                Cooldown critico activo por unos segundos para evitar ejecuciones repetidas del kill switch / safe mode.
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Checklist Live Ready</CardTitle>
          <CardDescription>
            Validacion rapida para operar en {modeLabel(modeDraft)}. Opcion B: nada se promueve a LIVE sin approve humano.
          </CardDescription>
          <CardContent className="space-y-2">
            {liveReadyItems.map((item) => (
              <ChecklistRow key={item.key} label={item.label} status={item.status} help={item.help} />
            ))}
            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
              <p className="font-semibold text-slate-100">Que hacer ahora</p>
              <ol className="mt-2 list-decimal space-y-1 pl-4">
                <li>Verifica exchange y permisos (Read + Trade, sin Withdraw).</li>
                <li>Corre rollout en Shadow/Canary desde Settings &gt; Rollout / Gates.</li>
                <li>Aprueba manualmente antes de STABLE_100.</li>
              </ol>
            </div>
            {modeDraft === "LIVE" ? (
              <Badge variant={canTradeLiveNow ? "success" : "warn"}>
                {canTradeLiveNow ? "Live listo para pruebas controladas (con approve)" : "Live bloqueado hasta completar checklist"}
              </Badge>
            ) : (
              <Badge variant="info">Modo no-LIVE: recomendado para diagnostico y pruebas</Badge>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Estado de conectores</CardTitle>
          <CardDescription>
            Estado por exchange soportado. El diagnostico detallado se muestra para el exchange seleccionado en el modo actual.
          </CardDescription>
          <CardContent className="space-y-2">
            {connectorRows.map((row) => (
              <div key={row.name} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-100">{row.name.toUpperCase()}</span>
                    {row.name === selectedExchange ? <Badge variant="info">activo</Badge> : null}
                  </div>
                  <Badge variant={row.variant}>{row.label}</Badge>
                </div>
                <p className="mt-2 text-xs text-slate-400">{row.detail}</p>
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={refreshing}
                onClick={() => {
                  void refreshAll(true);
                }}
                title="Reejecuta el diagnostico del exchange seleccionado."
              >
                Probar exchange
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  window.location.href = "/settings";
                }}
                title="Abrir Settings para revisar credenciales, modo y diagnostico completo."
              >
                Ir a Settings (Diagnostico)
              </Button>
            </div>
            {exchangeDiag ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
                <p className="font-semibold text-slate-100">Detalle tecnico del diagnostico</p>
                <div className="mt-2 grid gap-1">
                  <p>base_url: {exchangeDiag.base_url || "-"}</p>
                  <p>ws_url: {exchangeDiag.ws_url || "-"}</p>
                  <p>source: {exchangeDiag.key_source || "-"}</p>
                  <p>connector_ok: {exchangeDiag.connector_ok ? "si" : "no"} / order_ok: {exchangeDiag.order_ok ? "si" : "no"}</p>
                  {exchangeDiag.last_error ? <p className="text-amber-300">ultimo error: {exchangeDiag.last_error}</p> : null}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Estado de rollout / aprobacion</CardTitle>
          <CardDescription>
            Resumen del loop Safe Update (gates, canary, approve). Los detalles operativos siguen en Settings &gt; Rollout / Gates.
          </CardDescription>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Metric title="Estado rollout" value={rollout?.state || "IDLE"} compact />
              <Metric title="Gates LIVE" value={gates?.overall_status || "UNKNOWN"} compact />
              <Metric title="Aprobacion pendiente" value={rollout?.pending_live_approval ? "si" : "no"} compact />
              <Metric title="Aprobacion obligatoria" value={rollout?.live_stable_100_requires_approve ? "si" : "no"} compact />
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
              <p className="font-semibold text-slate-100">Que hacer ahora</p>
              <ol className="mt-2 list-decimal space-y-1 pl-4">
                <li>Ejecuta evaluacion offline y compara vs baseline.</li>
                <li>Inicia Shadow/Canary para generar telemetria de blending y KPIs.</li>
                <li>Aprueba manualmente solo cuando gates y canary esten OK.</li>
              </ol>
            </div>
            <Button
              variant="outline"
              onClick={() => {
                window.location.href = "/settings";
              }}
              title="Abrir panel completo de Rollout / Gates."
            >
              Ir a Rollout / Gates
            </Button>
          </CardContent>
        </Card>
      </section>

      {!hasData ? (
        <Card>
          <CardContent className="space-y-3">
            <p className="text-sm font-semibold text-slate-100">Todavia no hay datos de ejecucion</p>
            <p className="text-sm text-slate-400">
              Esta pantalla se llena con metricas reales de fills/slippage/latencia cuando corrés Paper o Testnet (y tambien con algunos datos de backtest si existen).
            </p>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
              <p className="font-semibold text-slate-100">Que hacer ahora</p>
              <ol className="mt-2 list-decimal space-y-1 pl-4">
                <li>Ir a Settings y verificar conectores / diagnostico.</li>
                <li>Ejecutar una sesion Testnet (10 min) o Paper.</li>
                <li>Volver a esta pantalla y refrescar.</li>
              </ol>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900"
                onClick={() => {
                  window.location.href = "/settings";
                }}
              >
                Ir a Settings (Diagnostico)
              </button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardTitle>Ejecucion (Diagnostico)</CardTitle>
        <CardDescription>
          Calidad de fills, spread/slippage, latencia, rate limits y salud operativa del conector. Esta seccion se alimenta con Paper/Testnet/Live.
        </CardDescription>
      </Card>

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

function modeLabel(mode: TradingMode | string): string {
  const normalized = String(mode).toUpperCase();
  if (normalized === "MOCK") return "Mock";
  if (normalized === "PAPER") return "Paper";
  if (normalized === "TESTNET") return "Testnet";
  if (normalized === "LIVE") return "Live";
  return normalized;
}

function statusLabel(status: BotStatusResponse["bot_status"] | string): string {
  const normalized = String(status).toUpperCase();
  if (normalized === "RUNNING") return "Corriendo";
  if (normalized === "PAUSED") return "Pausado";
  if (normalized === "SAFE_MODE") return "Modo seguro";
  if (normalized === "KILLED") return "Kill switch";
  return normalized;
}

function ChecklistRow({
  label,
  status,
  help,
}: {
  label: string;
  status: "pass" | "fail" | "warn" | "pending" | "manual";
  help: string;
}) {
  const badgeVariant =
    status === "pass" ? "success" : status === "fail" ? "danger" : status === "warn" ? "warn" : status === "manual" ? "info" : "neutral";
  const badgeText =
    status === "pass" ? "OK" : status === "fail" ? "FAIL" : status === "warn" ? "ATENCION" : status === "manual" ? "MANUAL" : "PENDIENTE";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-slate-100">{label}</p>
        <Badge variant={badgeVariant}>{badgeText}</Badge>
      </div>
      <p className="mt-1 text-xs text-slate-400">{help}</p>
    </div>
  );
}

function ActionButton({
  label,
  help,
  onClick,
  disabled,
  variant = "default",
}: {
  label: string;
  help: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "secondary" | "outline" | "danger";
}) {
  return (
    <Button className="w-full" variant={variant} disabled={disabled} onClick={onClick} title={help}>
      {label}
    </Button>
  );
}

function Metric(props: { label?: string; title?: string; value: string; compact?: boolean }) {
  const title = props.title || props.label || "";
  const compact = props.compact ?? false;
  return (
    <Card>
      <CardDescription>{title}</CardDescription>
      <CardTitle className={compact ? "mt-1 text-sm" : "mt-1 text-lg"}>{props.value}</CardTitle>
    </Card>
  );
}
