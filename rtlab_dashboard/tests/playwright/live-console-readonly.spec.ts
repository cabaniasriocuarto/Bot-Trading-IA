import { expect, type Page, type Route, test } from "@playwright/test";

const now = new Date("2026-04-29T03:00:00.000Z").toISOString();
const botId = "bot-live-readonly-smoke";

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function registerReadOnlyExecutionApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/v1/execution/metrics") {
      return fulfillJson(route, {
        maker_ratio: 0.66,
        fill_ratio: 0.92,
        requotes: 0,
        cancels: 0,
        avg_spread: 3.1,
        p95_spread: 5.4,
        avg_slippage: 1.2,
        p95_slippage: 2.1,
        rate_limit_hits: 0,
        api_errors: 0,
        latency_ms_p95: 110,
        series: [{ ts: now, latency_ms_p95: 110, spread_bps: 3.1, slippage_bps: 1.2 }],
        endpoint_errors: [],
        notes: ["Smoke read-only."],
      });
    }

    if (path === "/api/v1/bot/status") {
      return fulfillJson(route, {
        state: "RUNNING",
        bot_status: "RUNNING",
        risk_mode: "NORMAL",
        paused: false,
        killed: false,
        daily_pnl: 125.5,
        max_dd_value: 2.1,
        daily_loss_value: 0.4,
        last_heartbeat: now,
        equity: 10_250,
        pnl: { daily: 125.5, weekly: 300, monthly: 720 },
        max_dd: { value: 2.1, limit: 20 },
        daily_loss: { value: 0.4, limit: 5 },
        health: { api_latency_ms: 90, ws_connected: true, ws_lag_ms: 15, errors_5m: 0, rate_limits_5m: 0 },
        updated_at: now,
      });
    }

    if (path === "/api/v1/settings") {
      return fulfillJson(route, {
        mode: "PAPER",
        exchange: "binance",
        exchange_plugin_options: ["binance", "bybit", "oanda", "alpaca"],
        credentials: { exchange_configured: false, telegram_configured: false, telegram_chat_id: "" },
        telegram: { enabled: false, chat_id: "" },
        risk_defaults: { max_daily_loss: 5, max_dd: 20, max_positions: 10, risk_per_trade: 0.5 },
        execution: { post_only_default: true, slippage_max_bps: 10, request_timeout_ms: 12_000 },
        learning: {
          enabled: false,
          mode: "OFF",
          selector_algo: "thompson",
          drift_algo: "adwin",
          max_candidates: 30,
          top_n: 5,
          validation: { walk_forward: true, train_days: 252, test_days: 126, enforce_pbo: true, enforce_dsr: true },
          promotion: { allow_auto_apply: false, allow_live: false },
        },
        feature_flags: {},
        gate_checklist: [{ stage: "Paper >= 14 dias", done: true, note: "Smoke local." }],
      });
    }

    if (path === "/api/v1/health") {
      return fulfillJson(route, {
        ok: true,
        time: now,
        version: "smoke",
        ws: { connected: true, transport: "sse", url: "/api/events", last_event_at: now },
        exchange: { mode: "PAPER", name: "binance" },
        db: { ok: true, driver: "jsonl" },
      });
    }

    if (path === "/api/v1/gates") {
      return fulfillJson(route, {
        overall_status: "PASS",
        gates: [{ id: "read_only_smoke", status: "PASS", reason: "Smoke deterministic." }],
      });
    }

    if (path === "/api/v1/rollout/status") {
      return fulfillJson(route, {
        state: "stable",
        pending_live_approval: false,
        pending_live_approval_target: null,
        live_stable_100_requires_approve: true,
        routing: { mode: "paper", phase: "read-only", shadow_only: true },
      });
    }

    if (path === "/api/v1/exchange/diagnose") {
      return fulfillJson(route, {
        ok: true,
        mode: "paper",
        exchange: "binance",
        base_url: "mock://readonly",
        ws_url: "mock://readonly-ws",
        has_keys: false,
        key_source: "none",
        missing: [],
        expected_env_vars: [],
        last_error: "",
        connector_ok: true,
        connector_reason: "Smoke read-only.",
        order_ok: false,
        order_reason: "No crea ordenes.",
        checks: {},
      });
    }

    if (path === "/api/v1/strategies") {
      return fulfillJson(route, [
        {
          id: "strat-alpha",
          name: "Alpha Trend",
          version: "1.0.0",
          enabled: true,
          enabled_for_trading: true,
          primary: true,
          params: {},
          created_at: now,
          updated_at: now,
          notes: "Smoke strategy.",
          tags: ["smoke"],
          primary_for_modes: ["paper"],
        },
      ]);
    }

    if (path === "/api/v1/bots") {
      return fulfillJson(route, {
        items: [
          {
            id: botId,
            display_name: "Bot smoke read-only",
            domain_type: "futures",
            registry_status: "active",
            capital_base_usd: 10_000,
            max_total_exposure_pct: 30,
            max_asset_exposure_pct: 15,
            risk_profile: "medium",
            risk_per_trade_pct: 0.5,
            max_daily_loss_pct: 3,
            max_drawdown_pct: 12,
            max_positions: 3,
            name: "Bot smoke read-only",
            engine: "rtlab",
            mode: "paper",
            status: "active",
            pool_strategy_ids: ["strat-alpha", "strat-beta"],
            strategy_selection_by_symbol: { "BTC/USDT": "strat-alpha", "ETH/USDT": "strat-beta" },
            universe_name: "smoke-usdt",
            universe_family: "usdm_futures",
            universe: ["BTC/USDT", "ETH/USDT"],
            max_live_symbols: 12,
            notes: "Smoke bot.",
            created_at: now,
            updated_at: now,
          },
        ],
      });
    }

    if (path === `/api/v1/bots/${botId}/policy-state`) {
      return fulfillJson(route, {
        bot_id: botId,
        policy_state: {
          engine: "rtlab",
          mode: "paper",
          status: "active",
          pool_strategy_ids: ["strat-alpha", "strat-beta"],
          universe_name: "smoke-usdt",
          universe: ["BTC/USDT", "ETH/USDT"],
          max_live_symbols: 12,
          notes: "Read-only smoke.",
          created_at: now,
          updated_at: now,
        },
      });
    }

    if (path === `/api/v1/bots/${botId}/decision-log`) {
      return fulfillJson(route, {
        bot_id: botId,
        items: [],
        total: 0,
        page: 1,
        page_size: 8,
        breaker_events: [],
      });
    }

    if (path === `/api/v1/bots/${botId}/lifecycle-operational`) {
      return fulfillJson(route, {
        bot_id: botId,
        lifecycle_operational: {
          contract_version: "rtlops84/v1",
          bot_id: botId,
          allowed_trade_symbols: ["BTC/USDT", "ETH/USDT"],
          rejected_trade_symbols: [],
          progressing_symbols: ["BTC/USDT"],
          blocked_symbols: ["ETH/USDT"],
          lifecycle_operational_by_symbol: {},
          progression_allowed: true,
          status: "warning",
          errors: [],
          items: [
            {
              symbol: "BTC/USDT",
              runtime_symbol_id: "runtime:btc",
              selection_key: "sel:btc",
              net_decision_key: "net:btc",
              base_lifecycle_state: "progressing",
              operational_status: "active",
              lifecycle_state: "progressing",
              progression_allowed: true,
              selected_strategy_id: "strat-alpha",
              decision_action: "trade",
              errors: [],
            },
          ],
          updated_at: now,
        },
      });
    }

    if (path === `/api/v1/bots/${botId}/scope-eligibility`) {
      return fulfillJson(route, {
        bot_id: botId,
        scope_eligibility: {
          contract_version: "rtlops96/v1",
          bot_id: botId,
          domain_type: "futures",
          registry_status: "active",
          policy_state: {
            engine: "rtlab",
            mode: "paper",
            status: "active",
            pool_strategy_ids: ["strat-alpha", "strat-beta"],
            universe_name: "smoke-usdt",
            universe: ["BTC/USDT", "ETH/USDT"],
            max_live_symbols: 12,
            notes: "Read-only smoke.",
            created_at: now,
            updated_at: now,
          },
          ownership: {
            entity_kind: "bot",
            entity_id: botId,
            persisted_scope_owner: "bot_registry",
            strategy_role: "consumer_only",
            research_scope_modes: ["batch", "beast"],
            operation_scope_modes: ["shadow", "paper", "testnet", "live"],
            operation_manual_selector_allowed: false,
          },
          scope_source: "bot_runtime_scope",
          universe_name: "smoke-usdt",
          market_family: "usdm_futures",
          quote_asset: "USDT",
          symbols_configured: ["BTC/USDT", "ETH/USDT"],
          configured_symbols_count: 2,
          max_active_symbols: 12,
          eligible_symbols: ["BTC/USDT", "ETH/USDT"],
          ineligible_symbols: [],
          blocking_reasons: [],
          is_blocking: false,
          items: [],
          reason_codes: [],
          status: "valid",
          errors: [],
          storage_fields: [],
          api: {
            detail_path: `/api/v1/bots/${botId}`,
            scope_eligibility_path: `/api/v1/bots/${botId}/scope-eligibility`,
            multi_symbol_path: `/api/v1/bots/${botId}/multi-symbol`,
            strategy_eligibility_path: `/api/v1/bots/${botId}/symbol-strategy-eligibility`,
            runtime_path: `/api/v1/bots/${botId}/runtime`,
            lifecycle_operational_path: `/api/v1/bots/${botId}/lifecycle-operational`,
          },
          updated_at: now,
        },
      });
    }

    if (path === `/api/v1/bots/${botId}/order-intents-by-symbol`) {
      return fulfillJson(route, {
        order_intents_by_symbol: {
          contract_version: "rtlops97/v1",
          bot_id: botId,
          operation_mode: "paper",
          scope_source: "bot_runtime_scope",
          source_contracts: { scope: "rtlops96/v1", paper_policy: "rtlops68-slice3/v1" },
          paper_execution_policy: {
            policy_version: "rtlops68-slice3/v1",
            mode: "single_intent_safe",
            multi_symbol_per_cycle_enabled: false,
            max_symbols_per_cycle: 1,
            max_intents_per_cycle: 1,
            read_model_allows_multi_symbol_observability: true,
            blocking_reason_on_excess: "paper_multi_symbol_execution_disabled",
            source: "runtime_controls.paper_execution",
            effective_actionable_symbols: ["BTC/USDT"],
            observability_only_symbols: ["ETH/USDT"],
            blocking_reasons: ["paper_multi_symbol_execution_disabled"],
          },
          symbols: ["BTC/USDT", "ETH/USDT"],
          actionable_symbols: ["BTC/USDT"],
          blocked_symbols: ["ETH/USDT"],
          no_action_symbols: [],
          order_intents_by_symbol: {
            "BTC/USDT": {
              symbol: "BTC/USDT",
              status: "actionable",
              source: "bot_runtime_net_decision",
              action: "trade",
              side: "BUY",
              selected_strategy_id: "strat-alpha",
              net_decision_key: "net:btc",
              decision_log_scope: { bot_id: botId, symbol: "BTC/USDT", mode: "paper" },
              blocking_reasons: [],
              reason_codes: [],
              evaluated_at: now,
              paper_execution_status: "execution_actionable",
              candidate_intents_count: 1,
              suppressed_intents_count: 0,
            },
            "ETH/USDT": {
              symbol: "ETH/USDT",
              status: "blocked",
              source: "bot_runtime_net_decision",
              action: "trade",
              side: "BUY",
              selected_strategy_id: "strat-beta",
              net_decision_key: "net:eth",
              decision_log_scope: { bot_id: botId, symbol: "ETH/USDT", mode: "paper" },
              blocking_reasons: ["paper_multi_symbol_execution_disabled"],
              reason_codes: ["paper_multi_symbol_execution_disabled"],
              evaluated_at: now,
              paper_execution_status: "observability_only",
              paper_execution_blocking_reasons: ["paper_multi_symbol_execution_disabled"],
              paper_policy_blocking_reasons: ["paper_multi_symbol_execution_disabled"],
              candidate_intents_count: 1,
              suppressed_intents_count: 1,
            },
          },
          blocking_reasons: ["paper_multi_symbol_execution_disabled"],
          reason_codes: ["paper_multi_symbol_execution_disabled"],
          status: "warning",
          evaluated_at: now,
          created_at: now,
        },
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: `Unhandled smoke route: ${path}` }),
    });
  });
}

