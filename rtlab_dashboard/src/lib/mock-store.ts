import fs from "node:fs";
import path from "node:path";

import type {
  AlertEvent,
  BacktestRun,
  BotStatusResponse,
  ExecutionStats,
  HealthResponse,
  LogEvent,
  PortfolioSnapshot,
  Position,
  RiskSnapshot,
  SettingsResponse,
  Strategy,
  StrategyManifest,
  Trade,
  TradingMode,
} from "@/lib/types";

export interface MockStore {
  version: string;
  status: BotStatusResponse;
  health: HealthResponse;
  settings: SettingsResponse;
  strategies: Strategy[];
  backtests: BacktestRun[];
  trades: Trade[];
  positions: Position[];
  portfolio: PortfolioSnapshot;
  risk: RiskSnapshot;
  execution: ExecutionStats;
  alerts: AlertEvent[];
  logs: LogEvent[];
}

const STORE_VERSION = "2.0.0";
const DATA_DIR = path.join(process.cwd(), ".rtlab_data");
const STORE_FILE = path.join(DATA_DIR, "mock_store.json");
const LOGS_JSONL = path.join(DATA_DIR, "logs.jsonl");

function isoMinutesAgo(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function isoHoursAgo(hours: number) {
  return new Date(Date.now() - hours * 60 * 60_000).toISOString();
}

function isoDaysAgo(days: number) {
  return new Date(Date.now() - days * 24 * 60 * 60_000).toISOString();
}

function ensureDataDir() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
}

function makeCurve(base: number, drift = 15) {
  const points: Array<{ time: string; equity: number; drawdown: number }> = [];
  let equity = base;
  let peak = base;
  for (let i = 0; i < 140; i += 1) {
    const shock = Math.sin(i / 7) * 28 + (Math.cos(i / 11) * 10 + drift);
    equity += shock;
    peak = Math.max(peak, equity);
    const dd = Math.min(0, (equity - peak) / peak);
    points.push({ time: isoDaysAgo(140 - i), equity: Number(equity.toFixed(2)), drawdown: Number(dd.toFixed(4)) });
  }
  return points;
}

function defaultManifest(): StrategyManifest {
  return {
    id: "trend_pullback_orderflow",
    name: "Tendencia + Pullback + Confirmación Order Flow",
    version: "1.0.0",
    author: "RTLAB",
    engine: "rtbot",
    timeframes: { primary: "15m", entry: "5m", execution: "1m" },
    supports: { long: true, short: true },
    inputs: ["ohlcv", "l2_book_topN", "trades_stream", "funding", "open_interest"],
    tags: ["trend", "pullback", "orderflow"],
  };
}

function defaultSchema() {
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      adx_threshold: { type: "number", minimum: 10, maximum: 60 },
      rsi_long_min: { type: "number", minimum: 20, maximum: 80 },
      rsi_long_max: { type: "number", minimum: 20, maximum: 90 },
      rsi_short_min: { type: "number", minimum: 10, maximum: 70 },
      rsi_short_max: { type: "number", minimum: 20, maximum: 80 },
      obi_long_min: { type: "number", minimum: 0, maximum: 1 },
      obi_short_max: { type: "number", minimum: 0, maximum: 1 },
      cvd_window_min: { type: "number", minimum: 1, maximum: 120 },
      risk_per_trade_pct: { type: "number", minimum: 0.1, maximum: 2.0 },
      max_daily_loss_pct: { type: "number", minimum: 0.5, maximum: 10 },
      max_dd_pct: { type: "number", minimum: 5, maximum: 50 },
      max_positions: { type: "number", minimum: 1, maximum: 50 },
      atr_stop_mult: { type: "number", minimum: 0.5, maximum: 6 },
      atr_take_mult: { type: "number", minimum: 1, maximum: 8 },
      trailing_activation_atr: { type: "number", minimum: 0.5, maximum: 6 },
      trailing_distance_atr: { type: "number", minimum: 0.5, maximum: 6 },
      time_stop_bars: { type: "number", minimum: 1, maximum: 120 },
      max_spread_bps: { type: "number", minimum: 1, maximum: 100 },
      max_slippage_bps: { type: "number", minimum: 1, maximum: 100 },
    },
    required: [
      "adx_threshold",
      "risk_per_trade_pct",
      "max_daily_loss_pct",
      "max_dd_pct",
      "max_positions",
      "atr_stop_mult",
      "atr_take_mult",
      "max_spread_bps",
      "max_slippage_bps",
    ],
  };
}

