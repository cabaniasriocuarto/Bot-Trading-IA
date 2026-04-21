import { describe, expect, it } from "vitest";

import {
  lifecycleOperationalStatusVariant,
  summarizeLifecycleOperational,
} from "@/lib/lifecycle-operational";
import type { BotLifecycleOperationalModel } from "@/lib/types";

describe("lifecycle-operational", () => {
  it("resume el segundo consumidor minimo con simbolos ordenados y overrides pausados", () => {
    const summary = summarizeLifecycleOperational({
      contract_version: "rtlops81/v1",
      bot_id: "BOT-001",
      domain_type: "spot",
      registry_status: "active",
      policy_state: {
        mode: "paper",
        status: "active",
        engine: "fixed_rules",
        universe: ["ethusdt", "btcusdt"],
        pool_strategy_ids: ["strat-a"],
        notes: "",
        created_at: "2026-04-21T12:00:00Z",
        updated_at: "2026-04-21T12:00:00Z",
      },
      runtime_contract_version: "rtlops77/v1",
      lifecycle_contract_version: "rtlops80/v1",
      lifecycle_status: "valid",
      execution_ready: true,
      allowed_trade_symbols: ["ethusdt"],
      rejected_trade_symbols: ["btcusdt"],
      lifecycle_operational_by_symbol: {
        btcusdt: "paused",
      },
      progressing_symbols: ["ethusdt"],
      blocked_symbols: [],
      progression_allowed: true,
      items: [
        {
          symbol: "ethusdt",
          runtime_symbol_id: "runtime:ETHUSDT",
          selection_key: "selection:ETHUSDT",
          net_decision_key: "decision:ETHUSDT",
          decision_log_scope: {
            bot_id: "BOT-001",
            symbol: "ETHUSDT",
          },
          selected_strategy_id: "strat-a",
          decision_action: "trade",
          decision_side: "BUY",
          base_lifecycle_state: "progressing",
          operational_status: "active",
          lifecycle_state: "progressing",
          progression_allowed: true,
          status: "valid",
          errors: [],
        },
        {
          symbol: "btcusdt",
          runtime_symbol_id: "runtime:BTCUSDT",
          selection_key: "selection:BTCUSDT",
          net_decision_key: "decision:BTCUSDT",
          decision_log_scope: {
            bot_id: "BOT-001",
            symbol: "BTCUSDT",
          },
          selected_strategy_id: null,
          decision_action: "flat",
          decision_side: null,
          base_lifecycle_state: "rejected",
          operational_status: "paused",
          lifecycle_state: "rejected",
          progression_allowed: false,
          status: "warning",
          errors: [
            {
              reason_code: "symbol_operational_paused",
              message: "symbol paused",
              symbol: "BTCUSDT",
            },
          ],
        },
      ],
      reason_codes: ["symbol_operational_paused"],
      status: "warning",
      errors: ["symbol paused"],
      storage_fields: ["lifecycle_operational_by_symbol"],
      api: {
        detail_path: "/api/v1/bots/BOT-001",
        lifecycle_path: "/api/v1/bots/BOT-001/lifecycle",
        lifecycle_operational_path: "/api/v1/bots/BOT-001/lifecycle-operational",
        runtime_path: "/api/v1/bots/BOT-001/runtime",
        policy_state_path: "/api/v1/bots/BOT-001/policy-state",
        decision_log_path: "/api/v1/bots/BOT-001/decision-log",
      },
      updated_at: "2026-04-21T12:00:00Z",
      archived_at: null,
    } satisfies BotLifecycleOperationalModel);

    expect(summary).not.toBeNull();
    expect(summary?.statusVariant).toBe("warn");
    expect(summary?.allowedSymbols).toEqual(["ETHUSDT"]);
    expect(summary?.rejectedSymbols).toEqual(["BTCUSDT"]);
    expect(summary?.pausedSymbols).toEqual(["BTCUSDT"]);
    expect(summary?.items.map((item) => item.symbol)).toEqual(["BTCUSDT", "ETHUSDT"]);
    expect(summary?.items[0]?.issues).toEqual(["symbol_operational_paused"]);
    expect(summary?.items[1]?.decisionLabel).toBe("BUY");
  });

  it("mapea variantes de badge por status canonico", () => {
    expect(lifecycleOperationalStatusVariant("valid")).toBe("success");
    expect(lifecycleOperationalStatusVariant("warning")).toBe("warn");
    expect(lifecycleOperationalStatusVariant("error")).toBe("danger");
    expect(lifecycleOperationalStatusVariant("unknown")).toBe("neutral");
  });
});
