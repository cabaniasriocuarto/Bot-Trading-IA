"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Line, LineChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet, apiPatch, apiPost } from "@/lib/client-api";
import type {
  BacktestRun,
  BacktestCatalogBatch,
  CatalogRunKpis,
  BacktestCatalogBatchesResponse,
  BacktestCatalogRun,
  BacktestCatalogRunsResponse,
  BacktestCompareResponse,
  BacktestRankingsResponse,
  RunValidatePromotionResponse,
  MassBacktestArtifactsResponse,
  MassBacktestResultRow,
  MassBacktestResultsResponse,
  MassBacktestStatusResponse,
  Strategy,
} from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

type RunForm = {
  strategy_id: string;
  market: "crypto" | "forex" | "equities";
  symbol: string;
  timeframe: "5m" | "10m" | "15m";
  start: string;
  end: string;
  fees_bps: string;
  spread_bps: string;
  slippage_bps: string;
  funding_bps: string;
  rollover_bps: string;
  validation_mode: "walk-forward" | "purged-cv" | "cpcv";
};

type RunsListFilters = {
  q: string;
  run_type: "" | "single" | "batch_child";
  status: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  min_trades: string;
  max_dd: string;
  sharpe: string;
  sort_by: "created_at" | "score" | "return" | "sharpe" | "sortino" | "dd" | "pf" | "expectancy" | "trades" | "strategy";
  sort_dir: "asc" | "desc";
};

const chartColors = ["#22d3ee", "#f97316", "#facc15", "#4ade80", "#f472b6"];
const MARKET_OPTIONS: Record<RunForm["market"], string[]> = {
  crypto: ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"],
  forex: ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
  equities: ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA"],
};

type MetricGrade = "muy_malo" | "malo" | "aceptable" | "bueno" | "excelente";

const GRADE_CLASS: Record<MetricGrade, string> = {
  muy_malo: "bg-violet-600/25 text-violet-100 border border-violet-500/40",
  malo: "bg-red-600/25 text-red-100 border border-red-500/40",
  aceptable: "bg-orange-600/25 text-orange-100 border border-orange-500/40",
  bueno: "bg-yellow-500/25 text-yellow-50 border border-yellow-400/40",
  excelente: "bg-green-600/25 text-green-100 border border-green-500/40",
};

function gradeMetric(key: string, rawValue: number | undefined): MetricGrade | null {
  if (typeof rawValue !== "number" || Number.isNaN(rawValue)) return null;
  const value = key === "max_dd" ? Math.abs(rawValue) * 100 : ["cagr", "winrate"].includes(key) ? rawValue * 100 : rawValue;
  switch (key) {
    case "cagr":
      if (value < 0) return "muy_malo";
      if (value <= 10) return "malo";
      if (value <= 20) return "aceptable";
      if (value <= 40) return "bueno";
      return "excelente";
    case "max_dd":
      if (value > 50) return "muy_malo";
      if (value >= 30) return "malo";
      if (value >= 15) return "aceptable";
      if (value >= 8) return "bueno";
      return "excelente";
    case "sharpe":
      if (value < 0) return "muy_malo";
      if (value <= 0.5) return "malo";
      if (value <= 1.0) return "aceptable";
      if (value <= 2.0) return "bueno";
      return "excelente";
    case "sortino":
      if (value < 0) return "muy_malo";
      if (value <= 0.7) return "malo";
      if (value <= 1.5) return "aceptable";
      if (value <= 3.0) return "bueno";
      return "excelente";
    case "calmar":
      if (value < 0) return "muy_malo";
      if (value <= 0.5) return "malo";
      if (value <= 1.0) return "aceptable";
      if (value <= 3.0) return "bueno";
      return "excelente";
    case "winrate":
      if (value < 35) return "muy_malo";
      if (value <= 45) return "malo";
      if (value <= 55) return "aceptable";
      if (value <= 65) return "bueno";
      return "excelente";
    case "turnover":
      if (value > 10) return "muy_malo";
      if (value >= 5) return "malo";
      if (value >= 2) return "aceptable";
      if (value >= 0.8) return "bueno";
      return "excelente";
    case "robustness":
      if (value < 40) return "muy_malo";
      if (value <= 55) return "malo";
      if (value <= 70) return "aceptable";
      if (value <= 85) return "bueno";
      return "excelente";
    default:
      return null;
  }
}

function gradeCellClass(key: string, value: number | undefined): string {
  const grade = gradeMetric(key, value);
  return grade ? GRADE_CLASS[grade] : "";
}

function statusVariant(status: string): "success" | "danger" | "warn" {
  const s = String(status || "").toLowerCase();
  if (["completed", "pass"].includes(s)) return "success";
  if (["failed", "canceled", "archived"].includes(s)) return "danger";
  return "warn";
}

function runTypeLabel(runType: string): string {
  return String(runType) === "batch_child" ? "Research Batch child" : "Quick Backtest";
}

function shortHash(value: string | null | undefined, size = 10): string {
  const v = String(value || "");
  return v ? v.slice(0, size) : "-";
}

function compactDate(value: string | null | undefined): string {
  const v = String(value || "");
  if (!v) return "-";
  return v.replace("T", " ").slice(0, 16);
}

function parseFeePctLabel(feeModel: string | null | undefined): string {
  const raw = String(feeModel || "");
  const num = Number(raw.split(":")[1] ?? "");
  if (!Number.isFinite(num)) return raw || "-";
  return `${fmtNum(num)} bps`;
}

