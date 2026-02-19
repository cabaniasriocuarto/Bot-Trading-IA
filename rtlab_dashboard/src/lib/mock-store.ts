import type {
  AlertEvent,
  BacktestRun,
  BotStatusResponse,
  ExecutionStats,
  LogEvent,
  PortfolioSnapshot,
  Position,
  RiskSnapshot,
  Strategy,
  Trade,
} from "@/lib/types";

export interface MockStore {
  status: BotStatusResponse;
  strategies: Strategy[];
  backtests: BacktestRun[];
  trades: Trade[];
  positions: Position[];
  portfolio: PortfolioSnapshot;
  risk: RiskSnapshot;
  execution: ExecutionStats;
  alerts: AlertEvent[];
  logs: LogEvent[];
  gateChecklist: Array<{ stage: string; done: boolean; note: string }>;
  featureFlags: Record<string, boolean>;
  activeProfile: "PAPER" | "TESTNET" | "LIVE";
}

function isoMinutesAgo(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function isoDaysAgo(days: number) {
  return new Date(Date.now() - days * 24 * 60 * 60_000).toISOString();
}

function makeCurve(base: number, drift = 15) {
  const points: Array<{ time: string; equity: number; drawdown: number }> = [];
  let equity = base;
  let peak = base;
  for (let i = 0; i < 120; i += 1) {
    const shock = Math.sin(i / 6) * 30 + (Math.cos(i / 11) * 15 + drift);
    equity += shock;
    peak = Math.max(peak, equity);
    const dd = Math.min(0, (equity - peak) / peak);
    points.push({ time: isoDaysAgo(120 - i), equity: Number(equity.toFixed(2)), drawdown: Number(dd.toFixed(4)) });
  }
  return points;
}

function makeStrategies(): Strategy[] {
  return [
    {
      id: "stg_001",
      name: "trend-pullback",
      version: "1.3.2",
      enabled: true,
      primary: true,
      params: { adx_min: 18, pb_atr: 0.7, vpin_limit: 70, slippage_guard_bps: 8 },
      created_at: isoDaysAgo(90),
      updated_at: isoDaysAgo(2),
      notes: "Primary paper profile strategy.",
      tags: ["trend", "orderflow", "paper"],
    },
    {
      id: "stg_002",
      name: "trend-pullback",
      version: "1.4.0-beta",
      enabled: false,
      primary: false,
      params: { adx_min: 20, pb_atr: 0.6, vpin_limit: 65, slippage_guard_bps: 7 },
      created_at: isoDaysAgo(21),
      updated_at: isoDaysAgo(1),
      notes: "Candidate version under validation.",
      tags: ["candidate", "ab-test"],
    },
    {
      id: "stg_003",
      name: "mean-reversion",
      version: "0.9.7",
      enabled: true,
      primary: false,
      params: { z_entry: 2.1, z_exit: 0.6, stop_atr: 1.5, hold_bars: 18 },
      created_at: isoDaysAgo(74),
      updated_at: isoDaysAgo(4),
      notes: "Lower turnover fallback.",
      tags: ["mean-reversion"],
    },
    {
      id: "stg_004",
      name: "momentum",
      version: "2.0.1",
      enabled: false,
      primary: false,
      params: { lookback: 48, rebalance_hours: 4, risk_cap: 0.14, turnover_cap: 0.25 },
      created_at: isoDaysAgo(120),
      updated_at: isoDaysAgo(20),
      notes: "Cross-sectional momentum sleeve.",
      tags: ["momentum", "portfolio"],
    },
  ];
}

function makeBacktests(): BacktestRun[] {
  const curves = [makeCurve(10000, 13), makeCurve(10000, 11), makeCurve(10000, 7), makeCurve(10000, 9)];
  return [
    {
      id: "bt_1001",
      strategy_id: "stg_001",
      period: { start: "2024-01-01", end: "2024-12-31" },
      universe: ["BTC/USDT", "ETH/USDT"],
      costs_model: { fees_bps: 5.5, spread_bps: 4.0, slippage_bps: 3.2, funding_bps: 1.0 },
      dataset_hash: "5f5e9f8f7d11dca2",
      git_commit: "136a5b7",
      metrics: {
        cagr: 0.42,
        max_dd: -0.14,
        sharpe: 1.8,
        sortino: 2.4,
        calmar: 2.9,
        winrate: 0.56,
        expectancy: 18.4,
        avg_trade: 12.6,
        turnover: 3.1,
        robust_score: 84.2,
      },
      status: "completed",
      artifacts_links: {
        report_json: "/api/backtests/bt_1001/report?format=report_json",
        trades_csv: "/api/backtests/bt_1001/report?format=trades_csv",
        equity_curve_csv: "/api/backtests/bt_1001/report?format=equity_curve_csv",
      },
      created_at: isoDaysAgo(8),
      duration_sec: 112,
      equity_curve: curves[0],
    },
    {
      id: "bt_1002",
      strategy_id: "stg_002",
      period: { start: "2024-01-01", end: "2024-12-31" },
      universe: ["BTC/USDT", "ETH/USDT"],
      costs_model: { fees_bps: 5.5, spread_bps: 4.4, slippage_bps: 3.5, funding_bps: 1.0 },
      dataset_hash: "8ca591f5e7cf5f91",
      git_commit: "136a5b7",
      metrics: {
        cagr: 0.38,
        max_dd: -0.12,
        sharpe: 1.73,
        sortino: 2.33,
        calmar: 3.1,
        winrate: 0.59,
        expectancy: 17.2,
        avg_trade: 11.4,
        turnover: 3.8,
        robust_score: 80.5,
      },
      status: "completed",
      artifacts_links: {
        report_json: "/api/backtests/bt_1002/report?format=report_json",
        trades_csv: "/api/backtests/bt_1002/report?format=trades_csv",
        equity_curve_csv: "/api/backtests/bt_1002/report?format=equity_curve_csv",
      },
      created_at: isoDaysAgo(5),
      duration_sec: 118,
      equity_curve: curves[1],
    },
    {
      id: "bt_1003",
      strategy_id: "stg_003",
      period: { start: "2024-06-01", end: "2025-01-31" },
      universe: ["BTC/USDT", "SOL/USDT", "ETH/USDT"],
      costs_model: { fees_bps: 5.5, spread_bps: 3.2, slippage_bps: 2.8, funding_bps: 1.0 },
      dataset_hash: "9a68fa2e5db32a71",
      git_commit: "136a5b7",
      metrics: {
        cagr: 0.29,
        max_dd: -0.1,
        sharpe: 1.42,
        sortino: 2.01,
        calmar: 2.8,
        winrate: 0.53,
        expectancy: 12.1,
        avg_trade: 9.1,
        turnover: 2.2,
        robust_score: 72.8,
      },
      status: "completed",
      artifacts_links: {
        report_json: "/api/backtests/bt_1003/report?format=report_json",
        trades_csv: "/api/backtests/bt_1003/report?format=trades_csv",
        equity_curve_csv: "/api/backtests/bt_1003/report?format=equity_curve_csv",
      },
      created_at: isoDaysAgo(12),
      duration_sec: 96,
      equity_curve: curves[2],
    },
    {
      id: "bt_1004",
      strategy_id: "stg_004",
      period: { start: "2024-01-01", end: "2025-01-31" },
      universe: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
      costs_model: { fees_bps: 5.5, spread_bps: 4.8, slippage_bps: 4.2, funding_bps: 1.1 },
      dataset_hash: "4ac8ec72f8c5e6d2",
      git_commit: "136a5b7",
      metrics: {
        cagr: 0.24,
        max_dd: -0.18,
        sharpe: 1.1,
        sortino: 1.7,
        calmar: 1.33,
        winrate: 0.51,
        expectancy: 8.2,
        avg_trade: 6.8,
        turnover: 4.9,
        robust_score: 60.4,
      },
      status: "completed",
      artifacts_links: {
        report_json: "/api/backtests/bt_1004/report?format=report_json",
        trades_csv: "/api/backtests/bt_1004/report?format=trades_csv",
        equity_curve_csv: "/api/backtests/bt_1004/report?format=equity_curve_csv",
      },
      created_at: isoDaysAgo(16),
      duration_sec: 134,
      equity_curve: curves[3],
    },
  ];
}

function makeTrades(): Trade[] {
  const rows: Trade[] = [];
  const symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
  const reasons = ["trend_pullback", "mean_revert", "breakout_confirm"];
  const exits = ["tp", "sl", "time_stop", "risk_cut"];
  for (let i = 0; i < 40; i += 1) {
    const side = i % 3 === 0 ? "short" : "long";
    const base = 25000 + i * 75;
    const entry = side === "long" ? base : base + 120;
    const move = (Math.sin(i / 3) + 0.3) * 220;
    const exit = side === "long" ? entry + move : entry - move;
    const pnl = (exit - entry) * 0.03 * (side === "long" ? 1 : -1);
    const fees = Math.abs(pnl) * 0.12;
    const slippage = Math.abs(pnl) * 0.08;
    rows.push({
      id: `tr_${1000 + i}`,
      strategy_id: i % 2 === 0 ? "stg_001" : "stg_003",
      symbol: symbols[i % symbols.length],
      side,
      timeframe: "5m",
      entry_time: isoMinutesAgo(60 * 24 - i * 37),
      exit_time: isoMinutesAgo(60 * 24 - i * 37 - 28),
      entry_px: Number(entry.toFixed(2)),
      exit_px: Number(exit.toFixed(2)),
      qty: Number((0.08 + (i % 4) * 0.03).toFixed(3)),
      fees: Number(fees.toFixed(2)),
      slippage: Number(slippage.toFixed(2)),
      pnl: Number(pnl.toFixed(2)),
      pnl_net: Number((pnl - fees - slippage).toFixed(2)),
      mae: Number((-Math.abs(move) * 0.5).toFixed(2)),
      mfe: Number((Math.abs(move) * 0.7).toFixed(2)),
      reason_code: reasons[i % reasons.length],
      exit_reason: exits[i % exits.length],
      events: [
        { ts: isoMinutesAgo(60 * 24 - i * 37), type: "signal", detail: "Signal generated from consensus filter." },
        { ts: isoMinutesAgo(60 * 24 - i * 37 - 2), type: "fill", detail: "Entry order filled." },
        { ts: isoMinutesAgo(60 * 24 - i * 37 - 15), type: "requote", detail: "Requote accepted by guard." },
        { ts: isoMinutesAgo(60 * 24 - i * 37 - 28), type: "exit", detail: `Exit by ${exits[i % exits.length]}.` },
      ],
      explain: {
        whitelist_ok: true,
        trend_ok: i % 7 !== 0,
        pullback_ok: i % 9 !== 0,
        orderflow_ok: i % 5 !== 0,
        vpin_ok: i % 11 !== 0,
        spread_ok: i % 8 !== 0,
      },
    });
  }
  return rows;
}

function createInitialStore(): MockStore {
  const trades = makeTrades();
  const positions: Position[] = [
    {
      symbol: "BTC/USDT",
      side: "long",
      qty: 0.14,
      entry_px: 102450,
      mark_px: 103120,
      pnl_unrealized: 93.8,
      exposure_usd: 14436.8,
      strategy_id: "stg_001",
    },
    {
      symbol: "ETH/USDT",
      side: "long",
      qty: 2.4,
      entry_px: 4020,
      mark_px: 3978,
      pnl_unrealized: -100.8,
      exposure_usd: 9547.2,
      strategy_id: "stg_003",
    },
    {
      symbol: "SOL/USDT",
      side: "short",
      qty: 28,
      entry_px: 220,
      mark_px: 214,
      pnl_unrealized: 168,
      exposure_usd: 5992,
      strategy_id: "stg_001",
    },
  ];

  const exposure = positions.map((p) => ({ symbol: p.symbol, exposure: p.exposure_usd }));
  const exposureTotal = exposure.reduce((acc, x) => acc + x.exposure, 0);

  return {
    status: {
      bot_status: "RUNNING",
      risk_mode: "NORMAL",
      paused: false,
      killed: false,
      equity: 11892.4,
      pnl: { daily: 142.7, weekly: 512.9, monthly: 1101.2 },
      max_dd: { value: -0.084, limit: -0.22 },
      daily_loss: { value: -0.012, limit: -0.05 },
      health: {
        api_latency_ms: 112,
        ws_connected: true,
        ws_lag_ms: 41,
        errors_5m: 0,
        rate_limits_5m: 1,
      },
      updated_at: new Date().toISOString(),
    },
    strategies: makeStrategies(),
    backtests: makeBacktests(),
    trades,
    positions,
    portfolio: {
      equity: 11892.4,
      pnl_daily: 142.7,
      pnl_weekly: 512.9,
      pnl_monthly: 1101.2,
      exposure_total: exposureTotal,
      exposure_by_symbol: exposure,
    },
    risk: {
      equity: 11892.4,
      dd: -0.084,
      daily_loss: -0.012,
      exposure_total: exposureTotal,
      exposure_by_symbol: exposure,
      circuit_breakers: ["spread_guard_warn", "vpin_guard_warn"],
      limits: {
        daily_loss_limit: -0.05,
        max_dd_limit: -0.22,
        max_positions: 20,
        max_total_exposure: 1.0,
      },
    },
    execution: {
      maker_ratio: 0.63,
      fill_ratio: 0.91,
      requotes: 14,
      cancels: 9,
      avg_spread: 4.6,
      p95_spread: 8.9,
      avg_slippage: 3.2,
      p95_slippage: 7.4,
      rate_limit_hits: 3,
      api_errors: 1,
    },
    alerts: [
      { id: "alt_1", ts: isoMinutesAgo(8), severity: "warn", message: "VPIN entered amber zone on ETH/USDT.", related_id: "tr_1017" },
      {
        id: "alt_2",
        ts: isoMinutesAgo(20),
        severity: "warn",
        message: "Fees + slippage reached 62% of expected edge on trend-pullback.",
        related_id: "stg_001",
      },
      {
        id: "alt_3",
        ts: isoMinutesAgo(27),
        severity: "info",
        message: "Backtest bt_1002 completed with robust score 80.5.",
        related_id: "bt_1002",
      },
      { id: "alt_4", ts: isoMinutesAgo(40), severity: "error", message: "Temporary requote burst detected on BTC/USDT.", related_id: "tr_1008" },
      {
        id: "alt_5",
        ts: isoMinutesAgo(55),
        severity: "warn",
        message: "Daily loss reached 80% of limit. Consider SAFE_MODE.",
        related_id: "tr_1022",
      },
    ],
    logs: [
      { id: "log_1", ts: isoMinutesAgo(2), severity: "info", module: "execution", message: "Order accepted by policy engine.", related_id: "tr_1031" },
      { id: "log_2", ts: isoMinutesAgo(6), severity: "warn", module: "risk", message: "Spread near configured limit.", related_id: "tr_1017" },
      { id: "log_3", ts: isoMinutesAgo(14), severity: "debug", module: "signals", message: "Consensus score 0.71 for BTC/USDT.", related_id: "tr_1031" },
      { id: "log_4", ts: isoMinutesAgo(25), severity: "error", module: "exchange", message: "429 received from ticker endpoint.", related_id: "bt_1001" },
    ],
    gateChecklist: [
      { stage: "Backtest completed", done: true, note: "Latest primary has robust_score > 80" },
      { stage: "Paper run >= 14 days", done: true, note: "17 days with stable DD" },
      { stage: "Live guardrails approved", done: false, note: "Pending admin signoff" },
    ],
    featureFlags: {
      orderflow: true,
      vpin: true,
      ml: false,
      stress_tests: true,
      alerts_smart: true,
    },
    activeProfile: "PAPER",
  };
}

declare global {
  var __rtlabMockStore: MockStore | undefined;
}

export function getMockStore() {
  if (!globalThis.__rtlabMockStore) {
    globalThis.__rtlabMockStore = createInitialStore();
  }
  return globalThis.__rtlabMockStore;
}

export function pushLog(log: Omit<LogEvent, "id" | "ts">) {
  const store = getMockStore();
  store.logs.unshift({
    id: `log_${Date.now()}`,
    ts: new Date().toISOString(),
    ...log,
  });
}

export function pushAlert(alert: Omit<AlertEvent, "id" | "ts">) {
  const store = getMockStore();
  store.alerts.unshift({
    id: `alt_${Date.now()}`,
    ts: new Date().toISOString(),
    ...alert,
  });
}