function defaultParams() {
  return {
    adx_threshold: 18,
    rsi_long_min: 45,
    rsi_long_max: 70,
    rsi_short_min: 30,
    rsi_short_max: 55,
    obi_long_min: 0.55,
    obi_short_max: 0.45,
    cvd_window_min: 8,
    risk_per_trade_pct: 0.75,
    max_daily_loss_pct: 5,
    max_dd_pct: 22,
    max_positions: 20,
    atr_stop_mult: 2,
    atr_take_mult: 3,
    trailing_activation_atr: 1.5,
    trailing_distance_atr: 2,
    time_stop_bars: 18,
    max_spread_bps: 12,
    max_slippage_bps: 10,
  };
}

function toYaml(params: Record<string, unknown>) {
  return Object.entries(params)
    .map(([key, value]) => `${key}: ${value}`)
    .join("\n");
}

function makeStrategies(): Strategy[] {
  const manifest = defaultManifest();
  const params = defaultParams();
  const defaultsYaml = toYaml(params);
  return [
    {
      id: manifest.id,
      name: manifest.name,
      version: manifest.version,
      enabled: true,
      primary: true,
      params,
      created_at: isoDaysAgo(160),
      updated_at: isoDaysAgo(1),
      last_run_at: isoHoursAgo(2),
      notes: "Estrategia default de consola. Tendencia + pullback + order flow con guardas de costos.",
      tags: manifest.tags,
      manifest,
      defaults_yaml: defaultsYaml,
      schema: defaultSchema(),
      pack_source: "default",
    },
    {
      id: "trend_pullback_orderflow_v101",
      name: manifest.name,
      version: "1.0.1",
      enabled: false,
      primary: false,
      params: { ...params, adx_threshold: 20, max_slippage_bps: 9 },
      created_at: isoDaysAgo(45),
      updated_at: isoDaysAgo(2),
      last_run_at: isoHoursAgo(26),
      notes: "Versión candidata para comparador A/B.",
      tags: [...manifest.tags, "candidate"],
      manifest: { ...manifest, version: "1.0.1", id: "trend_pullback_orderflow_v101" },
      defaults_yaml: toYaml({ ...params, adx_threshold: 20, max_slippage_bps: 9 }),
      schema: defaultSchema(),
      pack_source: "default",
    },
    {
      id: "mean_reversion_liquidity",
      name: "Mean Reversion + Liquidez",
      version: "0.9.2",
      enabled: false,
      primary: false,
      params: { z_entry: 2.2, z_exit: 0.8, hold_bars: 20, max_spread_bps: 8 },
      created_at: isoDaysAgo(70),
      updated_at: isoDaysAgo(4),
      last_run_at: isoHoursAgo(72),
      notes: "Estrategia secundaria, menor turnover.",
      tags: ["mean-reversion", "liquidity"],
      defaults_yaml: toYaml({ z_entry: 2.2, z_exit: 0.8, hold_bars: 20, max_spread_bps: 8 }),
      schema: {
        type: "object",
        properties: {
          z_entry: { type: "number" },
          z_exit: { type: "number" },
          hold_bars: { type: "number" },
          max_spread_bps: { type: "number" },
        },
      },
      pack_source: "default",
    },
  ];
}

