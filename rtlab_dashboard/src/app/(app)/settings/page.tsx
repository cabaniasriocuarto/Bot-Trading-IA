"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiGet, apiPost } from "@/lib/client-api";
import type { BacktestRun, ExchangeDiagnoseResponse, HealthResponse, SettingsResponse } from "@/lib/types";

type GateItem = {
  id: string;
  name: string;
  status: "PASS" | "FAIL" | "WARN";
  reason: string;
  details?: Record<string, unknown>;
};

type RolloutCheck = {
  id: string;
  ok?: boolean;
  reason?: string;
  details?: Record<string, unknown>;
};

type RolloutEvaluation = {
  phase?: string;
  state?: string;
  status?: string;
  passed?: boolean;
  hard_fail?: boolean;
  failed_ids?: string[];
  hard_fail_ids?: string[];
  checks?: RolloutCheck[];
  kpis?: Record<string, unknown>;
  routing?: Record<string, unknown>;
  evaluated_at?: string;
};

type RolloutDecisionChecks = {
  passed?: boolean;
  failed_ids?: string[];
  checks?: Array<RolloutCheck & { ok?: boolean }>;
};

type RolloutVersionSnapshot = {
  strategy_id?: string;
  run_id?: string;
  strategy_name?: string;
  strategy_version?: string;
  dataset_hash?: string;
  period?: { start?: string; end?: string };
  market?: string;
  symbol?: string;
  timeframe?: string;
  report_ref?: {
    metrics?: Record<string, unknown>;
    costs_breakdown?: Record<string, unknown>;
  };
};

type RolloutStatusResponse = {
  rollout_id?: string | null;
  state: string;
  current_phase?: string | null;
  baseline_version?: RolloutVersionSnapshot | null;
  candidate_version?: RolloutVersionSnapshot | null;
  weights?: { baseline_pct?: number; candidate_pct?: number };
  routing?: {
    mode?: string;
    shadow_only?: boolean;
    baseline_pct?: number;
    candidate_pct?: number;
    real_execution_candidate_pct?: number;
    phase?: string;
    phase_type?: string;
    blending?: Record<string, unknown> | null;
  };
  blending?: Record<string, unknown>;
  offline_gates?: RolloutDecisionChecks | null;
  compare_vs_baseline?: RolloutDecisionChecks | null;
  phase_kpis?: Record<string, Record<string, unknown>>;
  phase_evaluations?: Record<string, RolloutEvaluation>;
  live_signal_telemetry?: {
    recent?: Array<Record<string, unknown>>;
    phases?: Record<string, { events?: number; agreement_rate?: number; action_counts?: Record<string, Record<string, number>>; last?: Record<string, unknown> }>;
    last_decision?: Record<string, unknown> | null;
    updated_at?: string | null;
  };
  pending_live_approval?: boolean;
  pending_live_approval_target?: string | null;
  abort_reason?: string | null;
  rollback_snapshot?: Record<string, unknown> | null;
  config?: Record<string, unknown>;
  blending_config?: Record<string, unknown>;
  live_stable_100_requires_approve?: boolean;
  updated_at?: string;
};

type RolloutActionResponse = { ok?: boolean; state: RolloutStatusResponse };

const ROLLOUT_STATE_TO_EVAL_PHASE: Record<string, "paper_soak" | "testnet_soak" | "shadow" | "canary05" | "canary15" | "canary35" | "canary60"> = {
  PAPER_SOAK: "paper_soak",
  TESTNET_SOAK: "testnet_soak",
  LIVE_SHADOW: "shadow",
  LIVE_CANARY_05: "canary05",
  LIVE_CANARY_15: "canary15",
  LIVE_CANARY_35: "canary35",
  LIVE_CANARY_60: "canary60",
};

