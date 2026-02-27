"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet, apiPost } from "@/lib/client-api";
import type { Strategy, Trade } from "@/lib/types";
import { fmtPct, fmtUsd } from "@/lib/utils";

type TradesSummaryBucket = {
  trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  winrate: number;
  net_pnl: number;
  gross_pnl: number;
  fees_total: number;
  slippage_total: number;
  avg_trade: number;
  avg_holding_minutes: number;
};

type TradesSummaryResponse = {
  totals: TradesSummaryBucket;
  by_environment: Array<TradesSummaryBucket & { environment: string }>;
  by_mode: Array<TradesSummaryBucket & { mode: string; environment: string }>;
  by_strategy: Array<TradesSummaryBucket & { strategy_id: string; strategy_name: string }>;
  by_day: Array<TradesSummaryBucket & { day: string }>;
  by_strategy_day: Array<TradesSummaryBucket & { strategy_id: string; strategy_name: string; day: string; environment: string }>;
};

type TradeFilters = {
  strategy_id: string;
  symbol: string;
  side: string;
  mode: string;
  environment: string;
  reason_code: string;
  exit_reason: string;
  result: string;
  date_from: string;
  date_to: string;
};

type TradeSortKey = "exit_time" | "entry_time" | "strategy_id" | "symbol" | "run_mode" | "pnl_net" | "fees" | "slippage" | "qty";

const EMPTY_FILTERS: TradeFilters = {
  strategy_id: "",
  symbol: "",
  side: "",
  mode: "",
  environment: "",
  reason_code: "",
  exit_reason: "",
  result: "",
  date_from: "",
  date_to: "",
};

