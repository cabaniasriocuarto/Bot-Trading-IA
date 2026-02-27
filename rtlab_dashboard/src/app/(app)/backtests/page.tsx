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
  BeastModeStatusResponse,
  BeastModeJobsResponse,
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
  sort_by: "created_at" | "run_id" | "score" | "return" | "sharpe" | "sortino" | "dd" | "pf" | "winrate" | "expectancy" | "trades" | "strategy";
  sort_dir: "asc" | "desc";
};

type FocusRunTab = "overview" | "performance" | "trades_analysis" | "ratios" | "trades_list" | "artifacts";
type MassSortKey =
  | "rank"
  | "variant"
  | "strategy"
  | "score"
  | "trades"
  | "winrate"
  | "sharpe"
  | "calmar"
  | "expectancy"
  | "maxdd"
  | "costs";

type MassTopMetric = "score" | "winrate" | "sharpe" | "calmar" | "expectancy" | "trades" | "maxdd" | "costs";
type MassLeaderboardTab = "score_neto" | "winrate";

const chartColors = ["#22d3ee", "#f97316", "#facc15", "#4ade80", "#f472b6"];
const CATALOG_PRO_VIEWPORT_PX = 560;
const CATALOG_PRO_ROW_HEIGHT = 148;
const CATALOG_PRO_OVERSCAN_ROWS = 8;
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

function runStatusLabel(status: string): string {
  const s = String(status || "").toLowerCase();
  switch (s) {
    case "queued":
      return "En cola";
    case "preparing":
      return "Preparando";
    case "running":
      return "Corriendo";
    case "completed":
      return "Completado";
    case "completed_warn":
      return "Completado con avisos";
    case "failed":
      return "Fallido";
    case "canceled":
      return "Cancelado";
    case "archived":
      return "Archivado";
    default:
      return status || "-";
  }
}

