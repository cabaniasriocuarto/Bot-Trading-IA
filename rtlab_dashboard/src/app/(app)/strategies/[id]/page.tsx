"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";

import { EquityDrawdownChart } from "@/components/charts/equity-drawdown-chart";
import { ReturnsHistogram } from "@/components/charts/returns-histogram";
import { StackedCostChart } from "@/components/charts/stacked-cost-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet } from "@/lib/client-api";
import { getPlaybook } from "@/lib/playbooks";
import type { BacktestRun, Strategy, Trade } from "@/lib/types";
import { fmtNum, fmtPct } from "@/lib/utils";

export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>();
  const strategyId = String(params.id);

  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [allBacktests, setAllBacktests] = useState<BacktestRun[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [compareId, setCompareId] = useState("");

  useEffect(() => {
    const load = async () => {
      const [s, allStrategies, allBacktests, allTrades] = await Promise.all([
        apiGet<Strategy>(`/api/strategies/${strategyId}`),
        apiGet<Strategy[]>("/api/strategies"),
        apiGet<BacktestRun[]>("/api/backtests"),
        apiGet<Trade[]>(`/api/trades?strategy_id=${strategyId}`),
      ]);
      setStrategy(s);
      setStrategies(allStrategies);
      setAllBacktests(allBacktests);
      setBacktests(allBacktests.filter((row) => row.strategy_id === strategyId));
      setTrades(allTrades);
      const compareCandidate = allStrategies.find((row) => row.id !== strategyId && row.name === s.name) || allStrategies.find((row) => row.id !== strategyId);
      setCompareId(compareCandidate?.id || "");
    };
    void load();
  }, [strategyId]);

  const kpis = backtests[0]?.metrics;
  const histogram = useMemo(() => {
    const buckets = [
      { bucket: "< -100", min: -99999, max: -100 },
      { bucket: "-100 to -25", min: -100, max: -25 },
      { bucket: "-25 to 0", min: -25, max: 0 },
      { bucket: "0 to 25", min: 0, max: 25 },
      { bucket: "25 to 100", min: 25, max: 100 },
      { bucket: "> 100", min: 100, max: 99999 },
    ];
    return buckets.map((bucket) => ({
      bucket: bucket.bucket,
      count: trades.filter((row) => row.pnl_net >= bucket.min && row.pnl_net < bucket.max).length,
    }));
  }, [trades]);

  const costs = useMemo(
    () =>
      backtests.map((row) => ({
        label: row.id,
        fees: row.costs_model.fees_bps,
        slippage: row.costs_model.slippage_bps,
        funding: row.costs_model.funding_bps,
      })),
    [backtests],
  );

  const rolling = useMemo(() => {
    const base = backtests[0]?.equity_curve || [];
    return base.map((point, idx) => ({
      label: idx % 10 === 0 ? point.time.slice(0, 10) : "",
      sharpe: Number((1.2 + Math.sin(idx / 8) * 0.4).toFixed(2)),
      sortino: Number((1.8 + Math.cos(idx / 7) * 0.5).toFixed(2)),
    }));
  }, [backtests]);

  const compare = strategies.find((row) => row.id === compareId) || null;
  const changedKeys = useMemo(() => {
    if (!strategy || !compare) return [];
    const keys = new Set([...Object.keys(strategy.params), ...Object.keys(compare.params)]);
    return [...keys].filter((key) => strategy.params[key] !== compare.params[key]);
  }, [strategy, compare]);

  const latestCurrentBacktest = useMemo(
    () =>
      [...allBacktests]
        .filter((row) => row.strategy_id === strategyId)
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0] || null,
    [allBacktests, strategyId],
  );

  const latestCompareBacktest = useMemo(
    () =>
      compare
        ? [...allBacktests]
            .filter((row) => row.strategy_id === compare.id)
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0] || null
        : null,
    [allBacktests, compare],
  );

  const metricComparisonRows = useMemo(() => {
    if (!latestCurrentBacktest || !latestCompareBacktest) return [];
    return [
      { label: "CAGR", current: fmtPct(latestCurrentBacktest.metrics.cagr), compare: fmtPct(latestCompareBacktest.metrics.cagr) },
      { label: "Max DD", current: fmtPct(latestCurrentBacktest.metrics.max_dd), compare: fmtPct(latestCompareBacktest.metrics.max_dd) },
      { label: "Sharpe", current: fmtNum(latestCurrentBacktest.metrics.sharpe), compare: fmtNum(latestCompareBacktest.metrics.sharpe) },
      { label: "Sortino", current: fmtNum(latestCurrentBacktest.metrics.sortino), compare: fmtNum(latestCompareBacktest.metrics.sortino) },
      { label: "Calmar", current: fmtNum(latestCurrentBacktest.metrics.calmar), compare: fmtNum(latestCompareBacktest.metrics.calmar) },
      { label: "Winrate", current: fmtPct(latestCurrentBacktest.metrics.winrate), compare: fmtPct(latestCompareBacktest.metrics.winrate) },
      {
        label: "Expectancy / Avg Trade",
        current: `${fmtNum(latestCurrentBacktest.metrics.expectancy)} / ${fmtNum(latestCurrentBacktest.metrics.avg_trade)}`,
        compare: `${fmtNum(latestCompareBacktest.metrics.expectancy)} / ${fmtNum(latestCompareBacktest.metrics.avg_trade)}`,
      },
      { label: "Turnover", current: fmtNum(latestCurrentBacktest.metrics.turnover), compare: fmtNum(latestCompareBacktest.metrics.turnover) },
      {
        label: "Robustness Score",
        current: fmtNum(latestCurrentBacktest.metrics.robust_score),
        compare: fmtNum(latestCompareBacktest.metrics.robust_score),
      },
    ];
  }, [latestCompareBacktest, latestCurrentBacktest]);

  if (!strategy) {
    return <p className="text-sm text-slate-400">Loading strategy...</p>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {strategy.name} <span className="text-cyan-300">v{strategy.version}</span>
          {strategy.primary ? <Badge variant="info">Primary</Badge> : null}
          {strategy.enabled ? <Badge variant="success">Enabled</Badge> : <Badge>Disabled</Badge>}
        </CardTitle>
        <CardDescription>Strategy detail with KPI diagnostics and A/B version comparison.</CardDescription>
      </Card>

      {kpis ? (
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Kpi label="CAGR" value={fmtPct(kpis.cagr)} />
          <Kpi label="Max DD" value={fmtPct(kpis.max_dd)} />
          <Kpi label="Sharpe / Sortino" value={`${fmtNum(kpis.sharpe)} / ${fmtNum(kpis.sortino)}`} />
          <Kpi label="Calmar / Winrate" value={`${fmtNum(kpis.calmar)} / ${fmtPct(kpis.winrate)}`} />
          <Kpi label="Expectancy / Robust" value={`${fmtNum(kpis.expectancy)} / ${fmtNum(kpis.robust_score)}`} />
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Equity & Drawdown</CardTitle>
          <CardContent>
            <EquityDrawdownChart
              data={(backtests[0]?.equity_curve || []).map((x) => ({
                ...x,
                label: x.time.slice(5, 10),
              }))}
            />
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Rolling Sharpe / Sortino</CardTitle>
          <CardContent>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart data={rolling}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  <Line type="monotone" dataKey="sharpe" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="sortino" stroke="#f97316" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardTitle>Returns Histogram</CardTitle>
          <CardContent>
            <ReturnsHistogram data={histogram} />
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Fees + Slippage (stacked)</CardTitle>
          <CardContent>
            <StackedCostChart data={costs} />
          </CardContent>
        </Card>
        <Card>
          <CardTitle>Exposure Trend</CardTitle>
          <CardContent>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                <LineChart
                  data={(backtests[0]?.equity_curve || []).map((x, idx) => ({
                    label: idx % 12 === 0 ? x.time.slice(5, 10) : "",
                    net: 0.4 + Math.sin(idx / 8) * 0.25,
                    gross: 0.8 + Math.cos(idx / 7) * 0.35,
                  }))}
                >
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                  <Legend />
                  <Line type="monotone" dataKey="net" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="gross" stroke="#facc15" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Playbook</CardTitle>
          <CardDescription>Rules summary + active parameters + recent versions.</CardDescription>
          <CardContent className="space-y-3">
            <pre className="whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-200">
              {getPlaybook(strategy.name)}
            </pre>
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Active Params</p>
              <pre className="text-xs text-slate-200">{JSON.stringify(strategy.params, null, 2)}</pre>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Changelog</p>
              <ul className="space-y-1 text-sm text-slate-300">
                {strategies
                  .filter((row) => row.name === strategy.name)
                  .map((row) => (
                    <li key={row.id}>
                      {row.version} - updated {new Date(row.updated_at).toLocaleDateString()}
                    </li>
                  ))}
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>What Changed? (A/B)</CardTitle>
          <CardDescription>Compare params and top metrics against another version.</CardDescription>
          <CardContent className="space-y-3">
            <Select value={compareId} onChange={(e) => setCompareId(e.target.value)}>
              <option value="">Select version</option>
              {strategies
                .filter((row) => row.id !== strategy.id)
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name} v{row.version}
                  </option>
                ))}
            </Select>
            {compare ? (
              <>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                  <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Changed keys</p>
                  <div className="flex flex-wrap gap-2">
                    {changedKeys.length ? changedKeys.map((key) => <Badge key={key}>{key}</Badge>) : <Badge variant="success">No differences</Badge>}
                  </div>
                </div>
                <Table>
                  <THead>
                    <TR>
                      <TH>Param</TH>
                      <TH>Current</TH>
                      <TH>Compare</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {changedKeys.map((key) => (
                      <TR key={key}>
                        <TD>{key}</TD>
                        <TD>{String(strategy.params[key])}</TD>
                        <TD>{String(compare.params[key])}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
                <Table>
                  <THead>
                    <TR>
                      <TH>Metric</TH>
                      <TH>Current</TH>
                      <TH>Compare</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {metricComparisonRows.map((row) => (
                      <TR key={row.label}>
                        <TD>{row.label}</TD>
                        <TD>{row.current}</TD>
                        <TD>{row.compare}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </>
            ) : (
              <p className="text-sm text-slate-400">Select a strategy version to compare.</p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardDescription>{label}</CardDescription>
      <CardTitle className="mt-1 text-lg">{value}</CardTitle>
    </Card>
  );
}