export default function TradesPage() {
  const { role } = useSession();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [summaryData, setSummaryData] = useState<TradesSummaryResponse | null>(null);
  const [busyDelete, setBusyDelete] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deletePreviewCount, setDeletePreviewCount] = useState<number | null>(null);
  const [selectedTradeIds, setSelectedTradeIds] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<"30" | "60" | "100">("30");
  const [sortBy, setSortBy] = useState<TradeSortKey>("exit_time");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [topRowsSize, setTopRowsSize] = useState<"10" | "25" | "50">("10");
  const [filters, setFilters] = useState<TradeFilters>(EMPTY_FILTERS);

  const refresh = useCallback(async () => {
    const params = new URLSearchParams();
    if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
    if (filters.symbol) params.set("symbol", filters.symbol);
    if (filters.side) params.set("side", filters.side);
    if (filters.mode) params.set("mode", filters.mode);
    if (filters.environment) params.set("environment", filters.environment);
    if (filters.reason_code) params.set("reason_code", filters.reason_code);
    if (filters.exit_reason) params.set("exit_reason", filters.exit_reason);
    if (filters.result) params.set("result", filters.result);
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);
    params.set("limit", "5000");
    const [tradesRows, stgRows, summaryRows] = await Promise.all([
      apiGet<Trade[]>(`/api/v1/trades?${params.toString()}`),
      apiGet<Strategy[]>("/api/v1/strategies"),
      apiGet<TradesSummaryResponse>(`/api/v1/trades/summary?${params.toString()}`),
    ]);
    setTrades(tradesRows);
    setStrategies(stgRows);
    setSummaryData(summaryRows);
  }, [filters]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const uniqueSymbols = useMemo(() => [...new Set(trades.map((row) => row.symbol))], [trades]);
  const uniqueReasons = useMemo(() => [...new Set(trades.map((row) => row.reason_code))], [trades]);
  const uniqueExits = useMemo(() => [...new Set(trades.map((row) => row.exit_reason))], [trades]);
  const uniqueModes = useMemo(
    () => [...new Set(trades.map((row) => String((row as Trade & { run_mode?: string }).run_mode || "")))].filter(Boolean),
    [trades],
  );

  const localSummaryFallback = useMemo(() => {
    const total = trades.length;
    const wins = trades.filter((t) => Number(t.pnl_net || 0) > 0).length;
    const losses = trades.filter((t) => Number(t.pnl_net || 0) < 0).length;
    const breakeven = total - wins - losses;
    const netPnl = trades.reduce((acc, t) => acc + Number(t.pnl_net || 0), 0);
    const grossPnl = trades.reduce((acc, t) => acc + Number(t.pnl || 0), 0);
    const fees = trades.reduce((acc, t) => acc + Number(t.fees || 0), 0);
    const slippage = trades.reduce((acc, t) => acc + Number(t.slippage || 0), 0);
    const holdAvg = total
      ? trades.reduce((acc, t) => acc + Math.abs(new Date(t.exit_time).getTime() - new Date(t.entry_time).getTime()) / 60_000, 0) / total
      : 0;
    return {
      trades: total,
      wins,
      losses,
      breakeven,
      winrate: total ? wins / total : 0,
      net_pnl: netPnl,
      gross_pnl: grossPnl,
      fees_total: fees,
      slippage_total: slippage,
      avg_trade: total ? netPnl / total : 0,
      avg_holding_minutes: holdAvg,
    };
  }, [trades]);

  const totals = summaryData?.totals || localSummaryFallback;
  const summaryByEnvironment = summaryData?.by_environment || [];
  const summaryByMode = summaryData?.by_mode || [];
  const summaryByStrategy = useMemo(
    () => (summaryData?.by_strategy || []).slice(0, Number(topRowsSize)),
    [summaryData, topRowsSize],
  );
  const summaryByStrategyDay = useMemo(
    () => (summaryData?.by_strategy_day || []).slice(0, Number(topRowsSize)),
    [summaryData, topRowsSize],
  );

  const sortedTrades = useMemo(() => {
    const rows = [...trades];
    const getMode = (row: Trade) => String((row as Trade & { run_mode?: string }).run_mode || "backtest").toLowerCase();
    const dateNum = (raw: string | undefined | null) => {
      const ts = raw ? new Date(raw).getTime() : 0;
      return Number.isFinite(ts) ? ts : 0;
    };
    const dir = sortDir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      let av: number | string = 0;
      let bv: number | string = 0;
      switch (sortBy) {
        case "entry_time":
          av = dateNum(a.entry_time);
          bv = dateNum(b.entry_time);
          break;
        case "exit_time":
          av = dateNum(a.exit_time);
          bv = dateNum(b.exit_time);
          break;
        case "strategy_id":
          av = String(a.strategy_id || "");
          bv = String(b.strategy_id || "");
          break;
        case "symbol":
          av = String(a.symbol || "");
          bv = String(b.symbol || "");
          break;
        case "run_mode":
          av = getMode(a);
          bv = getMode(b);
          break;
        case "pnl_net":
          av = Number(a.pnl_net || 0);
          bv = Number(b.pnl_net || 0);
          break;
        case "fees":
          av = Number(a.fees || 0);
          bv = Number(b.fees || 0);
          break;
        case "slippage":
          av = Number(a.slippage || 0);
          bv = Number(b.slippage || 0);
          break;
        case "qty":
          av = Number(a.qty || 0);
          bv = Number(b.qty || 0);
          break;
      }
      if (typeof av === "string" || typeof bv === "string") {
        const cmp = String(av).localeCompare(String(bv));
        if (cmp !== 0) return cmp * dir;
        return String(a.id || "").localeCompare(String(b.id || "")) * dir;
      }
      if (av === bv) return String(a.id || "").localeCompare(String(b.id || "")) * dir;
      return (Number(av) - Number(bv)) * dir;
    });
    return rows;
  }, [sortBy, sortDir, trades]);

  const pageSizeNum = Number(pageSize);
  const totalPages = Math.max(1, Math.ceil(sortedTrades.length / pageSizeNum));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const pageRows = useMemo(() => {
    const start = (safePage - 1) * pageSizeNum;
    return sortedTrades.slice(start, start + pageSizeNum);
  }, [sortedTrades, safePage, pageSizeNum]);
  useEffect(() => {
    setPage(1);
    setDeletePreviewCount(null);
  }, [filters, pageSize, sortBy, sortDir]);

  useEffect(() => {
    setSelectedTradeIds([]);
  }, [filters, trades]);

  const pageStart = sortedTrades.length ? (safePage - 1) * pageSizeNum + 1 : 0;
  const pageEnd = Math.min(sortedTrades.length, safePage * pageSizeNum);

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setDeletePreviewCount(null);
    setDeleteMessage("");
    setDeleteError("");
  };

  const deletePayloadFromFilters = useCallback(
    (dryRun = false) => ({
      strategy_id: filters.strategy_id || null,
      symbol: filters.symbol || null,
      side: filters.side || null,
      mode: filters.mode || null,
      environment: filters.environment || null,
      reason_code: filters.reason_code || null,
      exit_reason: filters.exit_reason || null,
      result: filters.result || null,
      date_from: filters.date_from || null,
      date_to: filters.date_to || null,
      dry_run: dryRun,
    }),
    [filters],
  );

  const previewDeleteFiltered = async () => {
    if (role !== "admin") return;
    setBusyDelete(true);
    setDeleteError("");
    setDeleteMessage("");
    try {
      const res = await apiPost<{ deleted_count: number; dry_run: boolean }>("/api/v1/trades/bulk-delete", deletePayloadFromFilters(true));
      setDeletePreviewCount(Number(res?.deleted_count || 0));
      setDeleteMessage(`Preview: ${Number(res?.deleted_count || 0)} operaciones coinciden con los filtros actuales.`);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "No se pudo calcular el preview de borrado.");
    } finally {
      setBusyDelete(false);
    }
  };

  const bulkDeleteFiltered = async () => {
    if (role !== "admin" || !trades.length) return;
    setDeleteError("");
    setDeleteMessage("");
    const envLabel =
      filters.environment === "real"
        ? "entorno real (LIVE)"
        : filters.environment === "prueba"
          ? "entorno prueba (backtest/paper/testnet)"
          : "todos los entornos";
    const label = filters.mode ? `modo ${filters.mode} en ${envLabel}` : `${envLabel} con los filtros actuales`;
    const ok = window.confirm(`Vas a borrar ${trades.length} operaciones de ${label}. Esta accion modifica el historial de runs. Continuar?`);
    if (!ok) return;
    setBusyDelete(true);
    try {
      const res = await apiPost<{ deleted_count: number }>("/api/v1/trades/bulk-delete", deletePayloadFromFilters(false));
      await refresh();
      setDeletePreviewCount(null);
      setSelectedTradeIds([]);
      setDeleteMessage(`Borradas ${Number(res?.deleted_count || 0)} operaciones filtradas.`);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "No se pudieron borrar las operaciones filtradas.");
    } finally {
      setBusyDelete(false);
    }
  };

  const pageIds = useMemo(() => pageRows.map((row) => String(row.id)), [pageRows]);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedTradeIds.includes(id));
  const selectedTradesCount = selectedTradeIds.length;

  const toggleSelectTrade = (tradeId: string) => {
    setSelectedTradeIds((prev) => (prev.includes(tradeId) ? prev.filter((id) => id !== tradeId) : [...prev, tradeId]));
  };

  const toggleSelectPageTrades = () => {
    setSelectedTradeIds((prev) => {
      const prevSet = new Set(prev);
      if (allPageSelected) {
        return prev.filter((id) => !pageIds.includes(id));
      }
      pageIds.forEach((id) => prevSet.add(id));
      return Array.from(prevSet);
    });
  };

  const clearTradeSelection = () => setSelectedTradeIds([]);

  const bulkDeleteSelectedTrades = async () => {
    if (role !== "admin" || !selectedTradeIds.length) return;
    setDeleteError("");
    setDeleteMessage("");
    const ok = window.confirm(`Vas a borrar ${selectedTradeIds.length} operaciones seleccionadas. Esta accion es irreversible. Continuar?`);
    if (!ok) return;
    setBusyDelete(true);
    try {
      const res = await apiPost<{ deleted_count: number }>("/api/v1/trades/bulk-delete", {
        ids: selectedTradeIds,
        dry_run: false,
      });
      await refresh();
      setDeletePreviewCount(null);
      setSelectedTradeIds([]);
      setDeleteMessage(`Borradas ${Number(res?.deleted_count || 0)} operaciones seleccionadas.`);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "No se pudieron borrar las operaciones seleccionadas.");
    } finally {
      setBusyDelete(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Operaciones</CardTitle>
        <CardDescription>Historial de trades con filtros por estrategia/simbolo/resultado y separacion clara entre real (LIVE) y prueba.</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Estrategia</label>
            <Select value={filters.strategy_id} onChange={(e) => setFilters((prev) => ({ ...prev, strategy_id: e.target.value }))}>
              <option value="">Todas las estrategias</option>
              {strategies.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} v{row.version}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Simbolo</label>
            <Select value={filters.symbol} onChange={(e) => setFilters((prev) => ({ ...prev, symbol: e.target.value }))}>
              <option value="">Todos los simbolos</option>
              {uniqueSymbols.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Lado</label>
            <Select value={filters.side} onChange={(e) => setFilters((prev) => ({ ...prev, side: e.target.value }))}>
              <option value="">Todos los lados</option>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Resultado</label>
            <Select value={filters.result} onChange={(e) => setFilters((prev) => ({ ...prev, result: e.target.value }))}>
              <option value="">Todos los resultados</option>
              <option value="win">Ganadora</option>
              <option value="loss">Perdedora</option>
              <option value="breakeven">Neutra</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Modo</label>
            <Select value={filters.mode} onChange={(e) => setFilters((prev) => ({ ...prev, mode: e.target.value }))}>
              <option value="">Todos los modos</option>
              {["backtest", "paper", "testnet", "live", ...uniqueModes.filter((m) => !["backtest", "paper", "testnet", "live"].includes(m))]
                .filter(Boolean)
                .map((row) => (
                  <option key={row} value={row}>
                    {row}
                  </option>
                ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Entorno</label>
            <Select value={filters.environment} onChange={(e) => setFilters((prev) => ({ ...prev, environment: e.target.value }))}>
              <option value="">Todos los entornos</option>
              <option value="real">Real (LIVE)</option>
              <option value="prueba">Prueba (Backtest/Paper/Testnet)</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Motivo de entrada</label>
            <Select value={filters.reason_code} onChange={(e) => setFilters((prev) => ({ ...prev, reason_code: e.target.value }))}>
              <option value="">Todos los motivos</option>
              {uniqueReasons.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Motivo de salida</label>
            <Select value={filters.exit_reason} onChange={(e) => setFilters((prev) => ({ ...prev, exit_reason: e.target.value }))}>
              <option value="">Todos los motivos</option>
              {uniqueExits.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Desde</label>
            <Input type="date" value={filters.date_from} onChange={(e) => setFilters((prev) => ({ ...prev, date_from: e.target.value }))} />
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Hasta</label>
            <Input type="date" value={filters.date_to} onChange={(e) => setFilters((prev) => ({ ...prev, date_to: e.target.value }))} />
          </div>
          <div className="xl:col-span-2">
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Busqueda rapida de simbolo</label>
            <Input
              placeholder="Escribi un simbolo y presiona Enter (ej: BTCUSDT)"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  const value = (event.target as HTMLInputElement).value;
                  setFilters((prev) => ({ ...prev, symbol: value.trim() }));
                }
              }}
            />
          </div>
          <div className="flex items-end">
            <Button variant="outline" onClick={resetFilters}>
              Limpiar filtros
            </Button>
          </div>
          <div className="md:col-span-2 xl:col-span-6 grid gap-2 rounded border border-slate-800 bg-slate-950/40 p-2 text-xs text-slate-300 md:grid-cols-3">
            <div className="flex items-center gap-2">
              <span className="text-slate-400">Ordenar por</span>
              <Select value={sortBy} onChange={(e) => setSortBy(e.target.value as TradeSortKey)} className="h-8 min-w-[150px]">
                <option value="exit_time">Salida (timestamp)</option>
                <option value="entry_time">Entrada (timestamp)</option>
                <option value="pnl_net">PnL neto</option>
                <option value="strategy_id">Estrategia</option>
                <option value="symbol">Símbolo</option>
                <option value="run_mode">Modo</option>
                <option value="fees">Fees</option>
                <option value="slippage">Slippage</option>
                <option value="qty">Cantidad</option>
              </Select>
              <Select value={sortDir} onChange={(e) => setSortDir(e.target.value as "asc" | "desc")} className="h-8 min-w-[90px]">
                <option value="desc">Desc</option>
                <option value="asc">Asc</option>
              </Select>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-slate-400">Atajos entorno</span>
              <Button size="sm" variant={filters.environment === "" ? "default" : "outline"} className="h-7 px-2 text-[11px]" onClick={() => setFilters((prev) => ({ ...prev, environment: "" }))}>
                Todos
              </Button>
              <Button size="sm" variant={filters.environment === "real" ? "default" : "outline"} className="h-7 px-2 text-[11px]" onClick={() => setFilters((prev) => ({ ...prev, environment: "real" }))}>
                Real
              </Button>
              <Button size="sm" variant={filters.environment === "prueba" ? "default" : "outline"} className="h-7 px-2 text-[11px]" onClick={() => setFilters((prev) => ({ ...prev, environment: "prueba" }))}>
                Prueba
              </Button>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="text-slate-400">Seleccionadas: {selectedTradesCount}</span>
              <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" onClick={toggleSelectPageTrades} disabled={!pageRows.length}>
                {allPageSelected ? "Quitar página" : "Seleccionar página"}
              </Button>
              <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" onClick={clearTradeSelection} disabled={!selectedTradesCount}>
                Limpiar selección
              </Button>
              {role === "admin" ? (
                <Button size="sm" variant="outline" className="h-7 px-2 text-[11px]" onClick={bulkDeleteSelectedTrades} disabled={busyDelete || !selectedTradesCount}>
                  {busyDelete ? "Borrando..." : "Borrar seleccionadas"}
                </Button>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Resumen filtrado (decision rapida)</CardTitle>
        <CardDescription>
          Totales segun filtros actuales {filters.environment ? `(entorno: ${filters.environment})` : "(todos los entornos)"}.
        </CardDescription>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2 text-xs">Trades: <strong>{totals.trades}</strong></div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2 text-xs">WinRate: <strong>{fmtPct(totals.winrate)}</strong></div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2 text-xs">PnL neto: <strong className={totals.net_pnl >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(totals.net_pnl)}</strong></div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2 text-xs">Avg trade: <strong>{fmtUsd(totals.avg_trade)}</strong></div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2 text-xs">Fees + Slippage: <strong>{fmtUsd(totals.fees_total + totals.slippage_total)}</strong></div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2 text-xs">Holding prom.: <strong>{Math.round(totals.avg_holding_minutes)}m</strong></div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
            <span>Wins/Losses/Neutras: {totals.wins}/{totals.losses}/{totals.breakeven}</span>
            <span>PnL bruto: {fmtUsd(totals.gross_pnl)}</span>
            <span>Registros cargados: {sortedTrades.length}</span>
            {role === "admin" ? (
              <>
                <Button variant="outline" className="h-8 px-2" disabled={busyDelete} onClick={previewDeleteFiltered}>
                  {busyDelete ? "Calculando..." : "Preview borrado filtrado"}
                </Button>
                <Button variant="outline" className="h-8 px-2" disabled={!sortedTrades.length || busyDelete} onClick={bulkDeleteFiltered}>
                  {busyDelete ? "Borrando..." : "Borrar operaciones filtradas"}
                </Button>
              </>
            ) : null}
          </div>
          {deletePreviewCount !== null ? (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">
              Preview activo: {deletePreviewCount} operaciones coinciden con los filtros actuales.
            </div>
          ) : null}
          {deleteMessage ? <div className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-200">{deleteMessage}</div> : null}
          {deleteError ? <div className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-xs text-rose-200">{deleteError}</div> : null}

          <div className="grid gap-3 lg:grid-cols-3">
            <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Real vs prueba</p>
              <div className="space-y-2 text-xs">
                {summaryByEnvironment.length ? (
                  summaryByEnvironment.map((row) => (
                    <div key={row.environment} className="rounded border border-slate-800 px-2 py-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-200">{row.environment === "real" ? "Real (LIVE)" : "Prueba"}</span>
                        <span>{row.trades} trades</span>
                      </div>
                      <div className="text-slate-400">WinRate {fmtPct(row.winrate)} · PnL {fmtUsd(row.net_pnl)}</div>
                    </div>
                  ))
                ) : (
                  <p className="text-slate-500">Sin datos.</p>
                )}
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-950/40 p-2 lg:col-span-2">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Top estrategias (filtros actuales)</p>
                <Select value={topRowsSize} onChange={(e) => setTopRowsSize(e.target.value as "10" | "25" | "50")} className="h-8 min-w-[88px] text-xs">
                  <option value="10">10</option>
                  <option value="25">25</option>
                  <option value="50">50</option>
                </Select>
              </div>
              <div className="max-h-44 overflow-auto">
                <Table className="text-xs">
                  <THead>
                    <TR>
                      <TH>Estrategia</TH>
                      <TH>Trades</TH>
                      <TH>WinRate</TH>
                      <TH>PnL neto</TH>
                      <TH>Acción</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {summaryByStrategy.length ? (
                      summaryByStrategy.map((row) => (
                        <TR key={`st-${row.strategy_id}`}>
                          <TD className="max-w-[220px] truncate" title={`${row.strategy_name} (${row.strategy_id})`}>{row.strategy_name}</TD>
                          <TD>{row.trades}</TD>
                          <TD>{fmtPct(row.winrate)}</TD>
                          <TD className={row.net_pnl >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(row.net_pnl)}</TD>
                          <TD>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2 text-[11px]"
                              onClick={() => setFilters((prev) => ({ ...prev, strategy_id: row.strategy_id }))}
                            >
                              Filtrar
                            </Button>
                          </TD>
                        </TR>
                      ))
                    ) : (
                      <TR>
                        <TD colSpan={5} className="text-slate-500">Sin datos.</TD>
                      </TR>
                    )}
                  </TBody>
                </Table>
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Modos (click para filtrar)</p>
              <div className="space-y-2 text-xs">
                {summaryByMode.length ? (
                  summaryByMode.map((row) => (
                    <button
                      key={`${row.environment}-${row.mode}`}
                      type="button"
                      className="w-full rounded border border-slate-800 px-2 py-1 text-left hover:border-cyan-500/40"
                      onClick={() =>
                        setFilters((prev) => ({
                          ...prev,
                          mode: String(row.mode || ""),
                          environment: String(row.environment || ""),
                        }))
                      }
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-200">{String(row.mode || "-")}</span>
                        <span>{row.trades} trades</span>
                      </div>
                      <div className="text-slate-400">
                        {String(row.environment || "-")} · WR {fmtPct(row.winrate)} · PnL {fmtUsd(row.net_pnl)}
                      </div>
                    </button>
                  ))
                ) : (
                  <p className="text-slate-500">Sin datos.</p>
                )}
              </div>
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-slate-950/40 p-2">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Estrategia + dia + entorno</p>
            <div className="max-h-52 overflow-auto">
              <Table className="text-xs">
                <THead>
                  <TR>
                    <TH>Dia</TH>
                    <TH>Entorno</TH>
                    <TH>Estrategia</TH>
                    <TH>Trades</TH>
                    <TH>WinRate</TH>
                    <TH>PnL neto</TH>
                  </TR>
                </THead>
                <TBody>
                  {summaryByStrategyDay.length ? (
                    summaryByStrategyDay.map((row, idx) => (
                      <TR key={`${row.strategy_id}-${row.day}-${row.environment}-${idx}`}>
                        <TD>{row.day}</TD>
                        <TD>
                          <Badge variant={row.environment === "real" ? "danger" : "info"}>
                            {row.environment === "real" ? "real" : "prueba"}
                          </Badge>
                        </TD>
                        <TD className="max-w-[220px] truncate" title={`${row.strategy_name} (${row.strategy_id})`}>{row.strategy_name}</TD>
                        <TD>{row.trades}</TD>
                        <TD>{fmtPct(row.winrate)}</TD>
                        <TD className={row.net_pnl >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(row.net_pnl)}</TD>
                      </TR>
                    ))
                  ) : (
                    <TR>
                      <TD colSpan={6} className="text-slate-500">Sin datos con estos filtros.</TD>
                    </TR>
                  )}
                </TBody>
              </Table>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="overflow-x-auto">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-300">
            <div>
              Mostrando {pageStart}-{pageEnd} de {sortedTrades.length} operaciones filtradas · seleccionadas: {selectedTradesCount}
            </div>
            <div className="flex items-center gap-2">
              <span>Filas</span>
              <Select value={pageSize} onChange={(e) => setPageSize(e.target.value as "30" | "60" | "100")} className="h-8 min-w-[84px]">
                <option value="30">30</option>
                <option value="60">60</option>
                <option value="100">100</option>
              </Select>
              <Button variant="outline" className="h-8 px-2" disabled={safePage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Anterior</Button>
              <span>Pág. {safePage}/{totalPages}</span>
              <Button variant="outline" className="h-8 px-2" disabled={safePage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Siguiente</Button>
            </div>
          </div>
          <Table>
            <THead>
              <TR>
                <TH>
                  <input type="checkbox" checked={allPageSelected} onChange={toggleSelectPageTrades} />
                </TH>
                <TH>ID</TH>
                <TH>Timestamp</TH>
                <TH>Entorno</TH>
                <TH>Modo</TH>
                <TH>Run</TH>
                <TH>Estrategia</TH>
                <TH>Simbolo</TH>
                <TH>Lado</TH>
                <TH>Resultado</TH>
                <TH>Entrada / Salida</TH>
                <TH>Cantidad</TH>
                <TH>Fees</TH>
                <TH>Slippage</TH>
                <TH>Holding</TH>
                <TH>MFE/MAE</TH>
                <TH>PnL Neto</TH>
                <TH>Motivo</TH>
                <TH>Detalle</TH>
              </TR>
            </THead>
            <TBody>
              {pageRows.map((row) => {
                const holdMins = Math.abs(Math.round((new Date(row.exit_time).getTime() - new Date(row.entry_time).getTime()) / 60_000));
                const rowExt = row as Trade & { run_mode?: string; run_id?: string };
                const environment = rowExt.run_mode === "live" ? "real" : "prueba";
                return (
                  <TR key={row.id}>
                    <TD>
                      <input type="checkbox" checked={selectedTradeIds.includes(String(row.id))} onChange={() => toggleSelectTrade(String(row.id))} />
                    </TD>
                    <TD>{row.id}</TD>
                    <TD className="text-xs">{new Date(row.exit_time).toLocaleString()}</TD>
                    <TD>
                      <Badge variant={environment === "real" ? "danger" : "info"}>
                        {environment}
                      </Badge>
                    </TD>
                    <TD>
                      <Badge variant={rowExt.run_mode === "live" ? "danger" : rowExt.run_mode === "testnet" ? "warn" : rowExt.run_mode === "paper" ? "info" : "neutral"}>
                        {rowExt.run_mode || "backtest"}
                      </Badge>
                    </TD>
                    <TD className="text-xs font-mono text-slate-300">{rowExt.run_id || "-"}</TD>
                    <TD>
                      <button
                        type="button"
                        className="text-cyan-300 underline-offset-2 hover:underline"
                        onClick={() => setFilters((prev) => ({ ...prev, strategy_id: String(row.strategy_id || "") }))}
                      >
                        {row.strategy_id}
                      </button>
                    </TD>
                    <TD>{row.symbol}</TD>
                    <TD>{row.side}</TD>
                    <TD>
                      <Badge variant={row.pnl_net >= 0 ? "success" : "danger"}>{row.pnl_net >= 0 ? "win" : "loss"}</Badge>
                    </TD>
                    <TD>
                      <div className="text-xs">
                        <div>E {new Date(row.entry_time).toLocaleString()}</div>
                        <div>X {new Date(row.exit_time).toLocaleString()}</div>
                      </div>
                    </TD>
                    <TD>{row.qty}</TD>
                    <TD>{fmtUsd(row.fees)}</TD>
                    <TD>{fmtUsd(row.slippage)}</TD>
                    <TD>{holdMins}m</TD>
                    <TD>
                      {row.mfe.toFixed(2)} / {row.mae.toFixed(2)}
                    </TD>
                    <TD className={row.pnl_net >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(row.pnl_net)}</TD>
                    <TD>
                      <Badge variant={row.pnl_net >= 0 ? "success" : "warn"}>
                        {row.reason_code} / {row.exit_reason}
                      </Badge>
                    </TD>
                    <TD>
                      <Link href={`/trades/${row.id}`} className="text-cyan-300 underline">
                        Ver detalle
                      </Link>
                    </TD>
                  </TR>
                );
              })}
              {!trades.length ? (
                <TR>
                  <TD colSpan={19} className="py-4">
                    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-left">
                      <p className="text-sm font-semibold text-slate-100">Todavia no hay operaciones para estos filtros</p>
                      <p className="mt-1 text-xs text-slate-400">Ajusta filtros o ejecuta Paper/Testnet/Backtest para generar trades y analizarlos aca.</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Button variant="outline" onClick={resetFilters}>
                          Limpiar filtros
                        </Button>
                        <Button variant="outline" onClick={() => { window.location.href = "/backtests"; }}>
                          Ir a Backtests
                        </Button>
                      </div>
                    </div>
                  </TD>
                </TR>
              ) : null}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