export default function BacktestsPage() {
  const { role } = useSession();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [catalogRuns, setCatalogRuns] = useState<BacktestCatalogRun[]>([]);
  const [catalogRunCount, setCatalogRunCount] = useState(0);
  const [catalogBatches, setCatalogBatches] = useState<BacktestCatalogBatch[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [catalogCompareIds, setCatalogCompareIds] = useState<string[]>([]);
  const [catalogComparePreview, setCatalogComparePreview] = useState<BacktestCompareResponse | null>(null);
  const [catalogRankingPreset, setCatalogRankingPreset] = useState("balanceado");
  const [catalogRankings, setCatalogRankings] = useState<BacktestRankingsResponse | null>(null);
  const [catalogRankRequireOos, setCatalogRankRequireOos] = useState(false);
  const [catalogRankDataQualityOk, setCatalogRankDataQualityOk] = useState(false);
  const [catalogProLimit, setCatalogProLimit] = useState<"50" | "100" | "250" | "500">("100");
  const [catalogTableColumns, setCatalogTableColumns] = useState<Record<string, boolean>>({
    run: true,
    strategy: true,
    status: true,
    dates: true,
    market: true,
    dataset: true,
    costs: true,
    kpis: true,
    flags: true,
    rank: true,
  });
  const [deepCompareLegacyRuns, setDeepCompareLegacyRuns] = useState<BacktestRun[]>([]);
  const [promotionBusyRunId, setPromotionBusyRunId] = useState<string | null>(null);
  const [promotionPreview, setPromotionPreview] = useState<RunValidatePromotionResponse | null>(null);
  const [promotionError, setPromotionError] = useState("");
  const [promotionMessage, setPromotionMessage] = useState("");
  const [catalogFilters, setCatalogFilters] = useState<RunsListFilters>({
    q: "",
    run_type: "",
    status: "",
    strategy_id: "",
    symbol: "",
    timeframe: "",
    min_trades: "",
    max_dd: "",
    sharpe: "",
    sort_by: "created_at",
    sort_dir: "desc",
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [massRunning, setMassRunning] = useState(false);
  const [massError, setMassError] = useState("");
  const [massMessage, setMassMessage] = useState("");
  const [massSelectedStrategies, setMassSelectedStrategies] = useState<string[]>([]);
  const [massRunId, setMassRunId] = useState("");
  const [massStatus, setMassStatus] = useState<MassBacktestStatusResponse | null>(null);
  const [massResults, setMassResults] = useState<MassBacktestResultRow[]>([]);
  const [massArtifacts, setMassArtifacts] = useState<MassBacktestArtifactsResponse["items"]>([]);
  const [massOnlyPass, setMassOnlyPass] = useState(true);
  const [massSelectedRow, setMassSelectedRow] = useState<MassBacktestResultRow | null>(null);
  const [massForm, setMassForm] = useState({
    max_variants_per_strategy: "4",
    max_folds: "3",
    train_days: "180",
    test_days: "60",
    top_n: "10",
    seed: "42",
    dataset_source: "synthetic",
  });

  const [form, setForm] = useState<RunForm>({
    strategy_id: "",
    market: "crypto",
    symbol: "BTCUSDT",
    timeframe: "5m",
    start: "2024-01-01",
    end: "2024-12-31",
    fees_bps: "5.5",
    spread_bps: "4.0",
    slippage_bps: "3.0",
    funding_bps: "1.0",
    rollover_bps: "0.0",
    validation_mode: "walk-forward",
  });

  const refresh = useCallback(async () => {
    const [stg, bt] = await Promise.all([
      apiGet<Strategy[]>("/api/v1/strategies"),
      apiGet<BacktestRun[]>("/api/v1/backtests/runs"),
    ]);
    setStrategies(stg);
    setRuns(bt);
    if (!form.strategy_id && stg[0]) {
      setForm((prev) => ({ ...prev, strategy_id: stg[0].id }));
    }
    if (!massSelectedStrategies.length && stg.length) {
      setMassSelectedStrategies(stg.slice(0, Math.min(5, stg.length)).map((row) => row.id));
    }
  }, [form.strategy_id]);

  const refreshCatalogRuns = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError("");
    try {
      const params = new URLSearchParams();
      if (catalogFilters.q.trim()) params.set("q", catalogFilters.q.trim());
      if (catalogFilters.run_type) params.set("run_type", catalogFilters.run_type);
      if (catalogFilters.status) params.set("status", catalogFilters.status);
      if (catalogFilters.strategy_id) params.set("strategy_id", catalogFilters.strategy_id);
      if (catalogFilters.symbol) params.set("symbol", catalogFilters.symbol);
      if (catalogFilters.timeframe) params.set("timeframe", catalogFilters.timeframe);
      if (catalogFilters.min_trades.trim()) params.set("min_trades", catalogFilters.min_trades.trim());
      if (catalogFilters.max_dd.trim()) params.set("max_dd", catalogFilters.max_dd.trim());
      if (catalogFilters.sharpe.trim()) params.set("sharpe", catalogFilters.sharpe.trim());
      params.set("sort_by", catalogFilters.sort_by);
      params.set("sort_dir", catalogFilters.sort_dir);
      params.set("limit", "500");
      const path = `/api/v1/runs?${params.toString()}`;
      const payload = await apiGet<BacktestCatalogRunsResponse>(path);
      setCatalogRuns(payload.items || []);
      setCatalogRunCount(payload.count || 0);
    } catch (err) {
      setCatalogError(err instanceof Error ? err.message : "No se pudo cargar Backtests / Runs.");
    } finally {
      setCatalogLoading(false);
    }
  }, [catalogFilters]);

  const refreshCatalogBatches = useCallback(async () => {
    try {
      const payload = await apiGet<BacktestCatalogBatchesResponse>("/api/v1/batches");
      setCatalogBatches(payload.items || []);
    } catch {
      setCatalogBatches([]);
    }
  }, []);

  const refreshCatalogRankings = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.set("preset", catalogRankingPreset);
      if (catalogFilters.min_trades.trim()) params.set("min_trades", catalogFilters.min_trades.trim());
      if (catalogFilters.max_dd.trim()) params.set("max_dd", catalogFilters.max_dd.trim());
      if (catalogFilters.sharpe.trim()) params.set("sharpe", catalogFilters.sharpe.trim());
      if (catalogRankRequireOos) params.set("oos_pass", "true");
      if (catalogRankDataQualityOk) params.set("data_quality", "ok");
      params.set("limit", "50");
      const payload = await apiGet<BacktestRankingsResponse>(`/api/v1/rankings?${params.toString()}`);
      setCatalogRankings(payload);
    } catch {
      setCatalogRankings(null);
    }
  }, [catalogFilters.max_dd, catalogFilters.min_trades, catalogFilters.sharpe, catalogRankDataQualityOk, catalogRankRequireOos, catalogRankingPreset]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void refreshCatalogRuns();
    void refreshCatalogBatches();
    void refreshCatalogRankings();
  }, [refreshCatalogRuns, refreshCatalogBatches, refreshCatalogRankings]);

  useEffect(() => {
    const selectedCatalogRows = (catalogComparePreview?.items || []).slice(0, 4);
    const legacyIds = selectedCatalogRows
      .map((row) => String(row.legacy_json_id || ""))
      .filter((id) => id && !id.startsWith("BT-"));
    if (!legacyIds.length) {
      setDeepCompareLegacyRuns([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const results = await Promise.all(
          legacyIds.map(async (legacyId) => {
            try {
              return await apiGet<BacktestRun>(`/api/v1/backtests/runs/${encodeURIComponent(legacyId)}`);
            } catch {
              return null;
            }
          }),
        );
        if (!cancelled) {
          setDeepCompareLegacyRuns(results.filter((x): x is BacktestRun => Boolean(x)));
        }
      } catch {
        if (!cancelled) setDeepCompareLegacyRuns([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [catalogComparePreview]);

  useEffect(() => {
    const symbols = MARKET_OPTIONS[form.market];
    if (!symbols.includes(form.symbol)) {
      setForm((prev) => ({ ...prev, symbol: symbols[0] }));
    }
  }, [form.market, form.symbol]);

  const refreshMassPayload = useCallback(
    async (runId: string, onlyPass = massOnlyPass) => {
      if (!runId) return;
      const [status, results, artifacts] = await Promise.all([
        apiGet<MassBacktestStatusResponse>(`/api/v1/research/mass-backtest/status?run_id=${encodeURIComponent(runId)}`),
        apiGet<MassBacktestResultsResponse>(
          `/api/v1/research/mass-backtest/results?run_id=${encodeURIComponent(runId)}&limit=100${onlyPass ? "&only_pass=true" : ""}`,
        ),
        apiGet<MassBacktestArtifactsResponse>(`/api/v1/research/mass-backtest/artifacts?run_id=${encodeURIComponent(runId)}`),
      ]);
      setMassStatus(status);
      setMassResults(results.results || []);
      setMassArtifacts(artifacts.items || []);
      setMassSelectedRow((prev) => {
        if (!prev) return results.results?.[0] ?? null;
        return (results.results || []).find((row) => row.variant_id === prev.variant_id) || results.results?.[0] || null;
      });
    },
    [massOnlyPass],
  );

  useEffect(() => {
    if (!massRunId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const status = await apiGet<MassBacktestStatusResponse>(`/api/v1/research/mass-backtest/status?run_id=${encodeURIComponent(massRunId)}`);
        if (cancelled) return;
        setMassStatus(status);
        if (status.state === "COMPLETED" || status.state === "FAILED") {
          await refreshMassPayload(massRunId, massOnlyPass);
          return;
        }
      } catch {
        // best effort polling
      }
      if (!cancelled) window.setTimeout(() => void tick(), 1200);
    };
    void tick();
    return () => {
      cancelled = true;
    };
  }, [massRunId, massOnlyPass, refreshMassPayload]);

  const launchRun = async (event: FormEvent) => {
    event.preventDefault();
    setRunning(true);
    try {
      await apiPost("/api/v1/backtests/run", {
        strategy_id: form.strategy_id,
        market: form.market,
        symbol: form.symbol,
        timeframe: form.timeframe,
        start: form.start,
        end: form.end,
        period: { start: form.start, end: form.end },
        universe: [form.symbol],
        costs: {
          fees_bps: Number(form.fees_bps),
          spread_bps: Number(form.spread_bps),
          slippage_bps: Number(form.slippage_bps),
          funding_bps: Number(form.funding_bps),
          rollover_bps: Number(form.rollover_bps),
        },
        validation_mode: form.validation_mode,
      });
      await refresh();
    } finally {
      setRunning(false);
    }
  };

  const toggleRun = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 5) return prev;
      return [...prev, id];
    });
  };

  const toggleMassStrategy = (id: string) => {
    setMassSelectedStrategies((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleCatalogCompare = async (runId: string) => {
    const next = catalogCompareIds.includes(runId)
      ? catalogCompareIds.filter((x) => x !== runId)
      : [...catalogCompareIds, runId].slice(0, 10);
    setCatalogCompareIds(next);
    if (!next.length) {
      setCatalogComparePreview(null);
      return;
    }
    try {
      const qs = next.map((id) => `r=${encodeURIComponent(id)}`).join("&");
      const payload = await apiGet<BacktestCompareResponse>(`/api/v1/compare?${qs}`);
      setCatalogComparePreview(payload);
    } catch {
      setCatalogComparePreview(null);
    }
  };

  const patchCatalogRun = async (runId: string, patch: { alias?: string | null; tags?: string[]; pinned?: boolean; archived?: boolean }) => {
    try {
      await apiPatch<{ ok: boolean; run: BacktestCatalogRun }>(`/api/v1/runs/${encodeURIComponent(runId)}`, patch);
      await refreshCatalogRuns();
      await refreshCatalogRankings();
      await refreshCatalogBatches();
    } catch (err) {
      setCatalogError(err instanceof Error ? err.message : "No se pudo actualizar metadata del run.");
    }
  };

  const promptAliasCatalogRun = (row: BacktestCatalogRun) => {
    const next = window.prompt("Alias del run (opcional). El ID estructurado no cambia.", row.alias || "");
    if (next === null) return;
    void patchCatalogRun(row.run_id, { alias: next || null });
  };

  const inferBaselineForCandidate = (candidateRunId: string): string | undefined => {
    const selectedOther = catalogCompareIds.find((id) => id !== candidateRunId);
    if (selectedOther) return selectedOther;
    const fromPreview = (catalogComparePreview?.items || []).find((row) => row.run_id !== candidateRunId);
    return fromPreview?.run_id;
  };

  const validateRunPromotion = async (row: BacktestCatalogRun, targetMode: "paper" | "testnet" | "live" = "paper") => {
    setPromotionBusyRunId(row.run_id);
    setPromotionError("");
    setPromotionMessage("");
    try {
      const baseline_run_id = inferBaselineForCandidate(row.run_id);
      const payload = await apiPost<RunValidatePromotionResponse>(`/api/v1/runs/${encodeURIComponent(row.run_id)}/validate_promotion`, {
        baseline_run_id,
        target_mode: targetMode,
      });
      setPromotionPreview(payload);
      if (payload.rollout_ready) {
        setPromotionMessage(`Validación OK: ${row.run_id} listo para iniciar rollout (Opción B, sin auto-live).`);
      } else {
        setPromotionError(`Validación no apta para rollout: revisar constraints/gates/compare (${row.run_id}).`);
      }
    } catch (err) {
      setPromotionError(err instanceof Error ? err.message : "No se pudo validar el run para promoción.");
    } finally {
      setPromotionBusyRunId(null);
    }
  };

  const promoteRunToRollout = async (row: BacktestCatalogRun, targetMode: "paper" | "testnet" | "live" = "paper") => {
    setPromotionBusyRunId(row.run_id);
    setPromotionError("");
    setPromotionMessage("");
    try {
      const baseline_run_id = inferBaselineForCandidate(row.run_id);
      const payload = await apiPost<RunValidatePromotionResponse>(`/api/v1/runs/${encodeURIComponent(row.run_id)}/promote`, {
        baseline_run_id,
        target_mode: targetMode,
        note: "Promovido desde Backtests / Runs (Opción B)",
      });
      setPromotionPreview(payload);
      setPromotionMessage(`Rollout iniciado desde ${row.run_id}. Siguiente paso: Settings -> Rollout / Gates.`);
      await Promise.all([refreshCatalogRuns(), refreshCatalogRankings(), refreshCatalogBatches()]);
    } catch (err) {
      setPromotionError(err instanceof Error ? err.message : "No se pudo promover el run a rollout.");
    } finally {
      setPromotionBusyRunId(null);
    }
  };

  const startMassBacktests = async () => {
    if (!massSelectedStrategies.length) {
      setMassError("Seleccioná al menos una estrategia para research masivo.");
      return;
    }
    setMassRunning(true);
    setMassError("");
    setMassMessage("");
    try {
      const res = await apiPost<{ ok: boolean; run_id: string; state: string }>("/api/v1/research/mass-backtest/start", {
        strategy_ids: massSelectedStrategies,
        market: form.market,
        symbol: form.symbol,
        timeframe: form.timeframe,
        start: form.start,
        end: form.end,
        dataset_source: massForm.dataset_source,
        validation_mode: form.validation_mode,
        max_variants_per_strategy: Number(massForm.max_variants_per_strategy),
        max_folds: Number(massForm.max_folds),
        train_days: Number(massForm.train_days),
        test_days: Number(massForm.test_days),
        top_n: Number(massForm.top_n),
        seed: Number(massForm.seed),
        costs: {
          fees_bps: Number(form.fees_bps),
          spread_bps: Number(form.spread_bps),
          slippage_bps: Number(form.slippage_bps),
          funding_bps: Number(form.funding_bps),
          rollover_bps: Number(form.rollover_bps),
        },
      });
      setMassRunId(res.run_id);
      setMassMessage(`Research masivo iniciado: ${res.run_id}`);
      await refreshMassPayload(res.run_id, massOnlyPass).catch(() => undefined);
    } catch (err) {
      setMassError(err instanceof Error ? err.message : "No se pudo iniciar research masivo.");
    } finally {
      setMassRunning(false);
    }
  };

  const refreshMass = async () => {
    if (!massRunId) return;
    try {
      await refreshMassPayload(massRunId, massOnlyPass);
    } catch (err) {
      setMassError(err instanceof Error ? err.message : "No se pudo refrescar research masivo.");
    }
  };

  const markMassCandidate = async (row: MassBacktestResultRow) => {
    try {
      const res = await apiPost<{ ok: boolean; recommendation_draft: { id: string } }>("/api/v1/research/mass-backtest/mark-candidate", {
        run_id: massRunId,
        variant_id: row.variant_id,
        note: "Marcado desde Backtests / Research Masivo",
      });
      setMassMessage(`Draft Opción B creado: ${res.recommendation_draft.id}`);
    } catch (err) {
      setMassError(err instanceof Error ? err.message : "No se pudo marcar candidato.");
    }
  };

  const selectedRuns = runs.filter((run) => selected.includes(run.id)).slice(0, 5);
  const focusRun = selectedRuns[0] || runs[0] || null;

  const tradeStatsForRun = (run: BacktestRun | null) => {
    if (!run) {
      return { totalEntries: 0, totalExits: 0, totalRoundtrips: 0, tradeCount: 0 };
    }
    const fallbackCount = run.trades?.length || 0;
    const totalEntries = run.metrics.total_entries ?? fallbackCount;
    const totalExits = run.metrics.total_exits ?? fallbackCount;
    const totalRoundtrips = run.metrics.total_roundtrips ?? Math.min(totalEntries, totalExits);
    const tradeCount = run.metrics.trade_count ?? fallbackCount;
    return { totalEntries, totalExits, totalRoundtrips, tradeCount };
  };

  const focusTradeStats = tradeStatsForRun(focusRun);

  const consistency = useMemo(() => {
    if (selectedRuns.length < 2) return null;
    const periods = new Set(selectedRuns.map((run) => `${run.period.start}|${run.period.end}`));
    const universes = new Set(selectedRuns.map((run) => [...run.universe].sort().join(",")));
    const costs = new Set(
      selectedRuns.map(
        (run) =>
          `${run.costs_model.fees_bps}|${run.costs_model.spread_bps}|${run.costs_model.slippage_bps}|${run.costs_model.funding_bps}`,
      ),
    );
    return {
      samePeriod: periods.size === 1,
      sameUniverse: universes.size === 1,
      sameCosts: costs.size === 1,
    };
  }, [selectedRuns]);

  const overlayData = useMemo(() => {
    if (!selectedRuns.length) return [];
    const map = new Map<number, Record<string, number | string>>();
    selectedRuns.forEach((run) => {
      run.equity_curve.forEach((point, idx) => {
        const row = map.get(idx) || { index: idx };
        row[run.id] = point.equity;
        map.set(idx, row);
      });
    });
    return [...map.values()];
  }, [selectedRuns]);

  const overlayDDData = useMemo(() => {
    if (!selectedRuns.length) return [];
    const map = new Map<number, Record<string, number | string>>();
    selectedRuns.forEach((run) => {
      run.equity_curve.forEach((point, idx) => {
        const row = map.get(idx) || { index: idx };
        row[run.id] = point.drawdown;
        map.set(idx, row);
      });
    });
    return [...map.values()];
  }, [selectedRuns]);

  const catalogShortlist = catalogRuns.slice(0, 10);
  const recentBatches = catalogBatches.slice(0, 8);
  const batchChildrenCount = catalogRuns.filter((r) => r.run_type === "batch_child").length;
  const quickRunsCount = catalogRuns.filter((r) => r.run_type !== "batch_child").length;
  const catalogProRows = catalogRuns.slice(0, Number(catalogProLimit));

  const rankingPresets = useMemo(() => {
    const rows = [...catalogRuns];
    const byMetric = (id: string, label: string, sorter: (a: BacktestCatalogRun, b: BacktestCatalogRun) => number) => ({
      id,
      label,
      items: [...rows].sort(sorter).slice(0, 10),
    });
    const num = (r: BacktestCatalogRun, key: keyof CatalogRunKpis) => Number((r.kpis || {})[key] ?? 0);
    return [
      byMetric("top_retorno", "Top Retorno", (a, b) => num(b, "return_total") - num(a, "return_total")),
      byMetric("top_sharpe", "Top Sharpe", (a, b) => num(b, "sharpe") - num(a, "sharpe")),
      byMetric("top_sortino", "Top Sortino", (a, b) => num(b, "sortino") - num(a, "sortino")),
      byMetric("top_pf", "Top PF", (a, b) => num(b, "profit_factor") - num(a, "profit_factor")),
      byMetric("top_expectancy", "Top Expectancy", (a, b) => num(b, "expectancy_value") - num(a, "expectancy_value")),
      byMetric("top_winrate", "Top WinRate", (a, b) => num(b, "winrate") - num(a, "winrate")),
      byMetric("top_calmar", "Top Calmar", (a, b) => num(b, "calmar") - num(a, "calmar")),
      byMetric("top_cost_aware", "Top Cost-aware", (a, b) => num(a, "costs_ratio") - num(b, "costs_ratio")),
    ];
  }, [catalogRuns]);

  const selectedRankingPresetPreview = rankingPresets.find((p) => p.id === `top_${catalogRankingPreset}`) || null;

  const deepCompareRows = (catalogComparePreview?.items || []).slice(0, 4);
  const deepCompareEquityOverlay = useMemo(() => {
    if (!deepCompareLegacyRuns.length) return [];
    const map = new Map<number, Record<string, number | string>>();
    deepCompareLegacyRuns.forEach((run) => {
      run.equity_curve.forEach((point, idx) => {
        const row = map.get(idx) || { index: idx };
        row[run.id] = point.equity;
        map.set(idx, row);
      });
    });
    return [...map.values()];
  }, [deepCompareLegacyRuns]);

  const deepCompareDdOverlay = useMemo(() => {
    if (!deepCompareLegacyRuns.length) return [];
    const map = new Map<number, Record<string, number | string>>();
    deepCompareLegacyRuns.forEach((run) => {
      run.equity_curve.forEach((point, idx) => {
        const row = map.get(idx) || { index: idx };
        row[run.id] = point.drawdown;
        map.set(idx, row);
      });
    });
    return [...map.values()];
  }, [deepCompareLegacyRuns]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Quick Backtest</CardTitle>
        <CardDescription>Corrida rápida (single) para validar una estrategia y generar un Backtest Run auditable.</CardDescription>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" onSubmit={launchRun}>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Estrategia</label>
              <Select value={form.strategy_id} onChange={(e) => setForm((prev) => ({ ...prev, strategy_id: e.target.value }))}>
                {strategies.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name} v{row.version}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Mercado</label>
              <Select value={form.market} onChange={(e) => setForm((prev) => ({ ...prev, market: e.target.value as RunForm["market"] }))}>
                <option value="crypto">crypto</option>
                <option value="forex">forex</option>
                <option value="equities">equities</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Simbolo</label>
              <Select value={form.symbol} onChange={(e) => setForm((prev) => ({ ...prev, symbol: e.target.value }))}>
                {MARKET_OPTIONS[form.market].map((sym) => (
                  <option key={sym} value={sym}>
                    {sym}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Timeframe</label>
              <Select value={form.timeframe} onChange={(e) => setForm((prev) => ({ ...prev, timeframe: e.target.value as RunForm["timeframe"] }))}>
                <option value="5m">5m</option>
                <option value="10m">10m</option>
                <option value="15m">15m</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Desde</label>
              <Input type="date" value={form.start} onChange={(e) => setForm((prev) => ({ ...prev, start: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Hasta</label>
              <Input type="date" value={form.end} onChange={(e) => setForm((prev) => ({ ...prev, end: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Rollover bps</label>
              <Input value={form.rollover_bps} onChange={(e) => setForm((prev) => ({ ...prev, rollover_bps: e.target.value }))} />
            </div>

            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Fees bps</label>
              <Input value={form.fees_bps} onChange={(e) => setForm((prev) => ({ ...prev, fees_bps: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Spread bps</label>
              <Input value={form.spread_bps} onChange={(e) => setForm((prev) => ({ ...prev, spread_bps: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Slippage bps</label>
              <Input value={form.slippage_bps} onChange={(e) => setForm((prev) => ({ ...prev, slippage_bps: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Funding bps</label>
              <Input value={form.funding_bps} onChange={(e) => setForm((prev) => ({ ...prev, funding_bps: e.target.value }))} />
            </div>

            <div className="space-y-1 xl:col-span-2">
              <label className="text-xs uppercase tracking-wide text-slate-400">Validacion</label>
              <Select
                value={form.validation_mode}
                onChange={(e) => setForm((prev) => ({ ...prev, validation_mode: e.target.value as RunForm["validation_mode"] }))}
              >
                <option value="walk-forward">Walk-Forward</option>
                <option value="purged-cv">Purged CV</option>
                <option value="cpcv">CPCV</option>
              </Select>
            </div>
            <div className="xl:col-span-2 flex items-end">
              <Button disabled={role !== "admin" || running}>{running ? "Corriendo..." : "Ejecutar Quick Backtest"}</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>¿Qué usa este modo?</CardTitle>
        <CardDescription>Quick Backtest y Research Batch comparten identidad de runs; el batch es un contenedor que genera muchos runs.</CardDescription>
        <CardContent className="grid gap-3 xl:grid-cols-2">
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Quick Backtest (Single Backtest Run)</p>
            <p className="mt-2 text-sm text-slate-200">Usa el motor de simulacion normal con tus costos/config del formulario. Ideal para iterar rapido y comparar pocos runs.</p>
            <div className="mt-2 space-y-1 text-xs text-slate-400">
              <p>Motor: simulacion del backend actual</p>
              <p>Datos: fuente configurada (real si existe / fallback)</p>
              <p>Metricas: KPIs + costos netos + artifacts</p>
              <p>Cuando usarlo: validar una idea puntual o rerun exacto</p>
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Research Batch (Batch Experiment)</p>
            <p className="mt-2 text-sm text-slate-200">Lanza variantes/estrategias en lote (research offline) y genera multiples Backtest Runs hijos con score robusto y evidencia por regimen.</p>
            <div className="mt-2 space-y-1 text-xs text-slate-400">
              <p>Motor: Mass Backtest Engine (research)</p>
              <p>Datos: dataset mode recomendado (publicos + hash)</p>
              <p>Metricas: walk-forward, robustez, costos, ranking</p>
              <p>Cuando usarlo: comparar muchas variantes y producir candidatos (Opcion B)</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Backtests / Runs</CardTitle>
        <CardDescription>
          Lista unificada de runs (Quick + Research Batch child) con identidad estructurada, filtros, chips y metadata reproducible.
        </CardDescription>
        <CardContent className="space-y-4">
          {catalogError ? <p className="text-sm text-rose-300">{catalogError}</p> : null}

          <div className="grid gap-3 xl:grid-cols-6">
            <div className="space-y-1 xl:col-span-2">
              <label className="text-xs uppercase tracking-wide text-slate-400">Buscar</label>
              <Input
                placeholder="Run ID, alias, estrategia, tag, commit, dataset hash..."
                value={catalogFilters.q}
                onChange={(e) => setCatalogFilters((p) => ({ ...p, q: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Tipo</label>
              <Select value={catalogFilters.run_type} onChange={(e) => setCatalogFilters((p) => ({ ...p, run_type: e.target.value as RunsListFilters["run_type"] }))}>
                <option value="">Todos</option>
                <option value="single">Quick Backtest</option>
                <option value="batch_child">Research Batch child</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Estado</label>
              <Select value={catalogFilters.status} onChange={(e) => setCatalogFilters((p) => ({ ...p, status: e.target.value }))}>
                <option value="">Todos</option>
                <option value="queued">Queued</option>
                <option value="preparing">Preparing</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="completed_warn">Completed_warn</option>
                <option value="failed">Failed</option>
                <option value="canceled">Canceled</option>
                <option value="archived">Archived</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Estrategia</label>
              <Select value={catalogFilters.strategy_id} onChange={(e) => setCatalogFilters((p) => ({ ...p, strategy_id: e.target.value }))}>
                <option value="">Todas</option>
                {strategies.map((row) => (
                  <option key={`cat-filter-st-${row.id}`} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">TF</label>
              <Select value={catalogFilters.timeframe} onChange={(e) => setCatalogFilters((p) => ({ ...p, timeframe: e.target.value }))}>
                <option value="">Todos</option>
                <option value="5m">5m</option>
                <option value="10m">10m</option>
                <option value="15m">15m</option>
              </Select>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-8">
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Simbolo</label>
              <Input value={catalogFilters.symbol} onChange={(e) => setCatalogFilters((p) => ({ ...p, symbol: e.target.value.toUpperCase() }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Min Trades</label>
              <Input value={catalogFilters.min_trades} onChange={(e) => setCatalogFilters((p) => ({ ...p, min_trades: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Max DD</label>
              <Input value={catalogFilters.max_dd} onChange={(e) => setCatalogFilters((p) => ({ ...p, max_dd: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Sharpe &gt;=</label>
              <Input value={catalogFilters.sharpe} onChange={(e) => setCatalogFilters((p) => ({ ...p, sharpe: e.target.value }))} />
            </div>
            <div className="space-y-1 xl:col-span-2">
              <label className="text-xs uppercase tracking-wide text-slate-400">Ordenar por</label>
              <Select value={catalogFilters.sort_by} onChange={(e) => setCatalogFilters((p) => ({ ...p, sort_by: e.target.value as RunsListFilters["sort_by"] }))}>
                <option value="created_at">Recientes</option>
                <option value="score">Score</option>
                <option value="return">Retorno</option>
                <option value="sharpe">Sharpe</option>
                <option value="sortino">Sortino</option>
                <option value="dd">Max DD</option>
                <option value="pf">Profit Factor</option>
                <option value="expectancy">Expectancy</option>
                <option value="trades">Trades</option>
                <option value="strategy">Estrategia</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Direccion</label>
              <Select value={catalogFilters.sort_dir} onChange={(e) => setCatalogFilters((p) => ({ ...p, sort_dir: e.target.value as "asc" | "desc" }))}>
                <option value="desc">Desc</option>
                <option value="asc">Asc</option>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button type="button" variant="outline" onClick={() => void refreshCatalogRuns()} disabled={catalogLoading}>
                {catalogLoading ? "Cargando..." : "Aplicar filtros"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setCatalogFilters({
                    q: "",
                    run_type: "",
                    status: "",
                    strategy_id: "",
                    symbol: "",
                    timeframe: "",
                    min_trades: "",
                    max_dd: "",
                    sharpe: "",
                    sort_by: "created_at",
                    sort_dir: "desc",
                  });
                }}
              >
                Limpiar
              </Button>
            </div>
          </div>

          <div className="grid gap-3 xl:grid-cols-3">
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Resumen de Runs</p>
              <p className="mt-2 text-sm text-slate-200">
                Total filtrados: <span className="font-semibold">{catalogRunCount}</span>
              </p>
              <p className="text-xs text-slate-400">Quick Backtest: {quickRunsCount} | Research Batch child: {batchChildrenCount}</p>
              <p className="mt-2 text-xs text-slate-400">
                Comparador catalogo: {catalogCompareIds.length} seleccionados {catalogComparePreview ? `| same_dataset: ${catalogComparePreview.same_dataset ? "si" : "no"}` : ""}
              </p>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">Ranking (preset)</p>
                <Select value={catalogRankingPreset} onChange={(e) => setCatalogRankingPreset(e.target.value)}>
                  <option value="conservador">Conservador</option>
                  <option value="balanceado">Balanceado</option>
                  <option value="agresivo">Agresivo</option>
                  <option value="cost-aware">Cost-aware</option>
                  <option value="oos-first">OOS-first</option>
                </Select>
              </div>
              <div className="mt-2 flex gap-2">
                <Button type="button" variant="outline" onClick={() => void refreshCatalogRankings()}>
                  Recalcular ranking
                </Button>
              </div>
              <div className="mt-2 space-y-1 text-xs text-slate-300">
                {(catalogRankings?.items || []).slice(0, 3).map((row) => (
                  <p key={`rank-top-${row.run_id}`}>
                    #{row.rank ?? "-"} {row.run_id} · {row.strategy_name} · score {fmtNum(row.composite_score ?? 0)}
                  </p>
                ))}
                {!catalogRankings?.items?.length ? <p className="text-slate-400">Sin ranking disponible.</p> : null}
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Research Batches recientes</p>
              <div className="mt-2 space-y-1 text-xs text-slate-300">
                {recentBatches.length ? (
                  recentBatches.map((b) => (
                    <p key={`batch-mini-${b.batch_id}`}>
                      {b.batch_id} · {b.status} · {b.run_count_done}/{b.run_count_total}
                    </p>
                  ))
                ) : (
                  <p className="text-slate-400">Sin batches registrados.</p>
                )}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/40">
            <Table>
              <THead>
                <TR>
                  <TH>Comparar</TH>
                  <TH>Run ID</TH>
                  <TH>Tipo</TH>
                  <TH>Estado</TH>
                  <TH>Fecha</TH>
                  <TH>Estrategia</TH>
                  <TH>Mercado / TF</TH>
                  <TH>Rango</TH>
                  <TH>Dataset</TH>
                  <TH>Cost model</TH>
                  <TH>KPIs</TH>
                  <TH>Chips</TH>
                  <TH>Acciones</TH>
                </TR>
              </THead>
              <TBody>
                {catalogShortlist.map((row) => {
                  const symbols = row.symbols?.join(", ") || "-";
                  const tfs = row.timeframes?.join(", ") || "-";
                  const k = row.kpis || {};
                  const flags = (row.flags || {}) as Record<string, unknown>;
                  const expectancyValue = typeof k.expectancy_value === "number" ? k.expectancy_value : k.expectancy;
                  return (
                    <TR key={row.run_id}>
                      <TD>
                        <input
                          type="checkbox"
                          checked={catalogCompareIds.includes(row.run_id)}
                          onChange={() => void toggleCatalogCompare(row.run_id)}
                        />
                      </TD>
                      <TD className="align-top">
                        <p className="font-mono text-xs text-slate-100">{row.run_id}</p>
                        {row.alias ? <p className="text-xs text-cyan-300">{row.alias}</p> : null}
                      </TD>
                      <TD className="text-xs">{runTypeLabel(row.run_type)}</TD>
                      <TD>
                        <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                      </TD>
                      <TD className="text-xs">{compactDate(row.created_at)}</TD>
                      <TD className="align-top">
                        <p className="text-xs text-slate-200">{row.strategy_name}</p>
                        <p className="text-xs text-slate-400">{row.strategy_id} · v{row.strategy_version}</p>
                      </TD>
                      <TD className="text-xs">
                        {symbols}
                        <br />
                        <span className="text-slate-400">{tfs}</span>
                      </TD>
                      <TD className="text-xs">
                        {row.timerange_from} → {row.timerange_to}
                      </TD>
                      <TD className="text-xs">
                        <p>{row.dataset_source}</p>
                        <p className="font-mono text-slate-400">{shortHash(row.dataset_hash, 12)}</p>
                        <p className="font-mono text-slate-500">git {shortHash(row.code_commit_hash, 8)}</p>
                      </TD>
                      <TD className="text-xs">
                        <p>Fee {parseFeePctLabel(row.fee_model)}</p>
                        <p className="text-slate-400">{row.spread_model}</p>
                        <p className="text-slate-400">{row.slippage_model}</p>
                      </TD>
                      <TD className="text-xs">
                        <p>Ret {fmtPct((k.return_total as number | undefined) ?? (k.cagr as number | undefined) ?? 0)}</p>
                        <p>DD {fmtPct((k.max_dd as number | undefined) ?? 0)}</p>
                        <p>Sharpe {fmtNum((k.sharpe as number | undefined) ?? 0)} · PF {fmtNum((k.profit_factor as number | undefined) ?? 0)}</p>
                        <p>WR {fmtPct((k.winrate as number | undefined) ?? 0)} · Trades {fmtNum((k.trade_count as number | undefined) ?? (k.roundtrips as number | undefined) ?? 0)}</p>
                        <p>
                          Exp {fmtNum((expectancyValue as number | undefined) ?? 0)} {String(k.expectancy_unit || "")}
                        </p>
                      </TD>
                      <TD className="text-xs">
                        <div className="flex max-w-[200px] flex-wrap gap-1">
                          {row.pinned ? <Badge variant="success">PIN</Badge> : null}
                          {row.batch_id ? <Badge variant="warn">{row.batch_id}</Badge> : null}
                          {Object.entries(flags)
                            .filter(([, v]) => Boolean(v))
                            .slice(0, 4)
                            .map(([key]) => (
                              <Badge key={`${row.run_id}-flag-${key}`} variant={key === "DATA_WARNING" ? "danger" : "warn"}>
                                {key}
                              </Badge>
                            ))}
                        </div>
                      </TD>
                      <TD className="align-top">
                        <div className="flex flex-col gap-1">
                          <Button type="button" variant="outline" onClick={() => void toggleCatalogCompare(row.run_id)}>
                            {catalogCompareIds.includes(row.run_id) ? "Quitar" : "Comparar"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => void validateRunPromotion(row, "paper")}
                            disabled={role !== "admin" || promotionBusyRunId === row.run_id}
                          >
                            {promotionBusyRunId === row.run_id ? "Validando..." : "Validar"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => void promoteRunToRollout(row, "paper")}
                            disabled={role !== "admin" || promotionBusyRunId === row.run_id}
                          >
                            {promotionBusyRunId === row.run_id ? "Procesando..." : "Promover"}
                          </Button>
                          <Button type="button" variant="outline" onClick={() => promptAliasCatalogRun(row)} disabled={role !== "admin"}>
                            Alias
                          </Button>
                          <Button type="button" variant="outline" onClick={() => void patchCatalogRun(row.run_id, { pinned: !row.pinned })} disabled={role !== "admin"}>
                            {row.pinned ? "Desfijar" : "Fijar"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => void patchCatalogRun(row.run_id, { archived: row.status !== "archived" })}
                            disabled={role !== "admin"}
                          >
                            {row.status === "archived" ? "Desarchivar" : "Archivar"}
                          </Button>
                        </div>
                      </TD>
                    </TR>
                  );
                })}
                {!catalogShortlist.length ? (
                  <TR>
                    <TD colSpan={13} className="py-6 text-center text-sm text-slate-400">
                      Sin runs en el catalogo con estos filtros.
                    </TD>
                  </TR>
                ) : null}
              </TBody>
            </Table>
          </div>
          <p className="text-xs text-slate-400">Vista de shortlist (10 filas) para revisión rápida. Debajo tenés el comparador profesional del Bloque 4.</p>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Comparador Profesional (Runs)</CardTitle>
        <CardDescription>
          3 capas: shortlist (rápida), tabla pro (hasta 500 en esta fase) y deep compare (2-4 runs). Ranking con constraints para evitar ganadores truchos.
        </CardDescription>
        <CardContent className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 xl:col-span-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">D1 · Shortlist (selección rápida)</p>
                <Badge variant="warn">{catalogCompareIds.length}/10 seleccionados</Badge>
              </div>
              {catalogComparePreview?.warnings?.length ? (
                <div className="mt-2 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
                  Warnings: {catalogComparePreview.warnings.join(" | ")}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                {deepCompareRows.length ? (
                  deepCompareRows.map((row) => (
                    <button
                      key={`cmp-chip-${row.run_id}`}
                      type="button"
                      onClick={() => void toggleCatalogCompare(row.run_id)}
                      className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200"
                    >
                      {row.run_id} · {row.strategy_name} · S {fmtNum(Number((row.kpis || {}).sharpe || 0))}
                    </button>
                  ))
                ) : (
                  <p className="text-sm text-slate-400">Seleccioná runs en la lista para comparar.</p>
                )}
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Ranking predefinido + constraints</p>
              <div className="mt-2 grid gap-2">
                <Select value={catalogRankingPreset} onChange={(e) => setCatalogRankingPreset(e.target.value)}>
                  <option value="conservador">Conservador (score compuesto)</option>
                  <option value="balanceado">Balanceado (score compuesto)</option>
                  <option value="agresivo">Agresivo (score compuesto)</option>
                  <option value="cost-aware">Cost-aware (score compuesto)</option>
                  <option value="oos-first">OOS-first (score compuesto)</option>
                </Select>
                <label className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/40 px-2 py-2 text-xs">
                  <input type="checkbox" checked={catalogRankRequireOos} onChange={(e) => setCatalogRankRequireOos(e.target.checked)} />
                  OOS/WFA pass (si aplica)
                </label>
                <label className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/40 px-2 py-2 text-xs">
                  <input type="checkbox" checked={catalogRankDataQualityOk} onChange={(e) => setCatalogRankDataQualityOk(e.target.checked)} />
                  data_quality = ok (sin DATA_WARNING)
                </label>
                <Button type="button" variant="outline" onClick={() => void refreshCatalogRankings()}>
                  Recalcular ranking (constraints)
                </Button>
              </div>
              <div className="mt-3 space-y-1 text-xs text-slate-300">
                {(catalogRankings?.items || []).slice(0, 5).map((row) => (
                  <p key={`ranking-side-${row.run_id}`}>
                    #{row.rank ?? "-"} {row.run_id} · {fmtNum(row.composite_score ?? 0)}
                  </p>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Research → Validate → Promote (Opción B)</p>
            <p className="mt-1 text-xs text-slate-400">
              Validá un run con constraints + offline gates + compare vs baseline y, si pasa, iniciá rollout (sin auto-live). El LIVE real sigue con canary + rollback + approve.
            </p>
            {promotionMessage ? <p className="mt-2 text-sm text-emerald-300">{promotionMessage}</p> : null}
            {promotionError ? <p className="mt-2 text-sm text-rose-300">{promotionError}</p> : null}
            {promotionPreview ? (
              <div className="mt-3 grid gap-3 xl:grid-cols-3">
                <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs">
                  <p className="font-semibold text-slate-200">Candidato</p>
                  <p className="font-mono">{promotionPreview.candidate?.run_id}</p>
                  <p>{promotionPreview.candidate?.strategy_name}</p>
                  <p className="text-slate-400">dataset {shortHash(promotionPreview.candidate?.dataset_hash, 12)}</p>
                </div>
                <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs">
                  <p className="font-semibold text-slate-200">Baseline</p>
                  <p className="font-mono">{promotionPreview.baseline?.run_id}</p>
                  <p>{promotionPreview.baseline?.strategy_name}</p>
                  <p className="text-slate-400">dataset {shortHash(promotionPreview.baseline?.dataset_hash, 12)}</p>
                </div>
                <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs">
                  <p className="font-semibold text-slate-200">Resultado</p>
                  <p>Constraints: {promotionPreview.constraints?.passed ? "PASS" : "FAIL"}</p>
                  <p>Offline gates: {promotionPreview.offline_gates?.passed ? "PASS" : "FAIL"}</p>
                  <p>Compare vs baseline: {promotionPreview.compare_vs_baseline?.passed ? "PASS" : "FAIL"}</p>
                  <p>Rollout ready: {promotionPreview.rollout_ready ? "Sí" : "No"}</p>
                  <p className="text-slate-400">No auto-live: {promotionPreview.option_b_no_auto_live ? "Sí" : "No"}</p>
                </div>

                <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs xl:col-span-1">
                  <p className="font-semibold text-slate-200">Constraints</p>
                  {(promotionPreview.constraints?.checks || []).map((check) => (
                    <p key={`promo-c-${check.id}`} className={check.ok ? "text-emerald-200" : "text-rose-200"}>
                      {check.ok ? "PASS" : "FAIL"} · {check.id}
                    </p>
                  ))}
                </div>
                <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs xl:col-span-1">
                  <p className="font-semibold text-slate-200">Offline Gates</p>
                  {(promotionPreview.offline_gates?.checks || []).slice(0, 8).map((check) => (
                    <p key={`promo-g-${check.id}`} className={check.ok ? "text-emerald-200" : "text-rose-200"}>
                      {check.ok ? "PASS" : "FAIL"} · {check.id}
                    </p>
                  ))}
                </div>
                <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs xl:col-span-1">
                  <p className="font-semibold text-slate-200">Compare vs Baseline</p>
                  {(promotionPreview.compare_vs_baseline?.checks || []).map((check) => (
                    <p key={`promo-b-${check.id}`} className={check.ok ? "text-emerald-200" : "text-rose-200"}>
                      {check.ok ? "PASS" : "FAIL"} · {check.id}
                    </p>
                  ))}
                  {promotionPreview.rollout?.next_step ? <p className="mt-2 text-cyan-300">{promotionPreview.rollout.next_step}</p> : null}
                </div>
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">D2 · Comparison Table Pro (50–500+)</p>
                <p className="text-xs text-slate-400">
                  Fase actual: server-side filtros/sort + tabla amplia. Virtualización dedicada queda para el siguiente bloque.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-xs text-slate-300">Filas visibles</label>
                <Select value={catalogProLimit} onChange={(e) => setCatalogProLimit(e.target.value as "50" | "100" | "250" | "500")}>
                  <option value="50">50</option>
                  <option value="100">100</option>
                  <option value="250">250</option>
                  <option value="500">500</option>
                </Select>
              </div>
            </div>

            <div className="mt-3 grid gap-2 md:grid-cols-5">
              {[
                ["run", "Run"],
                ["strategy", "Estrategia"],
                ["status", "Estado"],
                ["dates", "Fechas"],
                ["market", "Mercado/TF"],
                ["dataset", "Dataset"],
                ["costs", "Costos"],
                ["kpis", "KPIs"],
                ["flags", "Chips"],
                ["rank", "Score/Rank"],
              ].map(([key, label]) => (
                <label key={`col-toggle-${key}`} className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/40 px-2 py-1 text-xs">
                  <input
                    type="checkbox"
                    checked={Boolean(catalogTableColumns[key])}
                    onChange={(e) => setCatalogTableColumns((prev) => ({ ...prev, [key]: e.target.checked }))}
                  />
                  {label}
                </label>
              ))}
            </div>

            <div className="mt-3 overflow-x-auto">
              <Table>
                <THead>
                  <TR>
                    <TH>Cmp</TH>
                    {catalogTableColumns.run ? <TH>Run</TH> : null}
                    {catalogTableColumns.strategy ? <TH>Estrategia</TH> : null}
                    {catalogTableColumns.status ? <TH>Estado</TH> : null}
                    {catalogTableColumns.dates ? <TH>Fechas</TH> : null}
                    {catalogTableColumns.market ? <TH>Mercado/TF</TH> : null}
                    {catalogTableColumns.dataset ? <TH>Dataset/Commit</TH> : null}
                    {catalogTableColumns.costs ? <TH>Costos</TH> : null}
                    {catalogTableColumns.kpis ? <TH>KPIs</TH> : null}
                    {catalogTableColumns.rank ? <TH>Score</TH> : null}
                    {catalogTableColumns.flags ? <TH>Flags</TH> : null}
                  </TR>
                </THead>
                <TBody>
                  {catalogProRows.map((row) => {
                    const k = row.kpis || {};
                    const flags = (row.flags || {}) as Record<string, unknown>;
                    const ret = (k.return_total as number | undefined) ?? (k.cagr as number | undefined) ?? 0;
                    const expectancyValue = typeof k.expectancy_value === "number" ? k.expectancy_value : k.expectancy;
                    return (
                      <TR key={`pro-${row.run_id}`}>
                        <TD>
                          <input type="checkbox" checked={catalogCompareIds.includes(row.run_id)} onChange={() => void toggleCatalogCompare(row.run_id)} />
                        </TD>
                        {catalogTableColumns.run ? (
                          <TD className="text-xs">
                            <p className="font-mono">{row.run_id}</p>
                            {row.alias ? <p className="text-cyan-300">{row.alias}</p> : null}
                            {row.batch_id ? <p className="text-slate-400">{row.batch_id}</p> : null}
                          </TD>
                        ) : null}
                        {catalogTableColumns.strategy ? (
                          <TD className="text-xs">
                            <p>{row.strategy_name}</p>
                            <p className="text-slate-400">{row.strategy_version}</p>
                          </TD>
                        ) : null}
                        {catalogTableColumns.status ? (
                          <TD>
                            <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                          </TD>
                        ) : null}
                        {catalogTableColumns.dates ? (
                          <TD className="text-xs">
                            <p>{compactDate(row.created_at)}</p>
                            <p className="text-slate-400">{row.timerange_from} → {row.timerange_to}</p>
                          </TD>
                        ) : null}
                        {catalogTableColumns.market ? (
                          <TD className="text-xs">
                            <p>{(row.symbols || []).join(", ") || "-"}</p>
                            <p className="text-slate-400">{(row.timeframes || []).join(", ") || "-"}</p>
                          </TD>
                        ) : null}
                        {catalogTableColumns.dataset ? (
                          <TD className="text-xs">
                            <p>{row.dataset_source}</p>
                            <p className="font-mono text-slate-400">{shortHash(row.dataset_hash, 12)}</p>
                            <p className="font-mono text-slate-500">git {shortHash(row.code_commit_hash, 8)}</p>
                          </TD>
                        ) : null}
                        {catalogTableColumns.costs ? (
                          <TD className="text-xs">
                            <p>{parseFeePctLabel(row.fee_model)}</p>
                            <p className="text-slate-400">{row.spread_model}</p>
                            <p className="text-slate-400">{row.slippage_model}</p>
                            <p className="text-slate-400">ratio {fmtNum((k.costs_ratio as number | undefined) ?? 0)}</p>
                          </TD>
                        ) : null}
                        {catalogTableColumns.kpis ? (
                          <TD className="text-xs">
                            <div className="grid gap-1">
                              <span className={gradeCellClass("sharpe", k.sharpe as number | undefined)}>Sharpe {fmtNum((k.sharpe as number | undefined) ?? 0)}</span>
                              <span className={gradeCellClass("max_dd", k.max_dd as number | undefined)}>DD {fmtPct((k.max_dd as number | undefined) ?? 0)}</span>
                              <span className={gradeCellClass("winrate", k.winrate as number | undefined)}>WR {fmtPct((k.winrate as number | undefined) ?? 0)}</span>
                              <span>Ret {fmtPct(ret)}</span>
                              <span>PF {fmtNum((k.profit_factor as number | undefined) ?? 0)} · Trades {fmtNum((k.trade_count as number | undefined) ?? (k.roundtrips as number | undefined) ?? 0)}</span>
                              <span>Exp {fmtNum((expectancyValue as number | undefined) ?? 0)} {String(k.expectancy_unit || "")}</span>
                            </div>
                          </TD>
                        ) : null}
                        {catalogTableColumns.rank ? (
                          <TD className="text-xs">
                            <p>Score {fmtNum(row.composite_score ?? 0)}</p>
                            <p className="text-slate-400">Rank {row.rank ?? "-"}</p>
                          </TD>
                        ) : null}
                        {catalogTableColumns.flags ? (
                          <TD className="text-xs">
                            <div className="flex max-w-[180px] flex-wrap gap-1">
                              {Object.entries(flags)
                                .filter(([, v]) => Boolean(v))
                                .slice(0, 6)
                                .map(([key]) => (
                                  <Badge key={`pro-flag-${row.run_id}-${key}`} variant={key === "DATA_WARNING" ? "danger" : "warn"}>
                                    {key}
                                  </Badge>
                                ))}
                            </div>
                          </TD>
                        ) : null}
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 xl:col-span-2">
              <p className="text-xs uppercase tracking-wide text-slate-400">D3 · Deep Compare (2-4 runs)</p>
              <p className="mt-1 text-xs text-slate-400">
                Usa runs del catálogo. Si existe `legacy_json_id`, muestra equity/DD; si no, compara KPIs/costos/régimen igual.
              </p>
              {deepCompareRows.length >= 2 ? (
                <div className="mt-3 space-y-3">
                  {catalogComparePreview && !catalogComparePreview.same_dataset ? (
                    <div className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
                      Warning: datasets distintos ({catalogComparePreview.dataset_hashes.join(", ")}). Comparación útil, pero no “manzanas con manzanas”.
                    </div>
                  ) : null}
                  <div className="overflow-x-auto">
                    <Table>
                      <THead>
                        <TR>
                          <TH>Run</TH>
                          <TH>Retorno</TH>
                          <TH>Max DD</TH>
                          <TH>Sharpe</TH>
                          <TH>Sortino</TH>
                          <TH>Calmar</TH>
                          <TH>PF</TH>
                          <TH>WinRate</TH>
                          <TH>Trades</TH>
                          <TH>Expectancy</TH>
                          <TH>Costs ratio</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {deepCompareRows.map((row) => {
                          const k = row.kpis || {};
                          const ret = (k.return_total as number | undefined) ?? (k.cagr as number | undefined) ?? 0;
                          const expectancyValue = typeof k.expectancy_value === "number" ? k.expectancy_value : k.expectancy;
                          return (
                            <TR key={`deep-kpi-${row.run_id}`}>
                              <TD className="text-xs">
                                <p className="font-mono">{row.run_id}</p>
                                <p className="text-slate-400">{row.strategy_name}</p>
                              </TD>
                              <TD className={gradeCellClass("cagr", ret)}>{fmtPct(ret)}</TD>
                              <TD className={gradeCellClass("max_dd", k.max_dd as number | undefined)}>{fmtPct((k.max_dd as number | undefined) ?? 0)}</TD>
                              <TD className={gradeCellClass("sharpe", k.sharpe as number | undefined)}>{fmtNum((k.sharpe as number | undefined) ?? 0)}</TD>
                              <TD className={gradeCellClass("sortino", k.sortino as number | undefined)}>{fmtNum((k.sortino as number | undefined) ?? 0)}</TD>
                              <TD className={gradeCellClass("calmar", k.calmar as number | undefined)}>{fmtNum((k.calmar as number | undefined) ?? 0)}</TD>
                              <TD>{fmtNum((k.profit_factor as number | undefined) ?? 0)}</TD>
                              <TD className={gradeCellClass("winrate", k.winrate as number | undefined)}>{fmtPct((k.winrate as number | undefined) ?? 0)}</TD>
                              <TD>{fmtNum((k.trade_count as number | undefined) ?? (k.roundtrips as number | undefined) ?? 0)}</TD>
                              <TD className="text-xs">
                                {fmtNum((expectancyValue as number | undefined) ?? 0)} {String(k.expectancy_unit || "")}
                              </TD>
                              <TD>{fmtNum((k.costs_ratio as number | undefined) ?? 0)}</TD>
                            </TR>
                          );
                        })}
                      </TBody>
                    </Table>
                  </div>

                  <div className="grid gap-3 xl:grid-cols-2">
                    <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
                      <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Equity (si hay detalle legacy)</p>
                      {deepCompareEquityOverlay.length ? (
                        <div className="h-56">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={deepCompareEquityOverlay}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                              <XAxis dataKey="index" stroke="#94a3b8" />
                              <YAxis stroke="#94a3b8" />
                              <Tooltip />
                              <Legend />
                              {deepCompareLegacyRuns.map((run, idx) => (
                                <Line
                                  key={`deep-eq-${run.id}`}
                                  type="monotone"
                                  dataKey={run.id}
                                  dot={false}
                                  stroke={chartColors[idx % chartColors.length]}
                                  strokeWidth={2}
                                />
                              ))}
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <p className="text-sm text-slate-400">Sin curvas de equity disponibles para estos runs (probablemente batch children sin detalle legacy).</p>
                      )}
                    </div>
                    <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
                      <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Drawdown (si hay detalle legacy)</p>
                      {deepCompareDdOverlay.length ? (
                        <div className="h-56">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={deepCompareDdOverlay}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                              <XAxis dataKey="index" stroke="#94a3b8" />
                              <YAxis stroke="#94a3b8" />
                              <Tooltip />
                              <Legend />
                              {deepCompareLegacyRuns.map((run, idx) => (
                                <Line
                                  key={`deep-dd-${run.id}`}
                                  type="monotone"
                                  dataKey={run.id}
                                  dot={false}
                                  stroke={chartColors[idx % chartColors.length]}
                                  strokeWidth={2}
                                />
                              ))}
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <p className="text-sm text-slate-400">Sin curvas de drawdown disponibles para estos runs.</p>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-sm text-slate-400">Seleccioná 2 a 4 runs desde “Backtests / Runs” para activar Deep Compare.</p>
              )}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Top predefinidos (métricos, con constraints del filtro)</p>
              <div className="mt-2 space-y-3 text-xs">
                {rankingPresets.map((preset) => (
                  <div key={`metric-preset-${preset.id}`} className="rounded border border-slate-800 bg-slate-950/40 p-2">
                    <p className="font-semibold text-slate-200">{preset.label}</p>
                    {(preset.items || []).slice(0, 3).map((row) => (
                      <p key={`${preset.id}-${row.run_id}`} className="text-slate-300">
                        {row.run_id} · {row.strategy_name}
                      </p>
                    ))}
                    {!preset.items.length ? <p className="text-slate-500">Sin datos</p> : null}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Quick Backtest (Legacy Compare)</CardTitle>
        <CardDescription>Comparador rápido 2-5 corridas del endpoint legacy. El comparador profesional de runs va en el bloque siguiente.</CardDescription>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Comparar</TH>
                <TH>ID</TH>
                <TH>Estado</TH>
                <TH>Duracion</TH>
                <TH>Mercado</TH>
                <TH>Simbolo</TH>
                <TH>TF</TH>
                <TH>Entradas/Salidas</TH>
                <TH>Fuente</TH>
                <TH>Dataset Hash</TH>
                <TH>Commit</TH>
                <TH>Metricas</TH>
                <TH>Exportar</TH>
              </TR>
            </THead>
            <TBody>
              {runs.map((run) => (
                <TR key={run.id}>
                  <TD>
                    <input type="checkbox" checked={selected.includes(run.id)} onChange={() => toggleRun(run.id)} />
                  </TD>
                  <TD>{run.id}</TD>
                  <TD>
                    <Badge variant={run.status === "completed" ? "success" : run.status === "failed" ? "danger" : "warn"}>{run.status}</Badge>
                  </TD>
                  <TD>{run.duration_sec}s</TD>
                  <TD>{run.market || "-"}</TD>
                  <TD>{run.symbol || run.universe?.[0] || "-"}</TD>
                  <TD>{run.timeframe || "-"}</TD>
                  <TD className="text-xs">
                    {tradeStatsForRun(run).totalEntries}/{tradeStatsForRun(run).totalExits} (RT {tradeStatsForRun(run).totalRoundtrips})
                  </TD>
                  <TD className="text-xs">{run.data_source || "-"}</TD>
                  <TD className="font-mono text-xs">{run.dataset_hash}</TD>
                  <TD className="font-mono text-xs">{run.git_commit}</TD>
                  <TD>
                    S:{fmtNum(run.metrics.sharpe)} D:{fmtPct(run.metrics.max_dd)} R:{fmtNum(run.metrics.robust_score)}
                  </TD>
                  <TD>
                    <div className="flex flex-col gap-1 text-xs text-cyan-300">
                      <a href={run.artifacts_links.report_json} className="underline">
                        report.json
                      </a>
                      <a href={run.artifacts_links.trades_csv} className="underline">
                        trades.csv
                      </a>
                      <a href={run.artifacts_links.equity_curve_csv} className="underline">
                        equity_curve.csv
                      </a>
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Research Batch (Backtests Masivos)</CardTitle>
        <CardDescription>
          Ejecuta variantes por estrategia con walk-forward, score robusto y evidencia por régimen. Opción B: genera drafts, no toca LIVE.
        </CardDescription>
        <CardContent className="space-y-4">
          {massMessage ? <p className="text-sm text-emerald-300">{massMessage}</p> : null}
          {massError ? <p className="text-sm text-rose-300">{massError}</p> : null}

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="space-y-3 xl:col-span-2">
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Pool de estrategias (research)</p>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {strategies.map((st) => (
                    <label key={`mass-st-${st.id}`} className="flex items-center justify-between gap-2 rounded border border-slate-800 bg-slate-950/40 px-2 py-1 text-xs">
                      <span className="truncate">{st.name}</span>
                      <input type="checkbox" checked={massSelectedStrategies.includes(st.id)} onChange={() => toggleMassStrategy(st.id)} disabled={role !== "admin"} />
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Variantes/estrategia</label>
                  <Input value={massForm.max_variants_per_strategy} onChange={(e) => setMassForm((p) => ({ ...p, max_variants_per_strategy: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Folds max</label>
                  <Input value={massForm.max_folds} onChange={(e) => setMassForm((p) => ({ ...p, max_folds: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Train días</label>
                  <Input value={massForm.train_days} onChange={(e) => setMassForm((p) => ({ ...p, train_days: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Test días</label>
                  <Input value={massForm.test_days} onChange={(e) => setMassForm((p) => ({ ...p, test_days: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Top N</label>
                  <Input value={massForm.top_n} onChange={(e) => setMassForm((p) => ({ ...p, top_n: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Seed</label>
                  <Input value={massForm.seed} onChange={(e) => setMassForm((p) => ({ ...p, seed: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Dataset source</label>
                  <Select value={massForm.dataset_source} onChange={(e) => setMassForm((p) => ({ ...p, dataset_source: e.target.value }))}>
                    <option value="synthetic">synthetic (rápido)</option>
                    <option value="auto">auto (real si existe)</option>
                  </Select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Filtro ranking</label>
                  <label className="flex h-10 items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 text-sm">
                    <input type="checkbox" checked={massOnlyPass} onChange={(e) => setMassOnlyPass(e.target.checked)} />
                    Solo hard-pass
                  </label>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button disabled={role !== "admin" || massRunning} onClick={startMassBacktests}>
                  {massRunning ? "Iniciando..." : "Ejecutar Backtests Masivos"}
                </Button>
                <Button variant="outline" disabled={!massRunId} onClick={refreshMass}>
                  Refrescar Research Batch
                </Button>
                {massRunId ? <Badge variant="warn">run_id: {massRunId}</Badge> : null}
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Estado</p>
                <div className="mt-2 flex items-center gap-2">
                  <Badge variant={massStatus?.state === "COMPLETED" ? "success" : massStatus?.state === "FAILED" ? "danger" : "warn"}>
                    {massStatus?.state || "IDLE"}
                  </Badge>
                  {typeof massStatus?.progress?.pct === "number" ? <span className="text-sm text-slate-300">{fmtNum(massStatus.progress.pct)}%</span> : null}
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  {massStatus?.progress?.completed_tasks ?? 0}/{massStatus?.progress?.total_tasks ?? 0} tareas
                </p>
                {massStatus?.error ? <p className="mt-2 text-xs text-rose-300 whitespace-pre-wrap">{String(massStatus.error)}</p> : null}
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Logs (últimos)</p>
                <div className="mt-2 max-h-40 space-y-1 overflow-auto text-xs text-slate-300">
                  {(massStatus?.logs || []).slice(-12).map((line, idx) => (
                    <p key={`mass-log-${idx}`} className="break-words">{line}</p>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Artifacts</p>
                <div className="mt-2 space-y-1 text-xs">
                  {massArtifacts.length ? (
                    massArtifacts.map((item) => (
                      <p key={item.name} className="text-slate-300">{item.name} ({item.size} bytes)</p>
                    ))
                  ) : (
                    <p className="text-slate-400">Sin artifacts todavía.</p>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2 overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/50 p-2">
              <Table>
                <THead>
                  <TR>
                    <TH>Rank</TH>
                    <TH>Variante</TH>
                    <TH>Estrategia</TH>
                    <TH>Score</TH>
                    <TH>Trades OOS</TH>
                    <TH>Sharpe</TH>
                    <TH>Calmar</TH>
                    <TH>Expectancy</TH>
                    <TH>MaxDD%</TH>
                    <TH>CostsRatio</TH>
                    <TH>Regímenes</TH>
                    <TH>Acción</TH>
                  </TR>
                </THead>
                <TBody>
                  {massResults.map((row) => (
                    <TR key={row.variant_id} onClick={() => setMassSelectedRow(row)} className="cursor-pointer">
                      <TD>{row.rank ?? "-"}</TD>
                      <TD className="font-mono text-xs">{row.variant_id}</TD>
                      <TD>{row.strategy_name || row.strategy_id}</TD>
                      <TD>{fmtNum(row.score)}</TD>
                      <TD>{row.summary?.trade_count_oos ?? "-"}</TD>
                      <TD>{fmtNum(row.summary?.sharpe_oos ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.calmar_oos ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.expectancy_net_usd ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.max_dd_oos_pct ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.costs_ratio ?? 0)}</TD>
                      <TD>{Object.keys(row.regime_metrics || {}).join(", ") || "-"}</TD>
                      <TD>
                        <Button
                          type="button"
                          variant="outline"
                          disabled={role !== "admin" || !massRunId}
                          onClick={(e) => {
                            e.stopPropagation();
                            void markMassCandidate(row);
                          }}
                        >
                          Marcar candidato
                        </Button>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>

            <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Drilldown (variante seleccionada)</p>
              {massSelectedRow ? (
                <>
                  <p className="text-sm text-slate-200">{massSelectedRow.strategy_name || massSelectedRow.strategy_id}</p>
                  <p className="text-xs font-mono text-slate-400">{massSelectedRow.variant_id}</p>
                  <div className="grid gap-2 grid-cols-2 text-xs">
                    <div className="rounded border border-slate-800 p-2">Score: {fmtNum(massSelectedRow.score)}</div>
                    <div className="rounded border border-slate-800 p-2">Promotable: {massSelectedRow.promotable ? "Sí" : "No"}</div>
                    <div className="rounded border border-slate-800 p-2">Trades OOS: {massSelectedRow.summary?.trade_count_oos ?? 0}</div>
                    <div className="rounded border border-slate-800 p-2">Stability: {fmtNum(massSelectedRow.summary?.stability ?? 0)}</div>
                  </div>
                  <div className="space-y-1 text-xs">
                    <p className="font-semibold text-slate-300">Por régimen</p>
                    {Object.entries(massSelectedRow.regime_metrics || {}).map(([regime, vals]) => (
                      <div key={regime} className="rounded border border-slate-800 p-2">
                        <p className="font-semibold text-slate-200">{regime}</p>
                        <p className="text-slate-400">
                          trades {vals.trade_count ?? 0} | sharpe {fmtNum(vals.sharpe_oos ?? 0)} | net {fmtNum(vals.net_pnl ?? 0)} | costs {fmtNum(vals.costs_ratio ?? 0)}
                        </p>
                      </div>
                    ))}
                  </div>
                  {massSelectedRow.hard_filter_reasons?.length ? (
                    <div className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
                      Filtros duros: {massSelectedRow.hard_filter_reasons.join(" | ")}
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="text-sm text-slate-400">Sin selección.</p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Detalle de Corrida</CardTitle>
        <CardDescription>{focusRun ? `Run ${focusRun.id}` : "Sin corridas disponibles."}</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 md:col-span-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">Dataset</p>
            <p className="text-sm text-slate-200">
              {(focusRun?.market || "-")}/{(focusRun?.symbol || focusRun?.universe?.[0] || "-")} @ {focusRun?.timeframe || "-"} | fuente{" "}
              {focusRun?.data_source || "-"}
            </p>
            <p className="text-xs font-mono text-slate-400 break-all">{focusRun?.dataset_hash || "-"}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Cantidad de entradas</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.totalEntries}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Salidas</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.totalExits}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Roundtrips</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.totalRoundtrips}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Trade Count</p>
            <p className="text-xl font-semibold text-slate-100">{focusTradeStats.tradeCount}</p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 md:col-span-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">Costos (del formulario)</p>
            <p className="text-sm text-slate-200">
              Fees {fmtNum(focusRun?.costs_breakdown?.fees_total ?? 0)} | Spread {fmtNum(focusRun?.costs_breakdown?.spread_total ?? 0)} | Slippage{" "}
              {fmtNum(focusRun?.costs_breakdown?.slippage_total ?? 0)} | Funding {fmtNum(focusRun?.costs_breakdown?.funding_total ?? 0)} | Rollover{" "}
              {fmtNum(focusRun?.costs_breakdown?.rollover_total ?? 0)}
            </p>
            <p className="text-xs text-slate-400">
              % sobre PnL bruto: fees {fmtPct(focusRun?.costs_breakdown?.fees_pct_of_gross_pnl ?? 0)} | spread{" "}
              {fmtPct(focusRun?.costs_breakdown?.spread_pct_of_gross_pnl ?? 0)} | slippage{" "}
              {fmtPct(focusRun?.costs_breakdown?.slippage_pct_of_gross_pnl ?? 0)} | funding{" "}
              {fmtPct(focusRun?.costs_breakdown?.funding_pct_of_gross_pnl ?? 0)} | rollover{" "}
              {fmtPct(focusRun?.costs_breakdown?.rollover_pct_of_gross_pnl ?? 0)}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Overlay de Equity</CardTitle>
          <CardDescription>Superposicion de corridas seleccionadas (2 a 5).</CardDescription>
          <CardContent>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart data={overlayData}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="index" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  {selectedRuns.map((run, idx) => (
                    <Line key={run.id} type="monotone" dataKey={run.id} stroke={chartColors[idx % chartColors.length]} strokeWidth={2} dot={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Overlay de Drawdown</CardTitle>
          <CardDescription>Comparacion del perfil de riesgo entre corridas.</CardDescription>
          <CardContent>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart data={overlayDDData}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="index" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  {selectedRuns.map((run, idx) => (
                    <Line key={run.id} type="monotone" dataKey={run.id} stroke={chartColors[idx % chartColors.length]} strokeWidth={2} dot={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardTitle>Comparador de Metricas</CardTitle>
        <CardDescription>KPIs por corrida con chequeo de robustez y consistencia.</CardDescription>
        <CardContent className="space-y-3">
          {consistency ? (
            <div className="flex flex-wrap gap-2">
              <Badge variant={consistency.samePeriod ? "success" : "warn"}>Periodo {consistency.samePeriod ? "alineado" : "diferente"}</Badge>
              <Badge variant={consistency.sameUniverse ? "success" : "warn"}>Universo {consistency.sameUniverse ? "alineado" : "diferente"}</Badge>
              <Badge variant={consistency.sameCosts ? "success" : "warn"}>Costos {consistency.sameCosts ? "alineado" : "diferente"}</Badge>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Selecciona al menos 2 corridas para activar comparacion.</p>
          )}
          <div className="flex flex-wrap gap-2 text-xs text-slate-300">
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.muy_malo}`}>Violeta: Muy malo</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.malo}`}>Rojo: Malo</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.aceptable}`}>Naranja: Aceptable</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.bueno}`}>Amarillo: Bueno</span>
            <span className={`rounded px-2 py-1 ${GRADE_CLASS.excelente}`}>Verde: Excelente</span>
          </div>
          <Table>
            <THead>
              <TR>
                <TH>Run</TH>
                <TH>Cant. entradas</TH>
                <TH>CAGR</TH>
                <TH>Max DD</TH>
                <TH>Sharpe</TH>
                <TH>Sortino</TH>
                <TH>Calmar</TH>
                <TH>Winrate</TH>
                <TH>Expectancy USD</TH>
                <TH>Avg Trade</TH>
                <TH>Turnover</TH>
                <TH>Robustez</TH>
              </TR>
            </THead>
            <TBody>
              {selectedRuns.map((run) => (
                <TR key={`cmp-${run.id}`}>
                  <TD>{run.id}</TD>
                  <TD>{tradeStatsForRun(run).totalEntries}</TD>
                  <TD className={gradeCellClass("cagr", run.metrics.cagr)}>{fmtPct(run.metrics.cagr)}</TD>
                  <TD className={gradeCellClass("max_dd", run.metrics.max_dd)}>{fmtPct(run.metrics.max_dd)}</TD>
                  <TD className={gradeCellClass("sharpe", run.metrics.sharpe)}>{fmtNum(run.metrics.sharpe)}</TD>
                  <TD className={gradeCellClass("sortino", run.metrics.sortino)}>{fmtNum(run.metrics.sortino)}</TD>
                  <TD className={gradeCellClass("calmar", run.metrics.calmar)}>{fmtNum(run.metrics.calmar)}</TD>
                  <TD className={gradeCellClass("winrate", run.metrics.winrate)}>{fmtPct(run.metrics.winrate)}</TD>
                  <TD>{fmtNum(run.metrics.expectancy)}</TD>
                  <TD>{fmtNum(run.metrics.avg_trade)}</TD>
                  <TD className={gradeCellClass("turnover", run.metrics.turnover)}>{fmtNum(run.metrics.turnover)}</TD>
                  <TD className={gradeCellClass("robustness", run.metrics.robustness_score ?? run.metrics.robust_score)}>
                    {fmtNum(run.metrics.robustness_score ?? run.metrics.robust_score)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