function formatMetricValue(value: unknown): string {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    if (Math.abs(value) >= 1000) return value.toLocaleString("es-AR", { maximumFractionDigits: 2 });
    if (Number.isInteger(value)) return String(value);
    return value.toLocaleString("es-AR", { maximumFractionDigits: 4 });
  }
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (value == null) return "-";
  return String(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function rolloutBadgeVariant(state: string | undefined): "success" | "warn" | "danger" | "neutral" {
  if (!state) return "neutral";
  if (state === "COMPLETED" || state === "LIVE_STABLE_100" || state.endsWith("_PASSED")) return "success";
  if (state === "ABORTED" || state === "ROLLED_BACK") return "danger";
  if (state.startsWith("PENDING") || state.includes("CANARY") || state.includes("SOAK") || state.includes("SHADOW")) return "warn";
  return "neutral";
}

function checkBadgeVariant(ok: boolean | undefined): "success" | "danger" | "neutral" {
  if (ok === true) return "success";
  if (ok === false) return "danger";
  return "neutral";
}

function InfoTip({ text }: { text: string }) {
  return (
    <span
      title={text}
      className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-700 text-[11px] text-slate-300 cursor-help"
      aria-label="Informacion"
    >
      ⓘ
    </span>
  );
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

export default function SettingsPage() {
  const { role } = useSession();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [gates, setGates] = useState<GateItem[]>([]);
  const [gatesOverall, setGatesOverall] = useState<"PASS" | "FAIL" | "WARN" | "UNKNOWN">("UNKNOWN");
  const [gatesLoading, setGatesLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [diag, setDiag] = useState({
    backend: "sin probar",
    ws: "sin probar",
    exchange: "sin probar",
  });
  const [exchangeDiag, setExchangeDiag] = useState<ExchangeDiagnoseResponse | null>(null);
  const [rollout, setRollout] = useState<RolloutStatusResponse | null>(null);
  const [rolloutBusy, setRolloutBusy] = useState(false);
  const [rolloutLoading, setRolloutLoading] = useState(true);
  const [rolloutMessage, setRolloutMessage] = useState("");
  const [rolloutError, setRolloutError] = useState("");
  const [backtestRuns, setBacktestRuns] = useState<BacktestRun[]>([]);
  const [rolloutCandidateRunId, setRolloutCandidateRunId] = useState("");
  const [rolloutBaselineRunId, setRolloutBaselineRunId] = useState("");
  const [rolloutReason, setRolloutReason] = useState("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await apiGet<SettingsResponse>("/api/v1/settings");
        setSettings(data);
        const gatesPayload = await apiGet<{ gates: GateItem[]; overall_status: "PASS" | "FAIL" | "WARN" }>("/api/v1/gates");
        setGates(gatesPayload.gates);
        setGatesOverall(gatesPayload.overall_status);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "No se pudo cargar configuracion.";
        setError(msg);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  useEffect(() => {
    let cancelled = false;

    const hydrateRolloutPanel = async () => {
      setRolloutLoading(true);
      try {
        const [rolloutStatus, runs] = await Promise.all([
          apiGet<RolloutStatusResponse>("/api/v1/rollout/status"),
          apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
        ]);
        if (cancelled) return;
        setRollout(rolloutStatus);
        const sortedRuns = [...runs].sort((a, b) => {
          const ta = Date.parse(a.created_at || "") || 0;
          const tb = Date.parse(b.created_at || "") || 0;
          return tb - ta;
        });
        setBacktestRuns(sortedRuns);
        if (!rolloutCandidateRunId && sortedRuns[0]?.id) {
          setRolloutCandidateRunId(sortedRuns[0].id);
        }
        if (!rolloutBaselineRunId) {
          const fallbackBaseline = sortedRuns.find((row) => row.id !== (sortedRuns[0]?.id ?? ""));
          if (fallbackBaseline?.id) setRolloutBaselineRunId(fallbackBaseline.id);
        }
      } catch (err) {
        if (cancelled) return;
        setRolloutError(err instanceof Error ? err.message : "No se pudo cargar rollout.");
      } finally {
        if (!cancelled) setRolloutLoading(false);
      }
    };

    void hydrateRolloutPanel();
    const timer = window.setInterval(() => {
      void apiGet<RolloutStatusResponse>("/api/v1/rollout/status")
        .then((payload) => {
          if (!cancelled) setRollout(payload);
        })
        .catch(() => {
          // silencioso: polling best-effort
        });
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [rolloutBaselineRunId, rolloutCandidateRunId]);

  const refreshRollout = async () => {
    try {
      const [rolloutStatus, runs] = await Promise.all([
        apiGet<RolloutStatusResponse>("/api/v1/rollout/status"),
        apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
      ]);
      setRollout(rolloutStatus);
      setBacktestRuns(
        [...runs].sort((a, b) => (Date.parse(b.created_at || "") || 0) - (Date.parse(a.created_at || "") || 0)),
      );
    } catch (err) {
      setRolloutError(err instanceof Error ? err.message : "No se pudo actualizar rollout.");
    }
  };

  const runRolloutAction = async (label: string, fn: () => Promise<RolloutActionResponse | { state: RolloutStatusResponse }>) => {
    setRolloutBusy(true);
    setRolloutError("");
    setRolloutMessage("");
    try {
      const res = await fn();
      setRollout(res.state);
      setRolloutMessage(label);
      await refreshRollout();
    } catch (err) {
      setRolloutError(err instanceof Error ? err.message : `No se pudo ejecutar: ${label}`);
    } finally {
      setRolloutBusy(false);
    }
  };

  const startRollout = async () => {
    if (!rolloutCandidateRunId) {
      setRolloutError("Seleccioná un run candidato.");
      return;
    }
    await runRolloutAction("Rollout iniciado", () =>
      apiPost<{ ok: boolean; state: RolloutStatusResponse }>("/api/v1/rollout/start", {
        candidate_run_id: rolloutCandidateRunId,
        baseline_run_id: rolloutBaselineRunId || undefined,
      }),
    );
  };

  const advanceRollout = async () => {
    await runRolloutAction("Rollout avanzado", () => apiPost<{ ok: boolean; state: RolloutStatusResponse }>("/api/v1/rollout/advance", {}));
  };

  const approveRollout = async () => {
    await runRolloutAction("Rollout aprobado", () =>
      apiPost<{ ok: boolean; state: RolloutStatusResponse }>("/api/v1/rollout/approve", { reason: rolloutReason || "Aprobado desde Settings UI" }),
    );
  };

  const rejectRollout = async () => {
    await runRolloutAction("Rollout rechazado", () =>
      apiPost<{ ok: boolean; state: RolloutStatusResponse }>("/api/v1/rollout/reject", { reason: rolloutReason || "Rechazado desde Settings UI" }),
    );
  };

  const rollbackRollout = async () => {
    await runRolloutAction("Rollback ejecutado", () =>
      apiPost<{ ok: boolean; state: RolloutStatusResponse }>("/api/v1/rollout/rollback", { reason: rolloutReason || "Rollback manual desde Settings UI" }),
    );
  };

  const evaluateCurrentRolloutPhase = async (autoAdvance: boolean) => {
    if (!rollout?.state) {
      setRolloutError("No hay rollout cargado.");
      return;
    }
    const phase = ROLLOUT_STATE_TO_EVAL_PHASE[rollout.state];
    if (!phase) {
      setRolloutError(`La fase actual (${rollout.state}) no se evalúa desde UI.`);
      return;
    }
    await runRolloutAction(autoAdvance ? "Fase evaluada y auto-avanzada" : "Fase evaluada", () =>
      apiPost<{ ok: boolean; state: RolloutStatusResponse; evaluation: RolloutEvaluation; phase: string; advanced: boolean }>("/api/v1/rollout/evaluate-phase", {
        phase,
        auto_abort: true,
        auto_advance: autoAdvance,
      }),
    );
  };

  const reevaluateGates = async () => {
    setGatesLoading(true);
    try {
      const res = await fetch("/api/v1/gates/reevaluate", {
        method: "POST",
        credentials: "include",
      });
      const body = (await res.json().catch(() => ({}))) as { gates?: GateItem[]; overall_status?: "PASS" | "FAIL" | "WARN"; detail?: string };
      if (!res.ok || !body.gates) {
        setError(body.detail || "No se pudieron reevaluar los gates.");
        return;
      }
      setGates(body.gates);
      setGatesOverall(body.overall_status || "UNKNOWN");
      setMessage("Gates reevaluados");
    } catch {
      setError("No se pudieron reevaluar los gates.");
    } finally {
      setGatesLoading(false);
    }
  };

  const save = async () => {
    if (!settings) return;
    if (settings.mode === "LIVE" && gatesOverall !== "PASS") {
      setError("LIVE bloqueado: reevalua gates y corrige los FAIL antes de guardar.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const runtimeMode = settings.mode.toLowerCase();
      if (role === "admin" && ["paper", "testnet", "live"].includes(runtimeMode)) {
        const modeRes = await fetch("/api/v1/bot/mode", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(runtimeMode === "live" ? { mode: "live", confirm: "ENABLE_LIVE" } : { mode: runtimeMode }),
        });
        const modeBody = (await modeRes.json().catch(() => ({}))) as { detail?: string; error?: string };
        if (!modeRes.ok) {
          setError(modeBody.detail || modeBody.error || "No se pudo cambiar el modo operativo.");
          return;
        }
      }
      const res = await fetch("/api/v1/settings", {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string; settings?: SettingsResponse };
      if (!res.ok) {
        setError(body.error || "No se pudo guardar.");
        return;
      }
      if (body.settings) setSettings(body.settings);
      setMessage("Guardado OK");
    } finally {
      setSaving(false);
    }
  };

  const testBackend = async () => {
    setDiag((prev) => ({ ...prev, backend: "probando..." }));
    try {
      const health = await apiGet<HealthResponse>("/api/v1/health");
      setDiag((prev) => ({ ...prev, backend: health.ok ? `ok (${health.exchange.mode}/${health.exchange.name})` : "fallo" }));
    } catch {
      setDiag((prev) => ({ ...prev, backend: "fallo" }));
    }
  };

  const testWs = async () => {
    const endpoint = "/api/events";
    setDiag((prev) => ({ ...prev, ws: "probando..." }));
    await new Promise<void>((resolve) => {
      const es = new EventSource(endpoint, { withCredentials: true });
      const timeout = setTimeout(() => {
        es.close();
        setDiag((prev) => ({ ...prev, ws: `WS timeout (${endpoint})` }));
        resolve();
      }, 5000);
      const markOk = () => {
        clearTimeout(timeout);
        es.close();
        setDiag((prev) => ({ ...prev, ws: `ok (${endpoint})` }));
        resolve();
      };
      es.addEventListener("health", markOk);
      es.onerror = () => {
        clearTimeout(timeout);
        es.close();
        setDiag((prev) => ({ ...prev, ws: `fallo (${endpoint})` }));
        resolve();
      };
    });
  };

  const testExchange = async () => {
    setDiag((prev) => ({ ...prev, exchange: "probando..." }));
    try {
      const mode = settings?.mode?.toLowerCase() || "paper";
      const res = await fetch(`/api/v1/exchange/diagnose?force=true&mode=${encodeURIComponent(mode)}`, {
        method: "GET",
        credentials: "include",
      });
      const body = (await res.json().catch(() => ({}))) as Partial<ExchangeDiagnoseResponse>;
      if (!res.ok) {
        const fail = body as { detail?: string; error?: string };
        setExchangeDiag(null);
        setDiag((prev) => ({ ...prev, exchange: fail.detail || fail.error || "fallo" }));
        return;
      }
      const parsed = body as ExchangeDiagnoseResponse;
      setExchangeDiag(parsed);
      if (!parsed.ok) {
        const missing = parsed.missing?.length ? ` | faltan: ${parsed.missing.join(", ")}` : "";
        const reason = parsed.last_error || parsed.order_reason || parsed.connector_reason || "fallo";
        setDiag((prev) => ({ ...prev, exchange: `${reason}${missing}` }));
        return;
      }
      setDiag((prev) => ({ ...prev, exchange: `ok (${parsed.mode})` }));
    } catch {
      setExchangeDiag(null);
      setDiag((prev) => ({ ...prev, exchange: "fallo" }));
    }
  };

  const testAlert = async () => {
    try {
      const res = await fetch("/api/v1/settings/test-alert", {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error("error");
      setMessage("Alerta de prueba enviada");
    } catch {
      setError("No se pudo enviar alerta de prueba.");
    }
  };

  if (loading) return <p className="text-sm text-slate-400">Cargando configuracion...</p>;
  if (!settings) return <p className="text-sm text-rose-300">No se pudo cargar configuracion: {error || "sin respuesta"}</p>;

  const liveLocked = settings.mode === "LIVE" && gatesOverall !== "PASS";
  const learning = settings.learning;
  const rolloutCurrentEvalKey =
    (rollout?.state && ROLLOUT_STATE_TO_EVAL_PHASE[rollout.state]) || (typeof rollout?.current_phase === "string" ? rollout.current_phase : undefined);
  const rolloutCurrentEval = rolloutCurrentEvalKey ? rollout?.phase_evaluations?.[rolloutCurrentEvalKey] : undefined;
  const rolloutCurrentKpis = rolloutCurrentEval?.kpis || (rolloutCurrentEvalKey ? rollout?.phase_kpis?.[rolloutCurrentEvalKey] : undefined);
  const rolloutStartDisabled = role !== "admin" || rolloutBusy || !rolloutCandidateRunId;
  const selectedCandidateRun = backtestRuns.find((row) => row.id === rolloutCandidateRunId);
  const selectedBaselineRun = backtestRuns.find((row) => row.id === rolloutBaselineRunId);
  const rolloutCanEvaluate = Boolean(rollout?.state && ROLLOUT_STATE_TO_EVAL_PHASE[rollout.state]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Configuracion (Admin)</CardTitle>
        <CardDescription>Perfiles, exchange, estado de credenciales, telegram, riesgo y ejecucion.</CardDescription>
        <CardContent className="space-y-2">
          {message ? <p className="text-sm text-emerald-300">{message}</p> : null}
          {error ? <p className="text-sm text-rose-300">{error}</p> : null}
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Modo y Exchange</CardTitle>
          <CardDescription>MOCK / PAPER / TESTNET / LIVE (LIVE con bloqueo por checklist).</CardDescription>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Modo</label>
              <Select value={settings.mode} onChange={(e) => setSettings((prev) => (prev ? { ...prev, mode: e.target.value as SettingsResponse["mode"] } : prev))} disabled={role !== "admin"}>
                <option value="MOCK">MOCK</option>
                <option value="PAPER">PAPER</option>
                <option value="TESTNET">TESTNET</option>
                <option value="LIVE" disabled={gatesOverall !== "PASS"}>
                  LIVE {gatesOverall !== "PASS" ? "(bloqueado)" : ""}
                </option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Exchange</label>
              <Select value={settings.exchange} onChange={(e) => setSettings((prev) => (prev ? { ...prev, exchange: e.target.value as SettingsResponse["exchange"] } : prev))} disabled={role !== "admin"}>
                {settings.exchange_plugin_options.map((row) => (
                  <option key={row} value={row}>
                    {row}
                  </option>
                ))}
              </Select>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300">
              Estado: <Badge variant={settings.mode === "LIVE" ? "danger" : settings.mode === "TESTNET" ? "warn" : "success"}>{settings.mode}</Badge>
              {liveLocked ? <p className="mt-2 text-xs text-amber-300">LIVE bloqueado: checklist incompleto.</p> : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Credenciales y Telegram</CardTitle>
          <CardDescription>Solo estado de credenciales, nunca secretos.</CardDescription>
          <CardContent className="space-y-3">
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300">
              Exchange keys: <strong>{settings.credentials.exchange_configured ? "configuradas" : "faltan"}</strong>
              <br />
              Telegram token/chat: <strong>{settings.credentials.telegram_configured ? "configurado" : "faltan"}</strong>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.telegram.enabled}
                  onChange={(e) => setSettings((prev) => (prev ? { ...prev, telegram: { ...prev.telegram, enabled: e.target.checked } } : prev))}
                  disabled={role !== "admin"}
                />
                Telegram habilitado
              </label>
              <Input
                value={settings.telegram.chat_id}
                onChange={(e) =>
                  setSettings((prev) =>
                    prev
                      ? {
                          ...prev,
                          telegram: { ...prev.telegram, chat_id: e.target.value },
                          credentials: { ...prev.credentials, telegram_chat_id: e.target.value },
                        }
                      : prev,
                  )
                }
                placeholder="Chat ID"
                disabled={role !== "admin"}
              />
            </div>
            <Button onClick={testAlert} variant="outline" disabled={role !== "admin"}>
              Probar alerta
            </Button>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Riesgo por defecto</CardTitle>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            <Input
              type="number"
              value={settings.risk_defaults.max_daily_loss}
              onChange={(e) =>
                setSettings((prev) => (prev ? { ...prev, risk_defaults: { ...prev.risk_defaults, max_daily_loss: Number(e.target.value) } } : prev))
              }
              placeholder="Max perdida diaria %"
              disabled={role !== "admin"}
            />
            <Input
              type="number"
              value={settings.risk_defaults.max_dd}
              onChange={(e) =>
                setSettings((prev) => (prev ? { ...prev, risk_defaults: { ...prev.risk_defaults, max_dd: Number(e.target.value) } } : prev))
              }
              placeholder="Max DD %"
              disabled={role !== "admin"}
            />
            <Input
              type="number"
              value={settings.risk_defaults.max_positions}
              onChange={(e) =>
                setSettings((prev) => (prev ? { ...prev, risk_defaults: { ...prev.risk_defaults, max_positions: Number(e.target.value) } } : prev))
              }
              placeholder="Max posiciones"
              disabled={role !== "admin"}
            />
            <Input
              type="number"
              value={settings.risk_defaults.risk_per_trade}
              onChange={(e) =>
                setSettings((prev) => (prev ? { ...prev, risk_defaults: { ...prev.risk_defaults, risk_per_trade: Number(e.target.value) } } : prev))
              }
              placeholder="Riesgo por trade %"
              disabled={role !== "admin"}
            />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Ejecucion</CardTitle>
          <CardContent className="space-y-2">
            <label className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={settings.execution.post_only_default}
                onChange={(e) =>
                  setSettings((prev) => (prev ? { ...prev, execution: { ...prev.execution, post_only_default: e.target.checked } } : prev))
                }
                disabled={role !== "admin"}
              />
              Post-only por defecto
            </label>
            <Input
              type="number"
              value={settings.execution.slippage_max_bps}
              onChange={(e) =>
                setSettings((prev) => (prev ? { ...prev, execution: { ...prev.execution, slippage_max_bps: Number(e.target.value) } } : prev))
              }
              placeholder="Slippage max bps"
              disabled={role !== "admin"}
            />
            <Input
              type="number"
              value={settings.execution.request_timeout_ms}
              onChange={(e) =>
                setSettings((prev) => (prev ? { ...prev, execution: { ...prev.execution, request_timeout_ms: Number(e.target.value) } } : prev))
              }
              placeholder="Timeout ms"
              disabled={role !== "admin"}
            />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardTitle>Cerebro / Aprendizaje</CardTitle>
        <CardDescription>Opcion B: genera recomendaciones y nunca aplica a LIVE automaticamente.</CardDescription>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm">
              <span className="flex items-center gap-2">
                Aprendizaje
                <InfoTip text={"Activa el modulo de aprendizaje controlado.\nSolo propone cambios; no toca LIVE."} />
              </span>
              <input
                type="checkbox"
                checked={learning.enabled}
                onChange={(e) =>
                  setSettings((prev) =>
                    prev ? { ...prev, learning: { ...prev.learning, enabled: e.target.checked } } : prev,
                  )
                }
                disabled={role !== "admin"}
              />
            </label>

            <div className="space-y-1">
              <label className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
                Mode
                <InfoTip text={"OFF: desactivado.\nRESEARCH: ejecuta research loop y guarda Top N recomendaciones."} />
              </label>
              <Select
                value={learning.mode}
                onChange={(e) =>
                  setSettings((prev) => (prev ? { ...prev, learning: { ...prev.learning, mode: e.target.value as "OFF" | "RESEARCH" } } : prev))
                }
                disabled={role !== "admin"}
              >
                <option value="OFF">OFF</option>
                <option value="RESEARCH">RESEARCH</option>
              </Select>
            </div>

            <div className="space-y-1">
              <label className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
                Selector
                <InfoTip text={"Thompson: explora/explota entre estrategias segun resultados.\nUCB1: usa cota superior e incertidumbre.\nRegime Rules: elige por reglas de mercado."} />
              </label>
              <Select
                value={learning.selector_algo}
                onChange={(e) =>
                  setSettings((prev) =>
                    prev
                      ? { ...prev, learning: { ...prev.learning, selector_algo: e.target.value as "thompson" | "ucb1" | "regime_rules" } }
                      : prev,
                  )
                }
                disabled={role !== "admin"}
              >
                <option value="thompson">Thompson</option>
                <option value="ucb1">UCB1</option>
                <option value="regime_rules">Regime Rules</option>
              </Select>
            </div>

            <div className="space-y-1">
              <label className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
                Drift
                <InfoTip text={"ADWIN: detecta cambio de distribucion en streams.\nPage-Hinkley: detecta cambio de media (CUSUM)."} />
              </label>
              <Select
                value={learning.drift_algo}
                onChange={(e) =>
                  setSettings((prev) =>
                    prev ? { ...prev, learning: { ...prev.learning, drift_algo: e.target.value as "adwin" | "page_hinkley" } } : prev,
                  )
                }
                disabled={role !== "admin"}
              >
                <option value="adwin">ADWIN</option>
                <option value="page_hinkley">Page-Hinkley</option>
              </Select>
            </div>

            <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm">
              <span className="flex items-center gap-2">
                Enforce PBO
                <InfoTip text={"PBO: probabilidad de sobreajuste del backtest.\nSi es alto, la recomendacion se rechaza."} />
              </span>
              <input
                type="checkbox"
                checked={learning.validation.enforce_pbo}
                onChange={(e) =>
                  setSettings((prev) =>
                    prev
                      ? { ...prev, learning: { ...prev.learning, validation: { ...prev.learning.validation, enforce_pbo: e.target.checked } } }
                      : prev,
                  )
                }
                disabled={role !== "admin"}
              />
            </label>

            <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm">
              <span className="flex items-center gap-2">
                Enforce DSR
                <InfoTip text={"DSR: corrige Sharpe por sesgo de seleccion.\nSi es bajo, la recomendacion se rechaza."} />
              </span>
              <input
                type="checkbox"
                checked={learning.validation.enforce_dsr}
                onChange={(e) =>
                  setSettings((prev) =>
                    prev
                      ? { ...prev, learning: { ...prev.learning, validation: { ...prev.learning.validation, enforce_dsr: e.target.checked } } }
                      : prev,
                  )
                }
                disabled={role !== "admin"}
              />
            </label>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs text-slate-300">
            <p className="font-semibold text-slate-200">Perfil de riesgo: {learning.risk_profile?.risk_profile || "medium"}</p>
            <p>
              PAPER: {learning.risk_profile?.paper?.risk_per_trade_pct ?? 0.5}% por trade | max pÃ©rdida diaria{" "}
              {learning.risk_profile?.paper?.max_daily_loss_pct ?? 3}% | max DD {learning.risk_profile?.paper?.max_drawdown_pct ?? 15}%
            </p>
            <p>
              LIVE inicial: {learning.risk_profile?.live_initial?.risk_per_trade_pct ?? 0.25}% por trade | max pÃ©rdida diaria{" "}
              {learning.risk_profile?.live_initial?.max_daily_loss_pct ?? 2}% | max DD {learning.risk_profile?.live_initial?.max_drawdown_pct ?? 10}% |
              max posiciones {learning.risk_profile?.max_positions ?? 10} | penaliza corr &gt;{" "}
              {learning.risk_profile?.correlation_penalty_threshold ?? 0.75}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Feature Flags</CardTitle>
        <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {Object.entries(settings.feature_flags).map(([key, value]) => (
            <label key={key} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm">
              <span>{key}</span>
              <input
                type="checkbox"
                checked={Boolean(value)}
                onChange={(e) =>
                  setSettings((prev) =>
                    prev
                      ? {
                          ...prev,
                          feature_flags: { ...prev.feature_flags, [key]: e.target.checked },
                        }
                      : prev,
                  )
                }
                disabled={role !== "admin"}
              />
            </label>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Diagnostico</CardTitle>
        <CardDescription>Probar backend (/health), WS (/api/events) y exchange (/api/v1/exchange/diagnose).</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Backend</p>
            <p className="text-sm text-slate-200">{diag.backend}</p>
            <Button variant="outline" onClick={testBackend}>Probar /health</Button>
          </div>
          <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">WS</p>
            <p className="text-sm text-slate-200">{diag.ws}</p>
            <Button variant="outline" onClick={testWs}>Probar WS</Button>
          </div>
          <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Exchange</p>
            <p className="text-sm text-slate-200">{diag.exchange}</p>
            {exchangeDiag ? (
              <div className="space-y-1 rounded-md border border-slate-800 bg-slate-950/60 p-2 text-xs text-slate-300">
                <p>base_url: {exchangeDiag.base_url}</p>
                <p>ws_url: {exchangeDiag.ws_url}</p>
                <p>source: {exchangeDiag.key_source}</p>
                {exchangeDiag.missing.length ? <p>faltan env vars: {exchangeDiag.missing.join(", ")}</p> : null}
                {exchangeDiag.missing.length ? <p className="text-amber-300">Cargalas en Railway -&gt; Service Variables</p> : null}
              </div>
            ) : null}
            <Button variant="outline" onClick={testExchange}>Probar exchange</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Gates LIVE</CardTitle>
        <CardDescription>LIVE solo habilitable cuando los gates requeridos estan en PASS.</CardDescription>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              Estado general:{" "}
              <Badge variant={gatesOverall === "PASS" ? "success" : gatesOverall === "WARN" ? "warn" : "danger"}>{gatesOverall}</Badge>
            </div>
            <Button variant="outline" disabled={role !== "admin" || gatesLoading} onClick={reevaluateGates}>
              {gatesLoading ? "Reevaluando..." : "Reevaluar gates"}
            </Button>
          </div>
          <div className="space-y-2">
            {gates.map((gate) => (
              <div key={gate.id} className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{gate.id}</span>
                  <Badge variant={gate.status === "PASS" ? "success" : gate.status === "WARN" ? "warn" : "danger"}>{gate.status}</Badge>
                </div>
                <p className="text-slate-300">{gate.reason}</p>
                {(gate.id === "G4_EXCHANGE_CONNECTOR_READY" || gate.id === "G7_ORDER_SIM_OR_PAPER_OK") && gate.status !== "PASS" ? (
                  <div className="mt-2 space-y-1 text-xs text-slate-400">
                    {toStringArray(gate.details?.missing_env_vars).length ? (
                      <p>
                        Variables faltantes: <span className="text-amber-300">{toStringArray(gate.details?.missing_env_vars).join(", ")}</span>
                      </p>
                    ) : null}
                    {toStringArray(gate.details?.missing_env_vars).length ? <p>Cargalas en Railway -&gt; Service Variables.</p> : null}
                    {typeof gate.details?.base_url === "string" ? <p>base_url: {String(gate.details?.base_url)}</p> : null}
                    {typeof gate.details?.ws_url === "string" ? <p>ws_url: {String(gate.details?.ws_url)}</p> : null}
                    {typeof gate.details?.ws_error === "string" && gate.details?.ws_error ? <p>ws_error: {String(gate.details?.ws_error)}</p> : null}
                    {typeof gate.details?.last_error === "string" && gate.details?.last_error ? <p>error: {String(gate.details?.last_error)}</p> : null}
                  </div>
                ) : null}
              </div>
            ))}
            {!gates.length ? <p className="text-sm text-slate-400">Sin gates disponibles.</p> : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Rollout / Gates</CardTitle>
        <CardDescription>Actualizacion segura de candidato vs baseline (offline gates, soaks, canary y rollback).</CardDescription>
        <CardContent className="space-y-4">
          {rolloutMessage ? <p className="text-sm text-emerald-300">{rolloutMessage}</p> : null}
          {rolloutError ? <p className="text-sm text-rose-300">{rolloutError}</p> : null}
          {rolloutLoading ? <p className="text-sm text-slate-400">Cargando rollout...</p> : null}

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-slate-100">Estado actual</p>
                <Badge variant={rolloutBadgeVariant(rollout?.state)}>{rollout?.state || "IDLE"}</Badge>
              </div>
              <div className="grid gap-2 text-xs text-slate-300 sm:grid-cols-2">
                <p>rollout_id: <span className="text-slate-100">{rollout?.rollout_id || "-"}</span></p>
                <p>fase: <span className="text-slate-100">{rollout?.current_phase || "-"}</span></p>
                <p>
                  weights:{" "}
                  <span className="text-slate-100">
                    B {formatMetricValue(rollout?.weights?.baseline_pct)}% / C {formatMetricValue(rollout?.weights?.candidate_pct)}%
                  </span>
                </p>
                <p>routing: <span className="text-slate-100">{rollout?.routing?.mode || "-"}</span></p>
                <p>pending approve: <span className="text-slate-100">{formatMetricValue(rollout?.pending_live_approval)}</span></p>
                <p>
                  target approve: <span className="text-slate-100">{rollout?.pending_live_approval_target || "-"}</span>
                </p>
              </div>
              {rollout?.live_stable_100_requires_approve ? (
                <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">
                  LIVE_STABLE_100 requiere aprobacion manual explicita.
                </p>
              ) : null}
              {rollout?.abort_reason ? (
                <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-xs text-rose-200">
                  Motivo abort/rollback: {rollout.abort_reason}
                </p>
              ) : null}
            </div>

            <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <p className="text-sm font-semibold text-slate-100">Acciones admin</p>
              <div className="grid gap-2 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Run candidato</label>
                  <Select value={rolloutCandidateRunId} onChange={(e) => setRolloutCandidateRunId(e.target.value)} disabled={role !== "admin" || rolloutBusy}>
                    <option value="">Seleccionar run</option>
                    {backtestRuns.map((run) => (
                      <option key={`cand-${run.id}`} value={run.id}>
                        {run.id} | {run.strategy_id} | {run.symbol || "-"} | {run.timeframe || "-"}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Run baseline</label>
                  <Select value={rolloutBaselineRunId} onChange={(e) => setRolloutBaselineRunId(e.target.value)} disabled={role !== "admin" || rolloutBusy}>
                    <option value="">Auto / Seleccionar run</option>
                    {backtestRuns.map((run) => (
                      <option key={`base-${run.id}`} value={run.id}>
                        {run.id} | {run.strategy_id} | {run.symbol || "-"} | {run.timeframe || "-"}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
              <Input
                value={rolloutReason}
                onChange={(e) => setRolloutReason(e.target.value)}
                placeholder="Motivo (approve/reject/rollback, opcional)"
                disabled={role !== "admin" || rolloutBusy}
              />
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <Button onClick={startRollout} disabled={rolloutStartDisabled}>{rolloutBusy ? "Procesando..." : "Start"}</Button>
                <Button variant="outline" onClick={refreshRollout} disabled={rolloutBusy}>Refresh</Button>
                <Button variant="outline" onClick={() => void evaluateCurrentRolloutPhase(false)} disabled={role !== "admin" || rolloutBusy || !rolloutCanEvaluate}>
                  Evaluar fase
                </Button>
                <Button variant="outline" onClick={() => void evaluateCurrentRolloutPhase(true)} disabled={role !== "admin" || rolloutBusy || !rolloutCanEvaluate}>
                  Evaluar + avanzar
                </Button>
                <Button variant="outline" onClick={advanceRollout} disabled={role !== "admin" || rolloutBusy}>Advance</Button>
                <Button variant="outline" onClick={approveRollout} disabled={role !== "admin" || rolloutBusy}>Approve</Button>
                <Button variant="outline" onClick={rejectRollout} disabled={role !== "admin" || rolloutBusy}>Reject</Button>
                <Button variant="danger" onClick={rollbackRollout} disabled={role !== "admin" || rolloutBusy}>Rollback</Button>
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-100">Baseline</p>
                <Badge variant={rollout?.baseline_version ? "success" : "neutral"}>{rollout?.baseline_version ? "activo" : "seleccionado"}</Badge>
              </div>
              {(() => {
                const baseline = rollout?.baseline_version;
                const fallback = selectedBaselineRun;
                const metrics = asRecord(baseline?.report_ref?.metrics);
                return (
                  <div className="space-y-1 text-xs text-slate-300">
                    <p>run_id: <span className="text-slate-100">{baseline?.run_id || fallback?.id || "-"}</span></p>
                    <p>strategy: <span className="text-slate-100">{baseline?.strategy_id || fallback?.strategy_id || "-"}</span></p>
                    <p>version: <span className="text-slate-100">{baseline?.strategy_version || "-"}</span></p>
                    <p>dataset_hash: <span className="text-slate-100">{baseline?.dataset_hash || fallback?.dataset_hash || "-"}</span></p>
                    <p>periodo: <span className="text-slate-100">{baseline?.period?.start || fallback?.period?.start || "-"} → {baseline?.period?.end || fallback?.period?.end || "-"}</span></p>
                    <p>expectancy: <span className="text-slate-100">{formatMetricValue(metrics.expectancy_usd_per_trade ?? metrics.expectancy ?? fallback?.metrics?.expectancy_usd_per_trade)}</span></p>
                    <p>sharpe: <span className="text-slate-100">{formatMetricValue(metrics.sharpe ?? fallback?.metrics?.sharpe)}</span> | max_dd: <span className="text-slate-100">{formatMetricValue(metrics.max_dd ?? fallback?.metrics?.max_dd)}</span></p>
                  </div>
                );
              })()}
            </div>

            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-100">Candidate</p>
                <Badge variant={rollout?.candidate_version ? "warn" : "neutral"}>{rollout?.candidate_version ? "rollout" : "seleccionado"}</Badge>
              </div>
              {(() => {
                const candidate = rollout?.candidate_version;
                const fallback = selectedCandidateRun;
                const metrics = asRecord(candidate?.report_ref?.metrics);
                return (
                  <div className="space-y-1 text-xs text-slate-300">
                    <p>run_id: <span className="text-slate-100">{candidate?.run_id || fallback?.id || "-"}</span></p>
                    <p>strategy: <span className="text-slate-100">{candidate?.strategy_id || fallback?.strategy_id || "-"}</span></p>
                    <p>version: <span className="text-slate-100">{candidate?.strategy_version || "-"}</span></p>
                    <p>dataset_hash: <span className="text-slate-100">{candidate?.dataset_hash || fallback?.dataset_hash || "-"}</span></p>
                    <p>periodo: <span className="text-slate-100">{candidate?.period?.start || fallback?.period?.start || "-"} → {candidate?.period?.end || fallback?.period?.end || "-"}</span></p>
                    <p>expectancy: <span className="text-slate-100">{formatMetricValue(metrics.expectancy_usd_per_trade ?? metrics.expectancy ?? fallback?.metrics?.expectancy_usd_per_trade)}</span></p>
                    <p>sharpe: <span className="text-slate-100">{formatMetricValue(metrics.sharpe ?? fallback?.metrics?.sharpe)}</span> | max_dd: <span className="text-slate-100">{formatMetricValue(metrics.max_dd ?? fallback?.metrics?.max_dd)}</span></p>
                  </div>
                );
              })()}
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-100">Offline Gates</p>
                <Badge variant={rollout?.offline_gates?.passed ? "success" : rollout?.offline_gates ? "danger" : "neutral"}>
                  {rollout?.offline_gates ? (rollout.offline_gates.passed ? "PASS" : "FAIL") : "N/A"}
                </Badge>
              </div>
              {rollout?.offline_gates?.failed_ids?.length ? (
                <p className="text-xs text-rose-300">Fails: {rollout.offline_gates.failed_ids.join(", ")}</p>
              ) : null}
              <div className="space-y-2">
                {(rollout?.offline_gates?.checks || []).map((check) => (
                  <div key={`offline-${check.id}`} className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-1 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-200">{check.id}</span>
                      <Badge variant={checkBadgeVariant(check.ok)}>{check.ok ? "PASS" : "FAIL"}</Badge>
                    </div>
                    {check.reason ? <p className="text-slate-400">{check.reason}</p> : null}
                  </div>
                ))}
                {!rollout?.offline_gates?.checks?.length ? <p className="text-xs text-slate-400">Sin evaluacion offline (iniciá rollout).</p> : null}
              </div>
            </div>

            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-100">Compare vs Baseline</p>
                <Badge variant={rollout?.compare_vs_baseline?.passed ? "success" : rollout?.compare_vs_baseline ? "danger" : "neutral"}>
                  {rollout?.compare_vs_baseline ? (rollout.compare_vs_baseline.passed ? "PASS" : "FAIL") : "N/A"}
                </Badge>
              </div>
              {rollout?.compare_vs_baseline?.failed_ids?.length ? (
                <p className="text-xs text-rose-300">Fails: {rollout.compare_vs_baseline.failed_ids.join(", ")}</p>
              ) : null}
              <div className="space-y-2">
                {(rollout?.compare_vs_baseline?.checks || []).map((check) => (
                  <div key={`compare-${check.id}`} className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-1 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-200">{check.id}</span>
                      <Badge variant={checkBadgeVariant(check.ok)}>{check.ok ? "PASS" : "FAIL"}</Badge>
                    </div>
                    {check.reason ? <p className="text-slate-400">{check.reason}</p> : null}
                  </div>
                ))}
                {!rollout?.compare_vs_baseline?.checks?.length ? <p className="text-xs text-slate-400">Sin comparacion (iniciá rollout).</p> : null}
              </div>
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-100">Fase actual + KPIs</p>
              <Badge variant={rolloutCurrentEval?.passed ? "success" : rolloutCurrentEval?.hard_fail ? "danger" : "warn"}>
                {rolloutCurrentEval?.status || "SIN_EVAL"}
              </Badge>
            </div>
            <div className="grid gap-2 text-xs text-slate-300 sm:grid-cols-2 xl:grid-cols-4">
              <p>eval_key: <span className="text-slate-100">{rolloutCurrentEvalKey || "-"}</span></p>
              <p>phase_type: <span className="text-slate-100">{rollout?.routing?.phase_type || "-"}</span></p>
              <p>shadow_only: <span className="text-slate-100">{formatMetricValue(rollout?.routing?.shadow_only)}</span></p>
              <p>updated_at: <span className="text-slate-100">{rollout?.updated_at || "-"}</span></p>
            </div>
            {rolloutCurrentEval?.failed_ids?.length ? (
              <p className="text-xs text-rose-300">Checks fallidos: {rolloutCurrentEval.failed_ids.join(", ")}</p>
            ) : null}
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {Object.entries(asRecord(rolloutCurrentKpis)).map(([key, value]) => (
                <div key={`kpi-${key}`} className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-1 text-xs">
                  <p className="text-slate-400">{key}</p>
                  <p className="font-semibold text-slate-100">{formatMetricValue(value)}</p>
                </div>
              ))}
              {!Object.keys(asRecord(rolloutCurrentKpis)).length ? (
                <p className="text-xs text-slate-400">Sin KPIs de fase todavia. Evaluá la fase actual.</p>
              ) : null}
            </div>
            {!!rolloutCurrentEval?.checks?.length ? (
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">Checks de fase</p>
                {rolloutCurrentEval.checks?.map((check) => (
                  <div key={`phase-check-${check.id}`} className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-1 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-200">{check.id}</span>
                      <Badge variant={checkBadgeVariant(check.ok)}>{check.ok ? "PASS" : "FAIL"}</Badge>
                    </div>
                    {check.reason ? <p className="text-slate-400">{check.reason}</p> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-100">Telemetria blending (baseline/candidate/blended)</p>
              <Badge variant={rollout?.live_signal_telemetry?.updated_at ? "info" : "neutral"}>
                {rollout?.live_signal_telemetry?.updated_at ? "ACTIVA" : "VACIA"}
              </Badge>
            </div>
            <p className="text-xs text-slate-400">
              Se llena en fases SHADOW/CANARY cuando el hook de routing/blending registra decisiones.
            </p>
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {Object.entries(rollout?.live_signal_telemetry?.phases || {}).map(([phaseName, row]) => (
                <div key={`telemetry-${phaseName}`} className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-200">{phaseName}</span>
                    <Badge variant="info">{formatMetricValue(row.events)}</Badge>
                  </div>
                  <p className="text-slate-400">agreement_rate: {formatMetricValue(row.agreement_rate)}</p>
                  {Object.entries(row.action_counts || {}).map(([source, counts]) => (
                    <p key={`telemetry-${phaseName}-${source}`} className="text-slate-300">
                      {source}: {Object.entries(counts || {})
                        .map(([action, n]) => `${action}:${n}`)
                        .join(" | ") || "-"}
                    </p>
                  ))}
                </div>
              ))}
              {!Object.keys(rollout?.live_signal_telemetry?.phases || {}).length ? (
                <p className="text-xs text-slate-400">Sin eventos de blending registrados.</p>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button disabled={role !== "admin" || saving} onClick={save}>
          {saving ? "Guardando..." : "Guardar"}
        </Button>
      </div>
    </div>
  );
}
