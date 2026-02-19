import { NextRequest, NextResponse } from "next/server";

import { getMockStore, pushAlert, pushLog } from "@/lib/mock-store";
import { toCsv } from "@/lib/utils";

function findStrategy(id: string) {
  const store = getMockStore();
  return store.strategies.find((row) => row.id === id);
}

function ensureAdmin(method: string, role: "admin" | "viewer") {
  if (method !== "GET" && role !== "admin") {
    return NextResponse.json({ error: "Forbidden: admin role required" }, { status: 403 });
  }
  return null;
}

function withQueryFilter<T extends { ts: string }>(rows: T[], searchParams: URLSearchParams) {
  const since = searchParams.get("since");
  if (!since) return rows;
  const sinceMs = new Date(since).getTime();
  if (Number.isNaN(sinceMs)) return rows;
  return rows.filter((row) => new Date(row.ts).getTime() >= sinceMs);
}

function buildBacktestRun() {
  const store = getMockStore();
  const id = `bt_${Date.now()}`;
  const now = new Date();
  const points = Array.from({ length: 90 }).map((_, idx) => ({
    time: new Date(now.getTime() - (90 - idx) * 24 * 60 * 60_000).toISOString(),
    equity: Number((10000 + idx * 18 + Math.sin(idx / 7) * 140).toFixed(2)),
    drawdown: Number((-Math.abs(Math.cos(idx / 11) * 0.08)).toFixed(4)),
  }));
  const run = {
    id,
    strategy_id: "stg_001",
    period: { start: "2025-01-01", end: "2025-12-31" },
    universe: ["BTC/USDT", "ETH/USDT"],
    costs_model: { fees_bps: 5.5, spread_bps: 4.0, slippage_bps: 3.1, funding_bps: 1.0 },
    dataset_hash: `${Date.now().toString(16)}a9`,
    git_commit: "136a5b7",
    metrics: {
      cagr: 0.33,
      max_dd: -0.11,
      sharpe: 1.55,
      sortino: 2.09,
      calmar: 3.0,
      winrate: 0.57,
      expectancy: 14.4,
      avg_trade: 10.2,
      turnover: 2.9,
      robust_score: 77.8,
    },
    status: "completed" as const,
    artifacts_links: {
      report_json: `/api/backtests/${id}/report?format=report_json`,
      trades_csv: `/api/backtests/${id}/report?format=trades_csv`,
      equity_curve_csv: `/api/backtests/${id}/report?format=equity_curve_csv`,
    },
    created_at: now.toISOString(),
    duration_sec: 134,
    equity_curve: points,
  };
  store.backtests.unshift(run);
  return run;
}