function runTypeLabel(runType: string): string {
  return String(runType) === "batch_child" ? "Child de Research Batch" : "Quick Backtest";
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

function utcDateLabel(value: string | null | undefined): string {
  const v = String(value || "");
  if (!v) return "-";
  try {
    return new Date(v).toISOString().replace("T", " ").slice(0, 16) + " UTC";
  } catch {
    return v;
  }
}

function parseFeePctLabel(feeModel: string | null | undefined): string {
  const raw = String(feeModel || "");
  const num = Number(raw.split(":")[1] ?? "");
  if (!Number.isFinite(num)) return raw || "-";
  return `${fmtNum(num)} bps`;
}

function massSummaryNum(row: MassBacktestResultRow, key: "trade_count_oos" | "winrate_oos" | "sharpe_oos" | "calmar_oos" | "expectancy_net_usd" | "max_dd_oos_pct" | "costs_ratio"): number {
  return Number(row.summary?.[key] ?? 0);
}

function massMetricValue(row: MassBacktestResultRow, metric: MassTopMetric): number {
  switch (metric) {
    case "score":
      return Number(row.score ?? 0);
    case "winrate":
      return massSummaryNum(row, "winrate_oos");
    case "sharpe":
      return massSummaryNum(row, "sharpe_oos");
    case "calmar":
      return massSummaryNum(row, "calmar_oos");
    case "expectancy":
      return massSummaryNum(row, "expectancy_net_usd");
    case "trades":
      return massSummaryNum(row, "trade_count_oos");
    case "maxdd":
      return massSummaryNum(row, "max_dd_oos_pct");
    case "costs":
      return massSummaryNum(row, "costs_ratio");
    default:
      return Number(row.score ?? 0);
  }
}

function massGatesPassed(row: MassBacktestResultRow): boolean | null {
  if (!row.gates_eval || typeof row.gates_eval.passed !== "boolean") return null;
  return !!row.gates_eval.passed;
}

function massGatesBadgeVariant(row: MassBacktestResultRow): "success" | "danger" | "warn" {
  const passed = massGatesPassed(row);
  if (passed === true) return "success";
  if (passed === false) return "danger";
  return "warn";
}

function uiErrMsg(err: unknown, fallback: string): string {
  const unpack = (raw: unknown): string | null => {
    if (raw == null) return null;
    if (typeof raw === "string") {
      const txt = raw.trim();
      if (!txt || txt === "[object Object]") return null;
      return txt;
    }
    if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
    if (Array.isArray(raw)) {
      const lines = raw.map((item) => unpack(item)).filter((x): x is string => Boolean(x));
      return lines.length ? lines.join(" | ") : null;
    }
    if (typeof raw === "object") {
      const rec = raw as Record<string, unknown>;
      const direct =
        unpack(rec.detail) ||
        unpack(rec.message) ||
        unpack(rec.error) ||
        unpack(rec.msg) ||
        unpack(rec.reason) ||
        unpack(rec.cause);
      if (direct) return direct;
      try {
        const encoded = JSON.stringify(raw);
        return encoded && encoded !== "{}" ? encoded : null;
      } catch {
        return null;
      }
    }
    return null;
  };

  if (err instanceof Error) {
    const msg = unpack(err.message);
    if (msg) return msg;
    const fromCause = unpack((err as Error & { cause?: unknown }).cause);
    if (fromCause) return fromCause;
  }
  const unpacked = unpack(err);
  if (unpacked) return unpacked;
  return fallback;
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
  const [catalogBulkBusy, setCatalogBulkBusy] = useState(false);
  const [catalogBulkMessage, setCatalogBulkMessage] = useState("");
  const [catalogBulkError, setCatalogBulkError] = useState("");
  const [catalogRankingPreset, setCatalogRankingPreset] = useState("balanceado");
  const [catalogRankings, setCatalogRankings] = useState<BacktestRankingsResponse | null>(null);
  const [catalogRankRequireOos, setCatalogRankRequireOos] = useState(false);
  const [catalogRankDataQualityOk, setCatalogRankDataQualityOk] = useState(false);
  const [catalogPageSize, setCatalogPageSize] = useState<"30" | "60" | "100">("30");
  const [catalogPage, setCatalogPage] = useState(1);
  const [catalogPageInput, setCatalogPageInput] = useState("1");
  const [catalogProLimit, setCatalogProLimit] = useState<"50" | "100" | "250" | "500">("100");
  const [catalogProScrollTop, setCatalogProScrollTop] = useState(0);
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
  const [massShortlistBusy, setMassShortlistBusy] = useState(false);
  const [massSelectedStrategies, setMassSelectedStrategies] = useState<string[]>([]);
  const [massRunId, setMassRunId] = useState("");
  const [massStatus, setMassStatus] = useState<MassBacktestStatusResponse | null>(null);
  const [massResults, setMassResults] = useState<MassBacktestResultRow[]>([]);
  const [massArtifacts, setMassArtifacts] = useState<MassBacktestArtifactsResponse["items"]>([]);
  const [massOnlyPass, setMassOnlyPass] = useState(true);
  const [beastTier, setBeastTier] = useState<"hobby" | "pro">("hobby");
  const [beastStatus, setBeastStatus] = useState<BeastModeStatusResponse | null>(null);
  const [beastJobs, setBeastJobs] = useState<BeastModeJobsResponse["items"]>([]);
  const [beastBusy, setBeastBusy] = useState(false);
  const [massSelectedRow, setMassSelectedRow] = useState<MassBacktestResultRow | null>(null);
  const [massSelectedVariantIds, setMassSelectedVariantIds] = useState<string[]>([]);
  const [massTopSelectMetric, setMassTopSelectMetric] = useState<MassTopMetric>("winrate");
  const [massTopSelectN, setMassTopSelectN] = useState("20");
  const [massAutoShortlistEnabled, setMassAutoShortlistEnabled] = useState(true);
  const [massLeaderboardTab, setMassLeaderboardTab] = useState<MassLeaderboardTab>("winrate");
  const [massSortKey, setMassSortKey] = useState<MassSortKey>("winrate");
  const [massSortDir, setMassSortDir] = useState<"asc" | "desc">("desc");
  const [massPageSize, setMassPageSize] = useState<"10" | "20" | "30" | "40" | "50">("20");
  const [massPage, setMassPage] = useState(1);
  const [massPageInput, setMassPageInput] = useState("1");
  const [massBatchPageSize, setMassBatchPageSize] = useState<"10" | "20" | "50" | "100" | "200" | "500">("20");
  const [massBatchPage, setMassBatchPage] = useState(1);
  const [massBatchPageInput, setMassBatchPageInput] = useState("1");
  const [massForm, setMassForm] = useState({
    max_variants_per_strategy: "4",
    max_folds: "3",
    train_days: "180",
    test_days: "60",
    top_n: "10",
    seed: "42",
    dataset_source: "auto",
    use_orderflow_data: true,
  });
  const [focusRunTab, setFocusRunTab] = useState<FocusRunTab>("overview");

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
      params.set("limit", "5000");
      const path = `/api/v1/runs?${params.toString()}`;
      const payload = await apiGet<BacktestCatalogRunsResponse>(path);
      setCatalogRuns(payload.items || []);
      setCatalogRunCount(payload.count || 0);
    } catch (err) {
      setCatalogError(uiErrMsg(err, "No se pudo cargar Backtests / Runs."));
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

  const buildCatalogComparePreview = useCallback(
    (runIds: string[]): BacktestCompareResponse | null => {
      const normalized = Array.from(new Set((runIds || []).map((x) => String(x || "").trim()).filter(Boolean)));
      if (!normalized.length) return null;
      const byId = new Map(catalogRuns.map((row) => [String(row.run_id), row]));
      const items = normalized.map((id) => byId.get(id)).filter((row): row is BacktestCatalogRun => Boolean(row));
      if (!items.length) return null;
      const dataset_hashes = Array.from(new Set(items.map((r) => String(r.dataset_hash || "")).filter(Boolean))).sort();
      const warnings: string[] = [];
      if (dataset_hashes.length > 1) warnings.push("datasets_distintos");
      return {
        items,
        count: items.length,
        warnings,
        dataset_hashes,
        same_dataset: dataset_hashes.length <= 1,
      };
    },
    [catalogRuns],
  );

  const setCatalogCompareSelection = useCallback(
    (runIds: string[]) => {
      const normalized = Array.from(new Set((runIds || []).map((x) => String(x || "").trim()).filter(Boolean)));
      setCatalogCompareIds(normalized);
      setCatalogComparePreview(buildCatalogComparePreview(normalized));
    },
    [buildCatalogComparePreview],
  );

  const toggleCatalogSort = useCallback((nextSortBy: RunsListFilters["sort_by"]) => {
    setCatalogFilters((prev) => {
      if (prev.sort_by === nextSortBy) {
        return { ...prev, sort_dir: prev.sort_dir === "desc" ? "asc" : "desc" };
      }
      return { ...prev, sort_by: nextSortBy, sort_dir: "desc" };
    });
  }, []);

  const catalogSortLabel = useCallback(
    (key: RunsListFilters["sort_by"]) => {
      if (catalogFilters.sort_by !== key) return "";
      return catalogFilters.sort_dir === "desc" ? " ▼" : " ▲";
    },
    [catalogFilters.sort_by, catalogFilters.sort_dir],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void refreshCatalogRuns();
    void refreshCatalogBatches();
    void refreshCatalogRankings();
  }, [refreshCatalogRuns, refreshCatalogBatches, refreshCatalogRankings]);

  useEffect(() => {
    setCatalogPage(1);
    setCatalogPageInput("1");
  }, [catalogRuns, catalogPageSize]);

  useEffect(() => {
    setCatalogProScrollTop(0);
  }, [catalogRuns, catalogProLimit]);

  useEffect(() => {
    setCatalogComparePreview(buildCatalogComparePreview(catalogCompareIds));
  }, [buildCatalogComparePreview, catalogCompareIds]);

  useEffect(() => {
    setMassPage(1);
    setMassPageInput("1");
  }, [massResults, massPageSize, massSortKey, massSortDir]);

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
          `/api/v1/research/mass-backtest/results?run_id=${encodeURIComponent(runId)}&limit=1000${onlyPass ? "&only_pass=true" : ""}`,
        ),
        apiGet<MassBacktestArtifactsResponse>(`/api/v1/research/mass-backtest/artifacts?run_id=${encodeURIComponent(runId)}`),
      ]);
      setMassStatus(status);
      setMassResults(results.results || []);
      setMassArtifacts(artifacts.items || []);
      setMassSelectedRow((prev) => {
        if (!prev) return null;
        return (results.results || []).find((row) => row.variant_id === prev.variant_id) || null;
      });
    },
    [massOnlyPass],
  );

  const refreshBeastPanel = useCallback(async () => {
    try {
      const [status, jobs] = await Promise.all([
        apiGet<BeastModeStatusResponse>("/api/v1/research/beast/status"),
        apiGet<BeastModeJobsResponse>("/api/v1/research/beast/jobs?limit=20"),
      ]);
      setBeastStatus(status);
      setBeastJobs(jobs.items || []);
    } catch {
      // best effort
    }
  }, []);

  useEffect(() => {
    if (massRunId) return;
    const firstBatch = (catalogBatches || []).find((b) => String(b.batch_id || "").startsWith("BX-"));
    if (!firstBatch) return;
    setMassRunId(firstBatch.batch_id);
    void refreshMassPayload(firstBatch.batch_id, massOnlyPass).catch(() => undefined);
  }, [catalogBatches, massOnlyPass, massRunId, refreshMassPayload]);

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

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        await refreshBeastPanel();
      } catch {
        // best effort
      }
      if (!cancelled) window.setTimeout(() => void tick(), 2000);
    };
    void tick();
    return () => {
      cancelled = true;
    };
  }, [refreshBeastPanel]);

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
      : [...catalogCompareIds, runId];
    setCatalogCompareSelection(next);
  };

  const selectCatalogPageForCompare = () => setCatalogCompareSelection(catalogPageRows.map((row) => row.run_id));
  const selectCatalogFilteredForCompare = () => setCatalogCompareSelection(catalogRuns.map((row) => row.run_id));
  const clearCatalogCompareSelection = () => setCatalogCompareSelection([]);

  const bulkCatalogRunsAction = async (action: "archive" | "unarchive" | "delete", runIds: string[]) => {
    const ids = Array.from(new Set((runIds || []).map((x) => String(x || "").trim()).filter(Boolean)));
    if (!ids.length) {
      setCatalogBulkError("No hay runs seleccionados.");
      return;
    }
    setCatalogBulkBusy(true);
    setCatalogBulkError("");
    setCatalogBulkMessage("");
    try {
      const res = await apiPost<{ ok: boolean; action: string; count?: number; deleted_count?: number; deleted_run_ids?: string[] }>("/api/v1/runs/bulk", {
        action,
        run_ids: ids,
      });
      const affectedIds = new Set<string>([
        ...ids,
        ...((res.deleted_run_ids || []).map((x) => String(x || ""))),
      ]);
      setCatalogBulkMessage(
        action === "delete"
          ? `Borrado masivo OK: ${res.deleted_count ?? res.count ?? ids.length} runs`
          : `${action === "archive" ? "Archivado" : "Desarchivado"} masivo OK: ${res.count ?? ids.length} runs`,
      );
      setCatalogCompareSelection(catalogCompareIds.filter((id) => !affectedIds.has(id)));
      await Promise.all([refreshCatalogRuns(), refreshCatalogRankings(), refreshCatalogBatches()]);
    } catch (err) {
      setCatalogBulkError(uiErrMsg(err, "No se pudo ejecutar la acción masiva."));
    } finally {
      setCatalogBulkBusy(false);
    }
  };

  const deleteSyntheticLegacyCatalogRuns = async () => {
    const syntheticIds = catalogRuns
      .filter((row) => String(row.dataset_source || "").toLowerCase().includes("synthetic"))
      .map((row) => row.run_id);
    if (!syntheticIds.length) {
      setCatalogBulkError("No hay runs sintéticos en la vista actual.");
      return;
    }
    const ok = window.confirm(`Vas a borrar ${syntheticIds.length} runs sintéticos de la vista actual. ¿Continuar?`);
    if (!ok) return;
    await bulkCatalogRunsAction("delete", syntheticIds);
  };

  const patchCatalogRun = async (runId: string, patch: { alias?: string | null; tags?: string[]; pinned?: boolean; archived?: boolean }) => {
    try {
      await apiPatch<{ ok: boolean; run: BacktestCatalogRun }>(`/api/v1/runs/${encodeURIComponent(runId)}`, patch);
      await refreshCatalogRuns();
      await refreshCatalogRankings();
      await refreshCatalogBatches();
    } catch (err) {
      setCatalogError(uiErrMsg(err, "No se pudo actualizar metadata del run."));
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
      setPromotionError(uiErrMsg(err, "No se pudo validar el run para promoción."));
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
      setPromotionError(uiErrMsg(err, "No se pudo promover el run a rollout."));
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
        use_orderflow_data: Boolean(massForm.use_orderflow_data),
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
      setMassError(uiErrMsg(err, "No se pudo iniciar research masivo."));
    } finally {
      setMassRunning(false);
    }
  };

  const startBeastBatch = async () => {
    if (!massSelectedStrategies.length) {
      setMassError("Seleccioná al menos una estrategia para Modo Bestia.");
      return;
    }
    setBeastBusy(true);
    setMassError("");
    setMassMessage("");
    try {
      const res = await apiPost<{ ok: boolean; run_id: string; state: string; mode?: string; queue_position?: number; estimated_trial_units?: number }>(
        "/api/v1/research/beast/start",
        {
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
          use_orderflow_data: Boolean(massForm.use_orderflow_data),
          tier: beastTier,
          costs: {
            fees_bps: Number(form.fees_bps),
            spread_bps: Number(form.spread_bps),
            slippage_bps: Number(form.slippage_bps),
            funding_bps: Number(form.funding_bps),
            rollover_bps: Number(form.rollover_bps),
          },
        },
      );
      setMassRunId(res.run_id);
      setMassMessage(`Modo Bestia encolado: ${res.run_id} (cola ${res.queue_position ?? "?"}, units ${res.estimated_trial_units ?? "?"})`);
      await Promise.all([refreshBeastPanel(), refreshMassPayload(res.run_id, massOnlyPass).catch(() => undefined)]);
    } catch (err) {
      setMassError(uiErrMsg(err, "No se pudo encolar el batch en Modo Bestia."));
    } finally {
      setBeastBusy(false);
    }
  };

  const beastStopAll = async () => {
    if (!confirm("¿Stop All de Modo Bestia? Se cancela la cola y no se despachan nuevos jobs. Los jobs ya corriendo terminan.")) return;
    setBeastBusy(true);
    try {
      const res = await apiPost<{ note?: string }>("/api/v1/research/beast/stop-all", { reason: "ui_stop_all" });
      setMassMessage(res.note || "Modo Bestia Stop All aplicado.");
      await refreshBeastPanel();
    } catch (err) {
      setMassError(uiErrMsg(err, "No se pudo ejecutar Stop All."));
    } finally {
      setBeastBusy(false);
    }
  };

  const beastResume = async () => {
    setBeastBusy(true);
    try {
      await apiPost("/api/v1/research/beast/resume", {});
      setMassMessage("Modo Bestia reanudado.");
      await refreshBeastPanel();
    } catch (err) {
      setMassError(uiErrMsg(err, "No se pudo reanudar Modo Bestia."));
    } finally {
      setBeastBusy(false);
    }
  };

  const refreshMass = async () => {
    if (!massRunId) return;
    try {
      await refreshMassPayload(massRunId, massOnlyPass);
    } catch (err) {
      setMassError(uiErrMsg(err, "No se pudo refrescar research masivo."));
    }
  };

  const selectMassBatch = async (runId: string) => {
    setMassRunId(runId);
    setMassSelectedRow(null);
    setMassError("");
    setMassMessage("");
    if (!runId) return;
    try {
      await refreshMassPayload(runId, massOnlyPass);
      await loadMassShortlistForBatch(runId, { syncCompare: false });
    } catch (err) {
      setMassError(uiErrMsg(err, "No se pudo cargar el Research Batch seleccionado."));
    }
  };

  const toggleMassSort = (key: MassSortKey) => {
    setMassSortKey((prev) => {
      if (prev === key) {
        setMassSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return prev;
      }
      setMassSortDir(key === "maxdd" || key === "costs" ? "asc" : "desc");
      return key;
    });
  };

  const massSortLabel = (key: MassSortKey) => {
    if (massSortKey !== key) return "";
    return massSortDir === "asc" ? " ▲" : " ▼";
  };

  const applyMassLeaderboardTab = (tab: MassLeaderboardTab) => {
    setMassLeaderboardTab(tab);
    setMassSortKey(tab === "score_neto" ? "score" : "winrate");
    setMassSortDir("desc");
    setMassPage(1);
    setMassPageInput("1");
  };

  const toggleMassVariantSelection = (variantId: string) => {
    setMassSelectedVariantIds((prev) => (prev.includes(variantId) ? prev.filter((x) => x !== variantId) : [...prev, variantId]));
  };

  const selectMassPageVariants = () => setMassSelectedVariantIds(massPageRows.map((row) => row.variant_id));
  const selectMassAllVariants = () => setMassSelectedVariantIds(massSortedRows.map((row) => row.variant_id));
  const clearMassVariantSelection = () => setMassSelectedVariantIds([]);

  const batchChildRunIds = (batch: BacktestCatalogBatch): string[] =>
    Array.from(
      new Set(
        (batch.children_runs || [])
          .map((row) => String(row.run_id || "").trim())
          .filter(Boolean),
      ),
    );

  const restoreMassShortlistFromBatch = useCallback(
    (batch: BacktestCatalogBatch | null | undefined, options?: { syncCompare?: boolean }) => {
      const rawItems = Array.isArray(batch?.best_runs_cache) ? batch!.best_runs_cache : [];
      if (!rawItems.length) return;
      const variantIds = Array.from(
        new Set(
          rawItems
            .map((row) => String((row as Record<string, unknown>)?.variant_id || "").trim())
            .filter(Boolean),
        ),
      );
      const runIds = Array.from(
        new Set(
          rawItems
            .map((row) => {
              const rec = row as Record<string, unknown>;
              return String(rec?.run_id || rec?.catalog_run_id || "").trim();
            })
            .filter(Boolean),
        ),
      );
      if (variantIds.length) setMassSelectedVariantIds(variantIds);
      if (options?.syncCompare && runIds.length) setCatalogCompareSelection(runIds);
      setMassMessage(`Shortlist BX restaurada: ${variantIds.length} variantes${runIds.length ? `, ${runIds.length} runs` : ""}.`);
    },
    [setCatalogCompareSelection],
  );

  const loadMassShortlistForBatch = useCallback(
    async (batchId: string, options?: { syncCompare?: boolean }) => {
      const id = String(batchId || "").trim();
      if (!id) return;
      setMassShortlistBusy(true);
      try {
        const batch = await apiGet<BacktestCatalogBatch>(`/api/v1/batches/${encodeURIComponent(id)}`);
        restoreMassShortlistFromBatch(batch, options);
      } catch (err) {
        setMassError(uiErrMsg(err, "No se pudo cargar la shortlist guardada para este batch."));
      } finally {
        setMassShortlistBusy(false);
      }
    },
    [restoreMassShortlistFromBatch],
  );

  const saveMassShortlistForBatch = async () => {
    if (!massRunId) {
      setMassError("Seleccioná un batch BX antes de guardar shortlist.");
      return;
    }
    const selectedRows = massSortedRows.filter((row) => massSelectedVariantIds.includes(row.variant_id));
    if (!selectedRows.length) {
      setMassError("Seleccioná variantes antes de guardar la shortlist.");
      return;
    }
    const items = selectedRows.map((row) => ({
      variant_id: row.variant_id,
      run_id: String(row.catalog_run_id || "") || null,
      strategy_id: row.strategy_id,
      strategy_name: row.strategy_name,
      score: Number(row.score || 0),
      winrate_oos: Number(row.summary?.winrate_oos || 0),
      sharpe_oos: Number(row.summary?.sharpe_oos || 0),
      costs_ratio: Number(row.summary?.costs_ratio || 0),
    }));
    setMassShortlistBusy(true);
    try {
      const payload = await apiPost<{ ok: boolean; saved_count: number; batch: BacktestCatalogBatch }>(
        `/api/v1/batches/${encodeURIComponent(massRunId)}/shortlist`,
        {
          items,
          source: "ui_research_batch",
          note: "Shortlist guardada desde Leaderboards",
        },
      );
      setMassMessage(`Shortlist BX guardada: ${payload.saved_count} variantes.`);
      await refreshCatalogBatches();
    } catch (err) {
      setMassError(uiErrMsg(err, "No se pudo guardar la shortlist del batch."));
    } finally {
      setMassShortlistBusy(false);
    }
  };

  const compareMassSelectedVariantsInRuns = () => {
    const selectedRows = massSortedRows.filter((row) => massSelectedVariantIds.includes(row.variant_id));
    const runIds = selectedRows.map((row) => String(row.catalog_run_id || "")).filter(Boolean);
    if (!runIds.length) {
      setMassError("Las variantes seleccionadas no tienen run_id de catálogo para comparar.");
      return;
    }
    setCatalogCompareSelection(runIds);
    setMassMessage(`Comparador cargado con ${runIds.length} runs desde el batch seleccionado.`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const selectMassTopVariants = (metric: MassTopMetric, nRaw: string, options?: { compareInRuns?: boolean; auto?: boolean }) => {
    const nParsed = Number(String(nRaw || "0").replace(/[^0-9]/g, ""));
    const n = Math.min(Math.max(Number.isFinite(nParsed) ? Math.trunc(nParsed) : 0, 1), 500);
    if (!massSortedRows.length) {
      setMassError("No hay variantes cargadas para seleccionar top N.");
      return;
    }
    const asc = metric === "maxdd" || metric === "costs";
    const ranked = [...massSortedRows].sort((a, b) => {
      const av = massMetricValue(a, metric);
      const bv = massMetricValue(b, metric);
      if (av === bv) return String(a.variant_id || "").localeCompare(String(b.variant_id || ""));
      return asc ? av - bv : bv - av;
    });
    const picked = ranked.slice(0, Math.min(n, ranked.length));
    setMassSelectedVariantIds(picked.map((row) => row.variant_id));
    if (picked[0]) setMassSelectedRow(picked[0]);
    setMassMessage(`${options?.auto ? "Auto-shortlist" : "Top N"}: ${picked.length} variantes por ${metric}.`);
    if (options?.compareInRuns) {
      const runIds = picked.map((row) => String(row.catalog_run_id || "")).filter(Boolean);
      if (runIds.length) {
        setCatalogCompareSelection(runIds);
        setMassMessage(`${options?.auto ? "Auto-shortlist" : "Top N"} cargado en Comparador de Runs: ${runIds.length} runs (${metric}).`);
      } else {
        setMassError("Las variantes top seleccionadas no tienen run BT todavía para comparar.");
      }
    }
  };

  const bulkMassSelectedVariantsAction = async (action: "archive" | "delete") => {
    const selectedRows = massSortedRows.filter((row) => massSelectedVariantIds.includes(row.variant_id));
    const runIds = selectedRows.map((row) => String(row.catalog_run_id || "")).filter(Boolean);
    if (!runIds.length) {
      setMassError("Seleccioná variantes con run de catálogo para aplicar acción masiva.");
      return;
    }
    if (action === "delete") {
      const ok = window.confirm(`Vas a borrar ${runIds.length} runs del catálogo (batch actual). ¿Continuar?`);
      if (!ok) return;
    }
    try {
      setMassError("");
      setMassMessage("");
      await apiPost("/api/v1/runs/bulk", { action, run_ids: runIds });
      setMassMessage(`${action === "delete" ? "Borrado" : "Archivado"} masivo OK: ${runIds.length} runs del batch.`);
      setMassSelectedVariantIds([]);
      await Promise.all([refreshMass(), refreshCatalogRuns(), refreshCatalogBatches(), refreshCatalogRankings()]);
    } catch (err) {
      setMassError(uiErrMsg(err, "No se pudo ejecutar la acción masiva sobre variantes."));
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
      setMassError(uiErrMsg(err, "No se pudo marcar candidato."));
    }
  };

  const selectedRuns = runs.filter((run) => selected.includes(run.id));
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

  const focusRunChartData = useMemo(() => {
    if (!focusRun) return [];
    return (focusRun.equity_curve || []).map((point, idx) => ({
      index: idx,
      equity: point.equity,
      drawdown: point.drawdown,
      time: point.time,
    }));
  }, [focusRun]);

  const focusTrades = focusRun?.trades || [];

  const focusTradeAnalysis = useMemo(() => {
    const trades = focusTrades;
    if (!trades.length) {
      return {
        total: 0,
        wins: 0,
        losses: 0,
        breakeven: 0,
        avgWin: 0,
        avgLoss: 0,
        maxWin: 0,
        maxLoss: 0,
        longCount: 0,
        shortCount: 0,
        topEntryReasons: [] as Array<[string, number]>,
        topExitReasons: [] as Array<[string, number]>,
      };
    }
    const wins = trades.filter((t) => (t.pnl_net ?? t.pnl) > 0);
    const losses = trades.filter((t) => (t.pnl_net ?? t.pnl) < 0);
    const breakeven = trades.length - wins.length - losses.length;
    const avg = (arr: number[]) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);
    const entryMap = new Map<string, number>();
    const exitMap = new Map<string, number>();
    for (const t of trades) {
      const entry = String(t.reason_code || "sin_motivo");
      const exit = String(t.exit_reason || "sin_motivo");
      entryMap.set(entry, (entryMap.get(entry) || 0) + 1);
      exitMap.set(exit, (exitMap.get(exit) || 0) + 1);
    }
    const sortMap = (m: Map<string, number>) => [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
    return {
      total: trades.length,
      wins: wins.length,
      losses: losses.length,
      breakeven,
      avgWin: avg(wins.map((t) => t.pnl_net ?? t.pnl)),
      avgLoss: avg(losses.map((t) => t.pnl_net ?? t.pnl)),
      maxWin: Math.max(...trades.map((t) => t.pnl_net ?? t.pnl)),
      maxLoss: Math.min(...trades.map((t) => t.pnl_net ?? t.pnl)),
      longCount: trades.filter((t) => t.side === "long").length,
      shortCount: trades.filter((t) => t.side === "short").length,
      topEntryReasons: sortMap(entryMap),
      topExitReasons: sortMap(exitMap),
    };
  }, [focusTrades]);

  const focusArtifacts = useMemo(() => {
    const links = focusRun?.artifacts_links;
    if (!links) return [] as Array<{ label: string; href: string | null | undefined }>;
    return [
      { label: "Reporte JSON", href: links.report_json },
      { label: "Trades CSV", href: links.trades_csv },
      { label: "Equity Curve CSV", href: links.equity_curve_csv },
    ];
  }, [focusRun]);

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

  const catalogTotalPages = Math.max(1, Math.ceil(catalogRuns.length / Number(catalogPageSize)));
  const catalogPageSafe = Math.min(Math.max(catalogPage, 1), catalogTotalPages);
  const catalogPageStart = (catalogPageSafe - 1) * Number(catalogPageSize);
  const catalogPageEnd = Math.min(catalogPageStart + Number(catalogPageSize), catalogRuns.length);
  const catalogPageRows = catalogRuns.slice(catalogPageStart, catalogPageEnd);
  const catalogPageNumbers = Array.from({ length: Math.min(catalogTotalPages, 7) }, (_, idx) => {
    if (catalogTotalPages <= 7) return idx + 1;
    const windowStart = Math.max(1, Math.min(catalogPageSafe - 3, catalogTotalPages - 6));
    return windowStart + idx;
  });
  const recentBatches = catalogBatches.slice(0, 8);
  const sortedBatchOptions = useMemo(
    () =>
      [...catalogBatches]
        .filter((b) => String(b.batch_id || "").startsWith("BX-"))
        .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))),
    [catalogBatches],
  );
  const massBatchTotalPages = Math.max(1, Math.ceil(sortedBatchOptions.length / Number(massBatchPageSize)));
  const massBatchPageSafe = Math.min(Math.max(massBatchPage, 1), massBatchTotalPages);
  const massBatchPageStart = (massBatchPageSafe - 1) * Number(massBatchPageSize);
  const massBatchPageEnd = Math.min(massBatchPageStart + Number(massBatchPageSize), sortedBatchOptions.length);
  const massBatchPageRows = sortedBatchOptions.slice(massBatchPageStart, massBatchPageEnd);
  const massBatchPageNumbers = Array.from({ length: Math.min(massBatchTotalPages, 7) }, (_, idx) => {
    if (massBatchTotalPages <= 7) return idx + 1;
    const windowStart = Math.max(1, Math.min(massBatchPageSafe - 3, massBatchTotalPages - 6));
    return windowStart + idx;
  });
  const batchChildrenCount = catalogRuns.filter((r) => r.run_type === "batch_child").length;
  const quickRunsCount = catalogRuns.filter((r) => r.run_type !== "batch_child").length;
  const catalogProRows = catalogRuns.slice(0, Number(catalogProLimit));
  const catalogProRowsPerViewport = Math.max(1, Math.ceil(CATALOG_PRO_VIEWPORT_PX / CATALOG_PRO_ROW_HEIGHT));
  const catalogProStartIndex = Math.max(0, Math.floor(catalogProScrollTop / CATALOG_PRO_ROW_HEIGHT) - CATALOG_PRO_OVERSCAN_ROWS);
  const catalogProEndIndex = Math.min(
    catalogProRows.length,
    catalogProStartIndex + catalogProRowsPerViewport + CATALOG_PRO_OVERSCAN_ROWS * 2,
  );
  const catalogProTopPadPx = catalogProStartIndex * CATALOG_PRO_ROW_HEIGHT;
  const catalogProBottomPadPx = Math.max(0, (catalogProRows.length - catalogProEndIndex) * CATALOG_PRO_ROW_HEIGHT);
  const catalogProVisibleRows = useMemo(
    () => catalogProRows.slice(catalogProStartIndex, catalogProEndIndex),
    [catalogProRows, catalogProStartIndex, catalogProEndIndex],
  );
  const catalogProColumnCount = useMemo(() => {
    const dynamic = [
      "run",
      "strategy",
      "status",
      "dates",
      "market",
      "dataset",
      "costs",
      "kpis",
      "rank",
      "flags",
    ].reduce((acc, key) => acc + (catalogTableColumns[key] ? 1 : 0), 0);
    return 1 + dynamic;
  }, [catalogTableColumns]);

  const massSortedRows = useMemo(() => {
    const rows = [...massResults];
    const dir = massSortDir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      let av = 0;
      let bv = 0;
      switch (massSortKey) {
        case "rank":
          av = Number(a.rank ?? 0);
          bv = Number(b.rank ?? 0);
          break;
        case "variant":
          return String(a.variant_id || "").localeCompare(String(b.variant_id || "")) * dir;
        case "strategy":
          return String(a.strategy_name || a.strategy_id || "").localeCompare(String(b.strategy_name || b.strategy_id || "")) * dir;
        case "score":
          av = Number(a.score ?? 0);
          bv = Number(b.score ?? 0);
          break;
        case "trades":
          av = massSummaryNum(a, "trade_count_oos");
          bv = massSummaryNum(b, "trade_count_oos");
          break;
        case "winrate":
          av = massSummaryNum(a, "winrate_oos");
          bv = massSummaryNum(b, "winrate_oos");
          break;
        case "sharpe":
          av = massSummaryNum(a, "sharpe_oos");
          bv = massSummaryNum(b, "sharpe_oos");
          break;
        case "calmar":
          av = massSummaryNum(a, "calmar_oos");
          bv = massSummaryNum(b, "calmar_oos");
          break;
        case "expectancy":
          av = massSummaryNum(a, "expectancy_net_usd");
          bv = massSummaryNum(b, "expectancy_net_usd");
          break;
        case "maxdd":
          av = massSummaryNum(a, "max_dd_oos_pct");
          bv = massSummaryNum(b, "max_dd_oos_pct");
          break;
        case "costs":
          av = massSummaryNum(a, "costs_ratio");
          bv = massSummaryNum(b, "costs_ratio");
          break;
      }
      if (av === bv) return String(a.variant_id || "").localeCompare(String(b.variant_id || "")) * dir;
      return (av - bv) * dir;
    });
    return rows;
  }, [massResults, massSortDir, massSortKey]);

  const massTotalPages = Math.max(1, Math.ceil(massSortedRows.length / Number(massPageSize)));
  const massPageSafe = Math.min(Math.max(massPage, 1), massTotalPages);
  const massPageStart = (massPageSafe - 1) * Number(massPageSize);
  const massPageEnd = Math.min(massPageStart + Number(massPageSize), massSortedRows.length);
  const massPageRows = massSortedRows.slice(massPageStart, massPageEnd);
  const massSelectedRows = massSortedRows.filter((row) => massSelectedVariantIds.includes(row.variant_id));
  const massSelectedRowsWithCatalogRun = massSelectedRows.filter((row) => String(row.catalog_run_id || "").trim());
  const massPageNumbers = Array.from({ length: Math.min(massTotalPages, 7) }, (_, idx) => {
    if (massTotalPages <= 7) return idx + 1;
    const windowStart = Math.max(1, Math.min(massPageSafe - 3, massTotalPages - 6));
    return windowStart + idx;
  });

  useEffect(() => {
    if (!massSortedRows.length) {
      setMassSelectedRow(null);
      return;
    }
    setMassSelectedRow((prev) => {
      if (!prev) return massSortedRows[0];
      return massSortedRows.find((row) => row.variant_id === prev.variant_id) || massSortedRows[0];
    });
  }, [massSortedRows]);

  useEffect(() => {
    const valid = new Set(massSortedRows.map((row) => row.variant_id));
    setMassSelectedVariantIds((prev) => prev.filter((id) => valid.has(id)));
  }, [massSortedRows]);

  useEffect(() => {
    setMassBatchPage(1);
    setMassBatchPageInput("1");
  }, [massBatchPageSize]);

  useEffect(() => {
    setMassBatchPage((prev) => Math.min(Math.max(prev, 1), massBatchTotalPages));
  }, [massBatchTotalPages]);

  useEffect(() => {
    setMassBatchPageInput(String(massBatchPageSafe));
  }, [massBatchPageSafe]);

  useEffect(() => {
    if (!massAutoShortlistEnabled) return;
    if (!massSortedRows.length) return;
    if (!massRunId) return;
    const state = String(massStatus?.state || "");
    if (state && state !== "COMPLETED") return;
    // Auto-shortlist solo si todavía no hay selección activa para evitar pisar decisiones manuales.
    if (massSelectedVariantIds.length > 0) return;
    selectMassTopVariants(massTopSelectMetric, massTopSelectN, { auto: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [massAutoShortlistEnabled, massRunId, massSortedRows, massStatus?.state]);

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
        <CardTitle>Quick Backtest (opcional)</CardTitle>
        <CardDescription>Corrida puntual para validar una idea. El flujo principal de investigación es Research Batch + ranking + comparación.</CardDescription>
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
              <p>Datos: reales (si faltan, devuelve error; no sintéticos)</p>
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
                <option value="">Todos los tipos</option>
                <option value="single">Quick Backtest</option>
                <option value="batch_child">Child de Research Batch</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Estado</label>
              <Select value={catalogFilters.status} onChange={(e) => setCatalogFilters((p) => ({ ...p, status: e.target.value }))}>
                <option value="">Todos los estados</option>
                <option value="queued">En cola</option>
                <option value="preparing">Preparando</option>
                <option value="running">Corriendo</option>
                <option value="completed">Completado</option>
                <option value="completed_warn">Completado con avisos</option>
                <option value="failed">Fallido</option>
                <option value="canceled">Cancelado</option>
                <option value="archived">Archivado</option>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Estrategia</label>
              <Select value={catalogFilters.strategy_id} onChange={(e) => setCatalogFilters((p) => ({ ...p, strategy_id: e.target.value }))}>
                <option value="">Todas las estrategias</option>
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
                <option value="">Todos los timeframes</option>
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
                <option value="run_id">Run ID</option>
                <option value="score">Score</option>
                <option value="return">Retorno</option>
                <option value="sharpe">Sharpe</option>
                <option value="sortino">Sortino</option>
                <option value="dd">Max DD</option>
                <option value="pf">Profit Factor</option>
                <option value="winrate">WinRate</option>
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
              <p className="text-xs text-slate-400">Quick Backtest: {quickRunsCount} | Child de Research Batch: {batchChildrenCount}</p>
              <p className="text-xs text-slate-400">
                Mostrando {catalogRuns.length ? catalogPageStart + 1 : 0}-{catalogPageEnd} de {catalogRuns.length} runs cargados en esta vista.
              </p>
              <p className="mt-2 text-xs text-slate-400">
                Comparador catalogo: {catalogCompareIds.length} seleccionados {catalogComparePreview ? `| same_dataset: ${catalogComparePreview.same_dataset ? "si" : "no"}` : ""}
              </p>
              {catalogBulkMessage ? <p className="mt-2 text-xs text-emerald-300">{catalogBulkMessage}</p> : null}
              {catalogBulkError ? <p className="mt-2 text-xs text-rose-300">{catalogBulkError}</p> : null}
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
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-3 py-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" onClick={selectCatalogPageForCompare}>
                  Seleccionar pagina
                </Button>
                <Button type="button" variant="outline" onClick={selectCatalogFilteredForCompare}>
                  Seleccionar filtrados
                </Button>
                <Button type="button" variant="outline" onClick={clearCatalogCompareSelection}>
                  Limpiar seleccion
                </Button>
                <Badge variant="warn">{catalogCompareIds.length} seleccionados</Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={role !== "admin" || catalogBulkBusy || !catalogCompareIds.length}
                  onClick={() => void bulkCatalogRunsAction("archive", catalogCompareIds)}
                  title="Archiva (soft delete) los runs seleccionados"
                >
                  {catalogBulkBusy ? "Procesando..." : "Archivar seleccionados"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={role !== "admin" || catalogBulkBusy || !catalogCompareIds.length}
                  onClick={() => {
                    const ok = window.confirm(`Vas a borrar ${catalogCompareIds.length} runs seleccionados. ¿Continuar?`);
                    if (!ok) return;
                    void bulkCatalogRunsAction("delete", catalogCompareIds);
                  }}
                  title="Borra runs del catalogo y limpia run legacy asociado si existe"
                >
                  {catalogBulkBusy ? "Procesando..." : "Borrar seleccionados"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={role !== "admin" || catalogBulkBusy}
                  onClick={() => void deleteSyntheticLegacyCatalogRuns()}
                  title="Limpia runs synthetic_seeded / demo de la vista actual"
                >
                  Borrar runs sintéticos viejos
                </Button>
              </div>
            </div>
            <Table>
              <THead>
                <TR>
                  <TH>Comparar</TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("run_id")}>
                      Run ID{catalogSortLabel("run_id")}
                    </button>
                  </TH>
                  <TH>Tipo</TH>
                  <TH>Estado</TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("created_at")}>
                      Fecha{catalogSortLabel("created_at")}
                    </button>
                  </TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("strategy")}>
                      Estrategia{catalogSortLabel("strategy")}
                    </button>
                  </TH>
                  <TH>Mercado / TF</TH>
                  <TH>Rango</TH>
                  <TH>Dataset</TH>
                  <TH>Cost model</TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("return")}>
                      Ret%{catalogSortLabel("return")}
                    </button>
                  </TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("dd")}>
                      Max DD{catalogSortLabel("dd")}
                    </button>
                  </TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("sharpe")}>
                      Sharpe{catalogSortLabel("sharpe")}
                    </button>
                  </TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("pf")}>
                      PF{catalogSortLabel("pf")}
                    </button>
                  </TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("winrate")}>
                      WinRate{catalogSortLabel("winrate")}
                    </button>
                  </TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("trades")}>
                      Trades{catalogSortLabel("trades")}
                    </button>
                  </TH>
                  <TH>
                    <button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleCatalogSort("expectancy")}>
                      Expectancy{catalogSortLabel("expectancy")}
                    </button>
                  </TH>
                  <TH>Chips</TH>
                  <TH>Acciones</TH>
                </TR>
              </THead>
              <TBody>
                {catalogPageRows.map((row) => {
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
                        <Badge variant={statusVariant(row.status)}>{runStatusLabel(row.status)}</Badge>
                      </TD>
                      <TD className="text-xs" title={`Local: ${compactDate(row.created_at)}\nUTC: ${utcDateLabel(row.created_at)}`}>
                        <p>{compactDate(row.created_at)}</p>
                        <p className="text-slate-500">{utcDateLabel(row.created_at)}</p>
                      </TD>
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
                      <TD className="text-xs">{fmtPct((k.return_total as number | undefined) ?? (k.cagr as number | undefined) ?? 0)}</TD>
                      <TD className="text-xs">{fmtPct((k.max_dd as number | undefined) ?? 0)}</TD>
                      <TD className="text-xs">{fmtNum((k.sharpe as number | undefined) ?? 0)}</TD>
                      <TD className="text-xs">{fmtNum((k.profit_factor as number | undefined) ?? 0)}</TD>
                      <TD className="text-xs">{fmtPct((k.winrate as number | undefined) ?? 0)}</TD>
                      <TD className="text-xs">{fmtNum((k.trade_count as number | undefined) ?? (k.roundtrips as number | undefined) ?? 0)}</TD>
                      <TD className="text-xs">
                        {fmtNum((expectancyValue as number | undefined) ?? 0)} {String(k.expectancy_unit || "")}
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
                {!catalogPageRows.length ? (
                  <TR>
                    <TD colSpan={19} className="py-6">
                      <div className="mx-auto max-w-2xl rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-left">
                        <p className="text-sm font-semibold text-slate-100">Todavia no hay datos para esta vista</p>
                        <p className="mt-1 text-sm text-slate-400">
                          No hay runs que coincidan con los filtros actuales, o todavia no ejecutaste un Quick Backtest / Research Batch.
                        </p>
                        <div className="mt-3 grid gap-3 md:grid-cols-2">
                          <div className="rounded border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-300">
                            <p className="font-semibold text-slate-100">Que hacer ahora (rapido)</p>
                            <ol className="mt-2 list-decimal space-y-1 pl-4">
                              <li>Limpiar filtros de Runs.</li>
                              <li>Ejecutar un Quick Backtest.</li>
                              <li>O lanzar un Research Batch para generar multiples runs.</li>
                            </ol>
                          </div>
                          <div className="flex flex-col gap-2">
                            <Button type="button" variant="outline" onClick={() => {
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
                            }}>
                              Limpiar filtros de Runs
                            </Button>
                            <Button type="button" variant="outline" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
                              Ir a Quick Backtest / Research Batch
                            </Button>
                          </div>
                        </div>
                      </div>
                    </TD>
                  </TR>
                ) : null}
              </TBody>
            </Table>
          </div>
          <div className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3 md:flex-row md:items-end md:justify-between">
            <div className="grid gap-2 md:grid-cols-3 md:items-end">
              <div className="space-y-1">
                <label className="text-xs uppercase tracking-wide text-slate-400">Runs por pagina</label>
                <Select value={catalogPageSize} onChange={(e) => setCatalogPageSize(e.target.value as "30" | "60" | "100")}>
                  <option value="30">30</option>
                  <option value="60">60</option>
                  <option value="100">100</option>
                </Select>
              </div>
              <div className="space-y-1">
                <label className="text-xs uppercase tracking-wide text-slate-400">Ir a pagina</label>
                <Input
                  value={catalogPageInput}
                  onChange={(e) => setCatalogPageInput(e.target.value.replace(/[^0-9]/g, ""))}
                  placeholder="1"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    const requested = Number(catalogPageInput || "1");
                    if (!Number.isFinite(requested)) return;
                    const next = Math.min(Math.max(Math.trunc(requested), 1), catalogTotalPages);
                    setCatalogPage(next);
                    setCatalogPageInput(String(next));
                  }}
                >
                  Ir
                </Button>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={catalogPageSafe <= 1}
                onClick={() => {
                  const next = Math.max(1, catalogPageSafe - 1);
                  setCatalogPage(next);
                  setCatalogPageInput(String(next));
                }}
              >
                Anterior
              </Button>
              {catalogPageNumbers.map((n) => (
                <Button
                  key={`runs-page-${n}`}
                  type="button"
                  variant={n === catalogPageSafe ? "default" : "outline"}
                  onClick={() => {
                    setCatalogPage(n);
                    setCatalogPageInput(String(n));
                  }}
                >
                  {n}
                </Button>
              ))}
              <Button
                type="button"
                variant="outline"
                disabled={catalogPageSafe >= catalogTotalPages}
                onClick={() => {
                  const next = Math.min(catalogTotalPages, catalogPageSafe + 1);
                  setCatalogPage(next);
                  setCatalogPageInput(String(next));
                }}
              >
                Siguiente
              </Button>
            </div>
          </div>
          <p className="text-xs text-slate-400">Runs list paginada para trabajo diario. La shortlist de comparacion rapida esta en el Comparador Profesional (D1).</p>
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
                <Badge variant="warn">{catalogCompareIds.length} seleccionados</Badge>
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
                  Tabla virtualizada activa: filtros/sort server-side + ventana visible.
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
                <span className="text-xs text-slate-400">
                  Ventana {catalogProRows.length ? `${catalogProStartIndex + 1}-${catalogProEndIndex}` : "0-0"} de {catalogProRows.length}
                </span>
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

            <div className="mt-3 max-h-[560px] overflow-auto" onScroll={(event) => setCatalogProScrollTop(event.currentTarget.scrollTop)}>
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
                  {catalogProTopPadPx > 0 ? (
                    <TR className="hover:bg-transparent">
                      <TD colSpan={catalogProColumnCount} style={{ height: catalogProTopPadPx, padding: 0 }} />
                    </TR>
                  ) : null}
                  {catalogProVisibleRows.map((row) => {
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
                  {catalogProBottomPadPx > 0 ? (
                    <TR className="hover:bg-transparent">
                      <TD colSpan={catalogProColumnCount} style={{ height: catalogProBottomPadPx, padding: 0 }} />
                    </TR>
                  ) : null}
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
        <CardTitle className="flex items-center gap-2">
          Quick Backtest Legacy (Deprecado)
          <Badge variant="warn">Deprecado</Badge>
        </CardTitle>
        <CardDescription>
          Vista legacy para compatibilidad. El flujo oficial es Quick Backtest / Research Batch -&gt; Backtests / Runs -&gt; Comparador profesional.
        </CardDescription>
        <CardContent>
          <details className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">
            <summary className="cursor-pointer list-none text-sm font-semibold text-slate-200">Abrir comparador legacy (compatibilidad)</summary>
            <p className="mt-2 text-xs text-slate-400">
              Usalo solo para corridas viejas del endpoint legacy. Para investigacion y decisiones, usa la lista de Runs y el Comparador Profesional.
            </p>
            <div className="mt-3 overflow-x-auto">
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
            </div>
          </details>
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

          <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950/30 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-cyan-300">Bloque 1 · Crear Batch</p>
                <p className="text-xs text-slate-400">Configura parametros, estrategia y costos para lanzar un Research Batch reproducible.</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">
                Flujo oficial: Crear Batch -&gt; Batches (BX) -&gt; Leaderboards -&gt; Comparar -&gt; Marcar candidato
              </div>
            </div>

          <div className="grid gap-3 xl:grid-cols-4">
            <div className="space-y-1 xl:col-span-2">
              <label className="text-xs uppercase tracking-wide text-slate-400">Grupo de backtests (Research Batch / BX)</label>
              <Select
                value={massRunId}
                onChange={(e) => {
                  void selectMassBatch(e.target.value);
                }}
              >
                <option value="">Seleccionar batch...</option>
                {sortedBatchOptions.map((bx) => (
                  <option key={bx.batch_id} value={bx.batch_id}>
                    {bx.batch_id} · {compactDate(bx.created_at)} · {bx.status} · runs {bx.run_count_done}/{bx.run_count_total}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Orden por defecto</label>
              <div className="h-10 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">
                WinRate OOS (desc) {massSortLabel("winrate").trim() || "▼"}
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Vista</label>
              <div className="h-10 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">
                Primero elegís el batch (BX), luego ordenás y comparás variantes.
              </div>
            </div>
          </div>
          </div>

          <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950/30 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-cyan-300">Bloque 2 · Batches</p>
                <p className="text-xs text-slate-400">Lista paginada de grupos BX para elegir rapido el experimento correcto y operar sus runs hijos.</p>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-300">
                <span>{sortedBatchOptions.length} batches</span>
                <Select value={massBatchPageSize} onChange={(e) => setMassBatchPageSize(e.target.value as typeof massBatchPageSize)} className="h-8 min-w-[90px]">
                  <option value="10">10</option>
                  <option value="20">20</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                  <option value="200">200</option>
                  <option value="500">500</option>
                </Select>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/50 p-2">
              <Table>
                <THead>
                  <TR>
                    <TH>Batch (BX)</TH>
                    <TH>Creado</TH>
                    <TH>Estado</TH>
                    <TH>Progreso</TH>
                    <TH>Objetivo</TH>
                    <TH>Runs BT</TH>
                    <TH>Shortlist</TH>
                    <TH>Acciones</TH>
                  </TR>
                </THead>
                <TBody>
                  {massBatchPageRows.length ? (
                    massBatchPageRows.map((bx) => {
                      const childIds = batchChildRunIds(bx);
                      const isSelected = bx.batch_id === massRunId;
                      return (
                        <TR key={bx.batch_id} className={isSelected ? "bg-cyan-500/5" : ""}>
                          <TD className="font-mono text-xs">
                            <div className="flex items-center gap-2">
                              <span>{bx.batch_id}</span>
                              {isSelected ? <Badge variant="success">activo</Badge> : null}
                            </div>
                          </TD>
                          <TD className="text-xs" title={utcDateLabel(bx.created_at)}>{compactDate(bx.created_at)}</TD>
                          <TD><Badge variant={statusVariant(String(bx.status || ""))}>{runStatusLabel(String(bx.status || ""))}</Badge></TD>
                          <TD className="text-xs text-slate-300">{bx.run_count_done}/{bx.run_count_total} (fail {bx.run_count_failed})</TD>
                          <TD className="max-w-[280px] truncate text-xs text-slate-300" title={String(bx.objective || "-")}>
                            {String(bx.objective || "-")}
                          </TD>
                          <TD className="text-xs text-slate-300">{childIds.length || "-"}</TD>
                          <TD className="text-xs text-slate-300">
                            {Array.isArray(bx.best_runs_cache) ? bx.best_runs_cache.length : 0}
                          </TD>
                          <TD>
                            <div className="flex flex-wrap gap-1">
                              <Button type="button" variant="outline" className="h-8 px-2" onClick={() => void selectMassBatch(bx.batch_id)}>
                                Ver
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                className="h-8 px-2"
                                disabled={massShortlistBusy}
                                onClick={() => void loadMassShortlistForBatch(bx.batch_id, { syncCompare: true })}
                                title="Carga shortlist guardada para este batch"
                              >
                                Cargar shortlist
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                className="h-8 px-2"
                                disabled={role !== "admin" || !childIds.length}
                                onClick={() => void bulkCatalogRunsAction("archive", childIds)}
                                title="Archiva runs BT hijos del batch"
                              >
                                Archivar runs
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                className="h-8 px-2"
                                disabled={role !== "admin" || !childIds.length}
                                onClick={() => {
                                  const ok = window.confirm(`Vas a borrar ${childIds.length} runs BT del batch ${bx.batch_id}. ¿Continuar?`);
                                  if (!ok) return;
                                  void bulkCatalogRunsAction("delete", childIds);
                                }}
                                title="Borra runs BT del catalogo (no elimina el artifact BX)"
                              >
                                Borrar runs
                              </Button>
                            </div>
                          </TD>
                        </TR>
                      );
                    })
                  ) : (
                    <TR>
                      <TD colSpan={7} className="text-center text-sm text-slate-400">
                        Todavia no hay batches. Crea uno arriba para empezar el research.
                      </TD>
                    </TR>
                  )}
                </TBody>
              </Table>

              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-xs">
                <div className="text-slate-400">
                  Pagina {massBatchPageSafe}/{massBatchTotalPages} · Mostrando {sortedBatchOptions.length ? massBatchPageStart + 1 : 0}-{massBatchPageEnd} de {sortedBatchOptions.length}
                </div>
                <div className="flex items-center gap-1">
                  <Button type="button" variant="outline" className="h-8 px-2" disabled={massBatchPageSafe <= 1} onClick={() => setMassBatchPage((p) => Math.max(1, p - 1))}>
                    Anterior
                  </Button>
                  {massBatchPageNumbers.map((p) => (
                    <Button
                      key={`bx-page-${p}`}
                      type="button"
                      variant={p === massBatchPageSafe ? "default" : "outline"}
                      className="h-8 px-2"
                      onClick={() => {
                        setMassBatchPage(p);
                        setMassBatchPageInput(String(p));
                      }}
                    >
                      {p}
                    </Button>
                  ))}
                  <Button type="button" variant="outline" className="h-8 px-2" disabled={massBatchPageSafe >= massBatchTotalPages} onClick={() => setMassBatchPage((p) => Math.min(massBatchTotalPages, p + 1))}>
                    Siguiente
                  </Button>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <span>Ir a</span>
                  <Input
                    className="h-8 w-16"
                    value={massBatchPageInput}
                    onChange={(e) => setMassBatchPageInput(e.target.value.replace(/[^0-9]/g, ""))}
                    onBlur={() => {
                      const next = Number(massBatchPageInput || "1");
                      if (Number.isFinite(next)) setMassBatchPage(Math.min(massBatchTotalPages, Math.max(1, next)));
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const next = Number(massBatchPageInput || "1");
                        if (Number.isFinite(next)) setMassBatchPage(Math.min(massBatchTotalPages, Math.max(1, next)));
                      }
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950/30 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-cyan-300">Bloque 3 · Leaderboards</p>
                <p className="text-xs text-slate-400">Vista principal por Score Neto y secundaria por WinRate, con la misma tabla de variantes para comparar.</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">
                {massRunId ? `Batch activo: ${massRunId}` : "Primero elegi un batch BX"}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => applyMassLeaderboardTab("score_neto")}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold ${
                  massLeaderboardTab === "score_neto"
                    ? "border-cyan-400/50 bg-cyan-500/10 text-cyan-200"
                    : "border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                Score Neto (principal)
              </button>
              <button
                type="button"
                onClick={() => applyMassLeaderboardTab("winrate")}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold ${
                  massLeaderboardTab === "winrate"
                    ? "border-cyan-400/50 bg-cyan-500/10 text-cyan-200"
                    : "border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                WinRate (secundario)
              </button>
              <Badge variant="warn">Orden activo: {massSortKey}{massSortLabel(massSortKey)}</Badge>
              <span className="text-xs text-slate-400">Podes seguir ordenando por cualquier columna haciendo click en la tabla.</span>
            </div>
          </div>

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
                    <option value="auto">auto (real; falla si no existe)</option>
                    <option value="dataset">dataset (local reproducible)</option>
                  </Select>
                </div>
                <div className="space-y-1 md:col-span-2">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Politica de datos</label>
                  <div className="h-10 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">
                    Sin sinteticos: usa datos reales o devuelve error con la accion recomendada.
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Filtro ranking</label>
                  <label className="flex h-10 items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 text-sm">
                    <input type="checkbox" checked={massOnlyPass} onChange={(e) => setMassOnlyPass(e.target.checked)} />
                    Solo hard-pass
                  </label>
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wide text-slate-400">Order Flow</label>
                  <label className="flex h-10 items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 text-sm">
                    <input
                      type="checkbox"
                      checked={massForm.use_orderflow_data}
                      onChange={(e) => setMassForm((p) => ({ ...p, use_orderflow_data: e.target.checked }))}
                    />
                    Usar datos order flow (VPIN/L1)
                  </label>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button disabled={role !== "admin" || massRunning} onClick={startMassBacktests}>
                  {massRunning ? "Iniciando..." : "Ejecutar Backtests Masivos"}
                </Button>
                <Button
                  variant="outline"
                  disabled={role !== "admin" || beastBusy}
                  onClick={startBeastBatch}
                  title="Encola el batch en Modo Bestia (scheduler local fase 1, con budget governor y limites de concurrencia)"
                >
                  {beastBusy ? "Encolando Bestia..." : "Ejecutar en Modo Bestia"}
                </Button>
                <Button variant="outline" disabled={!massRunId} onClick={refreshMass}>
                  Refrescar Research Batch
                </Button>
                {massRunId ? <Badge variant="warn">run_id: {massRunId}</Badge> : null}
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-400">Modo Bestia (cola de jobs)</p>
                    <p className="mt-1 text-xs text-slate-400">
                      Scheduler local fase 1 (sin Celery/Redis todavia). Encola batches grandes con limites de concurrencia y budget diario.
                    </p>
                  </div>
                  <Badge variant={beastStatus?.enabled ? "success" : "warn"}>
                    {beastStatus?.enabled ? "habilitado" : "deshabilitado"}
                  </Badge>
                </div>

                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <div className="space-y-1">
                    <label className="text-xs uppercase tracking-wide text-slate-400">Tier Bestia</label>
                    <Select
                      value={beastTier}
                      onChange={(e) => setBeastTier(e.target.value as "hobby" | "pro")}
                      disabled={role !== "admin" || beastBusy}
                    >
                      <option value="hobby">Hobby</option>
                      <option value="pro">Pro</option>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs uppercase tracking-wide text-slate-400">Acciones</label>
                    <div className="flex h-10 items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-2">
                      <Button type="button" variant="outline" className="h-7 px-2" disabled={role !== "admin" || beastBusy} onClick={() => void refreshBeastPanel()}>
                        Refrescar
                      </Button>
                      <Button type="button" variant="outline" className="h-7 px-2" disabled={role !== "admin" || beastBusy} onClick={beastResume}>
                        Reanudar
                      </Button>
                      <Button type="button" variant="outline" className="h-7 px-2" disabled={role !== "admin" || beastBusy} onClick={beastStopAll}>
                        Stop All
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs">
                    <p className="text-slate-400">Scheduler</p>
                    <div className="mt-1 space-y-1 text-slate-200">
                      <p>Thread: {beastStatus?.scheduler?.thread_alive ? "activo" : "inactivo"}</p>
                      <p>Cola: {beastStatus?.scheduler?.queue_depth ?? 0}</p>
                      <p>Workers activos: {beastStatus?.scheduler?.workers_active ?? 0}/{beastStatus?.scheduler?.max_concurrent_jobs ?? "-"}</p>
                      <p>Stop solicitado: {beastStatus?.scheduler?.stop_requested ? "Si" : "No"}</p>
                    </div>
                    <p className="mt-2 text-[11px] text-slate-400">
                      {beastStatus?.scheduler?.rate_limit_enabled
                        ? `Rate limit policy: ${beastStatus?.scheduler?.max_requests_per_minute ?? "-"} req/min (aplica a la planificacion; limiter por exchange completo pendiente).`
                        : "Rate limit policy deshabilitada en policy snapshot."}
                    </p>
                  </div>

                  <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs">
                    <p className="text-slate-400">Budget governor</p>
                    <div className="mt-1 space-y-1 text-slate-200">
                      <p>Tier: {beastStatus?.budget?.tier || beastTier}</p>
                      <p>Cap diario: {beastStatus?.budget?.daily_cap ?? "-"}</p>
                      <p>Stop al: {typeof beastStatus?.budget?.stop_at_budget_pct === "number" ? `${fmtNum(beastStatus.budget.stop_at_budget_pct)}%` : "-"}</p>
                      <p>
                        Uso: {beastStatus?.budget?.daily_jobs_started ?? 0}/{beastStatus?.budget?.daily_cap ?? "-"} jobs
                        {typeof beastStatus?.budget?.usage_pct === "number" ? ` (${fmtNum(beastStatus.budget.usage_pct)}%)` : ""}
                      </p>
                      <p>
                        Done/Fail: {beastStatus?.budget?.daily_jobs_completed ?? 0}/{beastStatus?.budget?.daily_jobs_failed ?? 0}
                      </p>
                    </div>
                    {beastStatus?.requires_postgres ? (
                      <p className="mt-2 text-[11px] text-amber-300">
                        Policy marca Postgres como recomendado para Modo Bestia. Esta fase usa scheduler local con persistencia de estado JSON.
                      </p>
                    ) : null}
                  </div>
                </div>

                <div className="mt-3 rounded border border-slate-800 bg-slate-950/40 p-2">
                  <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                    <p className="uppercase tracking-wide text-slate-400">Jobs recientes</p>
                    <Badge variant="warn">{beastJobs.length} visibles</Badge>
                  </div>
                  {beastJobs.length ? (
                    <div className="max-h-48 space-y-1 overflow-auto text-xs">
                      {beastJobs.slice(0, 12).map((job) => (
                        <div key={`beast-job-${job.run_id}`} className="rounded border border-slate-800 bg-slate-900/60 px-2 py-1">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-slate-200">{job.run_id}</span>
                              <Badge variant={statusVariant(String(job.state || ""))}>{runStatusLabel(String(job.state || ""))}</Badge>
                              <Badge variant="warn">{String(job.tier || "-").toUpperCase()}</Badge>
                            </div>
                            <span className="text-slate-400" title={utcDateLabel(job.queued_at || job.started_at || job.finished_at)}>
                              {compactDate(job.queued_at || job.started_at || job.finished_at)}
                            </span>
                          </div>
                          <div className="mt-1 grid gap-1 md:grid-cols-2 text-slate-300">
                            <p>{job.market || "-"} / {job.symbol || "-"} / {job.timeframe || "-"}</p>
                            <p>strategies: {job.strategy_count ?? "-"} · units: {job.estimated_trial_units ?? "-"}</p>
                          </div>
                          {job.cancel_reason ? <p className="mt-1 text-rose-300">Cancelado: {job.cancel_reason}</p> : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400">
                      Todavia no hay jobs Beast. Usa “Ejecutar en Modo Bestia” para encolar batches grandes (si la policy lo permite).
                    </p>
                  )}
                </div>
              </div>

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
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-slate-300">
                <div>
                  {massRunId ? (
                    <>
                      <span className="font-semibold text-slate-100">{massRunId}</span>
                      {" · "}
                      Mostrando {massSortedRows.length ? massPageStart + 1 : 0}-{massPageEnd} de {massSortedRows.length} variantes
                    </>
                  ) : (
                    "Seleccioná un Research Batch (BX-...) para ver resultados."
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-slate-400">Filas</label>
                  <Select
                    value={massPageSize}
                    onChange={(e) => setMassPageSize(e.target.value as typeof massPageSize)}
                    className="h-8 min-w-[84px]"
                  >
                    <option value="10">10</option>
                    <option value="20">20</option>
                    <option value="30">30</option>
                    <option value="40">40</option>
                    <option value="50">50</option>
                  </Select>
                </div>
              </div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" variant="outline" onClick={selectMassPageVariants} disabled={!massPageRows.length}>
                    Seleccionar página (variantes)
                  </Button>
                  <Button type="button" variant="outline" onClick={selectMassAllVariants} disabled={!massSortedRows.length}>
                    Seleccionar todas (filtradas)
                  </Button>
                  <Button type="button" variant="outline" onClick={clearMassVariantSelection} disabled={!massSelectedVariantIds.length}>
                    Limpiar selección
                  </Button>
                  <Badge variant="warn">{massSelectedVariantIds.length} variantes</Badge>
                  <Badge variant="warn">{massSelectedRowsWithCatalogRun.length} con run BT</Badge>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={massTopSelectMetric} onChange={(e) => setMassTopSelectMetric(e.target.value as MassTopMetric)} className="h-8 min-w-[150px]">
                    <option value="winrate">Top por WinRate</option>
                    <option value="score">Top por Score</option>
                    <option value="sharpe">Top por Sharpe</option>
                    <option value="calmar">Top por Calmar</option>
                    <option value="expectancy">Top por Expectancy</option>
                    <option value="trades">Top por Trades</option>
                    <option value="maxdd">Top por MaxDD (menor mejor)</option>
                    <option value="costs">Top por CostsRatio (menor mejor)</option>
                  </Select>
                  <Input
                    className="h-8 w-20"
                    value={massTopSelectN}
                    onChange={(e) => setMassTopSelectN(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="20"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!massSortedRows.length}
                    onClick={() => selectMassTopVariants(massTopSelectMetric, massTopSelectN)}
                    title="Selecciona automáticamente el Top N por la métrica elegida"
                  >
                    Seleccionar Top N
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!massSortedRows.length}
                    onClick={() => selectMassTopVariants(massTopSelectMetric, massTopSelectN, { compareInRuns: true })}
                    title="Selecciona Top N y los carga en el Comparador de Runs"
                  >
                    Auto-shortlist → Comparar
                  </Button>
                  <label className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/40 px-2 py-1">
                    <input type="checkbox" checked={massAutoShortlistEnabled} onChange={(e) => setMassAutoShortlistEnabled(e.target.checked)} />
                    Auto-shortlist al cargar
                  </label>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!massSelectedRowsWithCatalogRun.length}
                    onClick={compareMassSelectedVariantsInRuns}
                    title="Carga los BT seleccionados en el Comparador Profesional de Runs"
                  >
                    Comparar seleccionadas en Runs
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={role !== "admin" || !massSelectedRowsWithCatalogRun.length}
                    onClick={() => void bulkMassSelectedVariantsAction("archive")}
                    title="Archiva (soft delete) los runs BT generados por estas variantes"
                  >
                    Archivar seleccionadas
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={role !== "admin" || !massSelectedRowsWithCatalogRun.length}
                    onClick={() => void bulkMassSelectedVariantsAction("delete")}
                    title="Borra runs BT del catálogo para estas variantes"
                  >
                    Borrar seleccionadas
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={role !== "admin" || massShortlistBusy || !massRunId || !massSelectedVariantIds.length}
                    onClick={() => void saveMassShortlistForBatch()}
                    title="Guarda la shortlist de variantes seleccionadas dentro del batch BX"
                  >
                    {massShortlistBusy ? "Guardando..." : "Guardar shortlist BX"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={massShortlistBusy || !massRunId}
                    onClick={() => void loadMassShortlistForBatch(massRunId, { syncCompare: true })}
                    title="Carga shortlist guardada del batch y la sincroniza con Comparador de Runs"
                  >
                    {massShortlistBusy ? "Cargando..." : "Cargar shortlist BX"}
                  </Button>
                </div>
              </div>
              <Table>
                <THead>
                  <TR>
                    <TH>Sel</TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("rank")}>Rank{massSortLabel("rank")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("variant")}>Variante{massSortLabel("variant")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("strategy")}>Estrategia{massSortLabel("strategy")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("score")}>Score{massSortLabel("score")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("trades")}>Trades OOS{massSortLabel("trades")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("winrate")}>WinRate{massSortLabel("winrate")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("sharpe")}>Sharpe{massSortLabel("sharpe")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("calmar")}>Calmar{massSortLabel("calmar")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("expectancy")}>Expectancy{massSortLabel("expectancy")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("maxdd")}>MaxDD%{massSortLabel("maxdd")}</button></TH>
                    <TH><button type="button" className="text-left hover:text-cyan-200" onClick={() => toggleMassSort("costs")}>CostsRatio{massSortLabel("costs")}</button></TH>
                    <TH>Gates</TH>
                    <TH>Regímenes</TH>
                    <TH>Acción</TH>
                  </TR>
                </THead>
                <TBody>
                  {massPageRows.map((row) => (
                    <TR key={row.variant_id} onClick={() => setMassSelectedRow(row)} className="cursor-pointer">
                      <TD onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={massSelectedVariantIds.includes(row.variant_id)}
                          onChange={() => toggleMassVariantSelection(row.variant_id)}
                        />
                      </TD>
                      <TD>{row.rank ?? "-"}</TD>
                      <TD className="font-mono text-xs">{row.variant_id}</TD>
                      <TD>{row.strategy_name || row.strategy_id}</TD>
                      <TD>{fmtNum(row.score)}</TD>
                      <TD>{row.summary?.trade_count_oos ?? "-"}</TD>
                      <TD>{fmtPct(row.summary?.winrate_oos ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.sharpe_oos ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.calmar_oos ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.expectancy_net_usd ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.max_dd_oos_pct ?? 0)}</TD>
                      <TD>{fmtNum(row.summary?.costs_ratio ?? 0)}</TD>
                      <TD>
                        <div className="space-y-1">
                          <Badge variant={massGatesBadgeVariant(row)}>
                            {massGatesPassed(row) === true ? "PASS" : massGatesPassed(row) === false ? "FAIL" : "N/A"}
                          </Badge>
                          {row.gates_eval?.fail_reasons?.length ? (
                            <p className="max-w-[180px] truncate text-[10px] text-rose-300" title={row.gates_eval.fail_reasons.join(" | ")}>
                              {row.gates_eval.fail_reasons.join(" | ")}
                            </p>
                          ) : null}
                        </div>
                      </TD>
                      <TD>{Object.keys(row.regime_metrics || {}).join(", ") || "-"}</TD>
                      <TD>
                        <Button
                          type="button"
                          variant="outline"
                          disabled={role !== "admin" || !massRunId || row.recommendable_option_b === false || massGatesPassed(row) === false}
                          title={
                            row.recommendable_option_b === false || massGatesPassed(row) === false
                              ? `No elegible para sugerencia (gates): ${(row.gates_eval?.fail_reasons || []).join(" | ") || "constraints"}`
                              : "Crear draft Opcion B desde esta variante"
                          }
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
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 px-1 text-xs">
                <div className="text-slate-400">
                  Página {massPageSafe}/{massTotalPages}
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    type="button"
                    className="h-8 px-2"
                    disabled={massPageSafe <= 1}
                    onClick={() => setMassPage((p) => Math.max(1, p - 1))}
                  >
                    Anterior
                  </Button>
                  {massPageNumbers.map((p) => (
                    <Button
                      key={`mass-page-${p}`}
                      type="button"
                      variant={p === massPageSafe ? "default" : "outline"}
                      className="h-8 px-2"
                      onClick={() => {
                        setMassPage(p);
                        setMassPageInput(String(p));
                      }}
                    >
                      {p}
                    </Button>
                  ))}
                  <Button
                    variant="outline"
                    type="button"
                    className="h-8 px-2"
                    disabled={massPageSafe >= massTotalPages}
                    onClick={() => setMassPage((p) => Math.min(massTotalPages, p + 1))}
                  >
                    Siguiente
                  </Button>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <span>Ir a</span>
                  <Input
                    className="h-8 w-16"
                    value={massPageInput}
                    onChange={(e) => setMassPageInput(e.target.value.replace(/[^0-9]/g, ""))}
                    onBlur={() => {
                      const next = Number(massPageInput || "1");
                      if (Number.isFinite(next)) setMassPage(Math.min(massTotalPages, Math.max(1, next)));
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        const next = Number(massPageInput || "1");
                        if (Number.isFinite(next)) setMassPage(Math.min(massTotalPages, Math.max(1, next)));
                      }
                    }}
                  />
                </div>
              </div>
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
                  <div className="space-y-2 text-xs">
                    <p className="font-semibold text-slate-300">Gates avanzados (PBO / DSR / WF / Stress)</p>
                    {massSelectedRow.gates_eval ? (
                      <>
                        <div
                          className={`rounded border p-2 ${
                            massSelectedRow.gates_eval.passed
                              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                              : "border-rose-500/40 bg-rose-500/10 text-rose-200"
                          }`}
                        >
                          Estado gates: {massSelectedRow.gates_eval.passed ? "PASS" : "FAIL"}
                          {massSelectedRow.gates_eval.fail_reasons?.length ? ` ? ${massSelectedRow.gates_eval.fail_reasons.join(" | ")}` : ""}
                        </div>
                        <div className="space-y-1">
                          {Object.entries(massSelectedRow.gates_eval.checks || {}).map(([key, check]) => {
                            const pass = typeof check?.pass === "boolean" ? check.pass : null;
                            return (
                              <div key={`gate-${key}`} className="rounded border border-slate-800 p-2">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-semibold text-slate-200">{key}</span>
                                  <Badge variant={pass === true ? "success" : pass === false ? "danger" : "warn"}>
                                    {pass === true ? "PASS" : pass === false ? "FAIL" : "N/A"}
                                  </Badge>
                                </div>
                                <p className="mt-1 break-words text-slate-400">
                                  {Object.entries(check || {})
                                    .filter(([k]) => !["pass"].includes(k))
                                    .slice(0, 8)
                                    .map(([k, v]) => `${k}=${typeof v === "number" ? fmtNum(v) : String(v)}`)
                                    .join(" ? ")}
                                </p>
                              </div>
                            );
                          })}
                        </div>
                      </>
                    ) : (
                      <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-slate-400">
                        Sin evaluacion de gates avanzados para esta variante.
                      </div>
                    )}
                  </div>
                  <div className="space-y-2 text-xs">
                    <p className="font-semibold text-slate-300">Microestructura (Order Flow L1 / VPIN)</p>
                    {massSelectedRow.microstructure?.available ? (
                      <>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="rounded border border-slate-800 p-2">VPIN CDF OOS: {fmtNum(massSelectedRow.microstructure.aggregate?.vpin_cdf_oos ?? 0)}</div>
                          <div className="rounded border border-slate-800 p-2">Soft/Hard folds: {massSelectedRow.microstructure.aggregate?.micro_soft_kill_folds ?? 0}/{massSelectedRow.microstructure.aggregate?.micro_hard_kill_folds ?? 0}</div>
                          <div className="rounded border border-slate-800 p-2">Ratio soft kill: {fmtPct(massSelectedRow.microstructure.aggregate?.micro_soft_kill_ratio ?? 0)}</div>
                          <div className="rounded border border-slate-800 p-2">Ratio hard kill: {fmtPct(massSelectedRow.microstructure.aggregate?.micro_hard_kill_ratio ?? 0)}</div>
                        </div>
                        <div
                          className={`rounded border p-2 ${
                            massSelectedRow.microstructure.symbol_kill?.hard
                              ? "border-red-500/40 bg-red-500/10 text-red-200"
                              : massSelectedRow.microstructure.symbol_kill?.soft
                                ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                                : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                          }`}
                        >
                          Kill s?mbolo: {massSelectedRow.microstructure.symbol_kill?.hard ? "HARD" : massSelectedRow.microstructure.symbol_kill?.soft ? "SOFT" : "Sin kill"}
                          {massSelectedRow.microstructure.symbol_kill?.reasons?.length
                            ? ` ? Razones: ${massSelectedRow.microstructure.symbol_kill.reasons.join(", ")}`
                            : ""}
                        </div>
                        {massSelectedRow.microstructure.fold_debug?.length ? (
                          <div className="space-y-1">
                            <p className="font-semibold text-slate-300">Debug por fold</p>
                            {massSelectedRow.microstructure.fold_debug.slice(0, 8).map((fd, idx) => (
                              <div key={`micro-fold-${fd.fold ?? idx}`} className="rounded border border-slate-800 p-2">
                                <p className="text-slate-200">Fold {fd.fold ?? "-"} ? {fd.test_start || "-"} ? {fd.test_end || "-"} ? kill {fd.hard_kill_symbol ? "HARD" : fd.soft_kill_symbol ? "SOFT" : "none"}</p>
                                <p className="text-slate-400">VPIN {fmtNum(fd.vpin ?? 0)} ? CDF max {fmtNum(fd.vpin_cdf ?? 0)} ? spread {fmtNum(fd.spread_bps ?? 0)}bps (x{fmtNum(fd.spread_multiplier ?? 1)}) ? slippage {fmtNum(fd.slippage_bps ?? 0)}bps (x{fmtNum(fd.slippage_multiplier ?? 1)}) ? vol x{fmtNum(fd.vol_multiplier ?? 1)}</p>
                                {fd.kill_reasons?.length ? <p className="text-amber-300">Razones: {fd.kill_reasons.join(", ")}</p> : null}
                                {!fd.available && fd.reason ? <p className="text-slate-500">No disponible: {fd.reason}</p> : null}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-slate-400">
                        No hay debug de microestructura para esta variante (dataset no legible u Order Flow L1 deshabilitado).
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-sm text-slate-400">Sin selección.</p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Detalle de Corrida (Strategy Tester)</CardTitle>
        <CardDescription>
          {focusRun
            ? `${focusRun.id} · ${focusRun.strategy_id} · ${focusRun.symbol || focusRun.universe?.[0] || "-"} · ${focusRun.timeframe || "-"}`
            : "Sin corridas disponibles."}
        </CardDescription>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {[
              ["overview", "Overview"],
              ["performance", "Performance"],
              ["trades_analysis", "Trades analysis"],
              ["ratios", "Risk / ratios"],
              ["trades_list", "Listado de trades"],
              ["artifacts", "Artifacts"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setFocusRunTab(id as FocusRunTab)}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold ${
                  focusRunTab === id
                    ? "border-cyan-400/50 bg-cyan-500/10 text-cyan-200"
                    : "border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {!focusRun ? (
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-300">
              <p className="font-semibold text-slate-100">Todavia no hay una corrida para mostrar</p>
              <p className="mt-1">Ejecuta un Quick Backtest o selecciona una corrida existente para ver su detalle por pestañas.</p>
            </div>
          ) : null}

          {focusRun && focusRunTab === "overview" ? (
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 md:col-span-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">Metadata y datos</p>
                <p className="text-sm text-slate-200">
                  {focusRun.market || "-"} / {focusRun.symbol || focusRun.universe?.[0] || "-"} @ {focusRun.timeframe || "-"} · fuente {focusRun.data_source || "-"}
                </p>
                <p className="text-xs text-slate-400">
                  Rango: {focusRun.period.start} → {focusRun.period.end} · Commit: <span className="font-mono">{shortHash(focusRun.git_commit, 12)}</span>
                </p>
                <p className="text-xs font-mono text-slate-400 break-all">Dataset hash: {focusRun.dataset_hash || "-"}</p>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Entradas</p>
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
                <p className="text-xs uppercase tracking-wide text-slate-400">Modelo de costos (resultado neto)</p>
                <p className="text-sm text-slate-200">
                  Fees {fmtNum(focusRun.costs_breakdown?.fees_total ?? 0)} | Spread {fmtNum(focusRun.costs_breakdown?.spread_total ?? 0)} | Slippage{" "}
                  {fmtNum(focusRun.costs_breakdown?.slippage_total ?? 0)} | Funding {fmtNum(focusRun.costs_breakdown?.funding_total ?? 0)} | Rollover{" "}
                  {fmtNum(focusRun.costs_breakdown?.rollover_total ?? 0)}
                </p>
                <p className="text-xs text-slate-400">
                  % sobre PnL bruto: fees {fmtPct(focusRun.costs_breakdown?.fees_pct_of_gross_pnl ?? 0)} · spread{" "}
                  {fmtPct(focusRun.costs_breakdown?.spread_pct_of_gross_pnl ?? 0)} · slippage{" "}
                  {fmtPct(focusRun.costs_breakdown?.slippage_pct_of_gross_pnl ?? 0)} · funding{" "}
                  {fmtPct(focusRun.costs_breakdown?.funding_pct_of_gross_pnl ?? 0)} · rollover{" "}
                  {fmtPct(focusRun.costs_breakdown?.rollover_pct_of_gross_pnl ?? 0)}
                </p>
              </div>
            </div>
          ) : null}

          {focusRun && focusRunTab === "performance" ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <MetricTile label="CAGR" value={fmtPct(focusRun.metrics.cagr)} gradeKey="cagr" numericValue={focusRun.metrics.cagr} />
                <MetricTile label="Max DD" value={fmtPct(focusRun.metrics.max_dd)} gradeKey="max_dd" numericValue={focusRun.metrics.max_dd} />
                <MetricTile label="PnL neto (aprox)" value={fmtNum(focusRun.costs_breakdown?.net_pnl_total ?? focusRun.costs_breakdown?.net_pnl ?? 0)} />
                <MetricTile
                  label={`Expectancy (${focusRun.metrics.expectancy_unit || focusRun.metrics.expectancy_pct_unit || "unidad"})`}
                  value={fmtNum(focusRun.metrics.expectancy)}
                />
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <Card>
                  <CardTitle>Equity curve</CardTitle>
                  <CardDescription>Performance acumulada de la corrida seleccionada.</CardDescription>
                  <CardContent>
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={250}>
                        <LineChart data={focusRunChartData}>
                          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                          <XAxis dataKey="index" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                          <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                          <Line type="monotone" dataKey="equity" stroke="#22d3ee" strokeWidth={2} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardTitle>Drawdown curve</CardTitle>
                  <CardDescription>Perfil de riesgo de la corrida seleccionada.</CardDescription>
                  <CardContent>
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={250}>
                        <LineChart data={focusRunChartData}>
                          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                          <XAxis dataKey="index" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                          <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                          <Line type="monotone" dataKey="drawdown" stroke="#f97316" strokeWidth={2} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          ) : null}

          {focusRun && focusRunTab === "trades_analysis" ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <MetricTile label="Trades" value={String(focusTradeAnalysis.total)} />
                <MetricTile label="W / L / BE" value={`${focusTradeAnalysis.wins} / ${focusTradeAnalysis.losses} / ${focusTradeAnalysis.breakeven}`} />
                <MetricTile label="Largos / Cortos" value={`${focusTradeAnalysis.longCount} / ${focusTradeAnalysis.shortCount}`} />
                <MetricTile label="Win rate" value={fmtPct(focusRun.metrics.winrate)} gradeKey="winrate" numericValue={focusRun.metrics.winrate} />
                <MetricTile label="Avg win (net)" value={fmtNum(focusTradeAnalysis.avgWin)} />
                <MetricTile label="Avg loss (net)" value={fmtNum(focusTradeAnalysis.avgLoss)} />
                <MetricTile label="Max win (net)" value={fmtNum(focusTradeAnalysis.maxWin)} />
                <MetricTile label="Max loss (net)" value={fmtNum(focusTradeAnalysis.maxLoss)} />
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Motivos de entrada (top)</p>
                  <div className="mt-2 space-y-2">
                    {focusTradeAnalysis.topEntryReasons.length ? (
                      focusTradeAnalysis.topEntryReasons.map(([reason, count]) => (
                        <div key={`entry-${reason}`} className="flex items-center justify-between gap-2 rounded border border-slate-800 px-2 py-1 text-sm">
                          <span className="truncate text-slate-200">{reason}</span>
                          <Badge variant="neutral">{count}</Badge>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">Sin datos de motivos de entrada.</p>
                    )}
                  </div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-400">Motivos de salida (top)</p>
                  <div className="mt-2 space-y-2">
                    {focusTradeAnalysis.topExitReasons.length ? (
                      focusTradeAnalysis.topExitReasons.map(([reason, count]) => (
                        <div key={`exit-${reason}`} className="flex items-center justify-between gap-2 rounded border border-slate-800 px-2 py-1 text-sm">
                          <span className="truncate text-slate-200">{reason}</span>
                          <Badge variant="neutral">{count}</Badge>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">Sin datos de motivos de salida.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {focusRun && focusRunTab === "ratios" ? (
            <div className="grid gap-3 xl:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Risk / performance ratios</p>
                <Table>
                  <TBody>
                    <TR>
                      <TD>Sharpe</TD>
                      <TD className={gradeCellClass("sharpe", focusRun.metrics.sharpe)}>{fmtNum(focusRun.metrics.sharpe)}</TD>
                    </TR>
                    <TR>
                      <TD>Sortino</TD>
                      <TD className={gradeCellClass("sortino", focusRun.metrics.sortino)}>{fmtNum(focusRun.metrics.sortino)}</TD>
                    </TR>
                    <TR>
                      <TD>Calmar</TD>
                      <TD className={gradeCellClass("calmar", focusRun.metrics.calmar)}>{fmtNum(focusRun.metrics.calmar)}</TD>
                    </TR>
                    <TR>
                      <TD>Profit Factor</TD>
                      <TD>{fmtNum(focusRun.metrics.profit_factor ?? 0)}</TD>
                    </TR>
                    <TR>
                      <TD>Turnover</TD>
                      <TD className={gradeCellClass("turnover", focusRun.metrics.turnover)}>{fmtNum(focusRun.metrics.turnover)}</TD>
                    </TR>
                    <TR>
                      <TD>Robustez</TD>
                      <TD className={gradeCellClass("robustness", focusRun.metrics.robustness_score ?? focusRun.metrics.robust_score)}>
                        {fmtNum(focusRun.metrics.robustness_score ?? focusRun.metrics.robust_score)}
                      </TD>
                    </TR>
                  </TBody>
                </Table>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-400">Costos y eficiencia</p>
                <Table>
                  <TBody>
                    <TR>
                      <TD>Gross PnL</TD>
                      <TD>{fmtNum(focusRun.costs_breakdown?.gross_pnl_total ?? focusRun.costs_breakdown?.gross_pnl ?? 0)}</TD>
                    </TR>
                    <TR>
                      <TD>Net PnL</TD>
                      <TD>{fmtNum(focusRun.costs_breakdown?.net_pnl_total ?? focusRun.costs_breakdown?.net_pnl ?? 0)}</TD>
                    </TR>
                    <TR>
                      <TD>Fees total</TD>
                      <TD>{fmtNum(focusRun.costs_breakdown?.fees_total ?? 0)}</TD>
                    </TR>
                    <TR>
                      <TD>Spread total</TD>
                      <TD>{fmtNum(focusRun.costs_breakdown?.spread_total ?? 0)}</TD>
                    </TR>
                    <TR>
                      <TD>Slippage total</TD>
                      <TD>{fmtNum(focusRun.costs_breakdown?.slippage_total ?? 0)}</TD>
                    </TR>
                    <TR>
                      <TD>Funding + Rollover</TD>
                      <TD>{fmtNum((focusRun.costs_breakdown?.funding_total ?? 0) + (focusRun.costs_breakdown?.rollover_total ?? 0))}</TD>
                    </TR>
                  </TBody>
                </Table>
              </div>
            </div>
          ) : null}

          {focusRun && focusRunTab === "trades_list" ? (
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">
                Listado de trades ({focusTrades.length}) · se muestran hasta 200 para mantener la UI fluida
              </p>
              {focusTrades.length ? (
                <div className="max-h-[32rem] overflow-auto rounded-lg border border-slate-800">
                  <Table>
                    <THead>
                      <TR>
                        <TH>Timestamp</TH>
                        <TH>Simbolo</TH>
                        <TH>Lado</TH>
                        <TH>Entrada</TH>
                        <TH>Salida</TH>
                        <TH>Qty</TH>
                        <TH>PnL neto</TH>
                        <TH>MFE</TH>
                        <TH>MAE</TH>
                        <TH>Motivo entrada</TH>
                        <TH>Motivo salida</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {focusTrades.slice(0, 200).map((trade) => (
                        <TR key={`focus-tr-${trade.id}`}>
                          <TD title={trade.exit_time}>{compactDate(trade.entry_time)}</TD>
                          <TD>{trade.symbol}</TD>
                          <TD>{trade.side}</TD>
                          <TD>{fmtNum(trade.entry_px)}</TD>
                          <TD>{fmtNum(trade.exit_px)}</TD>
                          <TD>{fmtNum(trade.qty)}</TD>
                          <TD className={(trade.pnl_net ?? trade.pnl) >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtNum(trade.pnl_net ?? trade.pnl)}</TD>
                          <TD>{fmtNum(trade.mfe)}</TD>
                          <TD>{fmtNum(trade.mae)}</TD>
                          <TD>{trade.reason_code || "-"}</TD>
                          <TD>{trade.exit_reason || "-"}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </div>
              ) : (
                <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-300">
                  <p className="font-semibold text-slate-100">Todavia no hay listado de trades</p>
                  <p className="mt-1">Algunas corridas no guardan trades completos. Ejecuta una corrida con export de trades para poblar esta pestaña.</p>
                </div>
              )}
            </div>
          ) : null}

          {focusRun && focusRunTab === "artifacts" ? (
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-wide text-slate-400">Artifacts del run</p>
              {focusArtifacts.some((a) => a.href) ? (
                <div className="grid gap-3 md:grid-cols-3">
                  {focusArtifacts.map((artifact) => (
                    <div key={artifact.label} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                      <p className="text-sm font-semibold text-slate-100">{artifact.label}</p>
                      {artifact.href ? (
                        <>
                          <p className="mt-1 break-all text-xs font-mono text-slate-400">{artifact.href}</p>
                          <div className="mt-2 flex gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => window.open(artifact.href || "", "_blank", "noopener,noreferrer")}
                            >
                              Descargar
                            </Button>
                          </div>
                        </>
                      ) : (
                        <p className="mt-1 text-xs text-slate-400">No disponible en esta corrida.</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-300">
                  <p className="font-semibold text-slate-100">No hay artifacts exportados</p>
                  <p className="mt-1">Ejecuta un quick backtest completo o exporta resultados para generar archivos descargables.</p>
                </div>
              )}
            </div>
          ) : null}
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

function MetricTile({
  label,
  value,
  gradeKey,
  numericValue,
}: {
  label: string;
  value: string;
  gradeKey?: string;
  numericValue?: number;
}) {
  const gradeClass = gradeKey ? gradeCellClass(gradeKey, numericValue) : "";
  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-900/60 p-3 ${gradeClass}`.trim()}>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-100">{value}</p>
    </div>
  );
}
