export type Role = "admin" | "viewer";

export type BotStatus = "RUNNING" | "PAUSED" | "SAFE_MODE" | "KILLED";
export type RuntimeMode = "PAPER" | "TESTNET" | "LIVE";
export type LegacyMockRuntimeAlias = "MOCK";
// Compatibilidad: el mock local del frontend todavia usa MOCK, pero el runtime
// real canonico del backend opera con PAPER / TESTNET / LIVE.
export type TradingMode = RuntimeMode | LegacyMockRuntimeAlias;
export type BotPolicyMode = "shadow" | "paper" | "testnet" | "live";
export type ResearchEvidenceMode = "backtest" | "shadow" | "paper" | "testnet";
export type BotRegistryDomainType = "spot" | "futures";
export type BotRegistryStatus = "active" | "archived";
export type BotRiskProfile = "conservative" | "medium" | "aggressive";
export type InstrumentUniverseFamily = "spot" | "margin" | "usdm_futures" | "coinm_futures" | string;

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
  // Legacy mixed field from /api/v1/strategies/{id}; prefer StrategyEvidenceResponse.last_oos in new UI.
  last_oos?: BacktestRun["metrics"] | null;
  primary_for_modes?: Array<"paper" | "testnet" | "live">;
  manifest?: StrategyManifest;
  defaults_yaml?: string;
  schema?: Record<string, unknown>;
  pack_source?: "default" | "upload";
}

export interface StrategyTruth {
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
  description?: string;
  params: Record<string, unknown>;
  params_yaml?: string;
  parameters_schema?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  notes: string;
  tags: string[];
  last_run_at?: string | null;
  primary_for_modes?: Array<"paper" | "testnet" | "live">;
}

export interface StrategyEvidenceItem {
  run_id: string;
  mode: string;
  created_at: string;
  metrics: BacktestRun["metrics"];
  tags: string[];
  notes: string;
  validation_mode: string;
}

