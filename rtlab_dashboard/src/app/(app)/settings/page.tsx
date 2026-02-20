"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiGet } from "@/lib/client-api";
import type { HealthResponse, SettingsResponse } from "@/lib/types";

type GateItem = {
  id: string;
  name: string;
  status: "PASS" | "FAIL" | "WARN";
  reason: string;
  details?: Record<string, unknown>;
};

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
    setDiag((prev) => ({ ...prev, ws: "probando..." }));
    await new Promise<void>((resolve) => {
      const es = new EventSource("/ws/v1/events", { withCredentials: true });
      const timeout = setTimeout(() => {
        es.close();
        setDiag((prev) => ({ ...prev, ws: "timeout" }));
        resolve();
      }, 5000);
      const markOk = () => {
        clearTimeout(timeout);
        es.close();
        setDiag((prev) => ({ ...prev, ws: "ok" }));
        resolve();
      };
      es.addEventListener("health", markOk);
      es.onerror = () => {
        clearTimeout(timeout);
        es.close();
        setDiag((prev) => ({ ...prev, ws: "fallo" }));
        resolve();
      };
    });
  };

  const testExchange = async () => {
    setDiag((prev) => ({ ...prev, exchange: "probando..." }));
    try {
      const res = await fetch("/api/v1/settings/test-exchange", {
        method: "POST",
        credentials: "include",
      });
      const body = (await res.json().catch(() => ({}))) as { ok?: boolean; message?: string; mode?: string };
      if (!res.ok || !body.ok) {
        setDiag((prev) => ({ ...prev, exchange: body.message || "fallo" }));
        return;
      }
      setDiag((prev) => ({ ...prev, exchange: `ok (${body.mode || ""})` }));
    } catch {
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
        <CardDescription>Probar backend (/health), WS (/ws/v1/events) y exchange (paper/testnet/mock).</CardDescription>
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
              </div>
            ))}
            {!gates.length ? <p className="text-sm text-slate-400">Sin gates disponibles.</p> : null}
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
