import { describe, expect, it } from "vitest";

import {
  buildBotRegistryDraft,
  buildDefaultBotRegistryDraft,
  getBotDisplayName,
  normalizeBotRegistryDraft,
} from "@/lib/bot-registry";
import type { BotRegistryContractResponse } from "@/lib/types";

const CONTRACT_FIXTURE: BotRegistryContractResponse = {
  contract_version: "rtlrese31/v1",
  storage: {
    kind: "json_file",
    path: "learning/bots.json",
    stable_id_field: "bot_id",
    supports_soft_archive: true,
    trace_fields: ["created_at", "updated_at", "last_change_type", "last_change_summary", "last_changed_by", "last_change_source"],
  },
  api: {
    list_path: "/api/v1/bots",
    create_path: "/api/v1/bots",
    detail_path: "/api/v1/bots/{bot_id}",
    patch_path: "/api/v1/bots/{bot_id}",
    archive_path: "/api/v1/bots/{bot_id}/archive",
    restore_path: "/api/v1/bots/{bot_id}/restore",
    policy_state_path: "/api/v1/bots/{bot_id}/policy-state",
    decision_log_path: "/api/v1/bots/{bot_id}/decision-log",
  },
  defaults: {
    display_name: "",
    alias: "",
    description: "",
    domain_type: "spot",
    registry_status: "active",
    engine: "bandit_thompson",
    mode: "paper",
    status: "active",
    universe_name: "",
    universe: [],
    pool_strategy_ids: [],
    max_live_symbols: 1,
    capital_base_usd: 10000,
    max_total_exposure_pct: 65,
    max_asset_exposure_pct: 25,
    risk_profile: "medium",
    risk_per_trade_pct: 0.5,
    max_daily_loss_pct: 3,
    max_drawdown_pct: 15,
    max_positions: 10,
    notes: "",
  },
  limits: {
    max_instances: 30,
    display_name_min_length: 3,
    display_name_max_length: 80,
    alias_max_length: 40,
    description_max_length: 280,
    notes_max_length: 500,
    universe_min_size: 1,
    pool_strategy_ids_min_size: 1,
    max_live_symbols_min: 1,
    max_live_symbols: 12,
    max_pool_strategies: 15,
    capital_base_usd_min: 0.01,
    percentage_min: 0.01,
    percentage_max: 100,
    max_positions_min: 1,
  },
  enums: {
    domain_types: ["spot", "futures"],
    registry_statuses: ["active", "archived"],
    risk_profiles: ["conservative", "medium", "aggressive"],
    modes: ["shadow", "paper", "testnet", "live"],
    statuses: ["active", "paused", "archived"],
    engines: ["fixed_rules", "bandit_thompson", "bandit_ucb1"],
    change_types: ["created", "updated", "archived", "reactivated"],
  },
  risk_profiles: {
    conservative: {
      risk_profile: "conservative",
      max_total_exposure_pct: 40,
      max_asset_exposure_pct: 15,
      risk_per_trade_pct: 0.25,
      max_daily_loss_pct: 1,
      max_drawdown_pct: 8,
      max_positions: 5,
    },
    medium: {
      risk_profile: "medium",
      max_total_exposure_pct: 65,
      max_asset_exposure_pct: 25,
      risk_per_trade_pct: 0.5,
      max_daily_loss_pct: 3,
      max_drawdown_pct: 15,
      max_positions: 10,
    },
    aggressive: {
      risk_profile: "aggressive",
      max_total_exposure_pct: 85,
      max_asset_exposure_pct: 35,
      risk_per_trade_pct: 1,
      max_daily_loss_pct: 5,
      max_drawdown_pct: 22,
      max_positions: 20,
    },
  },
  fields: {
    identity: ["id", "bot_id", "display_name", "alias", "description", "domain_type"],
    base_config: ["capital_base_usd", "risk_profile", "max_total_exposure_pct", "max_asset_exposure_pct", "risk_per_trade_pct", "max_daily_loss_pct", "max_drawdown_pct", "max_positions"],
    symbol_assignment: ["universe_name", "universe", "max_live_symbols", "symbol_assignment_status", "symbol_assignment_errors"],
    strategy_pool: ["pool_strategy_ids", "pool_strategies", "strategy_pool_status", "strategy_pool_errors", "max_pool_strategies"],
    policy_state: ["engine", "mode", "status", "notes"],
    governance: ["registry_status", "archived_at"],
    trace: ["created_at", "updated_at", "last_change_type", "last_change_summary", "last_changed_by", "last_change_source"],
  },
};