function makeTrades(strategies: Strategy[]): Trade[] {
  const rows: Trade[] = [];
  const strategyIds = strategies.map((s) => s.id);
  const symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
  const reasons = ["trend_pullback", "of_confirm", "risk_reentry"];
  const exits = ["tp", "sl", "time_stop", "trail_stop"];
  for (let i = 0; i < 80; i += 1) {
    const side = i % 3 === 0 ? "short" : "long";
    const base = 25000 + i * 70;
    const entry = side === "long" ? base : base + 130;
    const move = (Math.sin(i / 3) + 0.25) * 210;
    const exit = side === "long" ? entry + move : entry - move;
    const pnl = (exit - entry) * 0.03 * (side === "long" ? 1 : -1);
    const fees = Math.abs(pnl) * 0.09 + 1.8;
    const slippage = Math.abs(pnl) * 0.07 + 1.2;
    rows.push({
      id: `tr_${1100 + i}`,
      strategy_id: strategyIds[i % strategyIds.length],
      symbol: symbols[i % symbols.length],
      side,
      timeframe: "5m",
      entry_time: isoMinutesAgo(60 * 24 * 3 - i * 43),
      exit_time: isoMinutesAgo(60 * 24 * 3 - i * 43 - 31),
      entry_px: Number(entry.toFixed(2)),
      exit_px: Number(exit.toFixed(2)),
      qty: Number((0.08 + (i % 4) * 0.03).toFixed(3)),
      fees: Number(fees.toFixed(2)),
      slippage: Number(slippage.toFixed(2)),
      pnl: Number(pnl.toFixed(2)),
      pnl_net: Number((pnl - fees - slippage).toFixed(2)),
      mae: Number((-Math.abs(move) * 0.48).toFixed(2)),
      mfe: Number((Math.abs(move) * 0.66).toFixed(2)),
      reason_code: reasons[i % reasons.length],
      exit_reason: exits[i % exits.length],
      events: [
        { ts: isoMinutesAgo(60 * 24 * 3 - i * 43), type: "signal", detail: "Señal generada por consenso técnico + order flow." },
        { ts: isoMinutesAgo(60 * 24 * 3 - i * 43 - 2), type: "fill", detail: "Orden de entrada ejecutada." },
        { ts: isoMinutesAgo(60 * 24 * 3 - i * 43 - 17), type: "requote", detail: "Requote aceptado por guardas de spread." },
        { ts: isoMinutesAgo(60 * 24 * 3 - i * 43 - 31), type: "exit", detail: `Salida por ${exits[i % exits.length]}.` },
      ],
      explain: {
        whitelist_ok: true,
        trend_ok: i % 9 !== 0,
        pullback_ok: i % 8 !== 0,
        orderflow_ok: i % 6 !== 0,
        vpin_ok: i % 11 !== 0,
        spread_ok: i % 10 !== 0,
      },
    });
  }
  return rows;
}

