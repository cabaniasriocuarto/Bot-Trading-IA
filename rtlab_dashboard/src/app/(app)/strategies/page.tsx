"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiDelete, apiGet, apiPatch, apiPost } from "@/lib/client-api";
import type {
  BacktestRun,
  BotInstance,
  LearningExperienceSummaryResponse,
  LearningGuidanceRow,
  LearningProposal,
  ShadowStatusResponse,
  Strategy,
  StrategyKpis,
  StrategyKpisByRegimeResponse,
  StrategyKpisRow,
  TradingMode,
} from "@/lib/types";
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

const BOT_MODE_HELP: Record<string, string> = {
  shadow: "Mock en vivo: usa market data real, no envia ordenes y guarda experiencia source=shadow.",
  paper: "Paper interno: corre con fondos virtuales y sirve para validar la logica sin exchange real.",
  testnet: "Testnet del exchange: usa sandbox/API de prueba, distinto de shadow.",
  live: "Live real: sigue NO GO. Se deja visible solo como referencia operativa y no debe activarse ahora.",
};

const BOT_ENGINE_HELP: Record<string, string> = {
  fixed_rules: "Reglas fijas: usa la estrategia definida sin exploracion ni bandit.",
  bandit_thompson: "Thompson: prioriza estrategias con mejor evidencia historica y actualiza su preferencia con experiencia.",
  bandit_ucb1: "UCB1: balancea exploracion y explotacion con una cota superior conservadora.",
};

