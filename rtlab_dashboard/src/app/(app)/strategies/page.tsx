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
import type { BacktestRun, BotInstance, Strategy, StrategyKpis, StrategyKpisByRegimeResponse, StrategyKpisRow, TradingMode } from "@/lib/types";
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

type LearningStatusLite = {
  enabled?: boolean;
  mode?: string;
  regime?: string;
  selector_algo?: string;
  learning_pool?: {
    count?: number;
    strategy_ids?: string[];
    empty_block_recommend?: boolean;
  };
  warnings?: string[];
  selector?: {
    active_strategy_id?: string;
    reason?: string;
    explanation?: string;
    why?: string;
  };
};

type LearningRecommendationLite = {
  id: string;
  status?: string;
  mode?: string;
  active_strategy_id?: string;
  created_at?: string;
  reviewed_at?: string;
  note?: string;
  ranking?: Array<{
    strategy_id: string;
    name?: string;
    winrate?: number;
    trade_count?: number;
    expectancy?: number;
    expectancy_unit?: string;
    sharpe?: number;
    sortino?: number;
    calmar?: number;
    reward?: number;
  }>;
  weights_sugeridos?: Record<string, number>;
  recommendation_source?: "runtime" | "research" | string;
};

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
  const [learningStatus, setLearningStatus] = useState<LearningStatusLite | null>(null);
  const [learningRecommendations, setLearningRecommendations] = useState<LearningRecommendationLite[]>([]);
  const [bots, setBots] = useState<BotInstance[]>([]);
  const [learningBusy, setLearningBusy] = useState(false);
  const [learningActionBusyId, setLearningActionBusyId] = useState<string | null>(null);
  const [botCreateBusy, setBotCreateBusy] = useState(false);
  const [botActionBusyId, setBotActionBusyId] = useState<string | null>(null);
  const [strategySearch, setStrategySearch] = useState("");
  const [strategyStatusFilter, setStrategyStatusFilter] = useState<"all" | "active" | "disabled" | "archived">("all");
  const [strategySourceFilter, setStrategySourceFilter] = useState<"all" | "knowledge" | "uploaded">("all");
  const [strategyPage, setStrategyPage] = useState(1);
  const [strategyPageSize, setStrategyPageSize] = useState<"20" | "50" | "100">("20");

  const refresh = useCallback(async () => {
    const params = new URLSearchParams({ mode: kpiMode, from: kpiFrom, to: kpiTo });
    const [rows, bt, kpiTable, learningStatusRes, learningRecsRes, botsRes] = await Promise.all([
      apiGet<Strategy[]>("/api/v1/strategies"),
      apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
      apiGet<{ items: StrategyKpisRow[] }>(`/api/v1/strategies/kpis?${params.toString()}`),
      apiGet<LearningStatusLite>("/api/v1/learning/status").catch(() => null),
      apiGet<LearningRecommendationLite[]>("/api/v1/learning/recommendations").catch(() => []),
      apiGet<{ items: BotInstance[] }>("/api/v1/bots").catch(() => ({ items: [] })),
    ]);
    setStrategies(rows);
    setBacktests(bt);
    setStrategyKpisRows(kpiTable.items || []);
    setLearningStatus(learningStatusRes);
    setLearningRecommendations(Array.isArray(learningRecsRes) ? learningRecsRes : []);
    setBots(Array.isArray(botsRes?.items) ? botsRes.items : []);
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

  const strategyRowsFiltered = useMemo(() => {
    const term = strategySearch.trim().toLowerCase();
    const compact = (input: unknown) => String(input || "").replace(/\s+/g, " ").trim();
    const rows = strategies.filter((row) => {
      const status = String(row.status || (row.enabled ? "active" : "disabled")).toLowerCase();
      if (strategyStatusFilter !== "all" && status !== strategyStatusFilter) return false;
      const source = String(row.source || "uploaded").toLowerCase();
      if (strategySourceFilter !== "all" && source !== strategySourceFilter) return false;
      if (!term) return true;
      const searchable = [
        compact(row.name),
        row.id,
        row.version,
        row.notes || "",
        ...(row.tags || []),
      ]
        .join(" ")
        .toLowerCase();
      return searchable.includes(term);
    });
    rows.sort((a, b) => {
      const kpiA = kpiByStrategyId.get(a.id)?.kpis;
      const kpiB = kpiByStrategyId.get(b.id)?.kpis;
      const winA = Number(kpiA?.winrate || -1);
      const winB = Number(kpiB?.winrate || -1);
      if (winA !== winB) return winB - winA;
      const tradesA = Number(kpiA?.trade_count || 0);
      const tradesB = Number(kpiB?.trade_count || 0);
      if (tradesA !== tradesB) return tradesB - tradesA;
      return compact(a.name).localeCompare(compact(b.name));
    });
    return rows;
  }, [strategies, strategySearch, strategyStatusFilter, strategySourceFilter, kpiByStrategyId]);

  const strategyPageSizeNum = Number(strategyPageSize);
  const strategyTotalPages = Math.max(1, Math.ceil(strategyRowsFiltered.length / strategyPageSizeNum));
  const strategySafePage = Math.min(Math.max(strategyPage, 1), strategyTotalPages);
  const strategyRowsPage = useMemo(() => {
    const start = (strategySafePage - 1) * strategyPageSizeNum;
    return strategyRowsFiltered.slice(start, start + strategyPageSizeNum);
  }, [strategyRowsFiltered, strategySafePage, strategyPageSizeNum]);

  useEffect(() => {
    setStrategyPage(1);
  }, [strategySearch, strategyStatusFilter, strategySourceFilter, strategyPageSize]);

  const regimeRows = useMemo(() => {
    if (!selectedRegimeKpis?.regimes) return [];
    return ["trend", "range", "high_vol", "toxic"]
      .filter((key) => selectedRegimeKpis.regimes[key])
      .map((key) => selectedRegimeKpis.regimes[key]);
  }, [selectedRegimeKpis]);

  const learningPoolStrategies = useMemo(
    () => strategies.filter((row) => Boolean(row.allow_learning ?? true) && row.status !== "archived"),
    [strategies],
  );

  const myPickedStrategies = useMemo(
    () =>
      strategies.filter(
        (row) =>
          row.status !== "archived" &&
          (Boolean(row.is_primary) || Boolean(row.enabled_for_trading ?? row.enabled) || Boolean(row.allow_learning ?? true)),
      ),
    [strategies],
  );

  const learningPoolSummary = useMemo(() => {
    const rows = learningPoolStrategies.map((s) => kpiByStrategyId.get(s.id)).filter(Boolean) as StrategyKpisRow[];
    const tradesTotal = rows.reduce((acc, r) => acc + Number(r.kpis.trade_count || 0), 0);
    const weightedWins = rows.reduce((acc, r) => acc + Number(r.kpis.winrate || 0) * Number(r.kpis.trade_count || 0), 0);
    const netPnl = rows.reduce((acc, r) => acc + Number(r.kpis.net_pnl || 0), 0);
    const avgSharpe = rows.length ? rows.reduce((acc, r) => acc + Number(r.kpis.sharpe || 0), 0) / rows.length : 0;
    return {
      poolCount: learningPoolStrategies.length,
      tradesTotal,
      winrateWeighted: tradesTotal ? weightedWins / tradesTotal : 0,
      netPnl,
      avgSharpe,
      recommendationCount: learningRecommendations.length,
      pendingCount: learningRecommendations.filter((r) => String(r.status || "").toUpperCase().includes("PENDING")).length,
    };
  }, [learningPoolStrategies, kpiByStrategyId, learningRecommendations]);

  const botSuggestions = useMemo(
    () =>
      learningRecommendations
        .filter((row) => row.active_strategy_id)
        .slice(0, 8),
    [learningRecommendations],
  );

  const requestLearningRecommendation = async () => {
    setLearningBusy(true);
    setError("");
    try {
      const modeForLearning = kpiMode === "backtest" ? "paper" : kpiMode;
      await apiPost("/api/v1/learning/recommend", { mode: modeForLearning });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo generar recomendacion.");
    } finally {
      setLearningBusy(false);
    }
  };

  const reviewLearningRecommendation = async (recommendationId: string, action: "approve" | "reject") => {
    setLearningActionBusyId(recommendationId);
    setError("");
    try {
      await apiPost(`/api/v1/learning/${action}`, {
        recommendation_id: recommendationId,
        note: action === "approve" ? "Aprobado desde panel AutoBot" : "Rechazado desde panel AutoBot",
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `No se pudo ${action === "approve" ? "aprobar" : "rechazar"} la recomendacion.`);
    } finally {
      setLearningActionBusyId(null);
    }
  };

  const createBotFromCurrentPool = async () => {
    setBotCreateBusy(true);
    setError("");
    try {
      await apiPost("/api/v1/bots", {
        name: `AutoBot ${bots.length + 1}`,
        engine: learningStatus?.selector_algo === "ucb1" ? "bandit_ucb1" : learningStatus?.selector_algo === "regime_rules" ? "fixed_rules" : "bandit_thompson",
        mode: "paper",
        status: "active",
        pool_strategy_ids: learningPoolStrategies.map((row) => row.id),
        universe: ["BTCUSDT", "ETHUSDT"],
        notes: "Creado desde panel Estrategias (pool actual de aprendizaje).",
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear el bot.");
    } finally {
      setBotCreateBusy(false);
    }
  };

  const patchBot = async (botId: string, patch: Record<string, unknown>) => {
    setBotActionBusyId(botId);
    setError("");
    try {
      await apiPatch(`/api/v1/bots/${botId}`, patch);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar el bot.");
    } finally {
      setBotActionBusyId(null);
    }
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
      <Card>
        <CardTitle>Registro de Estrategias</CardTitle>
        <CardDescription>Knowledge Pack + importadas. TildÃ¡ Trading / Aprendizaje / Principal y revisÃ¡ KPIs por perÃ­odo y rÃ©gimen.</CardDescription>
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

          <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/40 p-3 md:grid-cols-5">
            <div className="md:col-span-2">
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Buscar estrategia</p>
              <Input
                value={strategySearch}
                onChange={(e) => setStrategySearch(e.target.value)}
                placeholder="ID, nombre, versiÃ³n, tag o nota"
              />
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Estado</p>
              <select
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                value={strategyStatusFilter}
                onChange={(e) => setStrategyStatusFilter(e.target.value as "all" | "active" | "disabled" | "archived")}
              >
                <option value="all">Todos</option>
                <option value="active">Activas</option>
                <option value="disabled">Deshabilitadas</option>
                <option value="archived">Archivadas</option>
              </select>
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Origen</p>
              <select
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                value={strategySourceFilter}
                onChange={(e) => setStrategySourceFilter(e.target.value as "all" | "knowledge" | "uploaded")}
              >
                <option value="all">Todos</option>
                <option value="knowledge">Knowledge Pack</option>
                <option value="uploaded">Importadas</option>
              </select>
            </div>
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Filas</p>
              <select
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                value={strategyPageSize}
                onChange={(e) => setStrategyPageSize(e.target.value as "20" | "50" | "100")}
              >
                <option value="20">20</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </div>
            <div className="md:col-span-5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
              <span>
                Mostrando {(strategyRowsFiltered.length ? (strategySafePage - 1) * strategyPageSizeNum + 1 : 0)}-
                {Math.min(strategyRowsFiltered.length, strategySafePage * strategyPageSizeNum)} de {strategyRowsFiltered.length} estrategias
              </span>
              <div className="flex items-center gap-1">
                <Button variant="outline" className="h-7 px-2 text-[11px]" disabled={strategySafePage <= 1} onClick={() => setStrategyPage((p) => Math.max(1, p - 1))}>
                  Anterior
                </Button>
                <span className="text-slate-300">PÃ¡g. {strategySafePage}/{strategyTotalPages}</span>
                <Button variant="outline" className="h-7 px-2 text-[11px]" disabled={strategySafePage >= strategyTotalPages} onClick={() => setStrategyPage((p) => Math.min(strategyTotalPages, p + 1))}>
                  Siguiente
                </Button>
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table className="text-xs">
              <THead>
                <TR>
                  <TH>Nombre</TH>
                  <TH>ID</TH>
                  <TH>VersiÃ³n</TH>
                  <TH>Origen</TH>
                  <TH>Estado</TH>
                  <TH>âœ… Trading</TH>
                  <TH>ðŸ§  Aprendizaje</TH>
                  <TH>â­ Principal</TH>
                  <TH>Primaria por modo</TH>
                  <TH>Ãšltimo backtest</TH>
                  <TH>Winrate / Trades</TH>
                  <TH>Expectancy</TH>
                  <TH>Notas</TH>
                  <TH>Acciones</TH>
                </TR>
              </THead>
              <TBody>
                {strategyRowsPage.map((row) => {
                  const compactName = String(row.name || "").replace(/\s+/g, " ").trim();
                  const compactNotes = String(row.notes || "").replace(/\s+/g, " ").trim();
                  return (
                  <TR key={row.id} className="align-middle text-[11px] [&>td]:py-1.5">
                    <TD className="max-w-[180px]">
                      <button className="block max-w-[170px] truncate text-left font-semibold text-cyan-300 hover:underline" title={compactName} onClick={() => pick(row)}>
                        {compactName || row.id}
                      </button>
                    </TD>
                    <TD className="max-w-[160px] truncate text-xs text-slate-300" title={row.id}>{row.id}</TD>
                    <TD className="whitespace-nowrap">{row.version}</TD>
                    <TD className="whitespace-nowrap"><Badge variant={row.source === "knowledge" ? "info" : "neutral"}>{row.source || "uploaded"}</Badge></TD>
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
                        <span className="text-[11px] text-slate-200 whitespace-nowrap">{row.primary_for_modes.join(" / ").toUpperCase()}</span>
                      ) : (
                        "-"
                      )}
                    </TD>
                    <TD className="whitespace-nowrap">{row.last_run_at ? new Date(row.last_run_at).toLocaleString() : "sin corridas"}</TD>
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
                        <span className="text-[11px] text-slate-200">
                          {fmtNum(kpiByStrategyId.get(row.id)!.kpis.expectancy_value)} {kpiByStrategyId.get(row.id)!.kpis.expectancy_unit}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">N/A</span>
                      )}
                    </TD>
                    <TD className="max-w-[160px] truncate text-slate-300" title={compactNotes}>{compactNotes || "-"}</TD>
                    <TD className="min-w-[190px]">
                      <div className="flex flex-wrap items-center gap-1">
                        <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]" onClick={() => pick(row)}>
                          Seleccionar
                        </Button>
                        <Button size="sm" variant="outline" className="hidden h-6 px-2 text-[11px]" onClick={() => pick(row)}>
                          RÃ©gimen
                        </Button>
                        <Button size="sm" variant="secondary" className="hidden" disabled={role !== "admin"} onClick={() => runAction(row.id, row.enabled ? "disable" : "enable")}>
                          {row.enabled ? "Deshabilitar" : "Habilitar"}
                        </Button>
                        <Button size="sm" variant="outline" className="hidden" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "PAPER")}>
                          Primaria PAPER
                        </Button>
                        <Button size="sm" variant="outline" className="hidden" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "TESTNET")}>
                          Primaria TESTNET
                        </Button>
                        <Button size="sm" variant="outline" className="hidden" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "LIVE")}>
                          Primaria LIVE
                        </Button>
                        <Button size="sm" variant="ghost" className="hidden" disabled={role !== "admin"} onClick={() => runAction(row.id, "duplicate")}>
                          Duplicar
                        </Button>
                        <Button size="sm" variant="outline" className="hidden" disabled={role !== "admin" || row.status === "archived"} onClick={() => void patchStrategy(row.id, { status: "archived" })}>
                          Archivar
                        </Button>
                        <details className="rounded border border-slate-700 bg-slate-950/70 px-2 py-0.5 text-[11px] text-slate-200">
                          <summary className="cursor-pointer select-none leading-6">MÃ¡s</summary>
                          <div className="mt-2 grid min-w-[170px] gap-1">
                            <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin"} onClick={() => runAction(row.id, row.enabled ? "disable" : "enable")}>
                              {row.enabled ? "Deshabilitar" : "Habilitar"}
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "PAPER")}>
                              Primaria PAPER
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "TESTNET")}>
                              Primaria TESTNET
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin"} onClick={() => setPrimary(row.id, "LIVE")}>
                              Primaria LIVE
                            </Button>
                            <Button size="sm" variant="ghost" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin"} onClick={() => runAction(row.id, "duplicate")}>
                              Duplicar
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || row.status === "archived"} onClick={() => void patchStrategy(row.id, { status: "archived" })}>
                              Archivar
                            </Button>
                          </div>
                        </details>
                        <Link href={`/strategies/${row.id}`} className="inline-flex h-6 items-center rounded-lg px-2 text-[11px] text-cyan-300 underline">
                          Detalle
                        </Link>
                      </div>
                    </TD>
                  </TR>
                );
                })}
                {!strategyRowsPage.length ? (
                  <TR>
                    <TD colSpan={14} className="py-4 text-center text-xs text-slate-400">
                      No hay estrategias para estos filtros. AjustÃ¡ bÃºsqueda/estado/origen.
                    </TD>
                  </TR>
                ) : null}
              </TBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
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
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">KPIs por RÃ©gimen</p>
              <div className="overflow-x-auto">
                <Table>
                  <THead>
                    <TR>
                      <TH>RÃ©gimen</TH>
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
                Fuente de rÃ©gimen: {selectedRegimeKpis.regime_rule_source || "heurÃ­stico"}.
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardTitle>AutoBot / Aprendizaje (OpciÃ³n B)</CardTitle>
        <CardDescription>
          Pool de estrategias para aprendizaje, mÃ©tricas agregadas y sugerencias del bot (requieren aprobaciÃ³n humana).
        </CardDescription>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Bot principal (pool actual)</p>
                <Badge variant={learningStatus?.enabled ? "success" : "warn"}>
                  {learningStatus?.enabled ? `ON Â· ${String(learningStatus?.mode || "OFF").toUpperCase()}` : "OFF"}
                </Badge>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                <div className="rounded border border-slate-800 p-2">Pool: <strong>{learningPoolSummary.poolCount}</strong></div>
                <div className="rounded border border-slate-800 p-2">Trades: <strong>{learningPoolSummary.tradesTotal}</strong></div>
                <div className="rounded border border-slate-800 p-2">WinRate pool: <strong>{fmtPct(learningPoolSummary.winrateWeighted)}</strong></div>
                <div className="rounded border border-slate-800 p-2">PnL neto pool: <strong>{fmtNum(learningPoolSummary.netPnl)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Sharpe prom.: <strong>{fmtNum(learningPoolSummary.avgSharpe)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Recs. pendientes: <strong>{learningPoolSummary.pendingCount}</strong></div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="outline" disabled={learningBusy || !learningStatus?.enabled} onClick={() => void requestLearningRecommendation()}>
                  {learningBusy ? "Generando..." : "Recomendar ahora"}
                </Button>
                <Button variant="outline" onClick={() => void refresh()}>
                  Refrescar
                </Button>
              </div>
              <p className="mt-2 text-[11px] text-slate-400">
                Selector: {learningStatus?.selector_algo || "-"} Â· RÃ©gimen actual: {learningStatus?.regime || "-"}.
                {" "}Las propuestas no aplican LIVE automÃ¡ticamente (OpciÃ³n B).
              </p>
              {learningStatus?.warnings?.length ? (
                <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-200">
                  {learningStatus.warnings.join(" | ")}
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Mis elegidas (pool + principal)</p>
              <div className="mt-2 max-h-56 space-y-2 overflow-auto">
                {myPickedStrategies.length ? (
                  myPickedStrategies.map((row) => {
                    const kpi = kpiByStrategyId.get(row.id)?.kpis;
                    return (
                      <div key={`mine-${row.id}`} className="rounded border border-slate-800 bg-slate-950/50 p-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate font-semibold text-slate-100" title={row.name}>{row.name}</p>
                          <div className="flex items-center gap-1">
                            {row.is_primary ? <Badge variant="warn">Principal</Badge> : null}
                            {row.allow_learning ? <Badge variant="info">Pool</Badge> : null}
                            {row.enabled_for_trading ?? row.enabled ? <Badge variant="success">Trading</Badge> : null}
                          </div>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-400">{row.id} Â· v{row.version}</p>
                        <p className="mt-1 text-[11px] text-slate-300">
                          Trades: <strong>{kpi?.trade_count ?? 0}</strong> Â· WinRate: <strong>{fmtPct(kpi?.winrate ?? 0)}</strong> Â· Sharpe: <strong>{fmtNum(kpi?.sharpe ?? 0)}</strong>
                        </p>
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded border border-slate-800 bg-slate-950/50 p-2 text-xs text-slate-400">
                    No hay estrategias seleccionadas todavÃ­a. MarcÃ¡ Trading / Aprendizaje / Principal en la tabla de la izquierda.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Sugerencias del bot (runtime + research)</p>
              <Badge variant={botSuggestions.length ? "info" : "neutral"}>{botSuggestions.length} visibles</Badge>
            </div>
            <div className="mt-2 space-y-2">
              {botSuggestions.length ? (
                botSuggestions.map((rec) => {
                  const top = rec.ranking?.[0];
                  const topStrategy = strategies.find((s) => s.id === rec.active_strategy_id);
                  const pending = String(rec.status || "").toUpperCase().includes("PENDING");
                  return (
                    <div key={rec.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="font-semibold text-slate-100">
                            {topStrategy?.name || rec.active_strategy_id || "Sin estrategia"}{" "}
                            <span className="text-slate-400">Â· {rec.mode || "-"}</span>
                          </p>
                          <p className="text-[11px] text-slate-400">
                            {rec.id} Â· {rec.recommendation_source || "runtime"} Â· {rec.created_at ? new Date(rec.created_at).toLocaleString() : "sin fecha"}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={pending ? "warn" : String(rec.status || "").toUpperCase().includes("APPROVED") ? "success" : "neutral"}>
                            {rec.status || "PENDING"}
                          </Badge>
                          {pending && role === "admin" ? (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-[11px]"
                                disabled={learningActionBusyId === rec.id}
                                onClick={() => void reviewLearningRecommendation(rec.id, "approve")}
                              >
                                Aprobar
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-[11px]"
                                disabled={learningActionBusyId === rec.id}
                                onClick={() => void reviewLearningRecommendation(rec.id, "reject")}
                              >
                                Rechazar
                              </Button>
                            </>
                          ) : null}
                        </div>
                      </div>
                      <div className="mt-2 grid gap-2 md:grid-cols-4">
                        <div className="rounded border border-slate-800 p-2">Trades: <strong>{top?.trade_count ?? 0}</strong></div>
                        <div className="rounded border border-slate-800 p-2">WinRate: <strong>{fmtPct(top?.winrate ?? 0)}</strong></div>
                        <div className="rounded border border-slate-800 p-2">Sharpe: <strong>{fmtNum(top?.sharpe ?? 0)}</strong></div>
                        <div className="rounded border border-slate-800 p-2">Expectancy: <strong>{fmtNum(top?.expectancy ?? 0)} {top?.expectancy_unit || ""}</strong></div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
                  TodavÃ­a no hay sugerencias del bot. ActivÃ¡ Aprendizaje en Settings y usÃ¡ â€œRecomendar ahoraâ€ para generar propuestas.
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Bots / AutoBots (multi-instancia)</p>
                <p className="text-[11px] text-slate-400">Administra operadores (shadow/paper/testnet/live), engine y pool de estrategias sin tocar LIVE autom&aacute;ticamente.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" onClick={() => void refresh()}>
                  Refrescar bots
                </Button>
                <Button
                  size="sm"
                  className="h-7 px-2 text-[11px]"
                  disabled={role !== "admin" || botCreateBusy}
                  onClick={() => void createBotFromCurrentPool()}
                >
                  {botCreateBusy ? "Creando..." : "Crear bot (pool actual)"}
                </Button>
              </div>
            </div>

            {bots.length ? (
              <div className="mt-3 overflow-x-auto">
                <Table className="text-xs">
                  <THead>
                    <TR>
                      <TH>Bot</TH>
                      <TH>Engine</TH>
                      <TH>Modo</TH>
                      <TH>Estado</TH>
                      <TH>Pool</TH>
                      <TH>Trades</TH>
                      <TH>WinRate</TH>
                      <TH>PnL neto</TH>
                      <TH>Sharpe</TH>
                      <TH>Recs</TH>
                      <TH>Kills</TH>
                      <TH>&Uacute;ltimo run</TH>
                      <TH>Acciones</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {bots.map((bot) => {
                      const m = bot.metrics;
                      const busy = botActionBusyId === bot.id;
                      return (
                        <TR key={bot.id} className="align-top">
                          <TD className="max-w-[180px]">
                            <div className="max-w-[180px]">
                              <p className="truncate font-semibold text-slate-100" title={bot.name}>{bot.name}</p>
                              <p className="truncate text-[11px] text-slate-400" title={bot.id}>{bot.id}</p>
                            </div>
                          </TD>
                          <TD className="whitespace-nowrap">{bot.engine}</TD>
                          <TD className="whitespace-nowrap">
                            <Badge variant={bot.mode === "live" ? "warn" : bot.mode === "testnet" ? "info" : "neutral"}>
                              {bot.mode.toUpperCase()}
                            </Badge>
                          </TD>
                          <TD className="whitespace-nowrap">
                            <Badge variant={bot.status === "active" ? "success" : bot.status === "paused" ? "warn" : "neutral"}>
                              {bot.status}
                            </Badge>
                          </TD>
                          <TD>{m?.strategy_count ?? bot.pool_strategy_ids.length}</TD>
                          <TD>{m?.trade_count ?? 0}</TD>
                          <TD>{fmtPct(m?.winrate ?? 0)}</TD>
                          <TD>{fmtNum(m?.net_pnl ?? 0)}</TD>
                          <TD>{fmtNum(m?.avg_sharpe ?? 0)}</TD>
                          <TD>
                            <span className="text-slate-300">
                              {(m?.recommendations_pending ?? 0)}/{(m?.recommendations_approved ?? 0)}/{(m?.recommendations_rejected ?? 0)}
                            </span>
                            <div className="text-[10px] text-slate-500">pend/apr/rech</div>
                          </TD>
                          <TD>{m?.kills_total ?? 0}</TD>
                          <TD className="whitespace-nowrap text-[11px] text-slate-300">
                            {m?.last_run_at ? new Date(m.last_run_at).toLocaleString() : "sin corridas"}
                          </TD>
                          <TD>
                            <div className="flex flex-wrap gap-1">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-[11px]"
                                disabled={role !== "admin" || busy}
                                onClick={() => void patchBot(bot.id, { status: bot.status === "active" ? "paused" : "active" })}
                              >
                                {bot.status === "active" ? "Pausar" : "Activar"}
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-[11px]"
                                disabled={role !== "admin" || busy}
                                onClick={() => void patchBot(bot.id, { pool_strategy_ids: learningPoolStrategies.map((row) => row.id) })}
                              >
                                Usar pool actual
                              </Button>
                              <details className="rounded border border-slate-700 bg-slate-950/70 px-2 py-0.5 text-[11px] text-slate-200">
                                <summary className="cursor-pointer select-none">M&aacute;s</summary>
                                <div className="mt-2 grid min-w-[170px] gap-1">
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { mode: "shadow" })}>
                                    Modo SHADOW
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { mode: "paper" })}>
                                    Modo PAPER
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { mode: "testnet" })}>
                                    Modo TESTNET
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { mode: "live" })}>
                                    Modo LIVE
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { engine: "fixed_rules" })}>
                                    Engine Reglas fijas
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { engine: "bandit_thompson" })}>
                                    Engine Thompson
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { engine: "bandit_ucb1" })}>
                                    Engine UCB1
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { status: "archived" })}>
                                    Archivar bot
                                  </Button>
                                </div>
                              </details>
                            </div>
                            <details className="mt-1 rounded border border-slate-800 bg-slate-950/30 p-2 text-[11px] text-slate-300">
                              <summary className="cursor-pointer select-none">Pool ({bot.pool_strategies?.length || 0})</summary>
                              <div className="mt-2 space-y-1">
                                {bot.pool_strategies?.length ? (
                                  bot.pool_strategies.map((s) => (
                                    <div key={`${bot.id}-${s.id}`} className="flex items-center justify-between gap-2 rounded border border-slate-800 px-2 py-1">
                                      <span className="truncate" title={s.name}>{s.name}</span>
                                      <div className="flex gap-1">
                                        {s.is_primary ? <Badge variant="warn">Principal</Badge> : null}
                                        {s.allow_learning ? <Badge variant="info">Pool</Badge> : null}
                                        {s.enabled_for_trading ? <Badge variant="success">Trading</Badge> : null}
                                      </div>
                                    </div>
                                  ))
                                ) : (
                                  <p className="text-slate-500">Sin estrategias asignadas.</p>
                                )}
                              </div>
                            </details>
                          </TD>
                        </TR>
                      );
                    })}
                  </TBody>
                </Table>
              </div>
            ) : (
              <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
                Todav&iacute;a no hay bots multi-instancia. Cre&aacute; uno desde el pool actual para operar shadow/paper/testnet con m&eacute;tricas separadas.
              </div>
            )}
          </div>
        </CardContent>
      </Card>
      </div>
    </div>
  );
}

