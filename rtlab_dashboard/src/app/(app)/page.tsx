"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useSession } from "@/components/providers/session-provider";
import { apiGet, apiPost } from "@/lib/client-api";
import type { AlertEvent, BotStatusResponse, PortfolioSnapshot, Position } from "@/lib/types";
import { fmtPct, fmtUsd } from "@/lib/utils";

export default function OverviewPage() {
  const { role } = useSession();
  const [status, setStatus] = useState<BotStatusResponse | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [loadError, setLoadError] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [cooldownUntil, setCooldownUntil] = useState<number>(0);

  const refresh = async () => {
    try {
      const [st, pf, pos, alt] = await Promise.all([
        apiGet<BotStatusResponse>("/api/v1/bot/status"),
        apiGet<PortfolioSnapshot>("/api/v1/portfolio"),
        apiGet<Position[]>("/api/v1/positions"),
        apiGet<AlertEvent[]>("/api/v1/alerts"),
      ]);
      setStatus(st);
      setPortfolio(pf);
      setPositions(pos);
      setAlerts(alt.slice(0, 8));
      setLoadError("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "No se pudo cargar el backend.";
      setLoadError(message);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    const events = new EventSource("/api/events", { withCredentials: true });
    events.addEventListener("health", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as {
        data?: { state?: BotStatusResponse["bot_status"]; daily_pnl?: number; dd?: number; ws_connected?: boolean };
      };
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              bot_status: payload.data?.state || prev.bot_status,
              state: payload.data?.state || prev.state,
              pnl: { ...prev.pnl, daily: payload.data?.daily_pnl ?? prev.pnl.daily },
              max_dd: { ...prev.max_dd, value: payload.data?.dd ?? prev.max_dd.value },
              health: { ...prev.health, ws_connected: payload.data?.ws_connected ?? prev.health.ws_connected },
              updated_at: new Date().toISOString(),
            }
          : prev,
      );
    });
    const alertHandlers = ["breaker_triggered", "api_error", "backtest_finished", "strategy_changed", "order_update", "fill"];
    for (const type of alertHandlers) {
      events.addEventListener(type, (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as AlertEvent;
        setAlerts((prev) => [payload, ...prev].slice(0, 8));
      });
    }
    events.onerror = () => {
      setLoadError("Stream de eventos desconectado. Reintentando...");
    };
    return () => {
      events.close();
    };
  }, []);

  const runAction = async (path: string, body?: Record<string, unknown>, cooldownMs = 0) => {
    setActionLoading(path);
    try {
      await apiPost(path, body);
      await refresh();
      if (cooldownMs > 0) setCooldownUntil(Date.now() + cooldownMs);
    } finally {
      setActionLoading(null);
    }
  };

  const onCooldown = Date.now() < cooldownUntil;

  const statusVariant = useMemo(() => {
    if (!status) return "neutral";
    if (status.bot_status === "RUNNING") return "success";
    if (status.bot_status === "SAFE_MODE") return "warn";
    if (status.bot_status === "KILLED") return "danger";
    return "neutral";
  }, [status]);

  return (
    <div className="space-y-5">
      {loadError ? <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-300">Estado desconocido: {loadError}</p> : null}
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardTitle className="flex items-center justify-between">
            Estado del bot
            <Badge variant={statusVariant}>{status?.bot_status || "desconocido"}</Badge>
          </CardTitle>
          <CardDescription className="mt-1">Estado operativo, salud del sistema y guardas de riesgo.</CardDescription>
          <CardContent className="grid grid-cols-2 gap-3">
            <Metric title="Equity" value={status ? fmtUsd(status.equity) : "--"} />
            <Metric title="PnL diario" value={status ? fmtUsd(status.pnl.daily) : "--"} />
            <Metric title="Max DD / Limite" value={status ? `${fmtPct(status.max_dd.value)} / ${fmtPct(status.max_dd.limit)}` : "--"} />
            <Metric
              title="Perdida diaria / Limite"
              value={status ? `${fmtPct(status.daily_loss.value)} / ${fmtPct(status.daily_loss.limit)}` : "--"}
            />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Salud</CardTitle>
          <CardContent className="space-y-2">
            <Metric title="Latencia API" value={status ? `${status.health.api_latency_ms} ms` : "--"} compact />
            <Metric title="WS conectado" value={status?.health.ws_connected ? "si" : "no"} compact />
            <Metric title="Lag WS" value={status ? `${status.health.ws_lag_ms} ms` : "--"} compact />
            <Metric title="Rate limits (5m)" value={status ? String(status.health.rate_limits_5m) : "--"} compact />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Portafolio</CardTitle>
          <CardContent className="space-y-2">
            <Metric title="Exposicion total" value={portfolio ? fmtUsd(portfolio.exposure_total) : "--"} compact />
            <Metric title="PnL semanal" value={portfolio ? fmtUsd(portfolio.pnl_weekly) : "--"} compact />
            <Metric title="PnL mensual" value={portfolio ? fmtUsd(portfolio.pnl_monthly) : "--"} compact />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Controles</CardTitle>
          <CardDescription>Acciones reservadas para admin.</CardDescription>
          <CardContent className="space-y-2">
            <Button
              className="w-full"
              variant="secondary"
              disabled={role !== "admin" || !!actionLoading}
              onClick={() => runAction("/api/v1/control/pause")}
            >
              {actionLoading === "/api/v1/control/pause" ? "Pausando..." : "Pausar"}
            </Button>
            <Button
              className="w-full"
              disabled={role !== "admin" || !!actionLoading}
              onClick={() => runAction("/api/v1/control/resume")}
            >
              {actionLoading === "/api/v1/control/resume" ? "Reanudando..." : "Reanudar"}
            </Button>
            <Button
              className="w-full"
              variant="outline"
              disabled={role !== "admin" || !!actionLoading || onCooldown}
              onClick={() => runAction("/api/v1/control/safe-mode", { enabled: true })}
            >
              Modo Seguro ON
            </Button>
            <Button
              className="w-full"
              variant="secondary"
              disabled={role !== "admin" || !!actionLoading || onCooldown}
              onClick={() => runAction("/api/v1/control/safe-mode", { enabled: false })}
            >
              Modo Seguro OFF
            </Button>
            <Button
              className="w-full"
              variant="danger"
              disabled={role !== "admin" || !!actionLoading || onCooldown}
              onClick={() => {
                const ok = window.confirm("Confirmar interruptor de emergencia. Esto detiene el trading.");
                if (!ok) return;
                const ok2 = window.confirm("Segunda confirmacion: ejecutar interruptor de emergencia ahora?");
                if (!ok2) return;
                void runAction("/api/v1/control/kill", undefined, 10_000);
              }}
            >
              Interruptor de Emergencia
            </Button>
            {onCooldown ? <p className="text-xs text-amber-300">Cooldown critico activo por unos segundos.</p> : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Posiciones Abiertas</CardTitle>
          <CardDescription>Exposicion actual y PnL no realizado.</CardDescription>
          <CardContent className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Simbolo</TH>
                  <TH>Lado</TH>
                  <TH>Cantidad</TH>
                  <TH>Entrada</TH>
                  <TH>Mark</TH>
                  <TH>No realizado</TH>
                </TR>
              </THead>
              <TBody>
                {positions.map((pos) => (
                  <TR key={`${pos.symbol}-${pos.strategy_id}`}>
                    <TD>{pos.symbol}</TD>
                    <TD>{pos.side}</TD>
                    <TD>{pos.qty}</TD>
                    <TD>{pos.entry_px.toFixed(2)}</TD>
                    <TD>{pos.mark_px.toFixed(2)}</TD>
                    <TD className={pos.pnl_unrealized >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(pos.pnl_unrealized)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Alertas Recientes</CardTitle>
          <CardDescription>Alertas operativas y anomalias del sistema.</CardDescription>
          <CardContent className="space-y-2">
            {alerts.map((alert) => (
              <div key={alert.id} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <Badge variant={alert.severity === "error" ? "danger" : alert.severity === "warn" ? "warn" : "info"}>
                    {alert.severity.toUpperCase()}
                  </Badge>
                  <span className="text-xs text-slate-400">{new Date(alert.ts).toLocaleString()}</span>
                </div>
                <p className="text-sm text-slate-200">{alert.message}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function Metric({ title, value, compact }: { title: string; value: string; compact?: boolean }) {
  return (
    <div className={compact ? "" : "rounded-xl border border-slate-800 bg-slate-900/70 p-3"}>
      <p className="text-xs uppercase tracking-wide text-slate-400">{title}</p>
      <p className={compact ? "text-sm font-semibold text-slate-100" : "mt-1 text-lg font-semibold text-slate-100"}>{value}</p>
    </div>
  );
}
