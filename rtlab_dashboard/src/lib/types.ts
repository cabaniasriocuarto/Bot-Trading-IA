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

export interface ExchangeDiagnoseResponse {
  ok: boolean;
  mode: "paper" | "testnet" | "live";
  exchange: string;
  base_url: string;
  ws_url: string;
  has_keys: boolean;
  key_source: "env" | "json" | "none";
  missing: string[];
  expected_env_vars: string[];
  last_error: string;
  connector_ok: boolean;
  connector_reason: string;
  order_ok: boolean;
  order_reason: string;
  diagnostics?: string[];
  checks: Record<string, unknown>;
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
  enabled_for_trading?: boolean;
  allow_learning?: boolean;
  is_primary?: boolean;
  primary: boolean;
  source?: "knowledge" | "uploaded" | string;
  status?: "active" | "disabled" | "archived" | string;
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

export interface StrategyKpis {
  run_count: number;
  trade_count: number;
  total_entries: number;
  total_exits: number;
  roundtrips: number;
  winrate: number;
  expectancy_value: number;
  expectancy_unit: string;
  avg_trade: number;
  max_dd: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  gross_pnl: number;
  net_pnl: number;
  costs_total: number;
  fees_total: number;
  spread_total: number;
  slippage_total: number;
  funding_total: number;
  costs_ratio: number;
  avg_holding_time: number;
  time_in_market: number;
  turnover: number;
  mfe_avg?: number | null;
  mae_avg?: number | null;
  slippage_p95_bps?: number | null;
  maker_ratio?: number | null;
  fill_ratio?: number | null;
  dataset_hashes?: string[];
  dataset_hash_warning?: boolean;
}

export interface StrategyKpisRow {
  strategy_id: string;
  name: string;
  mode: string;
  from?: string | null;
  to?: string | null;
  kpis: StrategyKpis;
  status?: string;
  enabled_for_trading?: boolean;
  allow_learning?: boolean;
  is_primary?: boolean;
  source?: string;
}

export interface StrategyKpisByRegimeResponse {
  strategy_id: string;
  name: string;
  mode: string;
  from?: string | null;
  to?: string | null;
  regime_rule_source?: string;
  regime_rules?: Record<string, string>;
  regimes: Record<string, { regime_label: string; kpis: StrategyKpis }>;
}

export interface StrategyComparison {
  left: Strategy;
  right: Strategy;
  changed_keys: string[];
}

export interface BacktestRun {
  id: string;
  strategy_id: string;
  market?: "crypto" | "forex" | "equities";
  symbol?: string;
  timeframe?: "5m" | "10m" | "15m";
  data_source?: string;
  period: {
    start: string;
    end: string;
  };
  dataset_range?: {
    start: string;
    end: string;
  };
  universe: string[];
  costs_model: {
    fees_bps: number;
    spread_bps: number;
    slippage_bps: number;
    funding_bps: number;
    rollover_bps?: number;
  };
  dataset_hash: string;
  dataset_manifest?: Record<string, unknown>;
  git_commit: string;
  metrics: {
    return_total?: number;
    cagr: number;
    max_dd: number;
    max_dd_duration_bars?: number;
    sharpe: number;
    sortino: number;
    calmar: number;
    winrate: number;
    expectancy: number;
    expectancy_usd_per_trade?: number;
    expectancy_pct_per_trade?: number;
    expectancy_unit?: string;
    expectancy_pct_unit?: string;
    avg_trade: number;
    avg_holding_time?: number;
    avg_holding_time_minutes?: number;
    profit_factor?: number;
    max_consecutive_losses?: number;
    exposure_time_pct?: number;
    turnover: number;
    exposure_avg?: number;
    robust_score: number;
    robustness_score?: number;
    total_entries?: number;
    total_exits?: number;
    total_roundtrips?: number;
    roundtrips?: number;
    trade_count?: number;
    pbo?: number | null;
    dsr?: number | null;
  };
  costs_breakdown?: {
    gross_pnl_total: number;
    gross_pnl?: number;
    fees_total: number;
    spread_total: number;
    slippage_total: number;
    funding_total: number;
    rollover_total?: number;
    total_cost: number;
    net_pnl?: number;
    net_pnl_total?: number;
    fees_pct_of_gross_pnl: number;
    spread_pct_of_gross_pnl: number;
    slippage_pct_of_gross_pnl: number;
    funding_pct_of_gross_pnl: number;
    rollover_pct_of_gross_pnl?: number;
    total_cost_pct_of_gross_pnl: number;
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
  learning: {
    enabled: boolean;
    mode: "OFF" | "RESEARCH";
    selector_algo: "thompson" | "ucb1" | "regime_rules";
    drift_algo: "adwin" | "page_hinkley";
    max_candidates: number;
    top_n: number;
    validation: {
      walk_forward: boolean;
      train_days: number;
      test_days: number;
      enforce_pbo: boolean;
      enforce_dsr: boolean;
      enforce_cpcv?: boolean;
    };
    promotion: {
      allow_auto_apply: boolean;
      allow_live: boolean;
    };
    risk_profile?: {
      risk_profile?: string;
      max_positions?: number;
      correlation_penalty_threshold?: number;
      paper?: {
        risk_per_trade_pct?: number;
        max_daily_loss_pct?: number;
        max_drawdown_pct?: number;
      };
      live_initial?: {
        risk_per_trade_pct?: number;
        max_daily_loss_pct?: number;
        max_drawdown_pct?: number;
      };
    };
  };
  feature_flags: Record<string, boolean>;
  gate_checklist: Array<{ stage: string; done: boolean; note: string }>;
}

export interface SessionUser {
  username: string;
  role: Role;
}