function makeBacktests(strategies: Strategy[]): BacktestRun[] {
  const curves = [makeCurve(10000, 13), makeCurve(10000, 11), makeCurve(10000, 9)];
  return strategies.slice(0, 3).map((strategy, idx) => ({
    id: `bt_${2000 + idx}`,
    strategy_id: strategy.id,
    period: { start: "2024-01-01", end: "2025-01-31" },
    universe: ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    costs_model: {
      fees_bps: 5.5 + idx * 0.4,
      spread_bps: 4 + idx * 0.6,
      slippage_bps: 3 + idx * 0.5,
      funding_bps: 1 + idx * 0.2,
    },
    dataset_hash: `${Date.now().toString(16).slice(0, 10)}${idx}`,
    git_commit: "785ef1f",
    metrics: {
      cagr: Number((0.28 + (3 - idx) * 0.05).toFixed(2)),
      max_dd: Number((-0.09 - idx * 0.02).toFixed(4)),
      sharpe: Number((1.75 - idx * 0.22).toFixed(2)),
      sortino: Number((2.25 - idx * 0.24).toFixed(2)),
      calmar: Number((2.6 - idx * 0.25).toFixed(2)),
      winrate: Number((0.58 - idx * 0.03).toFixed(2)),
      expectancy: Number((15.2 - idx * 2.1).toFixed(2)),
      avg_trade: Number((10.6 - idx * 1.4).toFixed(2)),
      turnover: Number((3.2 + idx * 0.9).toFixed(2)),
      robust_score: Number((84.2 - idx * 8.4).toFixed(2)),
    },
    status: "completed",
    artifacts_links: {
      report_json: `/api/v1/backtests/runs/bt_${2000 + idx}?format=report_json`,
      trades_csv: `/api/v1/backtests/runs/bt_${2000 + idx}?format=trades_csv`,
      equity_curve_csv: `/api/v1/backtests/runs/bt_${2000 + idx}?format=equity_curve_csv`,
    },
    created_at: isoDaysAgo(10 - idx * 2),
    duration_sec: 110 + idx * 14,
    equity_curve: curves[idx],
    drawdown_curve: curves[idx].map((x) => ({ time: x.time, value: x.drawdown })),
  }));
}

function makeExecutionSeries() {
  return Array.from({ length: 80 }).map((_, idx) => ({
    ts: isoMinutesAgo(80 - idx),
    latency_ms_p95: Number((108 + Math.sin(idx / 7) * 26 + (idx % 4) * 3).toFixed(1)),
    spread_bps: Number((4.2 + Math.abs(Math.sin(idx / 9)) * 3.1).toFixed(2)),
    slippage_bps: Number((3.1 + Math.abs(Math.cos(idx / 8)) * 2.4).toFixed(2)),
  }));
}

