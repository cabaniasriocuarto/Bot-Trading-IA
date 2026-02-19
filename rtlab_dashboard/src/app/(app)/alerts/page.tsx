"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet } from "@/lib/client-api";
import type { AlertEvent, LogEvent } from "@/lib/types";
import { toCsv } from "@/lib/utils";

export default function AlertsLogsPage() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [severity, setSeverity] = useState("");

  const refresh = useCallback(async () => {
    const since = new Date(Date.now() - 24 * 60 * 60_000).toISOString();
    const sev = severity ? `&severity=${severity}` : "";
    const [alertsRows, logsRows] = await Promise.all([
      apiGet<AlertEvent[]>(`/api/alerts?since=${encodeURIComponent(since)}${sev}`),
      apiGet<LogEvent[]>(`/api/logs?since=${encodeURIComponent(since)}${sev}`),
    ]);
    setAlerts(alertsRows);
    setLogs(logsRows);
  }, [severity]);

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

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          Alerts & Logs
          <div className="flex items-center gap-2">
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-[180px]">
              <option value="">All severities</option>
              <option value="info">Info</option>
              <option value="warn">Warn</option>
              <option value="error">Error</option>
              <option value="debug">Debug</option>
            </Select>
            <Button variant="outline" onClick={exportLogs}>
              Export Logs
            </Button>
          </div>
        </CardTitle>
        <CardDescription>Structured event stream with filters and drill-down context ids.</CardDescription>
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
                  <TD>{row.related || "-"}</TD>
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
