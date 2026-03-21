"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "@/lib/client-api";
import type {
  BotDecisionLogResponse,
  BotInstance,
  BotPolicyStateResponse,
  BotStatusResponse,
  ExecutionLiveOrderDetailResponse,
  ExecutionLiveOrdersReconcileResponse,
  ExecutionLiveOrdersResponse,
  ExecutionLiveOrdersUnresolvedResponse,
  ExecutionMarketStreamsSummary,
  ExchangeDiagnoseResponse,
  ExecutionStats,
  HealthResponse,
  LivePreflightPayload,
  LivePreflightRunResponse,
  LogEvent,
  SettingsResponse,
  Strategy,
  TradingMode,
} from "@/lib/types";
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

type LogsResponse = {
  items: LogEvent[];
  total: number;
  page: number;
  page_size: number;
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
const ACTIVE_POLL_MS = 12000;
const HIDDEN_POLL_MS = 30000;

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
  const [marketStreams, setMarketStreams] = useState<ExecutionMarketStreamsSummary | null>(null);
  const [livePreflight, setLivePreflight] = useState<LivePreflightPayload | null>(null);
  const [liveOrders, setLiveOrders] = useState<ExecutionLiveOrdersResponse | null>(null);
  const [liveOrdersUnresolved, setLiveOrdersUnresolved] = useState<ExecutionLiveOrdersUnresolvedResponse | null>(null);
  const [selectedLiveOrderId, setSelectedLiveOrderId] = useState("");
  const [selectedLiveOrderDetail, setSelectedLiveOrderDetail] = useState<ExecutionLiveOrderDetailResponse | null>(null);
  const [livePreflightBusy, setLivePreflightBusy] = useState(false);
  const [livePreflightAttestBusy, setLivePreflightAttestBusy] = useState(false);
  const [liveOrdersBusy, setLiveOrdersBusy] = useState(false);
  const [livePreflightNote, setLivePreflightNote] = useState("");
  const [exchangeDiagError, setExchangeDiagError] = useState("");
  const [panelLoading, setPanelLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [controlError, setControlError] = useState("");
  const [modeDraft, setModeDraft] = useState<TradingMode>("PAPER");
  const [modeBusy, setModeBusy] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState<number>(0);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [primaryDraft, setPrimaryDraft] = useState<Record<"paper" | "testnet" | "live", string>>({
    paper: "",
    testnet: "",
    live: "",
  });
  const [primaryBusyMode, setPrimaryBusyMode] = useState<"paper" | "testnet" | "live" | null>(null);
  const [botInstances, setBotInstances] = useState<BotInstance[]>([]);
  const [selectedBotPolicyState, setSelectedBotPolicyState] = useState<BotPolicyStateResponse | null>(null);
  const [selectedBotDecisionLog, setSelectedBotDecisionLog] = useState<BotDecisionLogResponse | null>(null);
  const [selectedBotDomainLoading, setSelectedBotDomainLoading] = useState(false);
  const [selectedBotDomainError, setSelectedBotDomainError] = useState("");
  const [selectedBotDomainNotice, setSelectedBotDomainNotice] = useState("");
  const [botModeFilter, setBotModeFilter] = useState<"all" | "shadow" | "paper" | "testnet" | "live">("all");
  const [botStatusFilter, setBotStatusFilter] = useState<"all" | "active" | "paused" | "archived">("all");
  const [botSelectedIds, setBotSelectedIds] = useState<string[]>([]);
  const [selectedExecutionBotId, setSelectedExecutionBotId] = useState("");
  const [botBulkBusy, setBotBulkBusy] = useState(false);
  const [isPageVisible, setIsPageVisible] = useState<boolean>(() => (typeof document === "undefined" ? true : document.visibilityState === "visible"));
  const pollInFlightRef = useRef(false);

  const loadExecutionMetrics = useCallback(async () => {
    const exec = await apiGet<ExecutionStats>("/api/v1/execution/metrics");
    setStats(exec);
    setError("");
  }, []);

  const loadTradingPanel = useCallback(async (forceExchange: boolean) => {
    const [status, currentSettings, healthPayload, gatesPayload, rolloutPayload, botsPayload, strategiesPayload, marketStreamsPayload, livePreflightPayload, liveOrdersPayload, liveOrdersUnresolvedPayload] = await Promise.all([
      apiGet<BotStatusResponse>("/api/v1/bot/status"),
      apiGet<SettingsResponse>("/api/v1/settings"),
      apiGet<HealthResponse>("/api/v1/health"),
      apiGet<GatesResponse>("/api/v1/gates"),
      apiGet<RolloutStatusLite>("/api/v1/rollout/status"),
      apiGet<{ items: BotInstance[] }>("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0").catch(() => ({ items: [] })),
      apiGet<Strategy[]>("/api/v1/strategies").catch(() => [] as Strategy[]),
      apiGet<ExecutionMarketStreamsSummary>("/api/v1/execution/market-streams/summary").catch(() => null as ExecutionMarketStreamsSummary | null),
      apiGet<LivePreflightPayload>("/api/v1/exchange/live-preflight?mode=live").catch(() => null as LivePreflightPayload | null),
      apiGet<ExecutionLiveOrdersResponse>("/api/v1/execution/live-orders?environment=live&limit=25").catch(() => null as ExecutionLiveOrdersResponse | null),
      apiGet<ExecutionLiveOrdersUnresolvedResponse>("/api/v1/execution/live-orders/unresolved?environment=live").catch(() => null as ExecutionLiveOrdersUnresolvedResponse | null),
    ]);
    setBotStatus(status);
    setSettings(currentSettings);
    setHealth(healthPayload);
    setGates(gatesPayload);
    setRollout(rolloutPayload);
    setBotInstances(Array.isArray(botsPayload?.items) ? botsPayload.items : []);
    setMarketStreams(marketStreamsPayload);
    setLivePreflight(livePreflightPayload);
    setLiveOrders(liveOrdersPayload);
    setLiveOrdersUnresolved(liveOrdersUnresolvedPayload);
    setModeDraft(currentSettings.mode);
    setStrategies(Array.isArray(strategiesPayload) ? strategiesPayload : []);
    const rows = Array.isArray(strategiesPayload) ? strategiesPayload : [];
    const findPrimaryId = (mode: "paper" | "testnet" | "live") =>
      String(rows.find((row) => Array.isArray(row.primary_for_modes) && row.primary_for_modes.includes(mode))?.id || "");
    setPrimaryDraft({
      paper: findPrimaryId("paper"),
      testnet: findPrimaryId("testnet"),
      live: findPrimaryId("live"),
    });

    const mode = (currentSettings.mode || "PAPER").toLowerCase();
    try {
      const diag = await apiGet<ExchangeDiagnoseResponse>(`/api/v1/exchange/diagnose?force=${forceExchange ? "true" : "false"}&mode=${encodeURIComponent(mode)}`);
      setExchangeDiag(diag);
      setExchangeDiagError("");
    } catch (err) {
      setExchangeDiag(null);
      setExchangeDiagError(err instanceof Error ? err.message : "No se pudo diagnosticar el exchange.");
    }
  }, []);

  const refreshAll = useCallback(async (forceExchange = false) => {
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
  }, [loadExecutionMetrics, loadTradingPanel]);

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
  }, [loadExecutionMetrics, loadTradingPanel]);

  useEffect(() => {
    const onVisibility = () => {
      setIsPageVisible(document.visibilityState === "visible");
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (cancelled) return;
      if (pollInFlightRef.current) {
        timer = setTimeout(tick, isPageVisible ? ACTIVE_POLL_MS : HIDDEN_POLL_MS);
        return;
      }
      pollInFlightRef.current = true;
      try {
        if (isPageVisible) {
          await Promise.all([loadExecutionMetrics(), loadTradingPanel(false)]);
        } else {
          // Hidden tab: keep lightweight status updates at lower frequency.
          await loadTradingPanel(false);
        }
      } catch {
        // Best-effort polling: user can always refresh manually.
      } finally {
        pollInFlightRef.current = false;
      }
      timer = setTimeout(tick, isPageVisible ? ACTIVE_POLL_MS : HIDDEN_POLL_MS);
    };

    timer = setTimeout(tick, isPageVisible ? ACTIVE_POLL_MS : HIDDEN_POLL_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [isPageVisible, loadExecutionMetrics, loadTradingPanel]);

  useEffect(() => {
    const firstId = liveOrders?.items?.[0]?.execution_order_id || "";
    if (!selectedLiveOrderId && firstId) {
      setSelectedLiveOrderId(firstId);
    } else if (selectedLiveOrderId && !(liveOrders?.items || []).some((row) => row.execution_order_id === selectedLiveOrderId)) {
      setSelectedLiveOrderId(firstId);
    }
  }, [liveOrders, selectedLiveOrderId]);

  useEffect(() => {
    let cancelled = false;
    const loadLiveOrderDetail = async () => {
      if (!selectedLiveOrderId) {
        setSelectedLiveOrderDetail(null);
        return;
      }
      try {
        const payload = await apiGet<ExecutionLiveOrderDetailResponse>(`/api/v1/execution/live-orders/${encodeURIComponent(selectedLiveOrderId)}`);
        if (!cancelled) setSelectedLiveOrderDetail(payload);
      } catch {
        if (!cancelled) setSelectedLiveOrderDetail(null);
      }
    };
    void loadLiveOrderDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedLiveOrderId, liveOrders]);

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
      { metric: "Maker ratio (%)", value: (stats?.maker_ratio || 0) * 100, unit: "%" },
      { metric: "Fill ratio (%)", value: (stats?.fill_ratio || 0) * 100, unit: "%" },
      { metric: "Slippage p95 (bps)", value: stats?.p95_slippage || 0, unit: "bps" },
      { metric: "Spread p95 (bps)", value: stats?.p95_spread || 0, unit: "bps" },
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

  const livePreflightLatest = livePreflight?.latest || null;
  const livePreflightGate = livePreflight?.live_enablement_gate || null;
  const livePreflightAttestationStatus = livePreflight?.attestation_status || null;
  const livePreflightAttestation = livePreflight?.latest_attestation || null;
  const livePreflightChecks = livePreflightLatest?.checks ? Object.entries(livePreflightLatest.checks) : [];
  const livePreflightRecentRuns = livePreflight?.recent_runs?.slice(0, 5) || [];
  const livePreflightStatus: "pass" | "fail" | "warn" | "pending" =
    !livePreflightLatest
      ? "pending"
      : livePreflightGate?.ok
        ? "pass"
        : livePreflightLatest.overall_status === "WARN"
          ? "warn"
          : "fail";
  const livePreflightHelp = !livePreflightLatest
    ? "Todavia no hay una corrida persistida del preflight LIVE final."
    : livePreflightGate?.ok
      ? `Preflight PASS y fresco hasta ${formatDateTime(livePreflightLatest.expires_at)}.`
      : livePreflightGate?.reason === "live_preflight_expired"
        ? `El ultimo preflight vencio en ${formatDateTime(livePreflightLatest.expires_at)}.`
        : livePreflightLatest.blocking_reasons?.length
          ? `Bloqueos: ${livePreflightLatest.blocking_reasons.join(", ")}.`
          : `Estado ${livePreflightLatest.overall_status}.`;
  const manualPermsStatus: "pass" | "fail" | "warn" | "pending" | "manual" = !livePreflightAttestationStatus
    ? "manual"
    : livePreflightAttestationStatus.status === "PASS"
      ? "pass"
      : "fail";
  const manualPermsHelp = livePreflightAttestationStatus
    ? livePreflightAttestationStatus.status === "PASS"
      ? `Attestation vigente hasta ${formatDateTime(livePreflightAttestationStatus.expires_at)} por ${livePreflightAttestation?.verified_by || "admin"}.`
      : `Attestation manual requerida: ${livePreflightAttestationStatus.reason}.`
    : "Chequeo manual en el panel del exchange. Requisito obligatorio antes de LIVE.";
  const liveOrdersRows = liveOrders?.items || [];
  const liveOrdersUnresolvedCount = liveOrdersUnresolved?.count ?? 0;
  const liveOrdersSoftDeadlineSec = liveOrdersUnresolved?.soft_deadline_sec ?? 5;
  const liveOrdersHardDeadlineSec = liveOrdersUnresolved?.hard_deadline_sec ?? 30;
  const selectedLiveOrder = selectedLiveOrderDetail?.order || liveOrdersRows.find((row) => row.execution_order_id === selectedLiveOrderId) || null;
  const selectedLiveOrderTimeline = selectedLiveOrderDetail?.timeline || [];

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
      status: manualPermsStatus,
      help: manualPermsHelp,
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
      key: "preflight",
      label: "Preflight LIVE final",
      status: livePreflightStatus,
      help: livePreflightHelp,
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
    liveReadyItems.find((row) => row.key === "gates")?.status === "pass" &&
    liveReadyItems.find((row) => row.key === "preflight")?.status === "pass";
  const liveBlockingItems = liveReadyItems
    .filter((row) => ["keys", "connector", "gates", "preflight"].includes(String(row.key)))
    .filter((row) => row.status !== "pass");
  const liveBotsBlocked = liveBlockingItems.length > 0;
  const liveBotsBlockedReason = liveBlockingItems.map((row) => row.label).join(", ");

  const primaryByMode = useMemo(() => {
    const findPrimary = (mode: "paper" | "testnet" | "live") =>
      strategies.find((row) => Array.isArray(row.primary_for_modes) && row.primary_for_modes.includes(mode)) || null;
    return {
      paper: findPrimary("paper"),
      testnet: findPrimary("testnet"),
      live: findPrimary("live"),
    };
  }, [strategies]);

  const strategyOptionsByMode = useMemo(() => {
    const base = [...strategies].filter((row) => String(row.status || "").toLowerCase() !== "archived");
    return {
      paper: base,
      testnet: base.filter((row) => Boolean(row.enabled_for_trading ?? row.enabled)),
      live: base.filter((row) => Boolean(row.enabled_for_trading ?? row.enabled)),
    };
  }, [strategies]);

  const runtimeModeLower = String(modeDraft || settings?.mode || "PAPER").toLowerCase();
  const runtimeModeKey: "paper" | "testnet" | "live" =
    runtimeModeLower === "live" ? "live" : runtimeModeLower === "testnet" ? "testnet" : "paper";

  const botRowsFiltered = useMemo(() => {
    return botInstances.filter((row) => {
      if (botModeFilter !== "all" && String(row.mode) !== botModeFilter) return false;
      if (botStatusFilter !== "all" && String(row.status) !== botStatusFilter) return false;
      return true;
    });
  }, [botInstances, botModeFilter, botStatusFilter]);

  const visibleBotIds = useMemo(() => botRowsFiltered.map((row) => String(row.id)), [botRowsFiltered]);
  const selectedBotIdsSet = useMemo(() => new Set(botSelectedIds), [botSelectedIds]);
  const selectedExecutionBot = useMemo(
    () => botInstances.find((row) => row.id === selectedExecutionBotId) || null,
    [botInstances, selectedExecutionBotId],
  );

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

  const toggleBotSelection = (botId: string, checked: boolean) => {
    setBotSelectedIds((prev) => {
      const set = new Set(prev);
      if (checked) set.add(botId);
      else set.delete(botId);
      return [...set];
    });
  };

  const selectVisibleBots = () => {
    setBotSelectedIds((prev) => [...new Set([...prev, ...visibleBotIds])]);
  };

  const clearBotSelection = () => {
    setBotSelectedIds([]);
  };

  const runBotsBulkPatch = async (patch: Record<string, unknown>, label: string) => {
    if (role !== "admin") return;
    if (!botSelectedIds.length) {
      setControlError("Selecciona al menos un operador (bot).");
      return;
    }
    if (String(patch.mode || "").toLowerCase() === "live" && liveBotsBlocked) {
      setControlError(`No se puede pasar operadores a LIVE: falta PASS en ${liveBotsBlockedReason}.`);
      return;
    }
    setBotBulkBusy(true);
    setControlError("");
    setMessage("");
    try {
      const res = await apiPost<{
        ok: boolean;
        updated_count: number;
        error_count: number;
        errors?: Array<{ id: string; detail: string }>;
      }>("/api/v1/bots/bulk-patch", {
        ids: botSelectedIds,
        ...patch,
      });
      if (res.error_count) {
        setControlError(`${label}: ${res.updated_count} OK / ${res.error_count} con error.`);
      } else {
        setMessage(`${label}: ${res.updated_count} bot(s) actualizados.`);
      }
      await refreshAll(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : `No se pudo ejecutar: ${label}`);
    } finally {
      setBotBulkBusy(false);
    }
  };

  const patchSingleBot = async (botId: string, patch: Record<string, unknown>, label: string) => {
    if (role !== "admin") return;
    if (String(patch.mode || "").toLowerCase() === "live" && liveBotsBlocked) {
      setControlError(`No se puede pasar ${botId} a LIVE: falta PASS en ${liveBotsBlockedReason}.`);
      return;
    }
    setBotBulkBusy(true);
    setControlError("");
    setMessage("");
    try {
      try {
        await apiPatch(`/api/v1/bots/${encodeURIComponent(botId)}/policy-state`, patch);
      } catch (err) {
        if (!isMissingRouteError(err)) throw err;
        await apiPatch(`/api/v1/bots/${encodeURIComponent(botId)}`, patch);
      }
      setMessage(`${label}: ${botId} actualizado.`);
      await refreshAll(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : `No se pudo ejecutar: ${label}`);
    } finally {
      setBotBulkBusy(false);
    }
  };

  const deleteBot = async (bot: BotInstance) => {
    if (!window.confirm(`Eliminar bot "${bot.name}"? Esta accion borra su registro activo.`)) return;
    setBotBulkBusy(true);
    setControlError("");
    setMessage("");
    try {
      await apiDelete(`/api/v1/bots/${encodeURIComponent(bot.id)}`);
      setBotSelectedIds((prev) => prev.filter((id) => id !== bot.id));
      if (selectedExecutionBotId === bot.id) setSelectedExecutionBotId("");
      setMessage(`Bot "${bot.name}" eliminado.`);
      await refreshAll(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : "No se pudo borrar el bot.");
    } finally {
      setBotBulkBusy(false);
    }
  };

  const deleteBotsBulk = async () => {
    if (role !== "admin") return;
    if (!botSelectedIds.length) {
      setControlError("Selecciona al menos un bot para borrar.");
      return;
    }
    if (!window.confirm(`Borrar ${botSelectedIds.length} bot(s) seleccionado(s)? Esta accion es irreversible.`)) return;
    setBotBulkBusy(true);
    setControlError("");
    setMessage("");
    try {
      let okCount = 0;
      let errCount = 0;
      for (const id of botSelectedIds) {
        try {
          await apiDelete(`/api/v1/bots/${encodeURIComponent(id)}`);
          okCount++;
        } catch {
          errCount++;
        }
      }
      setBotSelectedIds([]);
      if (botSelectedIds.includes(selectedExecutionBotId)) setSelectedExecutionBotId("");
      setMessage(`Borrados: ${okCount} bot(s)${errCount ? ` · Errores: ${errCount}` : ""}.`);
      await refreshAll(false);
    } finally {
      setBotBulkBusy(false);
    }
  };

  const applyMode = async () => {
    setModeBusy(true);
    setControlError("");
    setMessage("");
    try {
      const mode = modeDraft.toLowerCase();
      if (mode === "mock") {
        setControlError("MOCK es un alias legado del mock local del frontend. El runtime real usa PAPER / TESTNET / LIVE y los operadores usan SHADOW por separado.");
        return;
      }
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

  const runLivePreflight = async () => {
    if (role !== "admin") return;
    setLivePreflightBusy(true);
    setControlError("");
    setMessage("");
    try {
      const payload = await apiPost<LivePreflightRunResponse>("/api/v1/exchange/live-preflight/run", {
        mode: "live",
      });
      setMessage(
        payload.ok
          ? "Preflight LIVE final en PASS."
          : `Preflight LIVE final ${payload.run?.overall_status || "FAIL"}: ${payload.run?.blocking_reasons?.join(", ") || "revisar checks"}.`,
      );
      await refreshAll(true);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : "No se pudo ejecutar el preflight LIVE final.");
    } finally {
      setLivePreflightBusy(false);
    }
  };

  const saveLivePreflightAttestation = async () => {
    if (role !== "admin") return;
    setLivePreflightAttestBusy(true);
    setControlError("");
    setMessage("");
    try {
      await apiPost("/api/v1/exchange/live-preflight/attest", {
        mode: "live",
        manual_permissions_verified: true,
        trade_enabled_verified: true,
        withdraw_disabled_verified: true,
        ip_restriction_verified: true,
        note: livePreflightNote.trim(),
      });
      setMessage("Attestation manual LIVE guardada.");
      await refreshAll(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : "No se pudo guardar la attestation manual.");
    } finally {
      setLivePreflightAttestBusy(false);
    }
  };

  const runLiveOrdersReconcile = async (executionOrderId?: string) => {
    if (role !== "admin") return;
    setLiveOrdersBusy(true);
    setControlError("");
    setMessage("");
    try {
      const payload = await apiPost<ExecutionLiveOrdersReconcileResponse>("/api/v1/execution/live-orders/reconcile", {
        execution_order_id: executionOrderId || undefined,
        environment: "live",
        trigger: executionOrderId ? "MANUAL" : "STREAM_GAP",
      });
      const unresolved = payload?.unresolved?.count ?? 0;
      setMessage(
        executionOrderId
          ? `Reconciliacion manual ejecutada para ${executionOrderId}. Ordenes ambiguas restantes: ${unresolved}.`
          : `Reconciliacion manual ejecutada. Ordenes ambiguas restantes: ${unresolved}.`,
      );
      await refreshAll(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : "No se pudo reconciliar el journal live.");
    } finally {
      setLiveOrdersBusy(false);
    }
  };

  const applyPrimaryForMode = async (mode: "paper" | "testnet" | "live") => {
    if (role !== "admin") return;
    const strategyId = String(primaryDraft[mode] || "").trim();
    if (!strategyId) {
      setControlError(`Selecciona estrategia primaria para ${mode.toUpperCase()}.`);
      return;
    }
    setPrimaryBusyMode(mode);
    setControlError("");
    setMessage("");
    try {
      await apiPost(`/api/v1/strategies/${encodeURIComponent(strategyId)}/primary`, { mode });
      setMessage(`Primaria ${mode.toUpperCase()} actualizada a ${strategyId}.`);
      await refreshAll(false);
    } catch (err) {
      setControlError(err instanceof Error ? err.message : `No se pudo actualizar primaria ${mode.toUpperCase()}.`);
    } finally {
      setPrimaryBusyMode(null);
    }
  };

  const selectBotsWhere = (predicate: (bot: BotInstance) => boolean) => {
    const ids = botRowsFiltered.filter(predicate).map((row) => String(row.id));
    setBotSelectedIds(ids);
  };

  useEffect(() => {
    if (botSelectedIds.length === 1) {
      const only = String(botSelectedIds[0] || "");
      if (only && only !== selectedExecutionBotId) setSelectedExecutionBotId(only);
      return;
    }
    if (selectedExecutionBotId && botInstances.some((row) => row.id === selectedExecutionBotId)) return;
    const preferred =
      botInstances.find((row) => row.status === "active" && row.mode === runtimeModeKey) ||
      botInstances.find((row) => row.status === "active") ||
      botInstances[0];
    if (preferred) setSelectedExecutionBotId(preferred.id);
  }, [botInstances, botSelectedIds, runtimeModeKey, selectedExecutionBotId]);

  useEffect(() => {
    let cancelled = false;

    if (!selectedExecutionBotId) {
      setSelectedBotPolicyState(null);
      setSelectedBotDecisionLog(null);
      setSelectedBotDomainError("");
      setSelectedBotDomainNotice("");
      setSelectedBotDomainLoading(false);
      return () => {
        cancelled = true;
      };
    }

    const loadSelectedBotDomains = async () => {
      setSelectedBotDomainLoading(true);
      setSelectedBotDomainError("");
      setSelectedBotDomainNotice("");
      try {
        const [policyState, decisionLog] = await Promise.all([
          apiGet<BotPolicyStateResponse>(`/api/v1/bots/${encodeURIComponent(selectedExecutionBotId)}/policy-state`),
          apiGet<BotDecisionLogResponse>(`/api/v1/bots/${encodeURIComponent(selectedExecutionBotId)}/decision-log?page_size=8`),
        ]);
        if (cancelled) return;
        setSelectedBotPolicyState(policyState);
        setSelectedBotDecisionLog(decisionLog);
      } catch (err) {
        if (cancelled) return;
        const selectedBot = botInstances.find((row) => row.id === selectedExecutionBotId) || null;
        if (isMissingRouteError(err) && selectedBot) {
          try {
            const logsPayload = await apiGet<LogEvent[] | LogsResponse>("/api/v1/logs?page=1&page_size=100");
            const logsRows = Array.isArray(logsPayload) ? logsPayload : logsPayload.items;
            if (cancelled) return;
            setSelectedBotPolicyState(buildLegacyPolicyState(selectedBot));
            setSelectedBotDecisionLog(buildLegacyDecisionLog(selectedBot.id, logsRows));
            setSelectedBotDomainNotice(
              "Compatibilidad legacy activa: policy_state se reconstruye desde /api/v1/bots y decision_log desde /api/v1/logs mientras RTLRESE-14 no este integrado.",
            );
          } catch (fallbackErr) {
            if (cancelled) return;
            setSelectedBotPolicyState(buildLegacyPolicyState(selectedBot));
            setSelectedBotDecisionLog(buildLegacyDecisionLog(selectedBot.id, []));
            setSelectedBotDomainNotice(
              "Compatibilidad legacy parcial: policy_state se reconstruye desde /api/v1/bots. No hubo logs legacy disponibles para este bot.",
            );
            setSelectedBotDomainError(fallbackErr instanceof Error ? fallbackErr.message : "No se pudieron cargar logs legacy del bot seleccionado.");
          }
          return;
        }
        setSelectedBotPolicyState(null);
        setSelectedBotDecisionLog(null);
        setSelectedBotDomainError(err instanceof Error ? err.message : "No se pudieron cargar los dominios del bot seleccionado.");
      } finally {
        if (!cancelled) setSelectedBotDomainLoading(false);
      }
    };

    void loadSelectedBotDomains();
    return () => {
      cancelled = true;
    };
  }, [selectedExecutionBotId, botInstances]);

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
                  <option value="MOCK">Mock local legado (no runtime real)</option>
                  <option value="PAPER">Paper</option>
                  <option value="TESTNET">Testnet</option>
                  <option value="LIVE">Live</option>
                </Select>
                <p className="mt-1 text-xs text-slate-400">
                  Runtime global canonico: PAPER / TESTNET / LIVE. SHADOW aplica a operadores individuales; MOCK queda solo como alias legado del mock local.
                </p>
                {modeDraft === "LIVE" && liveBlockingItems.length ? (
                  <p className="mt-1 text-xs text-amber-300">
                    LIVE bloqueado por checklist: {liveBlockingItems.map((row) => row.label).join(" · ")}.
                  </p>
                ) : null}
              </div>
              <div className="flex items-end">
                <Button
                  variant="outline"
                  disabled={role !== "admin" || modeBusy || refreshing || (modeDraft === "LIVE" && !canTradeLiveNow)}
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
                help={selectedExecutionBot ? `Inicia usando el pool del bot: ${selectedExecutionBot.name}` : "Inicia el bot con la estrategia principal del modo actual."}
                disabled={role !== "admin" || !!actionLoading}
                onClick={() => void runControlAction("/api/v1/bot/start", selectedExecutionBotId ? { bot_id: selectedExecutionBotId } : undefined, { successMessage: "Bot iniciado." })}
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
                help={selectedExecutionBot ? `Reanuda usando el pool del bot: ${selectedExecutionBot.name}` : "Reanuda la operativa usando la estrategia principal del modo actual."}
                disabled={role !== "admin" || !!actionLoading}
                onClick={() => void runControlAction("/api/v1/control/resume", selectedExecutionBotId ? { bot_id: selectedExecutionBotId } : undefined, { successMessage: "Bot reanudado." })}
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

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Operador seleccionado</p>
                  <p className="text-[11px] text-slate-400">
                    Este selector administra bots del registry desde Ejecucion. El runtime global se sigue controlando en el bloque superior.
                  </p>
                </div>
                {selectedExecutionBot ? (
                  <Badge variant={selectedExecutionBot.status === "active" ? "success" : selectedExecutionBot.status === "paused" ? "warn" : "neutral"}>
                    {selectedExecutionBot.status}
                  </Badge>
                ) : (
                  <Badge variant="neutral">sin bot</Badge>
                )}
              </div>
              <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.7fr)_repeat(6,minmax(0,1fr))]">
                <div>
                  <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Bot / operador</label>
                  <Select value={selectedExecutionBotId} onChange={(e) => setSelectedExecutionBotId(e.target.value)} disabled={!botInstances.length}>
                    <option value="">Seleccionar bot...</option>
                    {botInstances.map((bot) => (
                      <option key={`execution-bot-${bot.id}`} value={bot.id}>
                        {`${bot.name} | ${bot.mode.toUpperCase()} | ${bot.status}`}
                      </option>
                    ))}
                  </Select>
                </div>
                <Metric title="Policy status" value={selectedBotPolicyState?.policy_state.status || selectedExecutionBot?.status || "--"} compact />
                <Metric title="Policy mode" value={selectedBotPolicyState?.policy_state.mode?.toUpperCase() || (selectedExecutionBot ? selectedExecutionBot.mode.toUpperCase() : "--")} compact />
                <Metric title="Policy engine" value={selectedBotPolicyState?.policy_state.engine || selectedExecutionBot?.engine || "--"} compact />
                <Metric title="Policy pool" value={selectedExecutionBot ? String(selectedBotPolicyState?.policy_state.pool_strategy_ids.length ?? selectedExecutionBot.pool_strategy_ids.length) : "--"} compact />
                <Metric title="Evidence trades" value={selectedExecutionBot ? String(selectedExecutionBot.metrics?.trade_count ?? 0) : "--"} compact />
                <Metric title="Evidence winRate" value={selectedExecutionBot ? fmtPct(selectedExecutionBot.metrics?.winrate ?? 0) : "--"} compact />
              </div>
              {selectedExecutionBot ? (
                <>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      disabled={role !== "admin" || botBulkBusy}
                      onClick={() =>
                        void patchSingleBot(
                          selectedExecutionBot.id,
                          { status: selectedExecutionBot.status === "active" ? "paused" : "active" },
                          selectedExecutionBot.status === "active" ? "Pausar bot" : "Activar bot",
                        )
                      }
                    >
                      {selectedExecutionBot.status === "active" ? "Pausar bot" : "Activar bot"}
                    </Button>
                    <Button variant="outline" disabled={role !== "admin" || botBulkBusy} onClick={() => void patchSingleBot(selectedExecutionBot.id, { mode: "shadow" }, "Cambiar bot a SHADOW")}>
                      Modo SHADOW
                    </Button>
                    <Button variant="outline" disabled={role !== "admin" || botBulkBusy} onClick={() => void patchSingleBot(selectedExecutionBot.id, { mode: "paper" }, "Cambiar bot a PAPER")}>
                      Modo PAPER
                    </Button>
                    <Button variant="outline" disabled={role !== "admin" || botBulkBusy} onClick={() => void patchSingleBot(selectedExecutionBot.id, { mode: "testnet" }, "Cambiar bot a TESTNET")}>
                      Modo TESTNET
                    </Button>
                    <Button variant="danger" disabled={role !== "admin" || botBulkBusy} onClick={() => void patchSingleBot(selectedExecutionBot.id, { status: "archived" }, "Archivar bot")}>
                      Archivar bot
                    </Button>
                    <Button variant="danger" disabled={role !== "admin" || botBulkBusy} onClick={() => void deleteBot(selectedExecutionBot)}>
                      Borrar bot
                    </Button>
                    <Button variant="ghost" className="text-[11px]" onClick={() => { window.location.href = "/strategies"; }}>
                      Editar pool →
                    </Button>
                  </div>
                  <p className="mt-2 text-[11px] text-slate-400">
                    Policy pool: <strong>{selectedBotPolicyState?.policy_state.pool_strategy_ids.length ?? selectedExecutionBot.pool_strategy_ids.length}</strong> estrategias
                    {selectedExecutionBot.metrics?.last_run_at ? ` · último run ${new Date(selectedExecutionBot.metrics.last_run_at).toLocaleString()}` : ""}
                    {selectedExecutionBot.metrics?.experience_by_source
                      ? ` · shadow ${selectedExecutionBot.metrics.experience_by_source.shadow?.episode_count ?? 0} / backtest ${selectedExecutionBot.metrics.experience_by_source.backtest?.episode_count ?? 0}`
                      : ""}
                  </p>
                  <div className="mt-3 grid gap-3 xl:grid-cols-2">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Bot policy state</p>
                          <p className="text-[11px] text-slate-400">Configuracion operativa declarativa del bot seleccionado. No mezcla evidence ni runtime global.</p>
                        </div>
                        <Badge variant={selectedBotPolicyState?.policy_state.status === "active" ? "success" : selectedBotPolicyState?.policy_state.status === "paused" ? "warn" : "neutral"}>
                          {selectedBotPolicyState?.policy_state.status || selectedExecutionBot.status}
                        </Badge>
                      </div>
                      {selectedBotDomainLoading && !selectedBotPolicyState ? (
                        <p className="mt-3 text-xs text-slate-400">Cargando policy state...</p>
                      ) : selectedBotPolicyState ? (
                        <div className="mt-3 space-y-2 text-xs text-slate-300">
                          <div className="grid gap-2 sm:grid-cols-2">
                            <div className="rounded border border-slate-800 p-2">Mode: <strong>{selectedBotPolicyState.policy_state.mode.toUpperCase()}</strong></div>
                            <div className="rounded border border-slate-800 p-2">Engine: <strong>{selectedBotPolicyState.policy_state.engine}</strong></div>
                            <div className="rounded border border-slate-800 p-2">Pool: <strong>{selectedBotPolicyState.policy_state.pool_strategy_ids.length}</strong></div>
                            <div className="rounded border border-slate-800 p-2">Updated: <strong>{selectedBotPolicyState.policy_state.updated_at ? new Date(selectedBotPolicyState.policy_state.updated_at).toLocaleString() : "-"}</strong></div>
                          </div>
                          <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
                            <p className="text-[10px] uppercase tracking-wide text-slate-500">Pool strategy IDs</p>
                            <p className="mt-1 break-all text-slate-200">
                              {selectedBotPolicyState.policy_state.pool_strategy_ids.length ? selectedBotPolicyState.policy_state.pool_strategy_ids.join(", ") : "Sin estrategias asignadas"}
                            </p>
                          </div>
                          <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
                            <p className="text-[10px] uppercase tracking-wide text-slate-500">Universe / notes</p>
                            <p className="mt-1 text-slate-200">
                              Universe: {selectedBotPolicyState.policy_state.universe.length ? selectedBotPolicyState.policy_state.universe.join(", ") : "none"}
                            </p>
                            <p className="mt-1 text-slate-400">{selectedBotPolicyState.policy_state.notes || "Sin notas declarativas."}</p>
                          </div>
                        </div>
                      ) : (
                        <p className="mt-3 text-xs text-slate-400">Sin policy state detallado para este bot.</p>
                      )}
                    </div>

                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Bot decision log</p>
                          <p className="text-[11px] text-slate-400">Logs recientes y breaker events asociados al bot seleccionado. Es evidencia operativa, no truth ni runtime base.</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="neutral">{selectedBotDecisionLog?.total ?? 0} logs</Badge>
                          <Badge variant="warn">{selectedBotDecisionLog?.breaker_events.length ?? 0} breakers</Badge>
                        </div>
                      </div>
                      {selectedBotDomainLoading && !selectedBotDecisionLog ? (
                        <p className="mt-3 text-xs text-slate-400">Cargando decision log...</p>
                      ) : selectedBotDecisionLog ? (
                        <div className="mt-3 space-y-3">
                          <div>
                            <p className="mb-2 text-[10px] uppercase tracking-wide text-slate-500">Logs recientes</p>
                            <div className="space-y-2">
                              {selectedBotDecisionLog.items.length ? (
                                selectedBotDecisionLog.items.slice(0, 5).map((row) => (
                                  <div key={row.id} className="rounded border border-slate-800 bg-slate-900/40 p-2 text-xs">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <span className="font-semibold text-slate-200">{row.message}</span>
                                      <Badge variant={row.severity === "error" ? "danger" : row.severity === "warn" ? "warn" : "neutral"}>
                                        {row.severity}
                                      </Badge>
                                    </div>
                                    <p className="mt-1 text-slate-400">
                                      {row.ts ? new Date(row.ts).toLocaleString() : "-"} · {row.module} · {row.type}
                                    </p>
                                  </div>
                                ))
                              ) : (
                                <p className="text-xs text-slate-400">Sin logs recientes asociados al bot.</p>
                              )}
                            </div>
                          </div>
                          <div>
                            <p className="mb-2 text-[10px] uppercase tracking-wide text-slate-500">Breaker events</p>
                            <div className="space-y-2">
                              {selectedBotDecisionLog.breaker_events.length ? (
                                selectedBotDecisionLog.breaker_events.slice(0, 3).map((row) => (
                                  <div key={`${row.id}-${row.ts}`} className="rounded border border-amber-500/20 bg-amber-500/5 p-2 text-xs">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <span className="font-semibold text-amber-100">{row.reason}</span>
                                      <Badge variant="warn">{row.mode.toUpperCase()}</Badge>
                                    </div>
                                    <p className="mt-1 text-amber-200/80">
                                      {row.ts ? new Date(row.ts).toLocaleString() : "-"}
                                      {row.run_id ? ` · run ${row.run_id}` : ""}
                                      {row.symbol ? ` · ${row.symbol}` : ""}
                                    </p>
                                  </div>
                                ))
                              ) : (
                                <p className="text-xs text-slate-400">Sin breaker events recientes para este bot.</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <p className="mt-3 text-xs text-slate-400">Sin decision log detallado para este bot.</p>
                      )}
                      {selectedBotDomainNotice ? (
                        <p className="mt-3 text-xs text-amber-200">{selectedBotDomainNotice}</p>
                      ) : null}
                      {selectedBotDomainError ? (
                        <p className="mt-3 text-xs text-amber-300">{selectedBotDomainError}</p>
                      ) : null}
                    </div>
                  </div>
                </>
              ) : (
                <p className="mt-3 text-xs text-slate-400">No hay bots cargados todavía. Crealos o editalos desde Estrategias.</p>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Estrategias primarias por modo</p>
                <Badge variant="info">Runtime actual: {runtimeModeKey.toUpperCase()}</Badge>
              </div>
              <p className="mb-3 text-xs text-slate-400">
                Define la estrategia principal que usa el bot por modo. Para LIVE solo aparecen estrategias habilitadas para trading.
              </p>
              <div className="grid gap-2 md:grid-cols-3">
                {(["paper", "testnet", "live"] as const).map((mode) => (
                  <div key={`primary-mode-${mode}`} className="rounded border border-slate-800 bg-slate-900/50 p-2 text-xs">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-semibold text-slate-200">{mode.toUpperCase()}</span>
                      {primaryByMode[mode] ? (
                        <Badge variant={mode === runtimeModeKey ? "success" : "neutral"}>{primaryByMode[mode]?.id}</Badge>
                      ) : (
                        <Badge variant="warn">sin primaria</Badge>
                      )}
                    </div>
                    <Select
                      value={primaryDraft[mode]}
                      onChange={(e) => setPrimaryDraft((prev) => ({ ...prev, [mode]: e.target.value }))}
                      disabled={role !== "admin" || primaryBusyMode === mode}
                    >
                      <option value="">Seleccionar estrategia...</option>
                      {strategyOptionsByMode[mode].map((row) => (
                        <option key={`${mode}-${row.id}`} value={row.id}>
                          {row.name} ({row.id})
                        </option>
                      ))}
                    </Select>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2 h-7 w-full px-2 text-[11px]"
                      disabled={role !== "admin" || primaryBusyMode === mode || !primaryDraft[mode]}
                      onClick={() => {
                        void applyPrimaryForMode(mode);
                      }}
                    >
                      {primaryBusyMode === mode ? "Guardando..." : `Guardar ${mode.toUpperCase()}`}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
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

        <Card>
          <CardTitle>Preflight LIVE Final</CardTitle>
          <CardDescription>
            Artefacto canonico y persistido para habilitar LIVE en forma fail-closed. No reemplaza los gates: los aterriza con cuenta, filtros, orden de prueba y attestation manual.
          </CardDescription>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={preflightBadgeVariant(livePreflightLatest?.overall_status)}>
                {livePreflightLatest ? `Overall ${livePreflightLatest.overall_status}` : "Sin corrida"}
              </Badge>
              <Badge variant={livePreflightGate?.ok ? "success" : "danger"}>
                {livePreflightGate?.ok ? "PASS fresco" : "Bloquea LIVE"}
              </Badge>
              <Badge variant={livePreflightAttestationStatus?.status === "PASS" ? "success" : "warn"}>
                {livePreflightAttestationStatus?.status === "PASS" ? "Attestation vigente" : "Attestation requerida"}
              </Badge>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <Metric title="Ultima corrida" value={formatDateTime(livePreflightLatest?.evaluated_at)} compact />
              <Metric title="Vence" value={formatDateTime(livePreflightLatest?.expires_at)} compact />
              <Metric title="Freshness (s)" value={String(livePreflightLatest?.freshness_seconds ?? 0)} compact />
              <Metric title="Bloqueos" value={String(livePreflightLatest?.blocking_reasons?.length ?? 0)} compact />
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
              <p className="font-semibold text-slate-100">Estado operativo</p>
              <p className="mt-2">
                {livePreflightHelp}
              </p>
              {livePreflightGate?.reason ? (
                <p className="mt-2 text-slate-400">gate: {livePreflightGate.reason}</p>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold text-slate-100">Attestation manual admin</p>
                {livePreflightAttestation ? (
                  <Badge variant="info">
                    {livePreflightAttestation.verified_by} · {formatDateTime(livePreflightAttestation.verified_at)}
                  </Badge>
                ) : (
                  <Badge variant="warn">pendiente</Badge>
                )}
              </div>
              <p className="mt-2">
                Verifiqué en panel del exchange: Read + Trade OK, Withdraw OFF, IP restriction OK.
              </p>
              <Textarea
                value={livePreflightNote}
                onChange={(e) => setLivePreflightNote(e.target.value)}
                className="mt-3 min-h-[88px] text-xs"
                placeholder="Nota operativa de attestation (opcional, pero recomendable)."
                disabled={role !== "admin" || livePreflightAttestBusy}
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={role !== "admin" || livePreflightAttestBusy}
                  onClick={() => {
                    void saveLivePreflightAttestation();
                  }}
                >
                  {livePreflightAttestBusy ? "Guardando..." : "Guardar attestation manual"}
                </Button>
                <Button
                  disabled={role !== "admin" || livePreflightBusy}
                  onClick={() => {
                    void runLivePreflight();
                  }}
                >
                  {livePreflightBusy ? "Ejecutando..." : "Ejecutar preflight"}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Subchecks de la ultima corrida</p>
              {livePreflightChecks.length ? (
                livePreflightChecks.map(([key, row]) => (
                  <div key={key} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-slate-100">{key}</p>
                        <p className="mt-1 text-xs text-slate-400">{String(row.detail || "-")}</p>
                      </div>
                      <Badge variant={preflightBadgeVariant(String(row.status || "FAIL"))}>{String(row.status || "FAIL")}</Badge>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">
                  Sin corrida persistida todavia.
                </div>
              )}
            </div>

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Historial reciente</p>
              {livePreflightRecentRuns.length ? (
                livePreflightRecentRuns.map((row) => (
                  <div key={row.preflight_id} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-300">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100">{formatDateTime(row.evaluated_at)}</span>
                        <Badge variant={preflightBadgeVariant(row.overall_status)}>{row.overall_status}</Badge>
                      </div>
                      <span className="text-slate-400">vence {formatDateTime(row.expires_at)}</span>
                    </div>
                    <p className="mt-2 text-slate-400">
                      bloqueos: {row.blocking_reasons.length ? row.blocking_reasons.join(", ") : "ninguno"}
                      {row.warnings.length ? ` · warnings: ${row.warnings.join(", ")}` : ""}
                    </p>
                  </div>
                ))
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Ordenes Live</CardTitle>
          <CardDescription>
            Maquina de estados canonica para Spot live. Journal append-only, recovery por startup y reconciliacion manual/REST cuando el stream deja estados ambiguos.
          </CardDescription>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric title="Ordenes visibles" value={String(liveOrders?.count ?? 0)} compact />
              <Metric title="Ambiguas" value={String(liveOrdersUnresolvedCount)} compact />
              <Metric title="Soft deadline (s)" value={String(liveOrdersSoftDeadlineSec)} compact />
              <Metric title="Hard deadline (s)" value={String(liveOrdersHardDeadlineSec)} compact />
            </div>

            {liveOrdersUnresolvedCount > 0 ? (
              <div className="rounded-lg border border-amber-700/60 bg-amber-950/30 p-3 text-xs text-amber-100">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold">Ordenes ambiguas / requieren reconciliacion</p>
                    <p className="mt-1 text-amber-200">
                      Hay {liveOrdersUnresolvedCount} orden(es) en UNKNOWN_PENDING_RECONCILIATION o MANUAL_REVIEW_REQUIRED. LIVE debe operar fail-closed hasta resolverlas.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    disabled={role !== "admin" || liveOrdersBusy}
                    onClick={() => {
                      void runLiveOrdersReconcile();
                    }}
                  >
                    {liveOrdersBusy ? "Reconciliando..." : "Reconciliar ahora"}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
                Sin ordenes ambiguas por encima del hard deadline. El runtime sigue reconciliando por startup, timeout unknown y comando manual.
              </div>
            )}

            {liveOrdersRows.length ? (
              <div className="rounded-lg border border-slate-800">
                <Table>
                  <THead>
                    <TR>
                      <TH>Hora</TH>
                      <TH>Simbolo</TH>
                      <TH>Lado</TH>
                      <TH>Tipo</TH>
                      <TH>Qty / QuoteQty</TH>
                      <TH>clientOrderId</TH>
                      <TH>exchangeOrderId</TH>
                      <TH>Estado local</TH>
                      <TH>Estado exchange</TH>
                      <TH>Filled %</TH>
                      <TH>Avg fill</TH>
                      <TH>Health</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {liveOrdersRows.map((row) => {
                      const selected = row.execution_order_id === selectedLiveOrderId;
                      return (
                        <TR
                          key={row.execution_order_id}
                          className={selected ? "bg-slate-900/70" : undefined}
                          onClick={() => {
                            setSelectedLiveOrderId(row.execution_order_id);
                          }}
                        >
                          <TD>{formatDateTime(row.last_event_at || row.submitted_at)}</TD>
                          <TD>{row.symbol}</TD>
                          <TD>{row.side || "-"}</TD>
                          <TD>{row.order_type || "-"}</TD>
                          <TD>
                            {row.requested_qty != null ? fmtNum(row.requested_qty) : "-"}
                            {row.requested_quote_order_qty != null ? ` / ${fmtNum(row.requested_quote_order_qty)}` : ""}
                          </TD>
                          <TD className="max-w-[180px] truncate" title={row.client_order_id || "-"}>
                            {row.client_order_id || "-"}
                          </TD>
                          <TD>{row.exchange_order_id || "-"}</TD>
                          <TD>
                            <Badge variant={localOrderStateVariant(row.current_local_state)}>{row.current_local_state}</Badge>
                          </TD>
                          <TD>
                            <Badge variant={exchangeOrderStatusVariant(row.last_exchange_order_status)}>{row.last_exchange_order_status || "-"}</Badge>
                          </TD>
                          <TD>{row.filled_pct != null ? `${row.filled_pct.toFixed(2)}%` : "-"}</TD>
                          <TD>{row.avg_fill_price != null ? fmtNum(row.avg_fill_price) : "-"}</TD>
                          <TD>
                            <div className="flex flex-col gap-1">
                              <Badge variant={reconcileStatusVariant(row.reconciliation_status)}>{row.reconciliation_status || "PENDING"}</Badge>
                              {row.unresolved_reason ? <span className="text-[11px] text-amber-300">{row.unresolved_reason}</span> : null}
                            </div>
                          </TD>
                        </TR>
                      );
                    })}
                  </TBody>
                </Table>
              </div>
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">
                Sin ordenes live persistidas todavia. Este panel se llena con submit REST, executionReport, reconciliacion y recovery.
              </div>
            )}

            <div className="grid gap-3 xl:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-100">Detalle de orden</p>
                    <p className="mt-1 text-xs text-slate-400">
                      Timeline auditable con precedencia WS &gt; reconcile/query &gt; REST response inicial.
                    </p>
                  </div>
                  {selectedLiveOrder ? (
                    <Button
                      variant="outline"
                      disabled={role !== "admin" || liveOrdersBusy}
                      onClick={() => {
                        void runLiveOrdersReconcile(selectedLiveOrder.execution_order_id);
                      }}
                    >
                      {liveOrdersBusy ? "Reconciliando..." : "Reconciliar orden"}
                    </Button>
                  ) : null}
                </div>

                {selectedLiveOrder ? (
                  <div className="mt-3 space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <Metric title="Estado local" value={selectedLiveOrder.current_local_state || "-"} compact />
                      <Metric title="Estado exchange" value={selectedLiveOrder.last_exchange_order_status || "-"} compact />
                      <Metric title="Execution type" value={selectedLiveOrder.last_execution_type || "-"} compact />
                      <Metric title="Terminal" value={selectedLiveOrder.terminal ? "si" : "no"} compact />
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-300">
                      <div className="grid gap-2 sm:grid-cols-2">
                        <p>clientOrderId: {selectedLiveOrder.client_order_id || "-"}</p>
                        <p>exchangeOrderId: {selectedLiveOrder.exchange_order_id || "-"}</p>
                        <p>qty: {selectedLiveOrder.requested_qty != null ? fmtNum(selectedLiveOrder.requested_qty) : "-"}</p>
                        <p>quoteQty: {selectedLiveOrder.requested_quote_order_qty != null ? fmtNum(selectedLiveOrder.requested_quote_order_qty) : "-"}</p>
                        <p>filled: {selectedLiveOrder.executed_qty != null ? fmtNum(selectedLiveOrder.executed_qty) : "-"}</p>
                        <p>avg fill: {selectedLiveOrder.avg_fill_price != null ? fmtNum(selectedLiveOrder.avg_fill_price) : "-"}</p>
                      </div>
                      {selectedLiveOrderDetail?.unresolved_reason ? (
                        <p className="mt-2 text-amber-300">unresolved_reason: {selectedLiveOrderDetail.unresolved_reason}</p>
                      ) : null}
                    </div>
                    <div className="space-y-2">
                      {selectedLiveOrderTimeline.length ? (
                        selectedLiveOrderTimeline.map((event) => (
                          <div key={event.event_id} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-300">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge variant="info">{event.source_type}</Badge>
                                <Badge variant={localOrderStateVariant(event.local_state_after)}>{event.local_state_after}</Badge>
                                {event.execution_type ? <Badge variant={exchangeOrderStatusVariant(event.execution_type)}>{event.execution_type}</Badge> : null}
                              </div>
                              <span className="text-slate-400">{formatDateTime(event.event_time_exchange || event.event_time_local)}</span>
                            </div>
                            <p className="mt-2 text-slate-400">
                              {event.local_state_before ? `${event.local_state_before} -> ${event.local_state_after}` : event.local_state_after}
                              {event.exchange_order_status ? ` · X=${event.exchange_order_status}` : ""}
                              {event.reject_reason ? ` · reject=${event.reject_reason}` : ""}
                              {event.expiry_reason ? ` · expiry=${event.expiry_reason}` : ""}
                            </p>
                            {event.raw_payload_json && Object.keys(event.raw_payload_json).length ? (
                              <pre className="mt-2 overflow-x-auto rounded bg-slate-950/60 p-2 text-[11px] text-slate-400">
                                {truncateJson(event.raw_payload_json)}
                              </pre>
                            ) : null}
                          </div>
                        ))
                      ) : (
                        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-400">
                          Sin timeline cargado para esta orden.
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-400">
                    Selecciona una orden para ver journal, payloads y reconciliacion.
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <p className="text-sm font-semibold text-slate-100">Reglas operativas RTLOPS-48</p>
                <div className="mt-3 space-y-2 text-xs text-slate-300">
                  <p>Estados canónicos: INTENT_CREATED, PRECHECK_PASSED, SUBMITTING, UNKNOWN_PENDING_RECONCILIATION, ACKED, WORKING, PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, CANCELED, REJECTED, EXPIRED, EXPIRED_STP, RECOVERED_OPEN, RECOVERED_TERMINAL, MANUAL_REVIEW_REQUIRED.</p>
                  <p>Autoridad: executionReport en tiempo real &gt; query/openOrders de reconciliación &gt; respuesta REST inicial.</p>
                  <p>Fail-closed: UNKNOWN_PENDING_RECONCILIATION o MANUAL_REVIEW_REQUIRED por encima de {liveOrdersHardDeadlineSec}s bloquea nuevos submits live del mismo bot+símbolo.</p>
                  <p>Dedup: WS por executionId cuando existe; si no, fallback robusto por clientOrderId + executionType + status + transactionTime + cumulativeFilledQty.</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
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
          <CardTitle>Runtime WebSocket de mercado</CardTitle>
          <CardDescription>
            Estado live/testnet de streams publicos Binance por familia. Este bloque no cubre user data privado.
          </CardDescription>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Metric title="Policy cargada" value={marketStreams?.policy_loaded ? "si" : "no"} compact />
              <Metric title="Sesiones activas" value={String(marketStreams?.running_sessions ?? 0)} compact />
              <Metric title="Live degradado" value={marketStreams?.live_degraded ? "si" : "no"} compact />
              <Metric title="Live bloqueado" value={marketStreams?.live_blocked ? "si" : "no"} compact />
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
              <p className="font-semibold text-slate-100">Separacion canonica</p>
              <div className="mt-2 grid gap-2">
                <p>binance_spot: spot / spot_wallet / spot_costs</p>
                <p>binance_um_futures: um_futures / futures_wallet / um_futures_costs</p>
              </div>
            </div>
            {marketStreams?.sessions?.length ? (
              <div className="space-y-2">
                {marketStreams.sessions.map((row) => (
                  <div key={`${row.execution_connector}-${row.environment}`} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-100">{row.execution_connector}</span>
                        <Badge variant={row.environment === "live" ? "danger" : "info"}>{row.environment}</Badge>
                      </div>
                      <Badge variant={row.block_live ? "danger" : row.degraded_mode ? "warn" : row.connected ? "success" : "neutral"}>
                        {row.block_live ? "BLOCK" : row.degraded_mode ? "WARN" : row.connected ? "OK" : "IDLE"}
                      </Badge>
                    </div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <p>familia: {row.market_family} / repo: {row.repo_family}</p>
                      <p>transport: {row.transport_mode}</p>
                      <p>simbolos: {row.symbols_subscribed?.join(", ") || "-"}</p>
                      <p>reconnects: {row.reconnect_count}</p>
                      <p>stale_ms: {row.stale_ms ?? "-"}</p>
                      <p>lag_ms: {row.stream_lag_estimate_ms ?? "-"}</p>
                    </div>
                    <p className="mt-2 text-[11px] text-slate-400">
                      razon: {row.reason || "-"}
                      {row.last_disconnect_reason ? ` · ultimo disconnect: ${row.last_disconnect_reason}` : ""}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">
                Sin sesiones activas. El runtime exige arranque explicito y sigue fail-closed.
              </div>
            )}
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

      <Card>
        <CardTitle>Operadores (bots) - administracion</CardTitle>
        <CardDescription>
          Selecciona operadores y aplica acciones masivas por estado/modo. Esto administra bots de aprendizaje; no reemplaza el bot runtime global.
        </CardDescription>
        <CardContent className="space-y-3">
          <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs text-slate-300">
            Runtime global: <strong>{runtimeModeKey.toUpperCase()}</strong> · Operadores visibles se gestionan por separado (shadow/paper/testnet/live).
          </div>
          <div className="grid gap-3 md:grid-cols-6">
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Filtro modo</label>
              <Select value={botModeFilter} onChange={(e) => setBotModeFilter(e.target.value as "all" | "shadow" | "paper" | "testnet" | "live")}>
                <option value="all">Todos</option>
                <option value="shadow">shadow</option>
                <option value="paper">paper</option>
                <option value="testnet">testnet</option>
                <option value="live">live</option>
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Filtro estado</label>
              <Select value={botStatusFilter} onChange={(e) => setBotStatusFilter(e.target.value as "all" | "active" | "paused" | "archived")}>
                <option value="all">Todos</option>
                <option value="active">active</option>
                <option value="paused">paused</option>
                <option value="archived">archived</option>
              </Select>
            </div>
            <div className="flex items-end">
              <Button variant="outline" className="w-full" onClick={selectVisibleBots} disabled={!visibleBotIds.length}>
                Seleccionar visibles ({visibleBotIds.length})
              </Button>
            </div>
            <div className="flex items-end">
              <Button variant="outline" className="w-full" onClick={clearBotSelection} disabled={!botSelectedIds.length}>
                Limpiar seleccion ({botSelectedIds.length})
              </Button>
            </div>
            <div className="flex items-end">
              <Button
                variant="outline"
                className="w-full"
                onClick={() => selectBotsWhere((row) => String(row.status) === "active")}
                disabled={!botRowsFiltered.length}
              >
                Seleccionar activos
              </Button>
            </div>
            <div className="flex items-end">
              <Button
                variant="outline"
                className="w-full"
                onClick={() => selectBotsWhere((row) => String(row.mode) === runtimeModeKey)}
                disabled={!botRowsFiltered.length}
              >
                Seleccionar modo runtime
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
            <span>Visibles: {botRowsFiltered.length}</span>
            <span>Seleccionados: {botSelectedIds.length}</span>
            <Badge variant={botBulkBusy ? "warn" : "neutral"}>{botBulkBusy ? "Aplicando..." : "Listo"}</Badge>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={role !== "admin" || botBulkBusy || !botSelectedIds.length} onClick={() => void runBotsBulkPatch({ status: "active" }, "Activar operadores")}>
              Activar
            </Button>
            <Button variant="outline" disabled={role !== "admin" || botBulkBusy || !botSelectedIds.length} onClick={() => void runBotsBulkPatch({ status: "paused" }, "Pausar operadores")}>
              Pausar
            </Button>
            <Button variant="outline" disabled={role !== "admin" || botBulkBusy || !botSelectedIds.length} onClick={() => void runBotsBulkPatch({ mode: "paper" }, "Cambiar modo a PAPER")}>
              Modo PAPER
            </Button>
            <Button variant="outline" disabled={role !== "admin" || botBulkBusy || !botSelectedIds.length} onClick={() => void runBotsBulkPatch({ mode: "testnet" }, "Cambiar modo a TESTNET")}>
              Modo TESTNET
            </Button>
            <Button
              variant="outline"
              disabled={role !== "admin" || botBulkBusy || !botSelectedIds.length || liveBotsBlocked}
              title={liveBotsBlocked ? `Bloqueado: ${liveBotsBlockedReason}` : "Cambiar modo de operadores a LIVE"}
              onClick={() => void runBotsBulkPatch({ mode: "live" }, "Cambiar modo a LIVE")}
            >
              Modo LIVE
            </Button>
            <Button variant="danger" disabled={role !== "admin" || botBulkBusy || !botSelectedIds.length} onClick={() => void runBotsBulkPatch({ status: "archived" }, "Archivar operadores")}>
              Archivar
            </Button>
            <Button variant="danger" disabled={role !== "admin" || botBulkBusy || !botSelectedIds.length} onClick={() => void deleteBotsBulk()}>
              Borrar
            </Button>
          </div>

          <div className="overflow-x-auto">
            <Table className="text-xs">
              <THead>
                <TR>
                  <TH></TH>
                  <TH>Bot</TH>
                  <TH>Engine</TH>
                  <TH>Modo</TH>
                  <TH>Estado</TH>
                  <TH>Pool</TH>
                  <TH>Trades</TH>
                  <TH>WinRate</TH>
                  <TH>PnL</TH>
                  <TH>Sharpe</TH>
                  <TH>Recs</TH>
                  <TH>Kills</TH>
                  <TH>Acciones</TH>
                </TR>
              </THead>
              <TBody>
                {botRowsFiltered.map((bot) => {
                  const selected = selectedBotIdsSet.has(bot.id);
                  const m = bot.metrics;
                  return (
                    <TR key={bot.id}>
                      <TD>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={(e) => toggleBotSelection(bot.id, e.target.checked)}
                        />
                      </TD>
                      <TD>
                        <div className="max-w-[180px]">
                          <p className="truncate font-semibold text-slate-100" title={bot.name}>{bot.name}</p>
                          <p className="truncate text-[11px] text-slate-400" title={bot.id}>{bot.id}</p>
                        </div>
                      </TD>
                      <TD>{bot.engine}</TD>
                      <TD><Badge variant={bot.mode === "live" ? "warn" : bot.mode === "testnet" ? "info" : "neutral"}>{bot.mode}</Badge></TD>
                      <TD><Badge variant={bot.status === "active" ? "success" : bot.status === "paused" ? "warn" : "neutral"}>{bot.status}</Badge></TD>
                      <TD>{m?.strategy_count ?? bot.pool_strategy_ids.length}</TD>
                      <TD>{m?.trade_count ?? 0}</TD>
                      <TD>{fmtPct(m?.winrate ?? 0)}</TD>
                      <TD className={(m?.net_pnl || 0) >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(m?.net_pnl ?? 0)}</TD>
                      <TD>{fmtNum(m?.avg_sharpe ?? 0)}</TD>
                      <TD>{m?.recommendations_pending ?? 0}/{m?.recommendations_approved ?? 0}/{m?.recommendations_rejected ?? 0}</TD>
                      <TD>
                        <div>{m?.kills_total ?? 0}</div>
                        <div className="text-[10px] text-slate-500">24h: {m?.kills_24h ?? 0}</div>
                      </TD>
                      <TD>
                        <div className="flex flex-wrap gap-1">
                          <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" disabled={role !== "admin" || botBulkBusy} onClick={() => void patchSingleBot(bot.id, { status: bot.status === "active" ? "paused" : "active" }, bot.status === "active" ? "Pausar operador" : "Activar operador")}>
                            {bot.status === "active" ? "Pausar" : "Activar"}
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px]" onClick={() => { window.location.href = "/strategies"; }}>
                            Pool →
                          </Button>
                          <Button size="sm" variant="danger" className="h-7 px-2 text-[11px]" disabled={role !== "admin" || botBulkBusy} onClick={() => void deleteBot(bot)}>
                            Borrar
                          </Button>
                        </div>
                      </TD>
                    </TR>
                  );
                })}
                {!botRowsFiltered.length ? (
                  <TR>
                    <TD colSpan={13} className="text-slate-400">
                      No hay operadores para estos filtros. Ajusta modo/estado o crea bots en Estrategias.
                    </TD>
                  </TR>
                ) : null}
              </TBody>
            </Table>
          </div>
        </CardContent>
      </Card>

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
                  <XAxis dataKey="metric" tick={{ fill: "#94a3b8", fontSize: 10 }} interval={0} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} label={{ value: "% / bps", angle: -90, position: "insideLeft", offset: 10, fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }}
                    formatter={(val, _name, props) => [`${Number(val ?? 0).toFixed(2)} ${(props.payload as { unit?: string } | undefined)?.unit ?? ""}`, "Valor"]}
                  />
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
                  <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} label={{ value: "Tiempo / muestra", position: "insideBottom", offset: -5, fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis
                    yAxisId="left"
                    tick={{ fill: "#94a3b8", fontSize: 11 }}
                    label={{ value: "Latencia p95 (ms)", angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 11 }}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fill: "#94a3b8", fontSize: 11 }}
                    label={{ value: "Spread (bps)", angle: 90, position: "insideRight", fill: "#94a3b8", fontSize: 11 }}
                  />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend wrapperStyle={{ color: "#cbd5e1", fontSize: 11 }} />
                  <Line yAxisId="left" type="monotone" dataKey="latency" name="Latencia p95 (ms)" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="spread" name="Spread (bps)" stroke="#f97316" strokeWidth={2} dot={false} />
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
  if (normalized === "MOCK") return "Mock local (legado)";
  if (normalized === "PAPER") return "Paper";
  if (normalized === "TESTNET") return "Testnet";
  if (normalized === "LIVE") return "Live";
  return normalized;
}

function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString();
}

function preflightBadgeVariant(status?: string): "success" | "danger" | "warn" | "neutral" {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "PASS") return "success";
  if (normalized === "WARN") return "warn";
  if (normalized === "FAIL") return "danger";
  return "neutral";
}

function localOrderStateVariant(state?: string | null): "success" | "danger" | "warn" | "info" | "neutral" {
  const normalized = String(state || "").toUpperCase();
  if (["FILLED", "RECOVERED_TERMINAL"].includes(normalized)) return "success";
  if (["REJECTED", "EXPIRED", "EXPIRED_STP", "MANUAL_REVIEW_REQUIRED"].includes(normalized)) return "danger";
  if (["UNKNOWN_PENDING_RECONCILIATION", "CANCEL_REQUESTED", "PARTIALLY_FILLED"].includes(normalized)) return "warn";
  if (["ACKED", "WORKING", "RECOVERED_OPEN", "PRECHECK_PASSED", "SUBMITTING"].includes(normalized)) return "info";
  return "neutral";
}

function exchangeOrderStatusVariant(status?: string | null): "success" | "danger" | "warn" | "info" | "neutral" {
  const normalized = String(status || "").toUpperCase();
  if (["NEW", "PARTIALLY_FILLED", "FILLED"].includes(normalized)) return normalized === "FILLED" ? "success" : normalized === "PARTIALLY_FILLED" ? "warn" : "info";
  if (["CANCELED", "REJECTED", "EXPIRED", "EXPIRED_IN_MATCH", "TRADE_PREVENTION"].includes(normalized)) return "danger";
  if (["TRADE", "REPLACED"].includes(normalized)) return "warn";
  return "neutral";
}

function reconcileStatusVariant(status?: string | null): "success" | "danger" | "warn" | "neutral" {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "RESOLVED") return "success";
  if (normalized === "UNRESOLVED") return "danger";
  if (normalized === "PENDING") return "warn";
  return "neutral";
}

function truncateJson(value: unknown): string {
  try {
    const rendered = JSON.stringify(value, null, 2);
    return rendered.length > 1200 ? `${rendered.slice(0, 1200)}\n...` : rendered;
  } catch {
    return String(value ?? "");
  }
}

function isMissingRouteError(err: unknown) {
  return err instanceof ApiError && err.status === 404;
}

function buildLegacyPolicyState(bot: BotInstance): BotPolicyStateResponse {
  return {
    bot_id: bot.id,
    policy_state: {
      engine: bot.engine,
      mode: bot.mode,
      status: bot.status,
      pool_strategy_ids: bot.pool_strategy_ids,
      universe: bot.universe || [],
      notes: bot.notes || "",
      created_at: bot.created_at,
      updated_at: bot.updated_at,
    },
  };
}

function buildLegacyDecisionLog(botId: string, logs: LogEvent[]): BotDecisionLogResponse {
  const items = logs.filter((row) => logReferencesBot(row, botId)).slice(0, 8);
  return {
    bot_id: botId,
    items,
    total: items.length,
    page: 1,
    page_size: items.length || 8,
    breaker_events: items
      .filter((row) => row.type === "breaker_triggered")
      .map((row, index) => ({
        id: index + 1,
        ts: row.ts,
        bot_id: botId,
        mode: String(row.payload?.mode || "unknown"),
        reason: String(row.payload?.reason || row.message || "breaker_triggered"),
        run_id: typeof row.payload?.run_id === "string" ? row.payload.run_id : null,
        symbol: typeof row.payload?.symbol === "string" ? row.payload.symbol : null,
        source_log_id: null,
      })),
  };
}

function logReferencesBot(row: LogEvent, botId: string) {
  if ((row.related_ids || []).some((relatedId) => String(relatedId) === botId)) return true;
  const payload = row.payload || {};
  if (String(payload.bot_id || "") === botId) return true;
  if (String(payload.botId || "") === botId) return true;
  if (String(payload.related_bot_id || "") === botId) return true;
  if (String(payload.relatedBotId || "") === botId) return true;
  return Array.isArray(payload.related_ids) && payload.related_ids.some((relatedId) => String(relatedId) === botId);
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