function createInitialStore(): MockStore {
  const strategies = makeStrategies();
  const trades = makeTrades(strategies);
  const backtests = makeBacktests(strategies);
  const positions: Position[] = [
    {
      symbol: "BTC/USDT",
      side: "long",
      qty: 0.14,
      entry_px: 102450,
      mark_px: 103120,
      pnl_unrealized: 93.8,
      exposure_usd: 14436.8,
      strategy_id: strategies[0].id,
    },
    {
      symbol: "ETH/USDT",
      side: "long",
      qty: 2.4,
      entry_px: 4020,
      mark_px: 3978,
      pnl_unrealized: -100.8,
      exposure_usd: 9547.2,
      strategy_id: strategies[0].id,
    },
  ];

  const exposureBySymbol = positions.map((p) => ({ symbol: p.symbol, exposure: p.exposure_usd }));
  const exposureTotal = Number(exposureBySymbol.reduce((acc, x) => acc + x.exposure, 0).toFixed(2));

  const mode: TradingMode = "MOCK";
  const settings: SettingsResponse = {
    mode,
    exchange: "binance",
    exchange_plugin_options: ["binance", "bybit", "oanda", "alpaca"],
    credentials: {
      exchange_configured: false,
      telegram_configured: Boolean(process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_CHAT_ID),
      telegram_chat_id: process.env.TELEGRAM_CHAT_ID || "",
    },
    telegram: {
      enabled: process.env.TELEGRAM_ENABLED === "true",
      chat_id: process.env.TELEGRAM_CHAT_ID || "",
    },
    risk_defaults: {
      max_daily_loss: 5,
      max_dd: 22,
      max_positions: 20,
      risk_per_trade: 0.75,
    },
    execution: {
      post_only_default: true,
      slippage_max_bps: 10,
      request_timeout_ms: 12000,
    },
    feature_flags: {
      orderflow: true,
      vpin: true,
      ml: false,
      stress_tests: true,
      alerts_smart: true,
    },
    gate_checklist: [
      { stage: "Backtest completado", done: true, note: "Score robustez > 80 en estrategia primaria." },
      { stage: "Paper >= 14 días", done: true, note: "17 días estables, DD bajo control." },
      { stage: "Aprobación LIVE", done: false, note: "Pendiente validación manual." },
    ],
  };

  const executionSeries = makeExecutionSeries();
  const execution: ExecutionStats = {
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
    latency_ms_p95: 142,
    series: executionSeries,
    endpoint_errors: [
      { endpoint: "/fapi/v1/depth", errors: 1, rate_limits: 2 },
      { endpoint: "/fapi/v1/order", errors: 0, rate_limits: 1 },
    ],
    notes: [
      "Slippage real cercana a estimada en ventana reciente.",
      "Spread p95 dentro de umbral configurado.",
      "Requotes concentrados en apertura de sesión US.",
    ],
  };

  const logs: LogEvent[] = [
    {
      id: "log_1001",
      ts: isoMinutesAgo(3),
      type: "order_update",
      severity: "info",
      module: "execution",
      message: "Orden limitada confirmada por exchange.",
      related_ids: ["tr_1128"],
      payload: { symbol: "BTC/USDT", order_type: "limit", status: "filled" },
    },
    {
      id: "log_1002",
      ts: isoMinutesAgo(9),
      type: "breaker_triggered",
      severity: "warn",
      module: "risk",
      message: "Guardia de spread en zona ámbar.",
      related_ids: ["tr_1122"],
      payload: { spread_bps: 9.2, threshold_bps: 10 },
    },
    {
      id: "log_1003",
      ts: isoMinutesAgo(16),
      type: "api_error",
      severity: "error",
      module: "exchange",
      message: "Rate limit temporal en endpoint de orderbook.",
      related_ids: ["bt_2000"],
      payload: { endpoint: "/fapi/v1/depth", status: 429 },
    },
  ];

  const alerts: AlertEvent[] = [
    {
      id: "alt_1001",
      ts: isoMinutesAgo(7),
      type: "breaker_triggered",
      severity: "warn",
      module: "risk",
      message: "Fees + slippage consumen 61% del edge esperado.",
      related_id: "tr_1120",
      data: { fees_bps: 5.9, slippage_bps: 4.1 },
    },
    {
      id: "alt_1002",
      ts: isoMinutesAgo(22),
      type: "backtest_finished",
      severity: "info",
      module: "backtest",
      message: "Backtest bt_2001 finalizado con robustez 75.8.",
      related_id: "bt_2001",
      data: { robust_score: 75.8 },
    },
    {
      id: "alt_1003",
      ts: isoMinutesAgo(37),
      type: "api_error",
      severity: "error",
      module: "exchange",
      message: "Burst de requotes detectado en BTC/USDT.",
      related_id: "tr_1119",
      data: { requotes_5m: 5 },
    },
  ];

  const status: BotStatusResponse = {
    state: "RUNNING",
    daily_pnl: 142.7,
    max_dd_value: -0.084,
    daily_loss_value: -0.012,
    last_heartbeat: new Date().toISOString(),
    bot_status: "RUNNING",
    risk_mode: "NORMAL",
    paused: false,
    killed: false,
    equity: 11892.4,
    pnl: { daily: 142.7, weekly: 512.9, monthly: 1101.2 },
    max_dd: { value: -0.084, limit: -0.22 },
    daily_loss: { value: -0.012, limit: -0.05 },
    health: {
      api_latency_ms: 96,
      ws_connected: true,
      ws_lag_ms: 34,
      errors_5m: 0,
      rate_limits_5m: 1,
    },
    updated_at: new Date().toISOString(),
  };

  const health: HealthResponse = {
    ok: true,
    time: new Date().toISOString(),
    version: STORE_VERSION,
    ws: {
      connected: true,
      transport: "sse",
      url: "/ws/v1/events",
      last_event_at: new Date().toISOString(),
    },
    exchange: {
      mode,
      name: "binance",
    },
    db: { ok: true, driver: "jsonl" },
  };

  const portfolio: PortfolioSnapshot = {
    equity: status.equity,
    pnl_daily: status.pnl.daily,
    pnl_weekly: status.pnl.weekly,
    pnl_monthly: status.pnl.monthly,
    exposure_total: exposureTotal,
    exposure_by_symbol: exposureBySymbol,
    open_positions: positions,
    history: Array.from({ length: 45 }).map((_, i) => ({
      ts: isoDaysAgo(45 - i),
      equity: Number((10000 + i * 38 + Math.sin(i / 6) * 120).toFixed(2)),
      pnl_daily: Number((Math.sin(i / 4) * 90).toFixed(2)),
    })),
    corr_matrix: [
      [1, 0.72, 0.58],
      [0.72, 1, 0.54],
      [0.58, 0.54, 1],
    ],
  };

  const risk: RiskSnapshot = {
    equity: status.equity,
    dd: status.max_dd.value,
    daily_loss: status.daily_loss.value,
    exposure_total: exposureTotal,
    exposure_by_symbol: exposureBySymbol,
    circuit_breakers: ["spread_guard_warn", "vpin_guard_warn"],
    limits: {
      daily_loss_limit: -settings.risk_defaults.max_daily_loss / 100,
      max_dd_limit: -settings.risk_defaults.max_dd / 100,
      max_positions: settings.risk_defaults.max_positions,
      max_total_exposure: 1.0,
      risk_per_trade: settings.risk_defaults.risk_per_trade / 100,
      close_all_enabled: true,
    },
    stress_tests: [
      { scenario: "Base", robust_score: 84.2 },
      { scenario: "Fees x2", robust_score: 74.1 },
      { scenario: "Slippage x2", robust_score: 69.4 },
      { scenario: "Spread shock", robust_score: 66.7 },
    ],
    forecast_band: {
      return_p50_30d: 0.042,
      return_p90_30d: 0.089,
      dd_p90_30d: -0.098,
    },
  };

  return {
    version: STORE_VERSION,
    status,
    health,
    settings,
    strategies,
    backtests,
    trades,
    positions,
    portfolio,
    risk,
    execution,
    alerts,
    logs,
  };
}