export async function handleMockApi(req: NextRequest, path: string[], role: "admin" | "viewer") {
  const adminGate = ensureAdmin(req.method, role);
  if (adminGate) return adminGate;

  const store = getMockStore();
  const [resource, id, action] = path;

  if (!resource) {
    return NextResponse.json({ ok: true, mode: "mock" });
  }

  if (resource === "status" && req.method === "GET") {
    store.status.updated_at = new Date().toISOString();
    return NextResponse.json(store.status);
  }

  if (resource === "portfolio" && req.method === "GET") {
    return NextResponse.json(store.portfolio);
  }

  if (resource === "positions" && req.method === "GET") {
    return NextResponse.json(store.positions);
  }

  if (resource === "trades" && req.method === "GET") {
    if (id) {
      const trade = store.trades.find((row) => row.id === id);
      if (!trade) return NextResponse.json({ error: "Trade not found" }, { status: 404 });
      return NextResponse.json(trade);
    }
    const q = req.nextUrl.searchParams;
    const strategyId = q.get("strategy_id");
    const symbol = q.get("symbol");
    const side = q.get("side");
    const exitReason = q.get("exit_reason");
    let rows = [...store.trades];
    if (strategyId) rows = rows.filter((row) => row.strategy_id === strategyId);
    if (symbol) rows = rows.filter((row) => row.symbol === symbol);
    if (side) rows = rows.filter((row) => row.side === side);
    if (exitReason) rows = rows.filter((row) => row.exit_reason === exitReason);
    return NextResponse.json(rows);
  }

  if (resource === "strategies") {
    if (!id && req.method === "GET") {
      return NextResponse.json(store.strategies);
    }

    if (id && !action && req.method === "GET") {
      const strategy = findStrategy(id);
      if (!strategy) return NextResponse.json({ error: "Strategy not found" }, { status: 404 });
      return NextResponse.json(strategy);
    }

    if (!id || !action || req.method !== "POST") {
      return NextResponse.json({ error: "Invalid strategy action" }, { status: 400 });
    }

    const strategy = findStrategy(id);
    if (!strategy) return NextResponse.json({ error: "Strategy not found" }, { status: 404 });

    if (action === "enable") {
      strategy.enabled = true;
      strategy.updated_at = new Date().toISOString();
      pushAlert({ severity: "info", message: `Strategy ${strategy.name}:${strategy.version} enabled.` });
      return NextResponse.json({ ok: true, strategy });
    }

    if (action === "disable") {
      strategy.enabled = false;
      strategy.updated_at = new Date().toISOString();
      pushAlert({ severity: "warn", message: `Strategy ${strategy.name}:${strategy.version} disabled.` });
      return NextResponse.json({ ok: true, strategy });
    }

    if (action === "set-primary") {
      store.strategies.forEach((row) => {
        row.primary = false;
      });
      strategy.primary = true;
      strategy.enabled = true;
      strategy.updated_at = new Date().toISOString();
      pushLog({ severity: "info", module: "registry", message: `Primary strategy set to ${strategy.id}` });
      return NextResponse.json({ ok: true, strategy });
    }

    if (action === "duplicate") {
      const clone = {
        ...strategy,
        id: `stg_${Date.now()}`,
        version: `${strategy.version}-copy`,
        primary: false,
        enabled: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      store.strategies.unshift(clone);
      return NextResponse.json({ ok: true, strategy: clone });
    }

    if (action === "params") {
      const payload = (await req.json()) as { params?: Record<string, unknown> };
      if (!payload.params || typeof payload.params !== "object") {
        return NextResponse.json({ error: "Invalid params payload" }, { status: 400 });
      }
      strategy.params = payload.params;
      strategy.updated_at = new Date().toISOString();
      pushLog({ severity: "info", module: "registry", message: `Params updated for ${strategy.id}` });
      return NextResponse.json({ ok: true, strategy });
    }
  }

  if (resource === "backtests") {
    if (id === "run" && req.method === "POST") {
      const run = buildBacktestRun();
      pushAlert({ severity: "info", message: `Backtest ${run.id} launched.` });
      return NextResponse.json({ ok: true, run });
    }

    if (!id && req.method === "GET") {
      return NextResponse.json(store.backtests);
    }

    if (id && action === "report" && req.method === "GET") {
      const run = store.backtests.find((row) => row.id === id);
      if (!run) return NextResponse.json({ error: "Backtest not found" }, { status: 404 });

      const format = req.nextUrl.searchParams.get("format");
      if (format === "trades_csv") {
        const tradeRows = store.trades
          .filter((row) => row.strategy_id === run.strategy_id)
          .slice(0, 25)
          .map((row) => ({
            id: row.id,
            symbol: row.symbol,
            side: row.side,
            entry_time: row.entry_time,
            exit_time: row.exit_time,
            pnl_net: row.pnl_net,
          }));
        return new NextResponse(toCsv(tradeRows), {
          headers: {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": `attachment; filename=${run.id}_trades.csv`,
          },
        });
      }

      if (format === "equity_curve_csv") {
        return new NextResponse(toCsv(run.equity_curve), {
          headers: {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": `attachment; filename=${run.id}_equity_curve.csv`,
          },
        });
      }

      return NextResponse.json(run);
    }
  }

  if (resource === "control" && req.method === "POST") {
    if (!id) return NextResponse.json({ error: "Missing control action" }, { status: 400 });
    if (id === "pause") {
      store.status.bot_status = "PAUSED";
      store.status.paused = true;
      pushAlert({ severity: "warn", message: "Bot paused by admin." });
      return NextResponse.json({ ok: true, state: store.status.bot_status });
    }
    if (id === "resume") {
      store.status.bot_status = "RUNNING";
      store.status.paused = false;
      store.status.killed = false;
      pushAlert({ severity: "info", message: "Bot resumed by admin." });
      return NextResponse.json({ ok: true, state: store.status.bot_status });
    }
    if (id === "safe-mode") {
      const payload = (await req.json().catch(() => ({ enabled: true }))) as { enabled?: boolean };
      const enabled = payload.enabled ?? true;
      store.status.bot_status = enabled ? "SAFE_MODE" : "RUNNING";
      store.status.risk_mode = enabled ? "SAFE" : "NORMAL";
      pushAlert({ severity: "warn", message: enabled ? "SAFE_MODE enabled." : "SAFE_MODE disabled." });
      return NextResponse.json({ ok: true, safe_mode: enabled });
    }
    if (id === "kill") {
      store.status.bot_status = "KILLED";
      store.status.killed = true;
      store.status.paused = true;
      pushAlert({ severity: "error", message: "KILL switch executed." });
      return NextResponse.json({ ok: true, state: store.status.bot_status });
    }
    if (id === "close-all") {
      store.positions = [];
      store.portfolio.exposure_total = 0;
      store.portfolio.exposure_by_symbol = [];
      pushAlert({ severity: "warn", message: "All positions were closed by admin action." });
      return NextResponse.json({ ok: true });
    }
  }

  if (resource === "risk" && req.method === "GET") {
    return NextResponse.json({ ...store.risk, gate_checklist: store.gateChecklist });
  }

  if (resource === "execution" && req.method === "GET") {
    return NextResponse.json(store.execution);
  }

  if (resource === "logs" && req.method === "GET") {
    const q = req.nextUrl.searchParams;
    const severity = q.get("severity");
    const moduleName = q.get("module");
    let rows = withQueryFilter([...store.logs], q);
    if (severity) rows = rows.filter((row) => row.severity === severity);
    if (moduleName) rows = rows.filter((row) => row.module === moduleName);
    return NextResponse.json(rows);
  }

  if (resource === "alerts" && req.method === "GET") {
    const q = req.nextUrl.searchParams;
    const severity = q.get("severity");
    let rows = withQueryFilter([...store.alerts], q);
    if (severity) rows = rows.filter((row) => row.severity === severity);
    return NextResponse.json(rows);
  }

  if (resource === "settings") {
    if (req.method === "GET") {
      return NextResponse.json({
        active_profile: store.activeProfile,
        feature_flags: store.featureFlags,
        exchange_default: "binance",
      });
    }
    if (req.method === "POST") {
      const payload = (await req.json()) as {
        active_profile?: "PAPER" | "TESTNET" | "LIVE";
        feature_flags?: Record<string, boolean>;
      };
      if (payload.active_profile) store.activeProfile = payload.active_profile;
      if (payload.feature_flags) {
        store.featureFlags = { ...store.featureFlags, ...payload.feature_flags };
      }
      pushLog({ severity: "info", module: "settings", message: "Settings updated by admin." });
      return NextResponse.json({ ok: true, active_profile: store.activeProfile, feature_flags: store.featureFlags });
    }
  }

  return NextResponse.json({ error: "Not found" }, { status: 404 });
}
