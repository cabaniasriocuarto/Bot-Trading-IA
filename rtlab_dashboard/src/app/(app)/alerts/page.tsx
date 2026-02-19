"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet } from "@/lib/client-api";
import type { AlertEvent, LogEvent } from "@/lib/types";

function toLocalInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function parseLocalInput(value: string) {
  const ms = new Date(value).getTime();
  if (Number.isNaN(ms)) return null;
  return new Date(ms).toISOString();
}

function relatedHref(relatedId: string) {
  if (relatedId.startsWith("tr_")) return `/trades/${relatedId}`;
  if (relatedId.startsWith("stg_")) return `/strategies/${relatedId}`;
  if (relatedId.startsWith("bt_")) return `/backtests?run=${relatedId}`;
  return "";
}

type Row = {
  type: string;
  ts: string;
  severity: "debug" | "info" | "warn" | "error";
  message: string;
  id: string;
  related: string;
  module: string;
  payload?: Record<string, unknown>;
};

export default function AlertsLogsPage() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [severity, setSeverity] = useState("");
  const [moduleName, setModuleName] = useState("");
  const [sinceInput, setSinceInput] = useState(() => toLocalInput(new Date(Date.now() - 24 * 60 * 60_000)));
  const [untilInput, setUntilInput] = useState(() => toLocalInput(new Date()));
  const [selected, setSelected] = useState<Row | null>(null);

  const buildQuery = useCallback(() => {
    const since = parseLocalInput(sinceInput);
    const until = parseLocalInput(untilInput);
    const params = new URLSearchParams();
    if (since) params.set("since", since);
    if (until) params.set("until", until);
    if (severity) params.set("severity", severity);
    if (moduleName) params.set("module", moduleName);
    return params;
  }, [moduleName, severity, sinceInput, untilInput]);

  const refresh = useCallback(async () => {
    const params = buildQuery();
    const query = params.toString();
    const [alertsRows, logsRows] = await Promise.all([
      apiGet<AlertEvent[]>(`/api/v1/alerts?${query}`),
      apiGet<LogEvent[]>(`/api/v1/logs?${query}`),
    ]);
    setAlerts(alertsRows);
    setLogs(logsRows);
  }, [buildQuery]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const events = new EventSource("/api/events", { withCredentials: true });
    const types = ["breaker_triggered", "api_error", "backtest_finished", "strategy_changed", "order_update", "fill", "health"];
    for (const type of types) {
      events.addEventListener(type, () => {
        void refresh();
      });
    }
    return () => events.close();
  }, [refresh]);

  const exportLogs = async (format: "csv" | "json") => {
    const params = buildQuery();
    params.set("format", format);
    const res = await fetch(`/api/v1/logs?${params.toString()}`, { credentials: "include" });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `rtlab_logs_${new Date().toISOString().slice(0, 10)}.${format}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const merged = useMemo<Row[]>(
    () =>
      [
        ...alerts.map((a) => ({
          type: a.type || "alert",
          ts: a.ts,
          severity: a.severity,
          message: a.message,
          id: a.id,
          related: a.related_id || "",
          module: a.module || "alerts",
          payload: a.data,
        })),
        ...logs.map((l) => ({
          type: l.type,
          ts: l.ts,
          severity: l.severity,
          message: l.message,
          id: l.id,
          related: l.related_ids?.[0] || "",
          module: l.module,
          payload: l.payload,
        })),
      ].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()),
    [alerts, logs],
  );

  const moduleOptions = useMemo(() => [...new Set(logs.map((row) => row.module))].sort(), [logs]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Alertas y Logs</CardTitle>
        <CardDescription>Stream de eventos estructurados con filtros y drill-down por fila.</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Desde</label>
            <Input type="datetime-local" value={sinceInput} onChange={(e) => setSinceInput(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Hasta</label>
            <Input type="datetime-local" value={untilInput} onChange={(e) => setUntilInput(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Severidad</label>
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-full">
              <option value="">Todas</option>
              <option value="info">Info</option>
              <option value="warn">Warn</option>
              <option value="error">Error</option>
              <option value="debug">Debug</option>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Modulo</label>
            <Select value={moduleName} onChange={(e) => setModuleName(e.target.value)} className="w-full">
              <option value="">Todos</option>
              {moduleOptions.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-end gap-2">
            <Button variant="outline" onClick={() => void refresh()}>
              Aplicar filtros
            </Button>
            <Button variant="outline" onClick={() => void exportLogs("csv")}>
              Exportar CSV
            </Button>
            <Button variant="outline" onClick={() => void exportLogs("json")}>
              Exportar JSON
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Tipo</TH>
                <TH>Timestamp</TH>
                <TH>Severidad</TH>
                <TH>Modulo</TH>
                <TH>Mensaje</TH>
                <TH>Relacionado</TH>
                <TH>ID</TH>
              </TR>
            </THead>
            <TBody>
              {merged.map((row) => (
                <TR key={`${row.type}-${row.id}`} className="cursor-pointer hover:bg-slate-900/50" onClick={() => setSelected(row)}>
                  <TD>{row.type}</TD>
                  <TD>{new Date(row.ts).toLocaleString()}</TD>
                  <TD>
                    <Badge variant={row.severity === "error" ? "danger" : row.severity === "warn" ? "warn" : "info"}>{row.severity}</Badge>
                  </TD>
                  <TD>{row.module}</TD>
                  <TD>{row.message}</TD>
                  <TD>
                    {row.related ? (
                      relatedHref(row.related) ? (
                        <Link href={relatedHref(row.related)} className="text-cyan-300 underline">
                          {row.related}
                        </Link>
                      ) : (
                        row.related
                      )
                    ) : (
                      "-"
                    )}
                  </TD>
                  <TD className="font-mono text-xs">{row.id}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      {selected ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setSelected(null)}>
          <div className="w-full max-w-2xl rounded-xl border border-slate-700 bg-slate-950 p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Detalle del evento</h3>
              <Button size="sm" variant="outline" onClick={() => setSelected(null)}>
                Cerrar
              </Button>
            </div>
            <div className="space-y-2 text-xs text-slate-300">
              <p>
                <strong>Tipo:</strong> {selected.type}
              </p>
              <p>
                <strong>Modulo:</strong> {selected.module}
              </p>
              <p>
                <strong>Mensaje:</strong> {selected.message}
              </p>
              <p>
                <strong>Timestamp:</strong> {new Date(selected.ts).toLocaleString()}
              </p>
            </div>
            <pre className="mt-3 max-h-72 overflow-auto rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200">
{JSON.stringify(selected.payload || {}, null, 2)}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}