function syncDerived(store: MockStore) {
  const exposureBySymbol = store.positions.map((p) => ({ symbol: p.symbol, exposure: p.exposure_usd }));
  const exposureTotal = Number(exposureBySymbol.reduce((acc, x) => acc + x.exposure, 0).toFixed(2));
  const mode = store.settings.mode;

  store.status.state = store.status.bot_status;
  store.status.daily_pnl = store.status.pnl.daily;
  store.status.max_dd_value = store.status.max_dd.value;
  store.status.daily_loss_value = store.status.daily_loss.value;
  store.status.last_heartbeat = store.status.updated_at;
  store.status.health.ws_connected = store.health.ws.connected;

  store.health.time = new Date().toISOString();
  store.health.exchange.mode = mode;
  store.health.exchange.name = store.settings.exchange;
  store.health.ws.last_event_at = store.status.updated_at;

  store.portfolio.equity = store.status.equity;
  store.portfolio.pnl_daily = store.status.pnl.daily;
  store.portfolio.pnl_weekly = store.status.pnl.weekly;
  store.portfolio.pnl_monthly = store.status.pnl.monthly;
  store.portfolio.exposure_total = exposureTotal;
  store.portfolio.exposure_by_symbol = exposureBySymbol;
  store.portfolio.open_positions = store.positions;

  store.risk.equity = store.status.equity;
  store.risk.dd = store.status.max_dd.value;
  store.risk.daily_loss = store.status.daily_loss.value;
  store.risk.exposure_total = exposureTotal;
  store.risk.exposure_by_symbol = exposureBySymbol;
  store.risk.limits.daily_loss_limit = -store.settings.risk_defaults.max_daily_loss / 100;
  store.risk.limits.max_dd_limit = -store.settings.risk_defaults.max_dd / 100;
  store.risk.limits.max_positions = store.settings.risk_defaults.max_positions;
  store.risk.limits.risk_per_trade = store.settings.risk_defaults.risk_per_trade / 100;

  store.execution.series = store.execution.series.slice(-120);
}

