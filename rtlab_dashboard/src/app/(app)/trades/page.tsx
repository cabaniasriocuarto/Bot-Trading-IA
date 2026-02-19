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
import type { Strategy, Trade } from "@/lib/types";
import { fmtUsd } from "@/lib/utils";

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [filters, setFilters] = useState({
    strategy_id: "",
    symbol: "",
    side: "",
    reason_code: "",
    exit_reason: "",
    result: "",
    date_from: "",
    date_to: "",
  });

  const refresh = useCallback(async () => {
    const params = new URLSearchParams();
    if (filters.strategy_id) params.set("strategy_id", filters.strategy_id);
    if (filters.symbol) params.set("symbol", filters.symbol);
    if (filters.side) params.set("side", filters.side);
    if (filters.reason_code) params.set("reason_code", filters.reason_code);
    if (filters.exit_reason) params.set("exit_reason", filters.exit_reason);
    if (filters.result) params.set("result", filters.result);
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);
    const [tradesRows, stgRows] = await Promise.all([
      apiGet<Trade[]>(`/api/trades?${params.toString()}`),
      apiGet<Strategy[]>("/api/strategies"),
    ]);
    setTrades(tradesRows);
    setStrategies(stgRows);
  }, [filters.date_from, filters.date_to, filters.exit_reason, filters.reason_code, filters.result, filters.side, filters.strategy_id, filters.symbol]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const uniqueSymbols = useMemo(() => [...new Set(trades.map((row) => row.symbol))], [trades]);
  const uniqueReasons = useMemo(() => [...new Set(trades.map((row) => row.reason_code))], [trades]);
  const uniqueExits = useMemo(() => [...new Set(trades.map((row) => row.exit_reason))], [trades]);

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Trades</CardTitle>
        <CardDescription>Advanced filters by strategy, symbol, side, result, reason, and date range with trade drill-down.</CardDescription>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Strategy</label>
            <Select value={filters.strategy_id} onChange={(e) => setFilters((prev) => ({ ...prev, strategy_id: e.target.value }))}>
              <option value="">All</option>
              {strategies.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} v{row.version}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Symbol</label>
            <Select value={filters.symbol} onChange={(e) => setFilters((prev) => ({ ...prev, symbol: e.target.value }))}>
              <option value="">All</option>
              {uniqueSymbols.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Side</label>
            <Select value={filters.side} onChange={(e) => setFilters((prev) => ({ ...prev, side: e.target.value }))}>
              <option value="">All</option>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Result</label>
            <Select value={filters.result} onChange={(e) => setFilters((prev) => ({ ...prev, result: e.target.value }))}>
              <option value="">All</option>
              <option value="win">Win</option>
              <option value="loss">Loss</option>
              <option value="breakeven">Breakeven</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Reason code</label>
            <Select value={filters.reason_code} onChange={(e) => setFilters((prev) => ({ ...prev, reason_code: e.target.value }))}>
              <option value="">All</option>
              {uniqueReasons.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Exit reason</label>
            <Select value={filters.exit_reason} onChange={(e) => setFilters((prev) => ({ ...prev, exit_reason: e.target.value }))}>
              <option value="">All</option>
              {uniqueExits.map((row) => (
                <option key={row} value={row}>
                  {row}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Date from</label>
            <Input type="date" value={filters.date_from} onChange={(e) => setFilters((prev) => ({ ...prev, date_from: e.target.value }))} />
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Date to</label>
            <Input type="date" value={filters.date_to} onChange={(e) => setFilters((prev) => ({ ...prev, date_to: e.target.value }))} />
          </div>
          <div className="md:col-span-2 xl:col-span-2">
            <label className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Quick symbol search</label>
            <Input
              placeholder="Type symbol and press enter (e.g., BTC/USDT)"
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
            <Button
              variant="outline"
              onClick={() =>
                setFilters({
                  strategy_id: "",
                  symbol: "",
                  side: "",
                  reason_code: "",
                  exit_reason: "",
                  result: "",
                  date_from: "",
                  date_to: "",
                })
              }
            >
              Reset Filters
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>ID</TH>
                <TH>Strategy</TH>
                <TH>Symbol</TH>
                <TH>Side</TH>
                <TH>Result</TH>
                <TH>Entry / Exit</TH>
                <TH>Qty</TH>
                <TH>Fees</TH>
                <TH>Slippage</TH>
                <TH>Holding</TH>
                <TH>MFE/MAE</TH>
                <TH>PnL Net</TH>
                <TH>Reason</TH>
                <TH>Detail</TH>
              </TR>
            </THead>
            <TBody>
              {trades.map((row) => {
                const holdMins = Math.abs(
                  Math.round((new Date(row.exit_time).getTime() - new Date(row.entry_time).getTime()) / 60_000),
                );
                return (
                  <TR key={row.id}>
                    <TD>{row.id}</TD>
                    <TD>{row.strategy_id}</TD>
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
                        Open
                      </Link>
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
