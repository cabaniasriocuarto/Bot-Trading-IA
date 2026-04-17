import { describe, expect, it } from "vitest";

import {
  DEFAULT_BOT_REGISTRY_DRAFT,
  buildBotRegistryDraft,
  getBotDisplayName,
  normalizeBotRegistryDraft,
} from "@/lib/bot-registry";

describe("bot-registry helpers", () => {
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
    });

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
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "ab",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        domain_type: "spot",
      }),
    ).toThrow("al menos 3 caracteres");

    expect(() =>
      normalizeBotRegistryDraft({
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        domain_type: "margin" as never,
      }),
    ).toThrow();

    expect(() =>
      normalizeBotRegistryDraft({
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        max_total_exposure_pct: "20",
        max_asset_exposure_pct: "25",
      }),
    ).toThrow("exposición por activo");

    expect(() =>
      normalizeBotRegistryDraft({
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT", "BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        max_live_symbols: "1",
      }),
    ).toThrow("duplicados");

    expect(() =>
      normalizeBotRegistryDraft({
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1"],
        max_live_symbols: "2",
      }),
    ).toThrow("cap live");

    expect(() =>
      normalizeBotRegistryDraft({
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: ["trend_pullback_orderflow_confirm_v1", "trend_pullback_orderflow_confirm_v1"],
      }),
    ).toThrow("estrategias duplicadas");

    expect(() =>
      normalizeBotRegistryDraft({
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: [],
      }),
    ).toThrow("al menos 1 estrategia");

    expect(() =>
      normalizeBotRegistryDraft({
        ...DEFAULT_BOT_REGISTRY_DRAFT,
        display_name: "Bot válido",
        universe_name: "core_spot_usdt",
        universe: ["BTCUSDT"],
        pool_strategy_ids: Array.from({ length: 16 }, (_, index) => `strategy_${index}`),
      }),
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
    });

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
