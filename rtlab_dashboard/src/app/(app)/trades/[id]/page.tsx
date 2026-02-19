"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { CandlestickChart } from "@/components/charts/candlestick-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet } from "@/lib/client-api";
import type { Trade } from "@/lib/types";
import { fmtUsd } from "@/lib/utils";

type CandleRow = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

function buildCandles(trade: Trade): CandleRow[] {
  const rows: CandleRow[] = [];
  const start = new Date(trade.entry_time).getTime() - 70 * 60_000;
  let last = trade.entry_px * 0.98;
  for (let i = 0; i < 120; i += 1) {
    const drift = Math.sin(i / 9) * 0.004 + (trade.side === "long" ? 0.0007 : -0.0007);
    const open = last;
    const close = open * (1 + drift);
    const high = Math.max(open, close) * 1.002;
    const low = Math.min(open, close) * 0.998;
    rows.push({
      time: new Date(start + i * 60_000).toISOString().slice(0, 19),
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
    });
    last = close;
  }
  const entryIdx = 40;
  const exitIdx = 75;
  if (rows[entryIdx]) rows[entryIdx].close = trade.entry_px;
  if (rows[exitIdx]) rows[exitIdx].close = trade.exit_px;
  return rows;
}

export default function TradeDetailPage() {
  const params = useParams<{ id: string }>();
  const tradeId = String(params.id);
  const [trade, setTrade] = useState<Trade | null>(null);

  useEffect(() => {
    const load = async () => {
      const row = await apiGet<Trade>(`/api/trades/${tradeId}`);
      setTrade(row);
    };
    void load();
  }, [tradeId]);

  const candles = useMemo(() => (trade ? buildCandles(trade) : []), [trade]);

  if (!trade) return <p className="text-sm text-slate-400">Loading trade...</p>;

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Trade {trade.id}
          <Badge variant={trade.side === "long" ? "success" : "warn"}>{trade.side}</Badge>
          <Badge>{trade.symbol}</Badge>
        </CardTitle>
        <CardDescription>Entry/exit markers, signals timeline, and explain-this checklist.</CardDescription>
      </Card>

      <Card>
        <CardTitle>Candle + Markers</CardTitle>
        <CardContent>
          <CandlestickChart
            candles={candles}
            markers={[
              {
                time: new Date(trade.entry_time).toISOString().slice(0, 19),
                text: "Entry",
                position: "belowBar",
                color: "#22d3ee",
              },
              {
                time: new Date(trade.exit_time).toISOString().slice(0, 19),
                text: "Exit",
                position: "aboveBar",
                color: "#f97316",
              },
            ]}
          />
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Trade Metrics</CardTitle>
          <CardContent className="grid grid-cols-2 gap-3">
            <Metric label="Entry" value={trade.entry_px.toFixed(2)} />
            <Metric label="Exit" value={trade.exit_px.toFixed(2)} />
            <Metric label="Qty" value={String(trade.qty)} />
            <Metric label="Fees" value={fmtUsd(trade.fees)} />
            <Metric label="Slippage" value={fmtUsd(trade.slippage)} />
            <Metric label="PnL net" value={fmtUsd(trade.pnl_net)} color={trade.pnl_net >= 0 ? "text-emerald-300" : "text-rose-300"} />
            <Metric label="MFE" value={trade.mfe.toFixed(2)} />
            <Metric label="MAE" value={trade.mae.toFixed(2)} />
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Explain This</CardTitle>
          <CardDescription>Decision checklist at entry time.</CardDescription>
          <CardContent>
            <ul className="space-y-2 text-sm">
              <Checklist label="Whitelist ok" value={trade.explain.whitelist_ok} />
              <Checklist label="Trend ok" value={trade.explain.trend_ok} />
              <Checklist label="Pullback ok" value={trade.explain.pullback_ok} />
              <Checklist label="Orderflow ok" value={trade.explain.orderflow_ok} />
              <Checklist label="VPIN ok" value={trade.explain.vpin_ok} />
              <Checklist label="Spread ok" value={trade.explain.spread_ok} />
            </ul>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardTitle>Trade Timeline (fills/cancel/requote)</CardTitle>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>Timestamp</TH>
                <TH>Type</TH>
                <TH>Detail</TH>
              </TR>
            </THead>
            <TBody>
              {trade.events.map((event, idx) => (
                <TR key={`${event.ts}-${event.type}-${idx}`}>
                  <TD>{new Date(event.ts).toLocaleString()}</TD>
                  <TD>{event.type}</TD>
                  <TD>{event.detail}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-base font-semibold text-slate-100 ${color || ""}`}>{value}</p>
    </div>
  );
}

function Checklist({ label, value }: { label: string; value: boolean }) {
  return (
    <li className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
      <span>{label}</span>
      <Badge variant={value ? "success" : "danger"}>{value ? "OK" : "FAIL"}</Badge>
    </li>
  );
}