function proposalBadge(status: string | undefined): "success" | "warn" | "danger" | "neutral" {
  const normalized = String(status || "").toLowerCase();
  if (normalized.includes("approved")) return "success";
  if (normalized.includes("reject")) return "danger";
  if (normalized.includes("needs_validation")) return "warn";
  if (normalized.includes("pending")) return "warn";
  return "neutral";
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
  const [learningStatus, setLearningStatus] = useState<LearningStatusLite | null>(null);
  const [learningRecommendations, setLearningRecommendations] = useState<LearningRecommendationLite[]>([]);
  const [learningExperienceSummary, setLearningExperienceSummary] = useState<LearningExperienceSummaryResponse | null>(null);
  const [learningProposals, setLearningProposals] = useState<LearningProposal[]>([]);
  const [learningGuidance, setLearningGuidance] = useState<LearningGuidanceRow[]>([]);
  const [shadowStatus, setShadowStatus] = useState<ShadowStatusResponse | null>(null);
  const [bots, setBots] = useState<BotInstance[]>([]);
  const [learningBusy, setLearningBusy] = useState(false);
  const [learningActionBusyId, setLearningActionBusyId] = useState<string | null>(null);
  const [proposalActionBusyId, setProposalActionBusyId] = useState<string | null>(null);
  const [shadowBusy, setShadowBusy] = useState(false);
  const [botCreateBusy, setBotCreateBusy] = useState(false);
  const [botActionBusyId, setBotActionBusyId] = useState<string | null>(null);
  const [strategyBulkBusy, setStrategyBulkBusy] = useState(false);
  const [strategySearch, setStrategySearch] = useState("");
  const [strategyStatusFilter, setStrategyStatusFilter] = useState<"all" | "active" | "disabled" | "archived">("all");
  const [strategySourceFilter, setStrategySourceFilter] = useState<"all" | "knowledge" | "uploaded">("all");
  const [strategyPage, setStrategyPage] = useState(1);
  const [strategyPageSize, setStrategyPageSize] = useState<"20" | "50" | "100">("20");
  const [selectedStrategyIds, setSelectedStrategyIds] = useState<string[]>([]);
  const [strategyTargetBotId, setStrategyTargetBotId] = useState("");
  const [botPoolDrafts, setBotPoolDrafts] = useState<Record<string, string[]>>({});

  const refresh = useCallback(async () => {
    const params = new URLSearchParams({ mode: kpiMode, from: kpiFrom, to: kpiTo });
    const [
      rows,
      bt,
      kpiTable,
      learningStatusRes,
      learningRecsRes,
      learningExperienceRes,
      learningProposalsRes,
      learningGuidanceRes,
      shadowStatusRes,
      botsRes,
    ] = await Promise.all([
      apiGet<Strategy[]>("/api/v1/strategies"),
      apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
      apiGet<{ items: StrategyKpisRow[] }>(`/api/v1/strategies/kpis?${params.toString()}`),
      apiGet<LearningStatusLite>("/api/v1/learning/status").catch(() => null),
      apiGet<LearningRecommendationLite[]>("/api/v1/learning/recommendations").catch(() => []),
      apiGet<LearningExperienceSummaryResponse>("/api/v1/learning/experience/summary").catch(() => null),
      apiGet<{ items: LearningProposal[] }>("/api/v1/learning/proposals").catch(() => ({ items: [] })),
      apiGet<{ items: LearningGuidanceRow[] }>("/api/v1/learning/guidance").catch(() => ({ items: [] })),
      apiGet<ShadowStatusResponse>("/api/v1/learning/shadow/status").catch(() => null),
      apiGet<{ items: BotInstance[] }>("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0").catch(() => ({ items: [] })),
    ]);
    setStrategies(rows);
    setBacktests(bt);
    setStrategyKpisRows(kpiTable.items || []);
    setLearningStatus(learningStatusRes);
    setLearningRecommendations(Array.isArray(learningRecsRes) ? learningRecsRes : []);
    setLearningExperienceSummary(learningExperienceRes);
    setLearningProposals(Array.isArray(learningProposalsRes?.items) ? learningProposalsRes.items : []);
    setLearningGuidance(Array.isArray(learningGuidanceRes?.items) ? learningGuidanceRes.items : []);
    setShadowStatus(shadowStatusRes);
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

  const strategyNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of strategies) map.set(row.id, row.name);
    return map;
  }, [strategies]);

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

  const learningProposalRows = useMemo(
    () =>
      [...learningProposals].sort(
        (a, b) => new Date(String(b.created_ts || "")).getTime() - new Date(String(a.created_ts || "")).getTime(),
      ),
    [learningProposals],
  );

  const guidanceByStrategyId = useMemo(() => {
    const map = new Map<string, LearningGuidanceRow>();
    for (const row of learningGuidance) map.set(String(row.strategy_id || ""), row);
    return map;
  }, [learningGuidance]);

  const selectedStrategies = useMemo(
    () => strategies.filter((row) => selectedStrategyIds.includes(row.id)),
    [strategies, selectedStrategyIds],
  );

  useEffect(() => {
    setSelectedStrategyIds((prev) => prev.filter((id) => strategies.some((row) => row.id === id)));
  }, [strategies]);

  useEffect(() => {
    if (!bots.length) {
      if (strategyTargetBotId) setStrategyTargetBotId("");
      return;
    }
    if (!strategyTargetBotId || !bots.some((row) => row.id === strategyTargetBotId)) {
      setStrategyTargetBotId(bots[0].id);
    }
  }, [bots, strategyTargetBotId]);

  useEffect(() => {
    setBotPoolDrafts((prev) => {
      const next: Record<string, string[]> = {};
      for (const bot of bots) {
        next[bot.id] = Array.isArray(prev[bot.id]) ? [...prev[bot.id]] : [...(bot.pool_strategy_ids || [])];
      }
      const prevKeys = Object.keys(prev);
      const nextKeys = Object.keys(next);
      if (
        prevKeys.length === nextKeys.length &&
        nextKeys.every((key) => Array.isArray(prev[key]) && prev[key].length === next[key].length && prev[key].every((id, idx) => id === next[key][idx]))
      ) {
        return prev;
      }
      return next;
    });
  }, [bots]);

  const toggleStrategySelection = (strategyId: string) => {
    setSelectedStrategyIds((prev) => (prev.includes(strategyId) ? prev.filter((id) => id !== strategyId) : [...prev, strategyId]));
  };

  const selectStrategyPage = () => {
    setSelectedStrategyIds((prev) => Array.from(new Set([...prev, ...strategyRowsPage.map((row) => row.id)])));
  };

  const selectStrategyFiltered = () => {
    setSelectedStrategyIds(strategyRowsFiltered.map((row) => row.id));
  };

  const clearSelectedStrategies = () => {
    setSelectedStrategyIds([]);
  };

  const runBulkStrategyPatch = async (patch: Parameters<typeof patchStrategy>[1], successLabel: string) => {
    if (!selectedStrategyIds.length) {
      setError("Selecciona al menos una estrategia.");
      return;
    }
    setStrategyBulkBusy(true);
    setError("");
    setUploadMsg("");
    try {
      for (const strategyId of selectedStrategyIds) {
        await apiPatch(`/api/v1/strategies/${strategyId}`, patch);
      }
      setUploadMsg(successLabel);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo aplicar la accion masiva.");
    } finally {
      setStrategyBulkBusy(false);
    }
  };

  const createBotFromSelectedStrategies = async () => {
    if (!selectedStrategyIds.length) {
      setError("Selecciona estrategias antes de crear un bot.");
      return;
    }
    setBotCreateBusy(true);
    setError("");
    setUploadMsg("");
    try {
      await apiPost("/api/v1/bots", {
        name: `AutoBot ${bots.length + 1}`,
        engine: learningStatus?.selector_algo === "ucb1" ? "bandit_ucb1" : learningStatus?.selector_algo === "regime_rules" ? "fixed_rules" : "bandit_thompson",
        mode: "paper",
        status: "active",
        pool_strategy_ids: selectedStrategyIds,
        universe: ["BTCUSDT", "ETHUSDT"],
        notes: "Creado desde seleccion multiple de estrategias.",
      });
      setUploadMsg(`Bot creado con ${selectedStrategyIds.length} estrategias.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear el bot desde la seleccion.");
    } finally {
      setBotCreateBusy(false);
    }
  };

  const applySelectedStrategiesToBot = async (mode: "append" | "replace") => {
    if (!strategyTargetBotId) {
      setError("Elige un bot destino.");
      return;
    }
    if (!selectedStrategyIds.length) {
      setError("Selecciona al menos una estrategia.");
      return;
    }
    const targetBot = bots.find((row) => row.id === strategyTargetBotId);
    if (!targetBot) {
      setError("No encontre el bot destino.");
      return;
    }
    const poolIds =
      mode === "replace"
        ? [...selectedStrategyIds]
        : Array.from(new Set([...(targetBot.pool_strategy_ids || []), ...selectedStrategyIds]));
    await patchBot(strategyTargetBotId, { pool_strategy_ids: poolIds });
    setUploadMsg(mode === "replace" ? `Pool de ${targetBot.name} reemplazado.` : `Estrategias agregadas a ${targetBot.name}.`);
  };

  const addRecommendationToBot = async (rec: LearningRecommendationLite) => {
    if (!strategyTargetBotId) {
      setError("Elige un bot destino antes de cargar sugerencias.");
      return;
    }
    const targetBot = bots.find((row) => row.id === strategyTargetBotId);
    if (!targetBot) {
      setError("No encontre el bot destino.");
      return;
    }
    const recommendedIds = Array.from(
      new Set(
        [
          rec.active_strategy_id,
          ...(Array.isArray(rec.ranking) ? rec.ranking.map((row) => row.strategy_id) : []),
        ].filter((value): value is string => Boolean(value && String(value).trim())),
      ),
    );
    if (!recommendedIds.length) {
      setError("La sugerencia no trae estrategias utilizables.");
      return;
    }
    await patchBot(targetBot.id, {
      pool_strategy_ids: Array.from(new Set([...(targetBot.pool_strategy_ids || []), ...recommendedIds])),
    });
    setUploadMsg(`Sugerencia cargada al bot ${targetBot.name}: ${recommendedIds.length} estrategias.`);
  };

  const toggleBotPoolDraftStrategy = (botId: string, strategyId: string) => {
    setBotPoolDrafts((prev) => {
      const current = Array.isArray(prev[botId]) ? prev[botId] : [];
      const next = current.includes(strategyId) ? current.filter((id) => id !== strategyId) : [...current, strategyId];
      return { ...prev, [botId]: next };
    });
  };

  const resetBotPoolDraft = (botId: string, fallbackIds: string[]) => {
    setBotPoolDrafts((prev) => ({ ...prev, [botId]: [...fallbackIds] }));
  };

  const saveBotPoolDraft = async (botId: string) => {
    const draftIds = botPoolDrafts[botId] || [];
    await patchBot(botId, { pool_strategy_ids: draftIds });
    setUploadMsg(`Pool del bot actualizado (${draftIds.length} estrategias).`);
  };

  const deleteBot = async (bot: BotInstance) => {
    if (!confirm(`Eliminar bot ${bot.name}? Esta accion borra su registro activo.`)) return;
    setBotActionBusyId(bot.id);
    setError("");
    setUploadMsg("");
    try {
      await apiDelete(`/api/v1/bots/${bot.id}`);
      setSelectedStrategyIds((prev) => [...prev]);
      setUploadMsg(`Bot ${bot.name} eliminado.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo borrar el bot.");
    } finally {
      setBotActionBusyId(null);
    }
  };

  const exportBotKnowledge = (bot: BotInstance) => {
    const poolIds = botPoolDrafts[bot.id] || bot.pool_strategy_ids || [];
    const payload = {
      exported_at: new Date().toISOString(),
      bot: {
        id: bot.id,
        name: bot.name,
        engine: bot.engine,
        mode: bot.mode,
        status: bot.status,
        universe: bot.universe || [],
        notes: bot.notes || "",
      },
      metrics: bot.metrics || {},
      pool: poolIds.map((strategyId) => {
        const strategy = strategies.find((row) => row.id === strategyId);
        const kpi = kpiByStrategyId.get(strategyId)?.kpis || null;
        const guidance = guidanceByStrategyId.get(strategyId) || null;
        const latestRun = latestBacktestByStrategy.get(strategyId) || null;
        return {
          strategy_id: strategyId,
          name: strategy?.name || strategyId,
          version: strategy?.version || null,
          source: strategy?.source || null,
          enabled_for_trading: strategy?.enabled_for_trading ?? strategy?.enabled ?? false,
          allow_learning: strategy?.allow_learning ?? true,
          is_primary: strategy?.is_primary ?? false,
          kpis: kpi,
          guidance,
          latest_backtest: latestRun,
        };
      }),
      proposals: learningProposalRows.filter((row) => poolIds.includes(row.proposed_strategy_id) || (row.replaces_strategy_id ? poolIds.includes(row.replaces_strategy_id) : false)),
      recommendations: learningRecommendations.filter((row) => {
        const rankingIds = Array.isArray(row.ranking) ? row.ranking.map((item) => item.strategy_id) : [];
        return poolIds.includes(String(row.active_strategy_id || "")) || rankingIds.some((id) => poolIds.includes(id));
      }),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${bot.id}_knowledge_export.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

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

  const recalculateLearningProposals = async () => {
    setLearningBusy(true);
    setError("");
    try {
      await apiPost("/api/v1/learning/proposals/recalculate", {});
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo recalcular Opcion B.");
    } finally {
      setLearningBusy(false);
    }
  };

  const reviewLearningProposal = async (proposalId: string, action: "approve" | "reject") => {
    setProposalActionBusyId(proposalId);
    setError("");
    try {
      await apiPost(`/api/v1/learning/proposals/${proposalId}/${action}`, {
        note: action === "approve" ? "Aprobado desde Aprendizaje (Opcion B)." : "Rechazado desde Aprendizaje (Opcion B).",
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : `No se pudo ${action} la propuesta.`);
    } finally {
      setProposalActionBusyId(null);
    }
  };

  const startShadowRunner = async (botId?: string) => {
    setShadowBusy(true);
    setError("");
    try {
      await apiPost("/api/v1/learning/shadow/start", {
        bot_id: botId || null,
        timeframe: shadowStatus?.timeframe || "5m",
        lookback_bars: shadowStatus?.lookback_bars || 240,
        poll_sec: shadowStatus?.poll_sec || 30,
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar shadow.");
    } finally {
      setShadowBusy(false);
    }
  };

  const stopShadowRunner = async (reason = "ui_stop_shadow") => {
    setShadowBusy(true);
    setError("");
    try {
      await apiPost("/api/v1/learning/shadow/stop", { reason });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo detener shadow.");
    } finally {
      setShadowBusy(false);
    }
  };

  const patchBot = async (botId: string, patch: Record<string, unknown>) => {
    setBotActionBusyId(botId);
    setError("");
    try {
      try {
        await apiPatch(`/api/v1/bots/${botId}/policy-state`, patch);
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 404) throw err;
        await apiPatch(`/api/v1/bots/${botId}`, patch);
      }
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

          <div className="grid gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3 lg:grid-cols-[1.6fr_1fr]">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={selectedStrategyIds.length ? "info" : "neutral"}>{selectedStrategyIds.length} seleccionadas</Badge>
                <Button variant="outline" className="h-7 px-2 text-[11px]" disabled={!strategyRowsPage.length} onClick={selectStrategyPage}>
                  Seleccionar pagina
                </Button>
                <Button variant="outline" className="h-7 px-2 text-[11px]" disabled={!strategyRowsFiltered.length} onClick={selectStrategyFiltered}>
                  Seleccionar filtradas
                </Button>
                <Button variant="outline" className="h-7 px-2 text-[11px]" disabled={!selectedStrategyIds.length} onClick={clearSelectedStrategies}>
                  Limpiar seleccion
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="h-8 px-3 text-[11px]" disabled={role !== "admin" || strategyBulkBusy || !selectedStrategyIds.length} onClick={() => void runBulkStrategyPatch({ allow_learning: true }, "Seleccion masiva marcada para aprendizaje.")}>
                  Marcar aprendizaje
                </Button>
                <Button variant="outline" className="h-8 px-3 text-[11px]" disabled={role !== "admin" || strategyBulkBusy || !selectedStrategyIds.length} onClick={() => void runBulkStrategyPatch({ allow_learning: false }, "Seleccion masiva removida del pool de aprendizaje.")}>
                  Quitar aprendizaje
                </Button>
                <Button variant="outline" className="h-8 px-3 text-[11px]" disabled={role !== "admin" || strategyBulkBusy || !selectedStrategyIds.length} onClick={() => void runBulkStrategyPatch({ status: "archived" }, "Seleccion masiva archivada.")}>
                  Archivar seleccionadas
                </Button>
                <Button className="h-8 px-3 text-[11px]" disabled={role !== "admin" || botCreateBusy || !selectedStrategyIds.length} onClick={() => void createBotFromSelectedStrategies()}>
                  {botCreateBusy ? "Creando..." : "Crear bot con seleccion"}
                </Button>
              </div>
              {selectedStrategies.length ? (
                <p className="text-[11px] text-slate-400">
                  Seleccion actual: {selectedStrategies.slice(0, 4).map((row) => row.name).join(" | ")}
                  {selectedStrategies.length > 4 ? ` +${selectedStrategies.length - 4}` : ""}
                </p>
              ) : null}
            </div>
            <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-[11px] uppercase tracking-wide text-slate-400">Bot destino</p>
              <Select value={strategyTargetBotId} onChange={(e) => setStrategyTargetBotId(e.target.value)} disabled={!bots.length}>
                <option value="">{bots.length ? "Elegir bot..." : "Sin bots"}</option>
                {bots.map((bot) => (
                  <option key={`bulk-bot-${bot.id}`} value={bot.id}>
                    {bot.name} ({bot.mode.toUpperCase()} / {bot.engine})
                  </option>
                ))}
              </Select>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="h-8 px-3 text-[11px]" disabled={role !== "admin" || !bots.length || !selectedStrategyIds.length || !strategyTargetBotId} onClick={() => void applySelectedStrategiesToBot("append")}>
                  Agregar a bot
                </Button>
                <Button variant="outline" className="h-8 px-3 text-[11px]" disabled={role !== "admin" || !bots.length || !selectedStrategyIds.length || !strategyTargetBotId} onClick={() => void applySelectedStrategiesToBot("replace")}>
                  Reemplazar pool
                </Button>
              </div>
              <p className="text-[11px] text-slate-400">
                Usa esta seleccion para crear bots nuevos o cargar estrategias a un bot existente sin tocar LIVE.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <Table className="text-xs">
              <THead>
                <TR>
                  <TH>
                    <input
                      type="checkbox"
                      checked={Boolean(strategyRowsPage.length) && strategyRowsPage.every((row) => selectedStrategyIds.includes(row.id))}
                      onChange={(e) => (e.target.checked ? selectStrategyPage() : setSelectedStrategyIds((prev) => prev.filter((id) => !strategyRowsPage.some((row) => row.id === id))))}
                    />
                  </TH>
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
                    <TD>
                      <input type="checkbox" checked={selectedStrategyIds.includes(row.id)} onChange={() => toggleStrategySelection(row.id)} />
                    </TD>
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
                    <TD colSpan={15} className="py-4 text-center text-xs text-slate-400">
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
              Evidence derivada (legacy): ultimo Max DD {fmtPct(latestBacktestByStrategy.get(selected.id)!.metrics.max_dd)} | Winrate {fmtPct(latestBacktestByStrategy.get(selected.id)!.metrics.winrate)}
            </div>
          ) : null}

          {selected && selectedKpis ? (
            <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence agregada de estrategia ({kpiMode.toUpperCase()})</p>
                <Badge variant={selectedKpis.dataset_hash_warning ? "warn" : "success"}>
                  {selectedKpis.dataset_hash_warning ? "datasets distintos" : "dataset consistente"}
                </Badge>
              </div>
              <p className="text-[11px] text-slate-400">
                Estas metricas son evidence agregada de runs, no verdad base declarativa de la estrategia.
              </p>
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
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence por regimen</p>
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
                <div className="rounded border border-slate-800 p-2">Episodes: <strong>{Number(learningExperienceSummary?.total_episodes || 0)}</strong></div>
                <div className="rounded border border-slate-800 p-2">Eventos: <strong>{Number(learningExperienceSummary?.total_events || 0)}</strong></div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="outline" disabled={learningBusy || !learningStatus?.enabled} onClick={() => void requestLearningRecommendation()}>
                  {learningBusy ? "Generando..." : "Recomendar ahora"}
                </Button>
                <Button variant="outline" disabled={learningBusy || role !== "admin"} onClick={() => void recalculateLearningProposals()}>
                  {learningBusy ? "Recalculando..." : "Recalcular Opcion B"}
                </Button>
                <Button variant="outline" disabled={shadowBusy || role !== "admin" || shadowStatus?.running} onClick={() => void startShadowRunner()}>
                  {shadowBusy && !shadowStatus?.running ? "Iniciando shadow..." : "Iniciar shadow"}
                </Button>
                <Button variant="outline" disabled={shadowBusy || role !== "admin" || !shadowStatus?.running} onClick={() => void stopShadowRunner()}>
                  {shadowBusy && shadowStatus?.running ? "Deteniendo..." : "Detener shadow"}
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
              <div className="mt-2 rounded border border-slate-800 bg-slate-950/50 p-2 text-[11px] text-slate-300">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={shadowStatus?.running ? "success" : "neutral"}>{shadowStatus?.running ? "Shadow corriendo" : "Shadow detenido"}</Badge>
                  <span>targets: <strong>{shadowStatus?.targets_count ?? 0}</strong></span>
                  <span>runs: <strong>{shadowStatus?.runs_created ?? 0}</strong></span>
                  <span>duplicados evitados: <strong>{shadowStatus?.skipped_duplicate_cycles ?? 0}</strong></span>
                </div>
                <p className="mt-1 text-slate-400">
                  Mock/shadow usa market data real, no envia ordenes y deja experiencia persistente para Opcion B.
                </p>
                {shadowStatus?.last_error ? <p className="mt-1 text-amber-300">Ultimo error: {shadowStatus.last_error}</p> : null}
              </div>
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
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-2 text-[11px]"
                            disabled={role !== "admin" || !strategyTargetBotId}
                            onClick={() => void addRecommendationToBot(rec)}
                          >
                            Agregar a bot
                          </Button>
                          {pending && role === "admin" && rec.recommendation_source !== "research" ? (
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

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Propuestas Opcion B</p>
                <Badge variant={learningProposalRows.length ? "info" : "neutral"}>{learningProposalRows.length} totales</Badge>
              </div>
              <div className="mt-2 space-y-2">
                {learningProposalRows.length ? (
                  learningProposalRows.slice(0, 6).map((proposal) => {
                    const reasons = Array.isArray(proposal.metrics?.reasons) ? proposal.metrics?.reasons || [] : [];
                    const proposalStrategyName = strategyNameById.get(proposal.proposed_strategy_id) || proposal.proposed_strategy_id;
                    const replacedStrategyName =
                      proposal.replaces_strategy_id && strategyNameById.get(proposal.replaces_strategy_id)
                        ? strategyNameById.get(proposal.replaces_strategy_id)
                        : proposal.replaces_strategy_id;
                    return (
                      <div key={proposal.id} className="rounded border border-slate-800 bg-slate-950/50 p-3 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <p className="font-semibold text-slate-100">{proposalStrategyName}</p>
                            <p className="text-[11px] text-slate-400">
                              {proposal.asset || "-"} / {proposal.timeframe || "-"} / {proposal.regime_label || "unknown"}
                              {replacedStrategyName ? ` / reemplaza ${replacedStrategyName}` : ""}
                            </p>
                          </div>
                          <Badge variant={proposalBadge(proposal.status)}>{proposal.status || "pending"}</Badge>
                        </div>
                        <div className="mt-2 grid gap-2 md:grid-cols-3">
                          <div className="rounded border border-slate-800 p-2">Conf.: <strong>{fmtPct(Number(proposal.confidence || 0))}</strong></div>
                          <div className="rounded border border-slate-800 p-2">Creada: <strong>{proposal.created_ts ? new Date(proposal.created_ts).toLocaleString() : "-"}</strong></div>
                          <div className="rounded border border-slate-800 p-2">Gate: <strong>{proposal.needs_validation ? "requiere validacion" : "ok"}</strong></div>
                        </div>
                        {proposal.rationale ? <p className="mt-2 text-slate-300">{proposal.rationale}</p> : null}
                        {reasons.length ? <p className="mt-2 text-amber-300">Motivos: {reasons.join(" | ")}</p> : null}
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-2 text-[11px]"
                            disabled={role !== "admin" || proposalActionBusyId === proposal.id || String(proposal.status || "").toLowerCase() === "approved"}
                            onClick={() => void reviewLearningProposal(proposal.id, "approve")}
                          >
                            Aprobar
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-2 text-[11px]"
                            disabled={role !== "admin" || proposalActionBusyId === proposal.id || String(proposal.status || "").toLowerCase() === "rejected"}
                            onClick={() => void reviewLearningProposal(proposal.id, "reject")}
                          >
                            Rechazar
                          </Button>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
                    Todavia no hay propuestas nuevas. Recalcula Opcion B cuando el Experience Store tenga suficiente evidencia.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Guiado por estrategia</p>
                <Badge variant={learningGuidance.length ? "info" : "neutral"}>{learningGuidance.length} filas</Badge>
              </div>
              <div className="mt-2 space-y-2">
                {learningGuidance.length ? (
                  learningGuidance.slice(0, 6).map((row) => {
                    const preferred = Array.isArray(row.preferred_regimes_json) ? row.preferred_regimes_json.join(", ") : String(row.preferred_regimes_json || "-");
                    const avoid = Array.isArray(row.avoid_regimes_json) ? row.avoid_regimes_json.join(", ") : String(row.avoid_regimes_json || "-");
                    return (
                      <div key={`guidance-${row.strategy_id}`} className="rounded border border-slate-800 bg-slate-950/50 p-3 text-xs">
                        <p className="font-semibold text-slate-100">{strategyNameById.get(row.strategy_id) || row.strategy_id}</p>
                        <p className="mt-1 text-slate-300">Regimenes preferidos: <strong>{preferred}</strong></p>
                        <p className="mt-1 text-slate-300">Evitar: <strong>{avoid}</strong></p>
                        <p className="mt-1 text-slate-300">
                          Conf. minima: <strong>{fmtPct(Number(row.min_confidence_to_recommend || 0))}</strong>
                          {" "}· Max spread: <strong>{fmtNum(Number(row.max_spread_bps_allowed || 0))} bps</strong>
                          {" "}· Max VPIN: <strong>{fmtNum(Number(row.max_vpin_allowed || 0))}</strong>
                        </p>
                        {row.notes ? <p className="mt-1 text-slate-400">{row.notes}</p> : null}
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-400">
                    Sin guidance todavia. Se genera a partir de experiencia valida y solo con estrategias Pool=true.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Bots / AutoBots (multi-instancia)</p>
                <p className="text-[11px] text-slate-400">Izquierda: policy_state del bot (engine/modo/status/pool). Derecha: evidence y decision log derivados (trades, Sharpe, breakers, experiencia).</p>
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
                      <TH>Policy engine</TH>
                      <TH>Policy mode</TH>
                      <TH>Policy status</TH>
                      <TH>Policy pool</TH>
                      <TH>Evidence trades</TH>
                      <TH>Evidence winRate</TH>
                      <TH>Evidence PnL</TH>
                      <TH>Evidence Sharpe</TH>
                      <TH>Recs</TH>
                      <TH>Breakers</TH>
                      <TH>&Uacute;ltimo run</TH>
                      <TH>Acciones</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {bots.map((bot) => {
                      const m = bot.metrics;
                      const busy = botActionBusyId === bot.id;
                      const experienceBySource = m?.experience_by_source;
                      const poolDraftIds = botPoolDrafts[bot.id] || bot.pool_strategy_ids || [];
                      const poolDraftRows = poolDraftIds
                        .map((strategyId) => strategies.find((row) => row.id === strategyId) || bot.pool_strategies?.find((row) => row.id === strategyId))
                        .filter((row): row is Strategy => Boolean(row));
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
                          <TD>
                            <div>{m?.trade_count ?? 0}</div>
                            <div className="text-[10px] text-slate-500">runs: {m?.run_count ?? 0}</div>
                            <div className="text-[10px] text-slate-500">
                              sh: {experienceBySource?.shadow?.episode_count ?? 0} · bt: {experienceBySource?.backtest?.episode_count ?? 0}
                            </div>
                          </TD>
                          <TD>{fmtPct(m?.winrate ?? 0)}</TD>
                          <TD>{fmtNum(m?.net_pnl ?? 0)}</TD>
                          <TD>{fmtNum(m?.avg_sharpe ?? 0)}</TD>
                          <TD>
                            <span className="text-slate-300">
                              {(m?.recommendations_pending ?? 0)}/{(m?.recommendations_approved ?? 0)}/{(m?.recommendations_rejected ?? 0)}
                            </span>
                            <div className="text-[10px] text-slate-500">pend/apr/rech</div>
                          </TD>
                          <TD>
                            <div>{m?.kills_total ?? 0}</div>
                            <div className="text-[10px] text-slate-500">24h: {m?.kills_24h ?? 0}</div>
                          </TD>
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
                              <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" onClick={() => exportBotKnowledge(bot)}>
                                Exportar
                              </Button>
                              <details className="rounded border border-slate-700 bg-slate-950/70 px-2 py-0.5 text-[11px] text-slate-200">
                                <summary className="cursor-pointer select-none">M&aacute;s</summary>
                                <div className="mt-2 min-w-[280px] space-y-2">
                                  <div className="rounded border border-slate-800 bg-slate-950/50 p-2">
                                    <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Modo</p>
                                    {(["shadow", "paper", "testnet", "live"] as const).map((modeKey) => (
                                      <div key={`${bot.id}-mode-${modeKey}`} className="mb-1 rounded border border-slate-800 p-2 last:mb-0">
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          className="h-7 justify-start px-2 text-[11px]"
                                          disabled={role !== "admin" || busy || modeKey === "live"}
                                          onClick={() => void patchBot(bot.id, { mode: modeKey })}
                                        >
                                          {`Modo ${modeKey.toUpperCase()}`}{modeKey === "live" ? " (bloqueado)" : ""}
                                        </Button>
                                        <p className="mt-1 text-[10px] text-slate-400">{BOT_MODE_HELP[modeKey]}</p>
                                      </div>
                                    ))}
                                  </div>
                                  <div className="rounded border border-slate-800 bg-slate-950/50 p-2">
                                    <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Engine</p>
                                    {(["fixed_rules", "bandit_thompson", "bandit_ucb1"] as const).map((engineKey) => (
                                      <div key={`${bot.id}-engine-${engineKey}`} className="mb-1 rounded border border-slate-800 p-2 last:mb-0">
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          className="h-7 justify-start px-2 text-[11px]"
                                          disabled={role !== "admin" || busy}
                                          onClick={() => void patchBot(bot.id, { engine: engineKey })}
                                        >
                                          {engineKey === "fixed_rules" ? "Engine Reglas fijas" : engineKey === "bandit_thompson" ? "Engine Thompson" : "Engine UCB1"}
                                        </Button>
                                        <p className="mt-1 text-[10px] text-slate-400">{BOT_ENGINE_HELP[engineKey]}</p>
                                      </div>
                                    ))}
                                  </div>
                                  <div className="rounded border border-slate-800 bg-slate-950/50 p-2">
                                    <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Shadow / Mock</p>
                                    <div className="flex flex-wrap gap-2">
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-7 px-2 text-[11px]"
                                        disabled={role !== "admin" || shadowBusy || bot.mode !== "shadow" || bot.status !== "active"}
                                        onClick={() => void startShadowRunner(bot.id)}
                                      >
                                        Simular en shadow
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-7 px-2 text-[11px]"
                                        disabled={role !== "admin" || shadowBusy || !shadowStatus?.running}
                                        onClick={() => void stopShadowRunner(`ui_stop_shadow:${bot.id}`)}
                                      >
                                        Detener shadow
                                      </Button>
                                    </div>
                                    <p className="mt-1 text-[10px] text-slate-400">
                                      El runner mock usa velas cerradas, no envia ordenes y guarda experiencia persistente.
                                    </p>
                                  </div>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void patchBot(bot.id, { status: "archived" })}>
                                    Archivar bot
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 justify-start px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void deleteBot(bot)}>
                                    Borrar bot
                                  </Button>
                                </div>
                              </details>
                            </div>
                            <details className="mt-1 rounded border border-slate-800 bg-slate-950/30 p-2 text-[11px] text-slate-300">
                              <summary className="cursor-pointer select-none">Pool editable ({poolDraftIds.length})</summary>
                              <div className="mt-2 space-y-2">
                                <div className="grid max-h-48 gap-1 overflow-auto rounded border border-slate-800 bg-slate-950/40 p-2">
                                  {strategies
                                    .filter((row) => row.status !== "archived")
                                    .map((strategy) => {
                                      const checked = poolDraftIds.includes(strategy.id);
                                      return (
                                        <label key={`${bot.id}-draft-${strategy.id}`} className="flex items-center justify-between gap-2 rounded border border-slate-800 px-2 py-1">
                                          <span className="truncate text-slate-200" title={strategy.name}>{strategy.name}</span>
                                          <input
                                            type="checkbox"
                                            checked={checked}
                                            disabled={role !== "admin" || busy}
                                            onChange={() => toggleBotPoolDraftStrategy(bot.id, strategy.id)}
                                          />
                                        </label>
                                      );
                                    })}
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => void saveBotPoolDraft(bot.id)}>
                                    Guardar pool
                                  </Button>
                                  <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" disabled={role !== "admin" || busy} onClick={() => resetBotPoolDraft(bot.id, bot.pool_strategy_ids || [])}>
                                    Resetear
                                  </Button>
                                </div>
                                <div className="space-y-1">
                                  {poolDraftRows.length ? (
                                    poolDraftRows.map((s) => {
                                      const kpi = kpiByStrategyId.get(s.id)?.kpis;
                                      const guidance = guidanceByStrategyId.get(s.id);
                                      return (
                                    <div key={`${bot.id}-${s.id}`} className="rounded border border-slate-800 px-2 py-1">
                                      <div className="flex items-center justify-between gap-2">
                                        <span className="truncate" title={s.name}>{s.name}</span>
                                        <div className="flex gap-1">
                                          {s.is_primary ? <Badge variant="warn">Principal</Badge> : null}
                                          {s.allow_learning ? <Badge variant="info">Pool</Badge> : null}
                                          {s.enabled_for_trading ? <Badge variant="success">Trading</Badge> : null}
                                        </div>
                                      </div>
                                      <p className="mt-1 text-[10px] text-slate-400">
                                        Trades: <strong>{kpi?.trade_count ?? 0}</strong>
                                        {" "}· WinRate: <strong>{fmtPct(kpi?.winrate ?? 0)}</strong>
                                        {" "}· Sharpe: <strong>{fmtNum(kpi?.sharpe ?? 0)}</strong>
                                        {" "}· Expectancy: <strong>{fmtNum(kpi?.expectancy_value ?? 0)} {kpi?.expectancy_unit || ""}</strong>
                                      </p>
                                      {guidance?.notes ? (
                                        <p className="mt-1 text-[10px] text-slate-500">{guidance.notes}</p>
                                      ) : null}
                                    </div>
                                  );
                                    })
                                ) : (
                                  <p className="text-slate-500">Sin estrategias asignadas.</p>
                                )}
                                </div>
                              </div>
                            </details>
                            <details className="mt-1 rounded border border-slate-800 bg-slate-950/30 p-2 text-[11px] text-slate-300">
                              <summary className="cursor-pointer select-none">Experiencia por fuente</summary>
                              <div className="mt-2 space-y-1">
                                {(["shadow", "testnet", "paper", "backtest"] as const).map((sourceKey) => {
                                  const source = experienceBySource?.[sourceKey];
                                  return (
                                    <div key={`${bot.id}-${sourceKey}`} className="rounded border border-slate-800 px-2 py-1">
                                      <p className="font-semibold text-slate-100">{sourceKey.toUpperCase()}</p>
                                      <p className="text-slate-300">
                                        episodes: <strong>{source?.episode_count ?? 0}</strong>
                                        {" "}· trades: <strong>{source?.trade_count ?? 0}</strong>
                                        {" "}· decisiones: <strong>{source?.decision_count ?? 0}</strong>
                                      </p>
                                      <p className="text-slate-400">
                                        enter/exit/hold/skip: {source?.enter_count ?? 0}/{source?.exit_count ?? 0}/{source?.hold_count ?? 0}/{source?.skip_count ?? 0}
                                        {" "}· peso prom.: {fmtNum(Number(source?.avg_source_weight ?? 0))}
                                      </p>
                                      {source?.last_end_ts ? <p className="text-slate-500">Ultimo cierre: {new Date(source.last_end_ts).toLocaleString()}</p> : null}
                                    </div>
                                  );
                                })}
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

