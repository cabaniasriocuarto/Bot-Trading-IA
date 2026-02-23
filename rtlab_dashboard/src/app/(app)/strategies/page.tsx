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
import { apiGet, apiPatch, apiPost } from "@/lib/client-api";
import type { BacktestRun, Strategy, StrategyKpis, StrategyKpisByRegimeResponse, StrategyKpisRow, TradingMode } from "@/lib/types";
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
  const [strategyKpisRows, setStrategyKpisRows] = useState<StrategyKpisRow[]>([]);
  const [selected, setSelected] = useState<Strategy | null>(null);
  const [selectedKpis, setSelectedKpis] = useState<StrategyKpis | null>(null);
  const [selectedRegimeKpis, setSelectedRegimeKpis] = useState<StrategyKpisByRegimeResponse | null>(null);
  const [kpiMode, setKpiMode] = useState<"backtest" | "paper" | "testnet" | "live">("backtest");
  const [kpiFrom, setKpiFrom] = useState("2024-01-01");
  const [kpiTo, setKpiTo] = useState("2026-12-31");
  const [editorText, setEditorText] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");

  const refresh = useCallback(async () => {
    const params = new URLSearchParams({ mode: kpiMode, from: kpiFrom, to: kpiTo });
    const [rows, bt, kpiTable] = await Promise.all([
      apiGet<Strategy[]>("/api/v1/strategies"),
      apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
      apiGet<{ items: StrategyKpisRow[] }>(`/api/v1/strategies/kpis?${params.toString()}`),
    ]);
    setStrategies(rows);
    setBacktests(bt);
    setStrategyKpisRows(kpiTable.items || []);
    if (!selected) return;
    const updated = rows.find((row) => row.id === selected.id);
    if (updated) {
      setSelected(updated);
      setEditorText(toYaml(updated.params));
    }
  }, [selected, kpiMode, kpiFrom, kpiTo]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selected) {
      setSelectedKpis(null);
      setSelectedRegimeKpis(null);
      return;
    }
    const params = new URLSearchParams({ mode: kpiMode, from: kpiFrom, to: kpiTo });
    void Promise.all([
      apiGet<{ kpis: StrategyKpis }>(`/api/v1/strategies/${selected.id}/kpis?${params.toString()}`),
      apiGet<StrategyKpisByRegimeResponse>(`/api/v1/strategies/${selected.id}/kpis_by_regime?${params.toString()}`),
    ])
      .then(([kpisRes, regimeRes]) => {
        setSelectedKpis(kpisRes.kpis);
        setSelectedRegimeKpis(regimeRes);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "No se pudieron cargar KPIs.");
      });
  }, [selected, kpiMode, kpiFrom, kpiTo]);

  const pick = (strategy: Strategy) => {
    setSelected(strategy);
    setEditorText(toYaml(strategy.params));
    setError("");
  };

  const runAction = async (id: string, action: "enable" | "disable" | "duplicate") => {
    setError("");
    try {
      await apiPost(`/api/v1/strategies/${id}/${action}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo ejecutar la accion.");
    }
  };

  const patchStrategy = async (id: string, patch: { enabled_for_trading?: boolean; allow_learning?: boolean; is_primary?: boolean; status?: "active" | "disabled" | "archived" }) => {
    setError("");
    try {
      await apiPatch(`/api/v1/strategies/${id}`, patch);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la estrategia.");
    }
  };

  const setPrimary = async (id: string, mode: TradingMode) => {
    setError("");
    try {
      await apiPost(`/api/v1/strategies/${id}/primary`, { mode: mode.toLowerCase() });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo definir la estrategia primaria.");
    }
  };

  const saveParams = async () => {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const parsed = parseYaml(editorText);
      const res = await fetch(`/api/v1/strategies/${selected.id}/params`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params: parsed }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string; detail?: string };
        throw new Error(body.error || body.detail || "No se pudo guardar parametros.");
      }
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

  const kpiByStrategyId = useMemo(() => {
    const map = new Map<string, StrategyKpisRow>();
    for (const row of strategyKpisRows) map.set(row.strategy_id, row);
    return map;
  }, [strategyKpisRows]);

  const regimeRows = useMemo(() => {
    if (!selectedRegimeKpis?.regimes) return [];
    return ["trend", "range", "high_vol", "toxic"]
      .filter((key) => selectedRegimeKpis.regimes[key])
      .map((key) => selectedRegimeKpis.regimes[key]);
  }, [selectedRegimeKpis]);

  return (
    <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
      <Card>
        <CardTitle>Registro de Estrategias</CardTitle>
        <CardDescription>Knowledge Pack + importadas. Tildá Trading / Aprendizaje / Principal y revisá KPIs por período y régimen.</CardDescription>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Importar Estrategia (ZIP o YAML)</p>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="file"
                accept=".zip,.yaml,.yml"
                disabled={role !== "admin" || uploading}
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              />
              <Button onClick={uploadStrategy} disabled={role !== "admin" || uploading || !uploadFile}>
                {uploading ? "Importando..." : "Importar estrategia"}
              </Button>
            </div>
            {uploadMsg ? <p className="mt-2 text-xs text-emerald-300">{uploadMsg}</p> : null}
            {error ? <p className="mt-2 text-xs text-rose-300">{error}</p> : null}
          </div>

          <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/50 p-3 md:grid-cols-4">
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Modo KPIs</p>
              <select
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                value={kpiMode}
                onChange={(e) => setKpiMode(e.target.value as "backtest" | "paper" | "testnet" | "live")}
              >
                <option value="backtest">Backtest</option>
                <option value="paper">Paper</option>
                <option value="testnet">Testnet</option>
                <option value="live">Live</option>
              </select>
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Desde</p>
              <Input type="date" value={kpiFrom} onChange={(e) => setKpiFrom(e.target.value)} />
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Hasta</p>
              <Input type="date" value={kpiTo} onChange={(e) => setKpiTo(e.target.value)} />
            </div>
            <div className="flex items-end">
              <Button variant="outline" onClick={() => void refresh()} className="w-full">
                Actualizar KPIs
              </Button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Nombre</TH>
                  <TH>ID</TH>
                  <TH>Versión</TH>
                  <TH>Origen</TH>
                  <TH>Estado</TH>
                  <TH>✅ Trading</TH>
                  <TH>🧠 Aprendizaje</TH>
                  <TH>⭐ Principal</TH>
                  <TH>Primaria por modo</TH>
                  <TH>Último backtest</TH>
                  <TH>Winrate / Trades</TH>
                  <TH>Expectancy</TH>
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
                    <TD className="text-xs text-slate-300">{row.id}</TD>
                    <TD>{row.version}</TD>
                    <TD><Badge variant={row.source === "knowledge" ? "info" : "neutral"}>{row.source || "uploaded"}</Badge></TD>
                    <TD>
                      <Badge variant={row.status === "active" ? "success" : row.status === "archived" ? "warn" : "neutral"}>
                        {row.status || (row.enabled ? "active" : "disabled")}
                      </Badge>
                    </TD>
                    <TD>
                      <input
                        type="checkbox"
                        checked={Boolean(row.enabled_for_trading ?? row.enabled)}
                        disabled={role !== "admin" || row.status === "archived"}
                        onChange={(e) => void patchStrategy(row.id, { enabled_for_trading: e.target.checked, status: e.target.checked ? "active" : "disabled" })}
                      />
                    </TD>
                    <TD>
                      <input
                        type="checkbox"
                        checked={Boolean(row.allow_learning ?? true)}
                        disabled={role !== "admin" || row.status === "archived"}
                        onChange={(e) => void patchStrategy(row.id, { allow_learning: e.target.checked })}
                      />
                    </TD>
                    <TD>
                      <button
                        type="button"
                        className={`rounded px-2 py-1 text-xs ${row.is_primary ? "bg-amber-500/20 text-amber-200" : "bg-slate-800 text-slate-300"}`}
                        disabled={role !== "admin" || row.status === "archived"}
                        onClick={() => void patchStrategy(row.id, { is_primary: true, enabled_for_trading: true, status: "active" })}
                      >
                        {row.is_primary ? "Principal" : "Marcar"}
                      </button>
                    </TD>
                    <TD>
                      {row.primary_for_modes?.length ? (
                        <span className="text-xs text-slate-200">{row.primary_for_modes.join(" / ").toUpperCase()}</span>
                      ) : (
                        "-"
                      )}
                    </TD>
                    <TD>{row.last_run_at ? new Date(row.last_run_at).toLocaleString() : "sin corridas"}</TD>
                    <TD>
                      {kpiByStrategyId.get(row.id) ? (
                        <span className="text-xs text-slate-200">
                          {fmtPct(kpiByStrategyId.get(row.id)!.kpis.winrate)} / {kpiByStrategyId.get(row.id)!.kpis.trade_count}
                        </span>
                      ) : latestBacktestByStrategy.get(row.id) ? (
                        <span className="text-xs text-slate-200">
                          Sharpe {fmtNum(latestBacktestByStrategy.get(row.id)!.metrics.sharpe)} / Robust {fmtNum(latestBacktestByStrategy.get(row.id)!.metrics.robust_score)}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">N/A</span>
                      )}
                    </TD>
                    <TD>
                      {kpiByStrategyId.get(row.id) ? (
                        <span className="text-xs text-slate-200">
                          {fmtNum(kpiByStrategyId.get(row.id)!.kpis.expectancy_value)} {kpiByStrategyId.get(row.id)!.kpis.expectancy_unit}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">N/A</span>
                      )}
                    </TD>
                    <TD className="max-w-[220px] truncate text-slate-300">{row.notes}</TD>
                    <TD>
                      <div className="flex flex-wrap gap-1">
                        <Button size="sm" variant="outline" onClick={() => pick(row)}>
                          Ver KPIs
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => pick(row)}>
                          Régimen
                        </Button>
                        <Button size="sm" variant="secondary" disabled={role !== "admin"} onClick={() => runAction(row.id, row.enabled ? "disable" : "enable")}>
                          {row.enabled ? "Deshabilitar" : "Habilitar"}
                        </Button>
                        <Button size="sm" variant="outline" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "PAPER")}>
                          Primaria PAPER
                        </Button>
                        <Button size="sm" variant="outline" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "TESTNET")}>
                          Primaria TESTNET
                        </Button>
                        <Button size="sm" variant="outline" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "LIVE")}>
                          Primaria LIVE
                        </Button>
                        <Button size="sm" variant="ghost" disabled={role !== "admin"} onClick={() => runAction(row.id, "duplicate")}>
                          Duplicar
                        </Button>
                        <Button size="sm" variant="outline" disabled={role !== "admin" || row.status === "archived"} onClick={() => void patchStrategy(row.id, { status: "archived" })}>
                          Archivar
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

          {selected && selectedKpis ? (
            <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">KPIs de Estrategia ({kpiMode.toUpperCase()})</p>
                <Badge variant={selectedKpis.dataset_hash_warning ? "warn" : "success"}>
                  {selectedKpis.dataset_hash_warning ? "datasets distintos" : "dataset consistente"}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded border border-slate-800 p-2">Winrate: <strong>{fmtPct(selectedKpis.winrate)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Trades: <strong>{selectedKpis.trade_count}</strong></div>
                <div className="rounded border border-slate-800 p-2">Expectancy: <strong>{fmtNum(selectedKpis.expectancy_value)} {selectedKpis.expectancy_unit}</strong></div>
                <div className="rounded border border-slate-800 p-2">Avg trade: <strong>{fmtNum(selectedKpis.avg_trade)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Max DD: <strong>{fmtPct(selectedKpis.max_dd)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Sharpe/Sortino/Calmar: <strong>{fmtNum(selectedKpis.sharpe)} / {fmtNum(selectedKpis.sortino)} / {fmtNum(selectedKpis.calmar)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Net PnL: <strong>{fmtNum(selectedKpis.net_pnl)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Costos totales: <strong>{fmtNum(selectedKpis.costs_total)}</strong> ({fmtPct(selectedKpis.costs_ratio)})</div>
                <div className="rounded border border-slate-800 p-2">Fees/Spread/Slippage/Funding: <strong>{fmtNum(selectedKpis.fees_total)} / {fmtNum(selectedKpis.spread_total)} / {fmtNum(selectedKpis.slippage_total)} / {fmtNum(selectedKpis.funding_total)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Holding/Market/Turnover: <strong>{fmtNum(selectedKpis.avg_holding_time)}m / {fmtPct(selectedKpis.time_in_market)} / {fmtNum(selectedKpis.turnover)}</strong></div>
                <div className="rounded border border-slate-800 p-2">MFE/MAE: <strong>{selectedKpis.mfe_avg == null ? "N/A" : fmtNum(selectedKpis.mfe_avg)} / {selectedKpis.mae_avg == null ? "N/A" : fmtNum(selectedKpis.mae_avg)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Slippage p95 / Fill / Maker: <strong>{selectedKpis.slippage_p95_bps == null ? "N/A" : `${fmtNum(selectedKpis.slippage_p95_bps)} bps`} / {selectedKpis.fill_ratio == null ? "N/A" : fmtPct(selectedKpis.fill_ratio)} / {selectedKpis.maker_ratio == null ? "N/A" : fmtPct(selectedKpis.maker_ratio)}</strong></div>
              </div>
              {selectedKpis.dataset_hashes?.length ? (
                <div className="rounded border border-slate-800 p-2 text-[11px] text-slate-300">
                  dataset_hash: {selectedKpis.dataset_hashes.join(", ")}
                </div>
              ) : null}
            </div>
          ) : null}

          {selected && selectedRegimeKpis ? (
            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">KPIs por Régimen</p>
              <div className="overflow-x-auto">
                <Table>
                  <THead>
                    <TR>
                      <TH>Régimen</TH>
                      <TH>Trades</TH>
                      <TH>Winrate</TH>
                      <TH>Expectancy</TH>
                      <TH>Net PnL</TH>
                      <TH>Costos %</TH>
                      <TH>Sharpe</TH>
                      <TH>Max DD</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {regimeRows.map((regime) => (
                      <TR key={regime.regime_label}>
                        <TD>{regime.regime_label}</TD>
                        <TD>{regime.kpis.trade_count}</TD>
                        <TD>{fmtPct(regime.kpis.winrate)}</TD>
                        <TD>{fmtNum(regime.kpis.expectancy_value)} {regime.kpis.expectancy_unit}</TD>
                        <TD>{fmtNum(regime.kpis.net_pnl)}</TD>
                        <TD>{fmtPct(regime.kpis.costs_ratio)}</TD>
                        <TD>{fmtNum(regime.kpis.sharpe)}</TD>
                        <TD>{fmtPct(regime.kpis.max_dd)}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
              <p className="text-[11px] text-slate-400">
                Fuente de régimen: {selectedRegimeKpis.regime_rule_source || "heurístico"}.
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