describe("bot-registry helpers", () => {
  it("arma el draft por defecto desde el contrato canónico del backend", () => {
    expect(buildDefaultBotRegistryDraft(CONTRACT_FIXTURE)).toEqual({
      display_name: "",
      alias: "",
      description: "",
      domain_type: "spot",
      universe_name: "",
      universe: [],
      pool_strategy_ids: [],
      max_live_symbols: "1",
      capital_base_usd: "10000",
      max_total_exposure_pct: "65",
      max_asset_exposure_pct: "25",
      risk_profile: "medium",
      risk_per_trade_pct: "0.5",
      max_daily_loss_pct: "3",
      max_drawdown_pct: "15",
      max_positions: "10",
    });
  });

  it("normaliza un draft valido con trim y campos opcionales vacios", () => {
    const normalized = normalizeBotRegistryDraft({
      display_name: "  Bot Momentum Spot  ",
      alias: "  momentum-a  ",
      description: "  Bot con identidad persistente  ",
      domain_type: "spot",
      universe_name: "core_spot_usdt",
      universe: ["BTCUSDT", "ETHUSDT"],
      pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1", "momentum_breakout_v2"],
      max_live_symbols: "2",
      capital_base_usd: "25000",
      max_total_exposure_pct: "70",
      max_asset_exposure_pct: "25",
      risk_profile: "medium",
      risk_per_trade_pct: "0.5",
      max_daily_loss_pct: "3",
      max_drawdown_pct: "15",
      max_positions: "8",
    }, CONTRACT_FIXTURE);

    expect(normalized).toEqual({
      display_name: "Bot Momentum Spot",
      alias: "momentum-a",
      description: "Bot con identidad persistente",
      domain_type: "spot",
      universe_name: "core_spot_usdt",
      universe: ["BTCUSDT", "ETHUSDT"],
      pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1", "momentum_breakout_v2"],
      max_live_symbols: 2,
      capital_base_usd: 25000,
      max_total_exposure_pct: 70,
      max_asset_exposure_pct: 25,
      risk_profile: "medium",
      risk_per_trade_pct: 0.5,
      max_daily_loss_pct: 3,
      max_drawdown_pct: 15,
      max_positions: 8,
    });
  });

  it("rechaza display_name corto, dominio invalido, símbolos duplicados o exposición inconsistente", () => {
    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "ab",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        domain_type: "spot",
      }, CONTRACT_FIXTURE),
    ).toThrow("al menos 3 caracteres");

    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        domain_type: "margin" as never,
      }, CONTRACT_FIXTURE),
    ).toThrow();

    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        max_total_exposure_pct: "20",
        max_asset_exposure_pct: "25",
      }, CONTRACT_FIXTURE),
    ).toThrow("exposición por activo");

    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT", "BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        max_live_symbols: "1",
      }, CONTRACT_FIXTURE),
    ).toThrow("duplicados");

    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        max_live_symbols: "2",
      }, CONTRACT_FIXTURE),
    ).toThrow("cap live");

    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1", "trend_pullback_orderflow_confirm_v1"],
      }, CONTRACT_FIXTURE),
    ).toThrow("estrategias duplicadas");

    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: [],
      }, CONTRACT_FIXTURE),
    ).toThrow("al menos 1 estrategia");

    expect(() =>
      normalizeBotRegistryDraft({
        ...buildDefaultBotRegistryDraft(CONTRACT_FIXTURE),
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: Array.from({ length: 16 }, (_, index) => `strategy_${index}`),
      }, CONTRACT_FIXTURE),
    ).toThrow("no puede superar 15");
  });

  it("arma draft desde un bot existente y prioriza display_name", () => {
    const draft = buildBotRegistryDraft({
      id: "BOT-000123",
      bot_id: "BOT-000123",
      display_name: "Bot Futures",
      name: "Legacy Name",
      alias: "fut-a",
      description: "Descripción del bot.",
      domain_type: "futures",
      registry_status: "active",
      universe_name: "core_usdm_perps",
      universe_family: "usdm_futures",
      universe: ["BTCUSDT", "ETHUSDT"],
      strategy_pool_status: "valid",
      strategy_pool_errors: [],
      max_pool_strategies: 15,
      max_live_symbols: 2,
      capital_base_usd: 32000,
      max_total_exposure_pct: 80,
      max_asset_exposure_pct: 30,
      risk_profile: "aggressive",
      risk_per_trade_pct: 1,
      max_daily_loss_pct: 5,
      max_drawdown_pct: 22,
      max_positions: 12,
      engine: "bandit_thompson",
      mode: "paper",
      status: "active",
      pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
      created_at: "2026-04-14T00:00:00Z",
      updated_at: "2026-04-14T00:00:00Z",
    }, CONTRACT_FIXTURE);

    expect(draft).toEqual({
      display_name: "Bot Futures",
      alias: "fut-a",
      description: "Descripción del bot.",
      domain_type: "futures",
      universe_name: "core_usdm_perps",
      universe: ["BTCUSDT", "ETHUSDT"],
      pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
      max_live_symbols: "2",
      capital_base_usd: "32000",
      max_total_exposure_pct: "80",
      max_asset_exposure_pct: "30",
      risk_profile: "aggressive",
      risk_per_trade_pct: "1",
      max_daily_loss_pct: "5",
      max_drawdown_pct: "22",
      max_positions: "12",
    });
    expect(getBotDisplayName({ display_name: "Bot Futures", name: "Legacy Name" })).toBe("Bot Futures");
    expect(getBotDisplayName({ display_name: "", name: "Legacy Name" })).toBe("Legacy Name");
  });
});
