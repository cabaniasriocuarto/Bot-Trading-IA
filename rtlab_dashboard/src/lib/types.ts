export type Role = "admin" | "viewer";

export type BotStatus = "RUNNING" | "PAUSED" | "SAFE_MODE" | "KILLED";

export interface Strategy {
  id: string;
  name: string;
  version: string;
  enabled: boolean;
  primary: boolean;
  params: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  notes: string;
  tags: string[];
}

export interface StrategyComparison {
  left: Strategy;
  right: Strategy;
  changed_keys: string[];
}

export interface BacktestRun {
  id: string;
  strategy_id: string;
  period: {
    start: string;
    end: string;
  };
  universe: string[];
  costs_model: {
    fees_bps: number;
    spread_bps: number;
    slippage_bps: number;
    funding_bps: number;
  };
  dataset_hash: string;
  git_commit: string;
  metrics: {
    cagr: number;
    max_dd: number;
    sharpe: number;
    sortino: number;
    calmar: number;
    winrate: number;
    expectancy: number;
    avg_trade: number;
    turnover: number;
    robust_score: number;
  };
  status: "queued" | "running" | "completed" | "failed";
  artifacts_links: {
    report_json: string;
    trades_csv: string;
    equity_curve_csv: string;
  };
  created_at: string;
  duration_sec: number;
  equity_curve: Array<{ time: string; equity: number; drawdown: number }>;
}

export interface TradeEvent {
  ts: string;
  type: "signal" | "fill" | "cancel" | "requote" | "exit";
  detail: string;
}

export interface Trade {
  id: string;
  strategy_id: string;
  symbol: string;
  side: "long" | "short";
  timeframe: string;
  entry_time: string;
  exit_time: string;
  entry_px: number;
  exit_px: number;
  qty: number;
  fees: number;
  slippage: number;
  pnl: number;
  pnl_net: number;
  mae: number;
  mfe: number;
  reason_code: string;
  exit_reason: string;
  events: TradeEvent[];
  explain: {
    whitelist_ok: boolean;
    trend_ok: boolean;
    pullback_ok: boolean;
    orderflow_ok: boolean;
    vpin_ok: boolean;
    spread_ok: boolean;
  };
}

export interface Position {
  symbol: string;
  side: "long" | "short";
  qty: number;
  entry_px: number;
  mark_px: number;
  pnl_unrealized: number;
  exposure_usd: number;
  strategy_id: string;
}

export interface PortfolioSnapshot {
  equity: number;
  pnl_daily: number;
  pnl_weekly: number;
  pnl_monthly: number;
  exposure_total: number;
  exposure_by_symbol: Array<{ symbol: string; exposure: number }>;
}

export interface RiskSnapshot {
  equity: number;
  dd: number;
  daily_loss: number;
  exposure_total: number;
  exposure_by_symbol: Array<{ symbol: string; exposure: number }>;
  circuit_breakers: string[];
  limits: {
    daily_loss_limit: number;
    max_dd_limit: number;
    max_positions: number;
    max_total_exposure: number;
  };
}

export interface ExecutionStats {
  maker_ratio: number;
  fill_ratio: number;
  requotes: number;
  cancels: number;
  avg_spread: number;
  p95_spread: number;
  avg_slippage: number;
  p95_slippage: number;
  rate_limit_hits: number;
  api_errors: number;
}

export interface AlertEvent {
  id: string;
  ts: string;
  severity: "info" | "warn" | "error";
  message: string;
  related_id?: string;
}

export interface LogEvent {
  id: string;
  ts: string;
  severity: "debug" | "info" | "warn" | "error";
  module: string;
  message: string;
  related_id?: string;
}

export interface BotStatusResponse {
  bot_status: BotStatus;
  risk_mode: "NORMAL" | "SAFE";
  paused: boolean;
  killed: boolean;
  equity: number;
  pnl: {
    daily: number;
    weekly: number;
    monthly: number;
  };
  max_dd: {
    value: number;
    limit: number;
  };
  daily_loss: {
    value: number;
    limit: number;
  };
  health: {
    api_latency_ms: number;
    ws_connected: boolean;
    ws_lag_ms: number;
    errors_5m: number;
    rate_limits_5m: number;
  };
  updated_at: string;
}

export interface SessionUser {
  username: string;
  role: Role;
}
