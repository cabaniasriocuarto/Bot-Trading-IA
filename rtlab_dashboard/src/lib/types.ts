export type Role = "admin" | "viewer";

export type BotStatus = "RUNNING" | "PAUSED" | "SAFE_MODE" | "KILLED";
export type TradingMode = "MOCK" | "PAPER" | "TESTNET" | "LIVE";

export interface HealthResponse {
  ok: boolean;
  time: string;
  version: string;
  ws: {
    connected: boolean;
    transport: "sse" | "ws";
    url: string;
    last_event_at: string;
  };
  exchange: {
    mode: TradingMode;
    name: string;
  };
  db: {
    ok: boolean;
    driver: "jsonl" | "sqlite";
  };
  cause?: string;
}

export interface StrategyManifest {
  id: string;
  name: string;
  version: string;
  author: string;
  engine: string;
  timeframes: {
    primary: string;
    entry: string;
    execution: string;
  };
  supports: {
    long: boolean;
    short: boolean;
  };
  inputs: string[];
  tags: string[];
}

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
  last_run_at?: string | null;
  last_oos?: BacktestRun["metrics"] | null;
  primary_for_modes?: Array<"paper" | "testnet" | "live">;
  manifest?: StrategyManifest;
  defaults_yaml?: string;
  schema?: Record<string, unknown>;
  pack_source?: "default" | "upload";
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
  drawdown_curve?: Array<{ time: string; value: number }>;
  trades?: Trade[];
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
  open_positions?: Position[];
  history?: Array<{ ts: string; equity: number; pnl_daily: number }>;
  corr_matrix?: Array<Array<number>>;
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
    risk_per_trade: number;
    close_all_enabled?: boolean;
  };
  stress_tests?: Array<{ scenario: string; robust_score: number }>;
  forecast_band?: {
    return_p50_30d: number;
    return_p90_30d: number;
    dd_p90_30d: number;
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
  latency_ms_p95: number;
  series: Array<{
    ts: string;
    latency_ms_p95: number;
    spread_bps: number;
    slippage_bps: number;
  }>;
  endpoint_errors?: Array<{ endpoint: string; errors: number; rate_limits: number }>;
  notes?: string[];
}

export interface AlertEvent {
  id: string;
  ts: string;
  severity: "info" | "warn" | "error";
  type?: string;
  module?: string;
  message: string;
  related_id?: string;
  data?: Record<string, unknown>;
}

export interface LogEvent {
  id: string;
  ts: string;
  severity: "debug" | "info" | "warn" | "error";
  type: string;
  module: string;
  message: string;
  related_ids?: string[];
  payload?: Record<string, unknown>;
}

export interface BotStatusResponse {
  state: BotStatus;
  daily_pnl: number;
  max_dd_value: number;
  daily_loss_value: number;
  last_heartbeat: string;
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
  cause?: string;
}

export interface SettingsResponse {
  mode: TradingMode;
  exchange: "binance" | "bybit" | "oanda" | "alpaca";
  exchange_plugin_options: Array<"binance" | "bybit" | "oanda" | "alpaca">;
  credentials: {
    exchange_configured: boolean;
    telegram_configured: boolean;
    telegram_chat_id?: string;
  };
  telegram: {
    enabled: boolean;
    chat_id: string;
  };
  risk_defaults: {
    max_daily_loss: number;
    max_dd: number;
    max_positions: number;
    risk_per_trade: number;
  };
  execution: {
    post_only_default: boolean;
    slippage_max_bps: number;
    request_timeout_ms: number;
  };
  feature_flags: Record<string, boolean>;
  gate_checklist: Array<{ stage: string; done: boolean; note: string }>;
}

export interface SessionUser {
  username: string;
  role: Role;
}
