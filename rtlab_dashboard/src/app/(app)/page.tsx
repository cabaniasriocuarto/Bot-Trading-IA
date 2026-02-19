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
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [cooldownUntil, setCooldownUntil] = useState<number>(0);

  const refresh = async () => {
    const [st, pf, pos, alt] = await Promise.all([
      apiGet<BotStatusResponse>("/api/status"),
      apiGet<PortfolioSnapshot>("/api/portfolio"),
      apiGet<Position[]>("/api/positions"),
      apiGet<AlertEvent[]>("/api/alerts"),
    ]);
    setStatus(st);
    setPortfolio(pf);
    setPositions(pos);
    setAlerts(alt.slice(0, 8));
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    const events = new EventSource("/api/events", { withCredentials: true });
    events.addEventListener("status", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { bot_status: BotStatusResponse["bot_status"] };
      setStatus((prev) => (prev ? { ...prev, bot_status: payload.bot_status, updated_at: new Date().toISOString() } : prev));
    });
    events.addEventListener("alert", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as AlertEvent;
      setAlerts((prev) => [payload, ...prev].slice(0, 8));
    });
    return () => events.close();
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
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardTitle className="flex items-center justify-between">
            Bot Status
            <Badge variant={statusVariant}>{status?.bot_status || "..."}</Badge>
          </CardTitle>
          <CardDescription className="mt-1">Operational state, health and risk guardrails.</CardDescription>
          <CardContent className="grid grid-cols-2 gap-3">
            <Metric title="Equity" value={status ? fmtUsd(status.equity) : "--"} />
            <Metric title="Daily PnL" value={status ? fmtUsd(status.pnl.daily) : "--"} />
            <Metric title="Max DD / Limit" value={status ? `${fmtPct(status.max_dd.value)} / ${fmtPct(status.max_dd.limit)}` : "--"} />
            <Metric
              title="Daily Loss / Limit"
              value={status ? `${fmtPct(status.daily_loss.value)} / ${fmtPct(status.daily_loss.limit)}` : "--"}
            />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Health</CardTitle>
          <CardContent className="space-y-2">
            <Metric title="API latency" value={status ? `${status.health.api_latency_ms} ms` : "--"} compact />
            <Metric title="WS connected" value={status?.health.ws_connected ? "yes" : "no"} compact />
            <Metric title="WS lag" value={status ? `${status.health.ws_lag_ms} ms` : "--"} compact />
            <Metric title="Rate limits (5m)" value={status ? String(status.health.rate_limits_5m) : "--"} compact />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Portfolio</CardTitle>
          <CardContent className="space-y-2">
            <Metric title="Exposure total" value={portfolio ? fmtUsd(portfolio.exposure_total) : "--"} compact />
            <Metric title="Weekly PnL" value={portfolio ? fmtUsd(portfolio.pnl_weekly) : "--"} compact />
            <Metric title="Monthly PnL" value={portfolio ? fmtUsd(portfolio.pnl_monthly) : "--"} compact />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Controls</CardTitle>
          <CardDescription>Admin-only actions</CardDescription>
          <CardContent className="space-y-2">
            <Button
              className="w-full"
              variant="secondary"
              disabled={role !== "admin" || !!actionLoading}
              onClick={() => runAction("/api/control/pause")}
            >
              {actionLoading === "/api/control/pause" ? "Pausing..." : "Pause"}
            </Button>
            <Button
              className="w-full"
              disabled={role !== "admin" || !!actionLoading}
              onClick={() => runAction("/api/control/resume")}
            >
              {actionLoading === "/api/control/resume" ? "Resuming..." : "Resume"}
            </Button>
            <Button
              className="w-full"
              variant="outline"
              disabled={role !== "admin" || !!actionLoading || onCooldown}
              onClick={() => runAction("/api/control/safe-mode", { enabled: true })}
            >
              Safe Mode ON
            </Button>
            <Button
              className="w-full"
              variant="secondary"
              disabled={role !== "admin" || !!actionLoading || onCooldown}
              onClick={() => runAction("/api/control/safe-mode", { enabled: false })}
            >
              Safe Mode OFF
            </Button>
            <Button
              className="w-full"
              variant="danger"
              disabled={role !== "admin" || !!actionLoading || onCooldown}
              onClick={() => {
                const ok = window.confirm("Confirm KILL switch. This action halts trading.");
                if (!ok) return;
                const ok2 = window.confirm("Second confirmation required: execute kill switch?");
                if (!ok2) return;
                void runAction("/api/control/kill", undefined, 10_000);
              }}
            >
              Kill Switch
            </Button>
            {onCooldown ? <p className="text-xs text-amber-300">Critical cooldown active for a few seconds.</p> : null}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Open Positions</CardTitle>
          <CardDescription>Current exposure and unrealized PnL.</CardDescription>
          <CardContent className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Symbol</TH>
                  <TH>Side</TH>
                  <TH>Qty</TH>
                  <TH>Entry</TH>
                  <TH>Mark</TH>
                  <TH>Unrealized</TH>
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
          <CardTitle>Recent Alerts</CardTitle>
          <CardDescription>Mirrored operational alerts and system anomalies.</CardDescription>
          <CardContent className="space-y-2">
            {alerts.map((alert) => (
              <div key={alert.id} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <Badge
                    variant={alert.severity === "error" ? "danger" : alert.severity === "warn" ? "warn" : "info"}
                  >
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