export interface StrategyEvidenceResponse {
  strategy_id: string;
  strategy_version: string;
  last_run_at?: string | null;
  run_count: number;
  last_oos?: BacktestRun["metrics"] | null;
  latest_run?: StrategyEvidenceItem | null;
  items: StrategyEvidenceItem[];
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

export interface BotInstanceMetrics {
  strategy_count: number;
  run_count: number;
  trade_count: number;
  winrate: number;
  net_pnl: number;
  avg_sharpe: number;
  expectancy_value: number;
  expectancy_unit: string;
  kills_total: number;
  kills_24h?: number;
  kills_global_total?: number;
  kills_global_24h?: number;
  kills_by_mode?: Record<string, number>;
  kills_by_mode_24h?: Record<string, number>;
  last_kill_at?: string | null;
  by_mode?: Record<string, { trade_count: number; winrate: number; net_pnl: number; avg_sharpe: number; expectancy_value?: number; run_count: number }>;
  experience_by_source?: Record<
    ResearchEvidenceMode,
    {
      episode_count: number;
      run_count: number;
      trade_count: number;
      decision_count: number;
      enter_count: number;
      exit_count: number;
      hold_count: number;
      skip_count: number;
      reduce_count: number;
      add_count: number;
      avg_source_weight: number;
      last_end_ts?: string | null;
    }
  >;
  last_run_at?: string | null;
  recommendations_pending?: number;
  recommendations_approved?: number;
  recommendations_rejected?: number;
}

export interface BotInstanceStrategyRef {
  id: string;
  name: string;
  allow_learning?: boolean;
  enabled_for_trading?: boolean;
  is_primary?: boolean;
  status?: "active" | "disabled" | "archived" | string;
}

export interface BotInstance {
  id: string;
  bot_id?: string;
  display_name: string;
  alias?: string | null;
  description?: string | null;
  domain_type: BotRegistryDomainType;
  registry_status: BotRegistryStatus;
  archived_at?: string | null;
  capital_base_usd: number;
  max_total_exposure_pct: number;
  max_asset_exposure_pct: number;
  risk_profile: BotRiskProfile;
  risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  max_positions: number;
  name: string;
  engine: string;
  mode: BotPolicyMode;
  status: "active" | "paused" | "archived";
  pool_strategy_ids: string[];
  pool_strategies?: BotInstanceStrategyRef[];
  strategy_pool_status?: "valid" | "error" | string;
  strategy_pool_errors?: string[];
  max_pool_strategies?: number | null;
  universe_name?: string | null;
  universe_family?: InstrumentUniverseFamily | null;
  universe?: string[];
  max_live_symbols?: number | null;
  symbol_assignment_status?: "valid" | "error" | string;
  symbol_assignment_errors?: string[];
  notes?: string;
  created_at: string;
  updated_at: string;
  metrics?: BotInstanceMetrics;
}

export interface BotPolicyState {
  engine: string;
  mode: BotPolicyMode;
  status: "active" | "paused" | "archived";
  pool_strategy_ids: string[];
  strategy_pool_status?: "valid" | "error" | string;
  strategy_pool_errors?: string[];
  max_pool_strategies?: number | null;
  universe_name?: string;
  universe: string[];
  max_live_symbols?: number | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface BotPolicyStateResponse {
  bot_id: string;
  policy_state: BotPolicyState;
}

export interface InstrumentUniverseItem {
  name: string;
  venue: string;
  family: InstrumentUniverseFamily;
  size: number;
  symbols: string[];
  sample_symbols: string[];
  fresh: boolean;
  stale: boolean;
  capability_required: boolean;
  capability_available: boolean;
}

export interface InstrumentUniverseSummaryResponse {
  items: InstrumentUniverseItem[];
  policy_source?: Record<string, unknown>;
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
  run_id?: string;
  run_mode?: "backtest" | "paper" | "testnet" | "live" | string;
  run_created_at?: string;
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

export interface BreakerEvent {
  id: number;
  ts: string;
  bot_id: string;
  mode: string;
  reason: string;
  run_id?: string | null;
  symbol?: string | null;
  source_log_id?: number | null;
}

export interface BotDecisionLogResponse {
  bot_id: string;
  items: LogEvent[];
  total: number;
  page: number;
  page_size: number;
  breaker_events: BreakerEvent[];
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
    engine_id?: string;
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

export interface LearningEngineConfigItem {
  id: string;
  name: string;
  enabled_default: boolean;
  description: string;
  ui_help: string;
  params: Record<string, unknown>;
  capabilities: string[];
  capabilities_detail?: Array<{
    id: string;
    requires?: string[];
    available?: boolean;
    missing?: string[];
    tier?: "runtime" | "research" | string;
    reason?: string;
  }>;
}

export interface LearningConfigResponse {
  ok: boolean;
  yaml_valid: boolean;
  source_mode: string;
  warnings: string[];
  learning_mode: {
    option?: string;
    enabled_default?: boolean;
    auto_apply_live?: boolean;
    require_human_approval?: boolean;
  };
  drift_detection: {
    enabled?: boolean;
    detectors?: Array<Record<string, unknown>>;
    runtime_detector_options?: Array<{ id: string; name: string; description: string }>;
  };
  engines: LearningEngineConfigItem[];
  selected_engine_id: string;
  selector_algo_compat?: "thompson" | "ucb1" | "regime_rules" | string;
  runtime_selector_compatible_engine_ids?: string[];
  safe_update: {
    enabled: boolean;
    gates_file: string;
    canary_schedule_pct: number[];
    rollback_auto: boolean;
    approve_required: boolean;
  };
  tiers?: Record<string, unknown>;
  capabilities_registry?: Record<string, { available?: boolean; missing?: string[]; tier?: string; reason?: string }>;
}

export interface SessionUser {
  username: string;
  role: Role;
}

export interface MassBacktestStatusResponse {
  run_id: string;
  state: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "NOT_FOUND" | string;
  created_at?: string;
  updated_at?: string;
  config?: Record<string, unknown>;
  progress?: {
    pct?: number;
    total_tasks?: number;
    completed_tasks?: number;
    current_variant?: number;
  };
  summary?: Record<string, unknown>;
  error?: string | null;
  logs?: string[];
  thread_alive?: boolean;
}

export interface MassBacktestResultRow {
  variant_id: string;
  catalog_run_id?: string;
  strategy_id: string;
  strategy_name?: string;
  template_id?: string | null;
  params?: Record<string, unknown>;
  score: number;
  rank?: number;
  hard_filters_pass?: boolean;
  promotable?: boolean;
  recommendable_option_b?: boolean;
  hard_filter_reasons?: string[];
  summary?: {
    trade_count_oos?: number;
    trade_count_by_symbol_oos?: Record<string, number>;
    min_trades_per_symbol_oos?: number;
    sharpe_oos?: number;
    sortino_oos?: number;
    calmar_oos?: number;
    winrate_oos?: number;
    profit_factor_oos?: number;
    max_dd_oos_pct?: number;
    expectancy_net_usd?: number;
    net_pnl_oos?: number;
    costs_ratio?: number;
    stability?: number;
    consistency_folds?: number;
    jitter_pass_rate?: number;
    dataset_hashes?: string[];
  };
  regime_metrics?: Record<string, {
    folds?: number;
    trade_count?: number;
    net_pnl?: number;
    expectancy_net_usd?: number;
    sharpe_oos?: number;
    max_dd_oos_pct?: number;
    costs_ratio?: number;
  }>;
  anti_overfitting?: Record<string, unknown>;
  gates_eval?: {
    passed?: boolean;
    fail_reasons?: string[];
    checks?: Record<string, {
      enabled?: boolean;
      available?: boolean;
      pass?: boolean;
      value?: number | null;
      min?: number;
      threshold?: number;
      [key: string]: unknown;
    }>;
    summary?: Record<string, unknown>;
  };
  microstructure?: {
    available?: boolean;
    policy?: Record<string, unknown>;
    source?: Record<string, unknown>;
    aggregate?: {
      vpin_cdf_oos?: number;
      micro_soft_kill_folds?: number;
      micro_hard_kill_folds?: number;
      micro_soft_kill_ratio?: number;
      micro_hard_kill_ratio?: number;
    };
    symbol_kill?: {
      soft?: boolean;
      hard?: boolean;
      reasons?: string[];
    };
    fold_debug?: Array<{
      fold?: number;
      test_start?: string;
      test_end?: string;
      available?: boolean;
      reason?: string;
      vpin?: number;
      vpin_cdf?: number;
      vpin_cdf_avg?: number;
      spread_bps?: number;
      spread_multiplier?: number;
      slippage_bps?: number;
      slippage_multiplier?: number;
      realized_vol?: number;
      vol_multiplier?: number;
      soft_kill_symbol?: boolean;
      hard_kill_symbol?: boolean;
      kill_reasons?: string[];
    }>;
  };
}

export interface MassBacktestResultsResponse {
  run_id: string;
  summary: Record<string, unknown>;
  results: MassBacktestResultRow[];
  query_backend?: { engine?: string } & Record<string, unknown>;
}

export interface MassBacktestArtifactsResponse {
  run_id: string;
  items: Array<{ name: string; path: string; size: number }>;
}

export interface BeastModeStatusResponse {
  enabled: boolean;
  policy_state?: "enabled" | "disabled" | "missing" | string;
  policy_available?: boolean;
  policy_enabled_declared?: boolean;
  policy_source_root?: string;
  policy_warnings?: string[];
  policy_files?: Record<string, { path?: string; exists?: boolean; valid?: boolean }>;
  scheduler?: {
    thread_alive?: boolean;
    stop_requested?: boolean;
    queue_depth?: number;
    workers_active?: number;
    active_run_ids?: string[];
    max_concurrent_jobs?: number;
    rate_limit_enabled?: boolean;
    max_requests_per_minute?: number;
    rate_limit_note?: string;
  };
  budget?: {
    tier?: string;
    daily_cap?: number;
    stop_at_budget_pct?: number;
    threshold_jobs?: number;
    daily_jobs_started?: number;
    daily_jobs_completed?: number;
    daily_jobs_failed?: number;
    daily_trial_units_started?: number;
    usage_pct?: number;
  };
  counts?: Record<string, number>;
  recent_history?: Array<Record<string, unknown>>;
  requires_postgres?: boolean;
  mode?: string;
}

export interface BeastModeJobsResponse {
  items: Array<{
    run_id: string;
    state: string;
    queued_at?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    tier?: string;
    estimated_trial_units?: number;
    strategy_count?: number;
    market?: string;
    symbol?: string;
    timeframe?: string;
    max_variants_per_strategy?: number;
    max_folds?: number;
    cancel_reason?: string;
  }>;
  count: number;
}

export interface LearningExperienceSummaryResponse {
  generated_at?: string;
  total_episodes?: number;
  total_events?: number;
  eligible_contexts?: number;
  proposals_pending?: number;
  sources?: Record<string, { episodes?: number; events?: number; source_weight_avg?: number }>;
  by_regime?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface LearningProposal {
  id: string;
  created_ts?: string;
  asset?: string;
  timeframe?: string;
  regime_label?: string;
  proposed_strategy_id: string;
  replaces_strategy_id?: string | null;
  confidence?: number;
  rationale?: string;
  status?: "pending" | "approved" | "rejected" | "needs_validation" | string;
  score_json?: Record<string, unknown>;
  metrics?: {
    reasons?: string[];
    [key: string]: unknown;
  };
  required_gates_json?: Record<string, unknown> | string[] | null;
  needs_validation?: boolean;
}

export interface LearningGuidanceRow {
  strategy_id: string;
  preferred_regimes_json?: string[] | Record<string, unknown>;
  avoid_regimes_json?: string[] | Record<string, unknown>;
  min_confidence_to_recommend?: number;
  max_risk_multiplier?: number;
  max_spread_bps_allowed?: number;
  max_vpin_allowed?: number;
  cost_stress_result?: string;
  notes?: string;
}

export interface ShadowStatusResponse {
  running: boolean;
  thread_alive: boolean;
  stop_requested: boolean;
  stop_reason?: string;
  allow_live: boolean;
  orders_sent: boolean;
  marketdata_base_url?: string;
  timeframe?: string;
  lookback_bars?: number;
  poll_sec?: number;
  symbol_requested?: string | null;
  active_bot_ids?: string[];
  active_strategy_ids?: string[];
  targets_count?: number;
  warnings?: string[];
  last_started_at?: string | null;
  last_cycle_at?: string | null;
  last_success_at?: string | null;
  last_error?: string;
  last_run_ids?: string[];
  cycles_total?: number;
  runs_created?: number;
  episodes_written?: number;
  skipped_duplicate_cycles?: number;
}

export interface CatalogRunKpis {
  return_total?: number;
  cagr?: number;
  max_dd?: number;
  sharpe?: number;
  sortino?: number;
  calmar?: number;
  profit_factor?: number;
  winrate?: number;
  expectancy?: number;
  expectancy_value?: number;
  expectancy_unit?: string;
  trade_count?: number;
  roundtrips?: number;
  avg_holding_time?: number;
  time_in_market?: number;
  costs_ratio?: number;
  gross_pnl?: number;
  net_pnl?: number;
  fees_total?: number;
  spread_total?: number;
  slippage_total?: number;
  funding_total?: number;
}

export interface BacktestCatalogRunRelatedBot {
  id: string;
  name: string;
  engine: string;
  mode: "shadow" | "paper" | "testnet" | "live" | string;
  status: "active" | "paused" | "archived" | string;
}

export interface BacktestCatalogRun {
  run_id: string;
  legacy_json_id?: string | null;
  run_type: "single" | "batch_child" | string;
  batch_id?: string | null;
  parent_run_id?: string | null;
  status: "queued" | "preparing" | "running" | "completed" | "completed_warn" | "failed" | "canceled" | "archived" | string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  created_by: string;
  mode: "backtest" | "paper" | "testnet" | "live" | string;
  strategy_id: string;
  strategy_name: string;
  strategy_version: string;
  strategy_config_hash: string;
  code_commit_hash: string;
  dataset_source: string;
  dataset_version: string;
  dataset_hash: string;
  symbols: string[];
  timeframes: string[];
  timerange_from: string;
  timerange_to: string;
  timezone: string;
  missing_data_policy: string;
  fee_model: string;
  spread_model: string;
  slippage_model: string;
  funding_model: string;
  latency_model?: string | null;
  fill_model: string;
  initial_capital: number;
  position_sizing_profile: string;
  max_open_positions: number;
  params_json?: Record<string, unknown>;
  seed?: number | null;
  hf_model_id?: string | null;
  hf_revision?: string | null;
  hf_commit_hash?: string | null;
  pipeline_task?: string | null;
  inference_mode?: string | null;
  alias?: string | null;
  tags: string[];
  pinned: boolean;
  title_structured: string;
  subtitle_structured: string;
  kpis: CatalogRunKpis;
  kpis_by_regime: Record<string, unknown>;
  flags: Record<string, unknown>;
  artifacts: Record<string, unknown>;
  updated_at: string;
  composite_score?: number;
  rank?: number;
  related_bot_ids?: string[];
  related_bots?: BacktestCatalogRunRelatedBot[];
}

export interface BacktestCatalogRunsResponse {
  items: BacktestCatalogRun[];
  count: number;
}

export interface BacktestCatalogBatch {
  batch_id: string;
  objective: string;
  universe: Record<string, unknown>;
  variables_explored: Record<string, unknown>;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  status: string;
  run_count_total: number;
  run_count_done: number;
  run_count_failed: number;
  best_runs_cache: Array<Record<string, unknown>>;
  config: Record<string, unknown>;
  summary: Record<string, unknown>;
  updated_at: string;
  children_runs?: BacktestCatalogRun[];
  artifacts_index?: Array<Record<string, unknown>>;
  runtime_status?: Record<string, unknown>;
}

export interface BacktestCatalogBatchesResponse {
  items: BacktestCatalogBatch[];
  count: number;
}

export interface ResearchFunnelStage {
  id: string;
  label: string;
  count: number;
  tone?: "neutral" | "success" | "warn" | "danger" | "info" | string;
  description?: string;
}

export interface ResearchFunnelResponse {
  generated_at?: string;
  counts?: Record<string, number>;
  evidence?: Record<string, number>;
  stages?: ResearchFunnelStage[];
  recent_candidates?: Array<{
    run_id: string;
    strategy_name?: string;
    asset?: string;
    timeframe?: string;
    candidate_stage?: string;
    evidence_status?: "trusted" | "legacy" | "quarantine" | string;
  }>;
  compatibility?: Record<string, unknown>;
}

export interface ResearchTrialLedgerItem {
  run_id: string;
  legacy_json_id?: string | null;
  batch_id?: string | null;
  run_type?: string;
  run_status?: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  strategy_id: string;
  strategy_name?: string;
  asset?: string;
  timeframe?: string;
  dataset_source?: string;
  dataset_hash?: string;
  commit_hash?: string;
  source?: string;
  evidence_status?: "trusted" | "legacy" | "quarantine" | string;
  evidence_flags?: string[];
  learning_excluded?: boolean;
  validation_quality?: string;
  cost_fidelity_level?: string;
  feature_set?: string;
  candidate_stage?: string;
  candidate_flags?: {
    shortlisted?: boolean;
    paso_gates?: boolean;
    strict_strategy_id?: boolean;
    [key: string]: unknown;
  };
  proposal_count?: number;
  proposal_statuses?: string[];
  proposal_needs_validation?: boolean;
  metrics?: {
    trade_count?: number;
    sharpe?: number | null;
    winrate?: number | null;
    max_dd?: number | null;
    net_pnl?: number | null;
    [key: string]: unknown;
  };
  costs?: {
    gross_pnl?: number | null;
    net_pnl?: number | null;
    fees_total?: number | null;
    spread_total?: number | null;
    slippage_total?: number | null;
    funding_total?: number | null;
    total_cost?: number | null;
    total_cost_source?: string;
    components_complete?: boolean;
    components_present?: boolean;
    [key: string]: unknown;
  };
  catalog_present?: boolean;
}

export interface ResearchTrialLedgerResponse {
  generated_at?: string;
  items: ResearchTrialLedgerItem[];
  count: number;
  status_filter?: string | null;
}

export interface BacktestCompareResponse {
  items: BacktestCatalogRun[];
  count: number;
  warnings: string[];
  dataset_hashes: string[];
  same_dataset: boolean;
}

export interface BacktestRankingsResponse {
  preset: string;
  constraints: Record<string, unknown>;
  total: number;
  items: BacktestCatalogRun[];
}

export interface RunPromotionCheck {
  id: string;
  ok: boolean;
  reason: string;
  details?: Record<string, unknown>;
}

export interface RunValidatePromotionResponse {
  ok: boolean;
  promotion_ok: boolean;
  live_direct_ok: boolean;
  requires_human_approval: boolean;
  option_b_no_auto_live: boolean;
  target_mode: "paper" | "testnet" | "live" | string;
  candidate: {
    run_id: string;
    catalog_run_id?: string;
    legacy_json_id?: string | null;
    strategy_id: string;
    strategy_name: string;
    dataset_hash?: string;
    period?: Record<string, unknown>;
    status?: string;
  };
  baseline: {
    run_id: string;
    catalog_run_id?: string;
    legacy_json_id?: string | null;
    strategy_id: string;
    strategy_name: string;
    dataset_hash?: string;
    period?: Record<string, unknown>;
    status?: string;
  };
  constraints: {
    passed: boolean;
    checks: RunPromotionCheck[];
  };
  offline_gates: {
    passed: boolean;
    failed_ids?: string[];
    summary?: string;
    checks?: RunPromotionCheck[];
  };
  compare_vs_baseline: {
    passed: boolean;
    failed_ids?: string[];
    summary?: string;
    checks?: RunPromotionCheck[];
  };
  rollout_ready: boolean;
  allowed_targets: Record<string, boolean>;
  rollout_start_body?: {
    candidate_run_id: string;
    baseline_run_id?: string;
  };
  promoted?: boolean;
  detail?: string;
  note?: string;
  rollout?: {
    state?: Record<string, unknown>;
    next_step?: string;
  };
}