function saveStore(store: MockStore) {
  ensureDataDir();
  syncDerived(store);
  fs.writeFileSync(STORE_FILE, JSON.stringify(store, null, 2), "utf8");
}

function appendJsonl(log: LogEvent) {
  ensureDataDir();
  fs.appendFileSync(LOGS_JSONL, `${JSON.stringify(log)}\n`, "utf8");
}

function loadStoreFromDisk(): MockStore | null {
  try {
    if (!fs.existsSync(STORE_FILE)) return null;
    const raw = fs.readFileSync(STORE_FILE, "utf8");
    const parsed = JSON.parse(raw) as MockStore;
    if (!parsed || typeof parsed !== "object" || !parsed.status || !parsed.settings) return null;
    return parsed;
  } catch {
    return null;
  }
}

declare global {
  var __rtlabMockStore: MockStore | undefined;
}

export function getMockStore() {
  if (!globalThis.__rtlabMockStore) {
    const restored = loadStoreFromDisk();
    globalThis.__rtlabMockStore = restored || createInitialStore();
    saveStore(globalThis.__rtlabMockStore);
  }
  return globalThis.__rtlabMockStore;
}

export function saveMockStore() {
  const store = getMockStore();
  saveStore(store);
}

export function pushLog(log: Omit<LogEvent, "id" | "ts">) {
  const store = getMockStore();
  const entry: LogEvent = {
    id: `log_${Date.now()}_${Math.floor(Math.random() * 999)}`,
    ts: new Date().toISOString(),
    ...log,
  };
  store.logs.unshift(entry);
  appendJsonl(entry);
  saveStore(store);
  return entry;
}

export function pushAlert(alert: Omit<AlertEvent, "id" | "ts">) {
  const store = getMockStore();
  const entry: AlertEvent = {
    id: `alt_${Date.now()}_${Math.floor(Math.random() * 999)}`,
    ts: new Date().toISOString(),
    ...alert,
  };
  store.alerts.unshift(entry);
  saveStore(store);
  return entry;
}

export function rotateExecutionSeries() {
  const store = getMockStore();
  const last = store.execution.series[store.execution.series.length - 1];
  const idx = store.execution.series.length;
  const next = {
    ts: new Date().toISOString(),
    latency_ms_p95: Number(((last?.latency_ms_p95 || 110) + Math.sin(idx / 7) * 1.6).toFixed(2)),
    spread_bps: Number(((last?.spread_bps || 4.2) + Math.sin(idx / 6) * 0.2).toFixed(2)),
    slippage_bps: Number(((last?.slippage_bps || 3.1) + Math.cos(idx / 6) * 0.2).toFixed(2)),
  };
  store.execution.series.push(next);
  store.execution.series = store.execution.series.slice(-120);
  store.execution.latency_ms_p95 = next.latency_ms_p95;
  store.execution.avg_spread = Number(
    (store.execution.series.reduce((acc, row) => acc + row.spread_bps, 0) / store.execution.series.length).toFixed(2),
  );
  store.execution.avg_slippage = Number(
    (store.execution.series.reduce((acc, row) => acc + row.slippage_bps, 0) / store.execution.series.length).toFixed(2),
  );
  store.execution.p95_spread = [...store.execution.series]
    .sort((a, b) => a.spread_bps - b.spread_bps)[Math.floor(store.execution.series.length * 0.95)]!.spread_bps;
  store.execution.p95_slippage = [...store.execution.series]
    .sort((a, b) => a.slippage_bps - b.slippage_bps)[Math.floor(store.execution.series.length * 0.95)]!.slippage_bps;
  store.status.updated_at = new Date().toISOString();
  saveStore(store);
}