test("la consola live read-only renderiza observabilidad sin acciones operativas", async ({ page }) => {
  await registerReadOnlyExecutionApi(page);

  const login = await page.request.post("/api/auth/login", {
    data: { username: "viewer", password: "viewer123!" },
  });
  expect(login.ok()).toBe(true);

  await page.goto("/execution");
  await expect(page).toHaveURL(/\/execution$/);
  await expect(page.getByText("Consola Live del Bot — solo lectura")).toBeVisible();

  const liveConsole = page
    .locator('div[class*="border-cyan-500"]')
    .filter({ hasText: "Consola Live del Bot — solo lectura" })
    .first();

  await expect(liveConsole).toContainText("read-only");
  await expect(liveConsole).toContainText("No crea órdenes");
  await expect(liveConsole).toContainText("Paper execution policy");
  await expect(liveConsole).toContainText("single-intent seguro");
  await expect(liveConsole).toContainText("Multi-symbol visible como observabilidad");
  await expect(liveConsole).toContainText("Razones de bloqueo");
  await expect(liveConsole).toContainText("BTC/USDT");
  await expect(liveConsole).toContainText("ETH/USDT");
  await expect(liveConsole).toContainText("strat-alpha");
  await expect(liveConsole).toContainText("paper_multi_symbol_execution_disabled");
  await expect(liveConsole.getByRole("columnheader", { name: "Símbolo" })).toBeVisible();
  await expect(liveConsole.getByRole("columnheader", { name: "Status" })).toBeVisible();
  await expect(liveConsole.getByRole("columnheader", { name: "Intent" })).toBeVisible();

  for (const action of [
    "Comprar",
    "Vender",
    "Cancelar",
    "Emergency cancel",
    "Freeze",
    "Unfreeze",
    "Promote",
    "Demote",
    "Start bot",
    "Stop bot",
    "Reconfigure",
    "Archive",
  ]) {
    await expect(liveConsole.getByRole("button", { name: new RegExp(action, "i") })).toHaveCount(0);
  }

  await expect(liveConsole.getByRole("combobox")).toHaveCount(0);
});
