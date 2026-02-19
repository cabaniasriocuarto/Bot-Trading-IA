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
import { toCsv } from "@/lib/utils";

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

export default function AlertsLogsPage() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [severity, setSeverity] = useState("");
  const [moduleName, setModuleName] = useState("");
  const [sinceInput, setSinceInput] = useState(() => toLocalInput(new Date(Date.now() - 24 * 60 * 60_000)));
  const [untilInput, setUntilInput] = useState(() => toLocalInput(new Date()));

  const refresh = useCallback(async () => {
    const since = parseLocalInput(sinceInput);
    const until = parseLocalInput(untilInput);
    const params = new URLSearchParams();
    if (since) params.set("since", since);
    if (until) params.set("until", until);
    if (severity) params.set("severity", severity);
    if (moduleName) params.set("module", moduleName);
    const query = params.toString();
    const [alertsRows, logsRows] = await Promise.all([
      apiGet<AlertEvent[]>(`/api/alerts?${query}`),
      apiGet<LogEvent[]>(`/api/logs?${query}`),
    ]);
    setAlerts(alertsRows);
    setLogs(logsRows);
  }, [moduleName, severity, sinceInput, untilInput]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const events = new EventSource("/api/events", { withCredentials: true });
    events.addEventListener("alert", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as AlertEvent;
      setAlerts((prev) => [payload, ...prev].slice(0, 50));
    });
    return () => events.close();
  }, []);

  const exportLogs = () => {
    const csv = toCsv(logs);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `rtlab_logs_${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const merged = useMemo(
    () =>
      [
        ...alerts.map((a) => ({ type: "alert", ts: a.ts, severity: a.severity, message: a.message, id: a.id, related: a.related_id || "" })),
        ...logs.map((l) => ({ type: "log", ts: l.ts, severity: l.severity, message: `[${l.module}] ${l.message}`, id: l.id, related: l.related_id || "" })),
      ].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()),
    [alerts, logs],
  );

  const moduleOptions = useMemo(() => [...new Set(logs.map((row) => row.module))].sort(), [logs]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          Alerts & Logs
        </CardTitle>
        <CardDescription>Structured event stream with filters and drill-down context ids.</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Since</label>
            <Input type="datetime-local" value={sinceInput} onChange={(e) => setSinceInput(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Until</label>
            <Input type="datetime-local" value={untilInput} onChange={(e) => setUntilInput(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Severity</label>
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-full">
              <option value="">All severities</option>
              <option value="info">Info</option>
              <option value="warn">Warn</option>
              <option value="error">Error</option>
              <option value="debug">Debug</option>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Module</label>
            <Select value={moduleName} onChange={(e) => setModuleName(e.target.value)} className="w-full">
              <option value="">All modules</option>
              {moduleOptions.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-end gap-2">
            <Button variant="outline" onClick={() => void refresh()}>
              Apply Filters
            </Button>
            <Button variant="outline" onClick={exportLogs}>
              Export Logs
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Type</TH>
                <TH>Timestamp</TH>
                <TH>Severity</TH>
                <TH>Message</TH>
                <TH>Related</TH>
                <TH>ID</TH>
              </TR>
            </THead>
            <TBody>
              {merged.map((row) => (
                <TR key={`${row.type}-${row.id}`}>
                  <TD>{row.type}</TD>
                  <TD>{new Date(row.ts).toLocaleString()}</TD>
                  <TD>
                    <Badge variant={row.severity === "error" ? "danger" : row.severity === "warn" ? "warn" : "info"}>{row.severity}</Badge>
                  </TD>
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
    </div>
  );
}
