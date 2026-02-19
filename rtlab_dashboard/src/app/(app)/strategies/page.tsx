"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiPost } from "@/lib/client-api";
import type { BacktestRun, Strategy } from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

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
    if (!rawKey || !rawVal) throw new Error(`Linea invalida: ${line}`);
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
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [selected, setSelected] = useState<Strategy | null>(null);
  const [editorText, setEditorText] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");

  const refresh = useCallback(async () => {
    const [rows, bt] = await Promise.all([
      apiGet<Strategy[]>("/api/v1/strategies"),
      apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
    ]);
    setStrategies(rows);
    setBacktests(bt);
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

  const runAction = async (id: string, action: "enable" | "disable" | "primary" | "duplicate") => {
    await apiPost(`/api/v1/strategies/${id}/${action}`);
    await refresh();
  };

  const saveParams = async () => {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const parsed = parseYaml(editorText);
      await fetch(`/api/v1/strategies/${selected.id}/params`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params: parsed }),
      });
      await refresh();
      setUploadMsg("Parametros guardados correctamente.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Formato invalido de parametros";
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const uploadStrategy = async () => {
    if (!uploadFile) return;
    setUploading(true);
    setUploadMsg("");
    setError("");
    try {
      const formData = new FormData();
      formData.set("file", uploadFile);
      const res = await fetch("/api/v1/strategies/upload", {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string; details?: string[]; strategy?: { name?: string } };
      if (!res.ok) {
        setError(body.error || "No se pudo subir la estrategia.");
        if (body.details?.length) {
          setUploadMsg(body.details.join(" | "));
        }
        return;
      }
      setUploadMsg(`Estrategia subida: ${body.strategy?.name || uploadFile.name}`);
      setUploadFile(null);
      await refresh();
    } finally {
      setUploading(false);
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

  const latestBacktestByStrategy = useMemo(() => {
    const map = new Map<string, BacktestRun>();
    [...backtests]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .forEach((run) => {
        if (!map.has(run.strategy_id)) {
          map.set(run.strategy_id, run);
        }
      });
    return map;
  }, [backtests]);

  return (
    <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
      <Card>
        <CardTitle>Registro de Estrategias</CardTitle>
        <CardDescription>Subir, habilitar, versionar, setear primaria y editar parametros.</CardDescription>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Subir Estrategia (Strategy Pack ZIP)</p>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="file"
                accept=".zip"
                disabled={role !== "admin" || uploading}
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              />
              <Button onClick={uploadStrategy} disabled={role !== "admin" || uploading || !uploadFile}>
                {uploading ? "Subiendo..." : "Subir Estrategia"}
              </Button>
            </div>
            {uploadMsg ? <p className="mt-2 text-xs text-emerald-300">{uploadMsg}</p> : null}
            {error ? <p className="mt-2 text-xs text-rose-300">{error}</p> : null}
          </div>

          <div className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Nombre</TH>
                  <TH>Version</TH>
                  <TH>Estado</TH>
                  <TH>Primaria</TH>
                  <TH>Ultima corrida</TH>
                  <TH>Ultimo OOS</TH>
                  <TH>Notas</TH>
                  <TH>Acciones</TH>
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
                    <TD>{row.enabled ? <Badge variant="success">habilitada</Badge> : <Badge variant="neutral">deshabilitada</Badge>}</TD>
                    <TD>{row.primary ? <Badge variant="info">primaria</Badge> : "-"}</TD>
                    <TD>{row.last_run_at ? new Date(row.last_run_at).toLocaleString() : "sin corridas"}</TD>
                    <TD>
                      {latestBacktestByStrategy.get(row.id) ? (
                        <span className="text-xs text-slate-200">
                          Sharpe {fmtNum(latestBacktestByStrategy.get(row.id)!.metrics.sharpe)} / Robust {fmtNum(latestBacktestByStrategy.get(row.id)!.metrics.robust_score)}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">N/A</span>
                      )}
                    </TD>
                    <TD className="max-w-[220px] truncate text-slate-300">{row.notes}</TD>
                    <TD>
                      <div className="flex flex-wrap gap-1">
                        <Button size="sm" variant="secondary" disabled={role !== "admin"} onClick={() => runAction(row.id, row.enabled ? "disable" : "enable")}>
                          {row.enabled ? "Deshabilitar" : "Habilitar"}
                        </Button>
                        <Button size="sm" variant="outline" disabled={role !== "admin"} onClick={() => runAction(row.id, "primary")}>
                          Set Primaria
                        </Button>
                        <Button size="sm" variant="ghost" disabled={role !== "admin"} onClick={() => runAction(row.id, "duplicate")}>
                          Duplicar
                        </Button>
                        <Link href={`/strategies/${row.id}`} className="inline-flex items-center rounded-lg px-2 text-xs text-cyan-300 underline">
                          Detalle
                        </Link>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Editor YAML de Parametros</CardTitle>
        <CardDescription>Edita params con validacion y vista de diff.</CardDescription>
        <CardContent className="space-y-3">
          {selected ? (
            <>
              <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2 text-xs text-slate-300">
                Editando: <strong>{selected.name}</strong> v{selected.version}
              </div>
              <Textarea value={editorText} onChange={(e) => setEditorText(e.target.value)} className="min-h-[230px] font-mono text-xs" />
              {error ? <p className="text-sm text-rose-300">{error}</p> : null}
              <Button disabled={role !== "admin" || saving} onClick={saveParams}>
                {saving ? "Guardando..." : "Guardar Parametros"}
              </Button>
              <div className="space-y-1 rounded-lg border border-slate-800 bg-slate-900/50 p-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Vista de Diff</p>
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
            <p className="text-sm text-slate-400">Selecciona una estrategia del registro para editar sus parametros.</p>
          )}

          {selected && latestBacktestByStrategy.get(selected.id) ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-xs text-slate-300">
              Ultimo MaxDD: {fmtPct(latestBacktestByStrategy.get(selected.id)!.metrics.max_dd)} | Winrate: {fmtPct(latestBacktestByStrategy.get(selected.id)!.metrics.winrate)}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
