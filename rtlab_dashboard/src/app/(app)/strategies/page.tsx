"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPost } from "@/lib/client-api";
import type { Strategy } from "@/lib/types";

const paramSchema = z.record(z.string(), z.union([z.number(), z.string(), z.boolean()]));

function toYaml(params: Record<string, unknown>) {
  return Object.entries(params)
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
}

function parseYaml(input: string) {
  const lines = input
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const out: Record<string, unknown> = {};
  for (const line of lines) {
    const [rawKey, ...rest] = line.split(":");
    const rawVal = rest.join(":").trim();
    if (!rawKey || !rawVal) throw new Error(`Invalid line: ${line}`);
    if (/^-?\d+(\.\d+)?$/.test(rawVal)) {
      out[rawKey.trim()] = Number(rawVal);
    } else if (rawVal.toLowerCase() === "true" || rawVal.toLowerCase() === "false") {
      out[rawKey.trim()] = rawVal.toLowerCase() === "true";
    } else {
      out[rawKey.trim()] = rawVal;
    }
  }
  return paramSchema.parse(out);
}

export default function StrategiesPage() {
  const { role } = useSession();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<Strategy | null>(null);
  const [editorText, setEditorText] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    const rows = await apiGet<Strategy[]>("/api/strategies");
    setStrategies(rows);
    if (!selected) return;
    const updated = rows.find((row) => row.id === selected.id);
    if (updated) {
      setSelected(updated);
      setEditorText(toYaml(updated.params));
    }
  }, [selected]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pick = (strategy: Strategy) => {
    setSelected(strategy);
    setEditorText(toYaml(strategy.params));
    setError("");
  };

  const runAction = async (id: string, action: "enable" | "disable" | "set-primary" | "duplicate") => {
    await apiPost(`/api/strategies/${id}/${action}`);
    await refresh();
  };

  const saveParams = async () => {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const parsed = parseYaml(editorText);
      await apiPost(`/api/strategies/${selected.id}/params`, { params: parsed });
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Invalid params format";
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const diff = useMemo(() => {
    if (!selected) return [];
    const before = toYaml(selected.params).split("\n");
    const after = editorText.split("\n");
    const max = Math.max(before.length, after.length);
    const rows: Array<{ before: string; after: string; changed: boolean }> = [];
    for (let i = 0; i < max; i += 1) {
      rows.push({
        before: before[i] || "",
        after: after[i] || "",
        changed: (before[i] || "") !== (after[i] || ""),
      });
    }
    return rows;
  }, [selected, editorText]);

  return (
    <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
      <Card>
        <CardTitle>Strategy Registry</CardTitle>
        <CardDescription>Enable/disable, set primary, duplicate and inspect active versions.</CardDescription>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Version</TH>
                <TH>Status</TH>
                <TH>Primary</TH>
                <TH>Notes</TH>
                <TH>Actions</TH>
              </TR>
            </THead>
            <TBody>
              {strategies.map((row) => (
                <TR key={row.id}>
                  <TD>
                    <button className="font-semibold text-cyan-300 hover:underline" onClick={() => pick(row)}>
                      {row.name}
                    </button>
                  </TD>
                  <TD>{row.version}</TD>
                  <TD>{row.enabled ? <Badge variant="success">enabled</Badge> : <Badge variant="neutral">disabled</Badge>}</TD>
                  <TD>{row.primary ? <Badge variant="info">primary</Badge> : "-"}</TD>
                  <TD className="max-w-[220px] truncate text-slate-300">{row.notes}</TD>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={role !== "admin"}
                        onClick={() => runAction(row.id, row.enabled ? "disable" : "enable")}
                      >
                        {row.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button size="sm" variant="outline" disabled={role !== "admin"} onClick={() => runAction(row.id, "set-primary")}>
                        Set Primary
                      </Button>
                      <Button size="sm" variant="ghost" disabled={role !== "admin"} onClick={() => runAction(row.id, "duplicate")}>
                        Duplicate
                      </Button>
                      <Link href={`/strategies/${row.id}`} className="inline-flex items-center rounded-lg px-2 text-xs text-cyan-300 underline">
                        Detail
                      </Link>
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Params YAML Editor</CardTitle>
        <CardDescription>Edit strategy params with validation and preview diff.</CardDescription>
        <CardContent className="space-y-3">
          {selected ? (
            <>
              <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2 text-xs text-slate-300">
                Editing: <strong>{selected.name}</strong> {selected.version}
              </div>
              <Textarea value={editorText} onChange={(e) => setEditorText(e.target.value)} className="min-h-[220px] font-mono text-xs" />
              {error ? <p className="text-sm text-rose-300">{error}</p> : null}
              <Button disabled={role !== "admin" || saving} onClick={saveParams}>
                {saving ? "Saving..." : "Save Params"}
              </Button>
              <div className="space-y-1 rounded-lg border border-slate-800 bg-slate-900/50 p-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Preview Diff</p>
                <div className="max-h-40 overflow-auto text-xs font-mono">
                  {diff.map((row, idx) => (
                    <div key={`${row.before}-${row.after}-${idx}`} className={row.changed ? "bg-amber-500/10 text-amber-200" : "text-slate-400"}>
                      - {row.before || " "}
                      <br />+ {row.after || " "}
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-400">Select a strategy from the registry to edit its params.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
