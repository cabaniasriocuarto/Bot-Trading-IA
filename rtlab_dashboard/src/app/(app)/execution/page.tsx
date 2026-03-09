"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiDelete, apiGet, apiPost } from "@/lib/client-api";
import type {
  BotInstance,
  BotLiveEligibilityResponse,
  BotStatusResponse,
  ExchangeDiagnoseResponse,
  ExecutionRealityResponse,
  ExecutionPreflightResponse,
  ExecutionStats,
  HealthResponse,
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
  const [botModeFilter, setBotModeFilter] = useState<"all" | "mock" | "paper" | "testnet" | "live">("all");
  const [botStatusFilter, setBotStatusFilter] = useState<"all" | "active" | "paused" | "archived">("all");
  const [botSelectedIds, setBotSelectedIds] = useState<string[]>([]);
  const [selectedExecutionBotId, setSelectedExecutionBotId] = useState("");
  const [botBulkBusy, setBotBulkBusy] = useState(false);
  const [botLiveEligibility, setBotLiveEligibility] = useState<BotLiveEligibilityResponse | null>(null);
  const [botLiveEligibilityError, setBotLiveEligibilityError] = useState("");
  const [botLiveEligibilityLoading, setBotLiveEligibilityLoading] = useState(false);
  const [executionReality, setExecutionReality] = useState<ExecutionRealityResponse | null>(null);
  const [executionRealityError, setExecutionRealityError] = useState("");
  const [executionRealityLoading, setExecutionRealityLoading] = useState(false);
  const [preflightResult, setPreflightResult] = useState<ExecutionPreflightResponse | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [isPageVisible, setIsPageVisible] = useState<boolean>(() => (typeof document === "undefined" ? true : document.visibilityState === "visible"));
  const pollInFlightRef = useRef(false);

  const loadExecutionMetrics = useCallback(async () => {
    const exec = await apiGet<ExecutionStats>("/api/v1/execution/metrics");
    setStats(exec);
    setError("");
  }, []);

  const loadTradingPanel = useCallback(async (forceExchange: boolean) => {
    const [status, currentSettings, healthPayload, gatesPayload, rolloutPayload, botsPayload, strategiesPayload] = await Promise.all([
      apiGet<BotStatusResponse>("/api/v1/bot/status"),
      apiGet<SettingsResponse>("/api/v1/settings"),
      apiGet<HealthResponse>("/api/v1/health"),
      apiGet<GatesResponse>("/api/v1/gates"),
      apiGet<RolloutStatusLite>("/api/v1/rollout/status"),
      apiGet<{ items: BotInstance[] }>("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0").catch(() => ({ items: [] })),
      apiGet<Strategy[]>("/api/v1/strategies").catch(() => [] as Strategy[]),
    ]);
    setBotStatus(status);
    setSettings(currentSettings);
    setHealth(healthPayload);
    setGates(gatesPayload);
    setRollout(rolloutPayload);
    setBotInstances(Array.isArray(botsPayload?.items) ? botsPayload.items : []);
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

  const loadBotLiveEligibility = useCallback(async (botId: string) => {
    if (!botId) {
      setBotLiveEligibility(null);
      setBotLiveEligibilityError("");
      return;
    }
    setBotLiveEligibilityLoading(true);
    setBotLiveEligibilityError("");
    try {
      const payload = await apiGet<BotLiveEligibilityResponse>(`/api/v1/bots/${encodeURIComponent(botId)}/live-eligibility`);
      setBotLiveEligibility(payload);
    } catch (err) {
      setBotLiveEligibility(null);
      setBotLiveEligibilityError(err instanceof Error ? err.message : "No se pudo cargar la elegibilidad live del bot.");
    } finally {
      setBotLiveEligibilityLoading(false);
    }
  }, []);

  const loadBotExecutionReality = useCallback(async (botId: string) => {
    if (!botId) {
      setExecutionReality(null);
      setExecutionRealityError("");
      return;
    }
    setExecutionRealityLoading(true);
    setExecutionRealityError("");
    try {
      const payload = await apiGet<ExecutionRealityResponse>(`/api/v1/execution/reality?bot_id=${encodeURIComponent(botId)}&limit=20`);
      setExecutionReality(payload);
    } catch (err) {
      setExecutionReality(null);
      setExecutionRealityError(err instanceof Error ? err.message : "No se pudo cargar la realidad de ejecucion del bot.");
    } finally {
      setExecutionRealityLoading(false);
    }
  }, []);

  const refreshAll = useCallback(async (forceExchange = false) => {
    setRefreshing(true);
    setMessage("");
    setControlError("");
    try {
      await Promise.all([loadExecutionMetrics(), loadTradingPanel(forceExchange)]);
      if (selectedExecutionBotId) {
        await Promise.all([loadBotLiveEligibility(selectedExecutionBotId), loadBotExecutionReality(selectedExecutionBotId)]);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "No se pudo actualizar la pantalla.";
      setError(msg);
    } finally {
      setRefreshing(false);
    }
  }, [loadBotExecutionReality, loadBotLiveEligibility, loadExecutionMetrics, loadTradingPanel, selectedExecutionBotId]);

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
        : "Inicia un rollout (mock/canary) desde Settings para poblar telemetria y validar antes de LIVE.",
    },
  ] as const;

  const canTradeLiveNow =
    modeDraft === "LIVE" &&
    liveReadyItems.find((row) => row.key === "keys")?.status === "pass" &&
    liveReadyItems.find((row) => row.key === "connector")?.status === "pass" &&
    liveReadyItems.find((row) => row.key === "gates")?.status === "pass";
  const liveBlockingItems = liveReadyItems
    .filter((row) => ["keys", "connector", "gates"].includes(String(row.key)))
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
      const res = await apiPost<{
        ok: boolean;
        updated_count: number;
        error_count: number;
      }>("/api/v1/bots/bulk-patch", {
        ids: [botId],
        ...patch,
      });
      if (res.error_count) {
        setControlError(`${label}: error al actualizar ${botId}.`);
      } else {
        setMessage(`${label}: ${botId} actualizado.`);
      }
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

  const runPreflightValidation = async () => {
    if (!selectedExecutionBotId) {
      setControlError("Selecciona un bot para validar preflight.");
      return;
    }
    setPreflightLoading(true);
    setControlError("");
    try {
      const payload = await apiPost<ExecutionPreflightResponse>("/api/v1/execution/live/validate-order", {
        bot_id: selectedExecutionBotId,
        mode: "live",
        side: "BUY",
      });
      setPreflightResult(payload);
      setMessage(payload.ok ? "Preflight live OK para el bot seleccionado." : "Preflight live con bloqueos o advertencias.");
    } catch (err) {
      setPreflightResult(null);
      setControlError(err instanceof Error ? err.message : "No se pudo validar el preflight live.");
    } finally {
      setPreflightLoading(false);
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
    if (!selectedExecutionBotId) {
      setBotLiveEligibility(null);
      setBotLiveEligibilityError("");
      setExecutionReality(null);
      setExecutionRealityError("");
      setPreflightResult(null);
      return;
    }
    setPreflightResult(null);
    void Promise.all([loadBotLiveEligibility(selectedExecutionBotId), loadBotExecutionReality(selectedExecutionBotId)]);
  }, [loadBotExecutionReality, loadBotLiveEligibility, selectedExecutionBotId]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Trading en Vivo (Paper / Testnet / Live) + Diagnostico</CardTitle>
        <CardDescription>
          Pantalla operativa para ejecutar, pausar y validar conectores. Incluye checklist Live Ready y metricas de ejecucion.
        </CardDescription>
      </Card>

      <Card>
        <CardTitle>Modos operativos y alcance</CardTitle>
        <CardDescription>
          Esta pantalla ejecuta el runtime por bot. Mock es simulacion interna; Paper usa mercado real con fills simulados; Testnet valida contra la API oficial de prueba; Live usa cuenta real con pre-flight y controles de riesgo.
        </CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <ModeScopeCard title="Mock" detail="Simula exchange, fills y errores dentro del sistema. Sirve para probar policy, UI y alertas sin tocar una API real." />
          <ModeScopeCard title="Paper" detail="Usa mercado real-time, pero capital y fills simulados. Sirve para validar el cerebro online sin dinero real." />
          <ModeScopeCard title="Testnet" detail="Usa la API de prueba del exchange para validar payloads, restricciones y cancel/replace con credenciales de sandbox." />
          <ModeScopeCard title="Live" detail="Usa cuenta real. Solo habilitado si pasa elegibilidad, riesgo, paridad live y checklist operativo." />
        </CardContent>
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
              <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.5fr)_repeat(5,minmax(0,1fr))]">
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
                <Metric title="Modo bot" value={selectedExecutionBot ? selectedExecutionBot.mode.toUpperCase() : "--"} compact />
                <Metric title="Engine" value={selectedExecutionBot?.engine || "--"} compact />
                <Metric title="Pool" value={selectedExecutionBot ? String(selectedExecutionBot.metrics?.strategy_count ?? selectedExecutionBot.pool_strategy_ids.length) : "--"} compact />
                <Metric title="Trades" value={selectedExecutionBot ? String(selectedExecutionBot.metrics?.trade_count ?? 0) : "--"} compact />
                <Metric title="WinRate" value={selectedExecutionBot ? fmtPct(selectedExecutionBot.metrics?.winrate ?? 0) : "--"} compact />
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
                      <Button variant="outline" disabled={role !== "admin" || botBulkBusy} onClick={() => void patchSingleBot(selectedExecutionBot.id, { mode: "mock" }, "Cambiar bot a MOCK")}>
                        Modo MOCK
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
                    <Button
                      variant="ghost"
                      className="text-[11px]"
                      onClick={() => {
                        window.location.href = selectedExecutionBotId ? `/bots?bot_id=${encodeURIComponent(selectedExecutionBotId)}` : "/bots";
                      }}
                    >
                      Abrir en Bots →
                    </Button>
                  </div>
                  <p className="mt-2 text-[11px] text-slate-400">
                    Pool actual: <strong>{selectedExecutionBot.pool_strategy_ids.length}</strong> estrategias
                    {selectedExecutionBot.metrics?.last_run_at ? ` · último run ${new Date(selectedExecutionBot.metrics.last_run_at).toLocaleString()}` : ""}
                    {selectedExecutionBot.metrics?.experience_by_source
                        ? ` · mock/shadow ${selectedExecutionBot.metrics.experience_by_source.shadow?.episode_count ?? 0} / backtest ${selectedExecutionBot.metrics.experience_by_source.backtest?.episode_count ?? 0} / live ${selectedExecutionBot.metrics.experience_by_source.live?.episode_count ?? 0}`
                      : ""}
                  </p>
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

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Elegibilidad live del bot</p>
                  <p className="text-[11px] text-slate-400">
                    Resume si el bot seleccionado puede pasar a validación live real y qué preflight bloquea hoy.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {botLiveEligibility?.runtime_mode ? <Badge variant="info">runtime {botLiveEligibility.runtime_mode}</Badge> : null}
                  {botLiveEligibility?.bot_mode ? <Badge variant="neutral">bot {botLiveEligibility.bot_mode}</Badge> : null}
                  {botLiveEligibility?.bot_status ? (
                    <Badge variant={botLiveEligibility.bot_status === "active" ? "success" : botLiveEligibility.bot_status === "paused" ? "warn" : "neutral"}>
                      {botLiveEligibility.bot_status}
                    </Badge>
                  ) : null}
                </div>
              </div>
              {!selectedExecutionBot ? (
                <p className="text-xs text-slate-400">Selecciona un bot para revisar su elegibilidad live y el preflight.</p>
              ) : botLiveEligibilityLoading ? (
                <p className="text-xs text-slate-400">Cargando elegibilidad live…</p>
              ) : botLiveEligibilityError ? (
                <p className="rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-300">{botLiveEligibilityError}</p>
              ) : botLiveEligibility ? (
                <div className="space-y-3">
                  <div className="grid gap-3 md:grid-cols-3">
                    <Metric title="Pool elegible" value={String(botLiveEligibility.pool_size)} compact />
                    <Metric title="Instrumentos live OK" value={String(botLiveEligibility.summary.eligible_instruments)} compact />
                    <Metric title="Paridad lista" value={String(botLiveEligibility.summary.parity_ready)} compact />
                  </div>
                  {botLiveEligibility.blocked_reasons.length ? (
                    <div className="rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-200">
                      <p className="font-semibold text-rose-100">Bloqueos activos</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {botLiveEligibility.blocked_reasons.map((reason) => (
                          <Badge key={`live-block-${reason}`} variant="danger">
                            {liveReasonLabel(reason)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {botLiveEligibility.warnings.length ? (
                    <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-200">
                      <p className="font-semibold text-amber-100">Advertencias</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {botLiveEligibility.warnings.map((warning) => (
                          <Badge key={`live-warning-${warning}`} variant="warn">
                            {liveReasonLabel(warning)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" disabled={preflightLoading || !selectedExecutionBotId} onClick={() => void runPreflightValidation()}>
                      {preflightLoading ? "Validando..." : "Validar preflight live"}
                    </Button>
                    <Button variant="ghost" disabled={!selectedExecutionBotId || botLiveEligibilityLoading} onClick={() => void loadBotLiveEligibility(selectedExecutionBotId)}>
                      Refrescar elegibilidad
                    </Button>
                  </div>
                  {preflightResult ? (
                    <div className="rounded border border-slate-800 bg-slate-900/50 p-3 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-semibold text-slate-100">Resultado de preflight</p>
                        <Badge variant={preflightResult.ok ? "success" : "warn"}>{preflightResult.ok ? "OK" : "Con bloqueos"}</Badge>
                      </div>
                      <div className="mt-2 space-y-2">
                        {preflightResult.checks.map((check) => (
                          <div key={`preflight-${check.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-800 px-2 py-1">
                            <div>
                              <p className="font-medium text-slate-200">{check.label}</p>
                              <p className="text-[11px] text-slate-400">{check.detail}</p>
                            </div>
                            <Badge variant={check.ok ? "success" : "danger"}>{check.ok ? "PASS" : "BLOCK"}</Badge>
                          </div>
                        ))}
                        {preflightResult.instrument ? (
                          <p className="text-[11px] text-slate-400">
                            Instrumento validado: <strong>{preflightResult.instrument.normalized_symbol}</strong> · {preflightResult.instrument.provider_market}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  <div className="overflow-x-auto rounded border border-slate-800">
                    <Table className="text-xs">
                      <THead>
                        <TR>
                          <TH>Instrumento</TH>
                          <TH>Mercado</TH>
                          <TH>Estado</TH>
                          <TH>Paridad</TH>
                          <TH>Live</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {botLiveEligibility.eligible_instruments.slice(0, 8).map((row) => (
                          <TR key={`eligible-live-${row.instrument_id}`}>
                            <TD>{row.normalized_symbol || row.provider_symbol}</TD>
                            <TD>{row.provider_market}</TD>
                            <TD>{row.status || "--"}</TD>
                            <TD>
                              <Badge variant={row.parity_status === "reference_dataset_ready" ? "success" : row.parity_status === "missing_dataset" ? "warn" : "neutral"}>
                                {row.parity_status || "sin_paridad"}
                              </Badge>
                            </TD>
                            <TD>
                              <Badge variant={row.eligible_live ? "success" : "danger"}>{row.eligible_live ? "habilitado" : "bloqueado"}</Badge>
                            </TD>
                          </TR>
                        ))}
                        {!botLiveEligibility.eligible_instruments.length ? (
                          <TR>
                            <TD colSpan={5} className="py-4 text-center text-xs text-slate-400">
                              No hay instrumentos candidatos para este bot.
                            </TD>
                          </TR>
                        ) : null}
                      </TBody>
                    </Table>
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Realidad de ejecucion por bot</p>
                  <p className="text-[11px] text-slate-400">
                    Resume fills, slippage, spread, maker/taker, impacto y reconciliacion del bot seleccionado. Esta vista es operativa; las decisiones del bot siguen en Bots.
                  </p>
                </div>
                {executionReality?.summary.latest_timestamp ? (
                  <Badge variant="neutral">ultimo evento {new Date(executionReality.summary.latest_timestamp).toLocaleString()}</Badge>
                ) : null}
              </div>
              {!selectedExecutionBot ? (
                <p className="text-xs text-slate-400">Selecciona un bot para revisar su realidad de ejecucion reciente.</p>
              ) : executionRealityLoading ? (
                <p className="text-xs text-slate-400">Cargando realidad de ejecucion…</p>
              ) : executionRealityError ? (
                <p className="rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-300">{executionRealityError}</p>
              ) : executionReality ? (
                <div className="space-y-3">
                  <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                    <Metric title="Eventos" value={String(executionReality.summary.count)} compact />
                    <Metric title="Slippage prom." value={`${fmtNum(executionReality.summary.avg_realized_slippage_bps)} bps`} compact />
                    <Metric title="Spread prom." value={`${fmtNum(executionReality.summary.avg_spread_bps)} bps`} compact />
                    <Metric title="Impacto prom." value={`${fmtNum(executionReality.summary.avg_impact_bps_est)} bps`} compact />
                    <Metric title="Latencia prom." value={`${fmtNum(executionReality.summary.avg_latency_ms)} ms`} compact />
                    <Metric title="Maker / Taker" value={`${fmtPct(executionReality.summary.maker_ratio)} / ${fmtPct(executionReality.summary.taker_ratio)}`} compact />
                  </div>
                  <div className="rounded border border-slate-800 bg-slate-900/50 p-2 text-xs text-slate-300">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-100">Reconciliacion</span>
                      {Object.entries(executionReality.summary.reconciliation_breakdown || {}).length ? (
                        Object.entries(executionReality.summary.reconciliation_breakdown || {}).map(([key, count]) => (
                          <Badge key={`reconciliation-${key}`} variant={reconciliationVariant(key)}>
                            {key}: {count}
                          </Badge>
                        ))
                      ) : (
                        <Badge variant="neutral">sin datos</Badge>
                      )}
                    </div>
                    <p className="mt-2 text-[11px] text-slate-400">
                      Simbolos observados: <strong>{executionReality.summary.symbols_count}</strong> · fill parcial promedio:{" "}
                      <strong>{fmtPct(executionReality.summary.avg_partial_fill_ratio)}</strong>
                    </p>
                  </div>
                  <div className="overflow-x-auto rounded border border-slate-800">
                    <Table className="text-xs">
                      <THead>
                        <TR>
                          <TH>Momento</TH>
                          <TH>Instrumento</TH>
                          <TH>Operacion</TH>
                          <TH>Maker/Taker</TH>
                          <TH>Slippage</TH>
                          <TH>Spread</TH>
                          <TH>Impacto</TH>
                          <TH>Latencia</TH>
                          <TH>Fill parcial</TH>
                          <TH>Reconciliacion</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {executionReality.items.map((row) => (
                          <TR key={`execution-reality-${row.execution_id}`}>
                            <TD>{row.timestamp ? new Date(row.timestamp).toLocaleString() : "--"}</TD>
                            <TD>{row.symbol || "--"}</TD>
                            <TD>{[row.side, row.order_type].filter(Boolean).join(" / ") || "--"}</TD>
                            <TD>{row.maker_taker || "--"}</TD>
                            <TD>{row.realized_slippage_bps != null ? `${fmtNum(row.realized_slippage_bps)} bps` : "--"}</TD>
                            <TD>{row.spread_bps != null ? `${fmtNum(row.spread_bps)} bps` : "--"}</TD>
                            <TD>{row.impact_bps_est != null ? `${fmtNum(row.impact_bps_est)} bps` : "--"}</TD>
                            <TD>{row.latency_ms != null ? `${fmtNum(row.latency_ms)} ms` : "--"}</TD>
                            <TD>{row.partial_fill_ratio != null ? fmtPct(row.partial_fill_ratio) : "--"}</TD>
                            <TD>
                              <Badge variant={reconciliationVariant(row.reconciliation_status)}>
                                {row.reconciliation_status || "sin dato"}
                              </Badge>
                            </TD>
                          </TR>
                        ))}
                        {!executionReality.items.length ? (
                          <TR>
                            <TD colSpan={10} className="py-4 text-center text-xs text-slate-400">
                              Todavia no hay eventos recientes de ejecucion para este bot.
                            </TD>
                          </TR>
                        ) : null}
                      </TBody>
                    </Table>
                  </div>
                </div>
              ) : null}
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
                  <li>Corre rollout en Mock/Canary desde Settings &gt; Rollout / Gates.</li>
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
                  <li>Inicia Mock/Canary para generar telemetria de blending y KPIs.</li>
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
            Runtime global: <strong>{runtimeModeKey.toUpperCase()}</strong> · Operadores visibles se gestionan por separado (mock/paper/testnet/live).
          </div>
          <div className="grid gap-3 md:grid-cols-6">
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Filtro modo</label>
                <Select value={botModeFilter} onChange={(e) => setBotModeFilter(e.target.value as "all" | "mock" | "paper" | "testnet" | "live")}>
                  <option value="all">Todos</option>
                  <option value="mock">mock</option>
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
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-[11px]"
                            onClick={() => {
                              window.location.href = `/bots?bot_id=${encodeURIComponent(bot.id)}`;
                            }}
                          >
                            Ver bot →
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

function ModeScopeCard({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
      <div className="mb-2">
        <Badge variant={title === "Live" ? "warn" : title === "Testnet" ? "info" : "neutral"}>{title}</Badge>
      </div>
      <p>{detail}</p>
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

function liveReasonLabel(reason: string): string {
  const normalized = String(reason).trim().toLowerCase();
  const labels: Record<string, string> = {
    pool_vacio: "Pool vacio",
    bot_archivado: "Bot archivado",
    bot_pausado: "Bot pausado",
    sin_instrumentos_elegibles_live: "Sin instrumentos elegibles para live",
    health_backend_no_ok: "Health backend no OK",
    runtime_actual_mock: "Runtime actual: mock",
    runtime_actual_paper: "Runtime actual: paper",
    runtime_actual_testnet: "Runtime actual: testnet",
    runtime_actual_live: "Runtime actual: live",
    live_runtime_enabled: "Live no habilitado en runtime",
    bot_mode_matches: "Modo del bot no coincide",
    instrument_found: "Instrumento no resoluble",
    instrument_tradable: "Instrumento no tradable",
    instrument_mode_enabled: "Instrumento no habilitado para este modo",
    parity_reference: "Falta referencia de mercado",
    parity_market_state: "Falta estado de mercado reciente",
    parity_mark_price: "Falta mark price reciente",
    qty_positive: "Cantidad invalida",
    side_declared: "Lado no declarado",
    pool_not_empty: "Pool vacio",
    bot_not_archived: "Bot archivado",
  };
  return labels[normalized] ?? normalized.replaceAll("_", " ");
}

function reconciliationVariant(status?: string | null): "success" | "warn" | "danger" | "neutral" {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized) return "neutral";
  if (normalized.includes("ok") || normalized.includes("matched") || normalized.includes("synced")) return "success";
  if (normalized.includes("warn") || normalized.includes("pending") || normalized.includes("partial")) return "warn";
  if (normalized.includes("fail") || normalized.includes("mismatch") || normalized.includes("error")) return "danger";
  return "neutral";
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
