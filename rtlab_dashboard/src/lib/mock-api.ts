import JSZip from "jszip";
import { NextRequest, NextResponse } from "next/server";

import { getMockStore, pushAlert, pushLog, saveMockStore } from "@/lib/mock-store";
import type { BacktestRun, BotStatusResponse, Strategy } from "@/lib/types";
import { toCsv } from "@/lib/utils";

type UserRole = "admin" | "viewer";

function ensureAdmin(method: string, role: UserRole) {
  if (method !== "GET" && role !== "admin") {
    return NextResponse.json({ error: "Acceso denegado: se requiere rol admin." }, { status: 403 });
  }
  return null;
}

function parseDateMs(value: string | null) {
  if (!value) return null;
  const ms = new Date(value).getTime();
  if (Number.isNaN(ms)) return null;
  return ms;
}

function withTimeRangeFilter<T extends { ts: string }>(rows: T[], searchParams: URLSearchParams) {
  const sinceMs = parseDateMs(searchParams.get("since"));
  const untilMs = parseDateMs(searchParams.get("until"));
  return rows.filter((row) => {
    const ts = new Date(row.ts).getTime();
    if (sinceMs !== null && ts < sinceMs) return false;
    if (untilMs !== null && ts > untilMs) return false;
    return true;
  });
}

function normalizePath(path: string[]) {
  if (!path.length) return ["v1", "health"];
  if (path[0] === "v1") return path;

  const [resource, id, action] = path;
  if (resource === "status") return ["v1", "bot", "status"];
  if (resource === "portfolio") return ["v1", "portfolio"];
  if (resource === "positions") return ["v1", "positions"];
  if (resource === "trades") return id ? ["v1", "trades", id] : ["v1", "trades"];
  if (resource === "alerts") return ["v1", "alerts"];
  if (resource === "logs") return ["v1", "logs"];
  if (resource === "execution") return ["v1", "execution", "metrics"];
  if (resource === "risk") return ["v1", "risk"];
  if (resource === "settings") return ["v1", "settings"];
  if (resource === "control") return ["v1", "control", id || ""];
  if (resource === "backtests") {
    if (id === "run") return ["v1", "backtests", "run"];
    if (!id) return ["v1", "backtests", "runs"];
    if (action === "report") return ["v1", "backtests", "runs", id];
    return ["v1", "backtests", "runs", id];
  }
  if (resource === "strategies") {
    if (!id) return ["v1", "strategies"];
    if (!action) return ["v1", "strategies", id];
    if (action === "set-primary") return ["v1", "strategies", id, "primary"];
    return ["v1", "strategies", id, action];
  }
  return ["v1", ...path];
}

async function readJsonBody<T>(req: NextRequest, fallback: T): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    return fallback;
  }
}

function parsePrimitive(value: string): unknown {
  const trimmed = value.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

function parseSimpleYaml(yaml: string) {
  const obj: Record<string, unknown> = {};
  for (const line of yaml.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf(":");
    if (idx < 1) continue;
    const key = trimmed.slice(0, idx).trim();
    const rawValue = trimmed.slice(idx + 1).trim();
    obj[key] = parsePrimitive(rawValue);
  }
  return obj;
}

function toYaml(params: Record<string, unknown>) {
  return Object.entries(params)
    .map(([key, value]) => `${key}: ${value}`)
    .join("\n");
}

function computeParamsDiff(previous: Record<string, unknown>, next: Record<string, unknown>) {
  const keys = new Set([...Object.keys(previous), ...Object.keys(next)]);
  return [...keys]
    .filter((key) => previous[key] !== next[key])
    .map((key) => ({ key, before: previous[key], after: next[key] }));
}

function validateAgainstSchema(strategy: Strategy, params: Record<string, unknown>) {
  const schema = strategy.schema;
  if (!schema || typeof schema !== "object") return [];
  const errors: string[] = [];
  const schemaObject = schema as { required?: string[]; properties?: Record<string, { type?: string; minimum?: number; maximum?: number }> };
  for (const required of schemaObject.required || []) {
    if (!(required in params)) errors.push(`Falta parámetro requerido: ${required}`);
  }
  for (const [key, value] of Object.entries(params)) {
    const rules = schemaObject.properties?.[key];
    if (!rules) continue;
    if (rules.type === "number" && typeof value !== "number") {
      errors.push(`El parámetro ${key} debe ser numérico.`);
      continue;
    }
    if (typeof value === "number") {
      if (typeof rules.minimum === "number" && value < rules.minimum) errors.push(`${key} debe ser >= ${rules.minimum}.`);
      if (typeof rules.maximum === "number" && value > rules.maximum) errors.push(`${key} debe ser <= ${rules.maximum}.`);
    }
  }
  return errors;
}

function buildBacktestRun(payload: {
  strategy_id: string;
  start: string;
  end: string;
  universe: string[];
  fees_bps: number;
  spread_bps: number;
  slippage_bps: number;
  funding_bps: number;
  validation_mode: string;
}) {
  const store = getMockStore();
  const strategy = store.strategies.find((row) => row.id === payload.strategy_id);
  const now = new Date();
  const id = `bt_${Date.now()}`;
  const costPenalty = payload.fees_bps + payload.spread_bps + payload.slippage_bps * 0.8 + payload.funding_bps * 0.5;
  const robustScore = Math.max(35, Math.min(92, Number((88 - costPenalty * 1.2 + Math.random() * 3).toFixed(2))));
  const sharpe = Number((0.9 + robustScore / 100).toFixed(2));
  const maxDd = Number((-0.08 - (95 - robustScore) / 600).toFixed(4));
  const points = Array.from({ length: 110 }).map((_, idx) => ({
    time: new Date(now.getTime() - (110 - idx) * 24 * 60 * 60_000).toISOString(),
    equity: Number((10000 + idx * (11 + sharpe * 2.3) + Math.sin(idx / 7) * 130).toFixed(2)),
    drawdown: Number((maxDd * Math.abs(Math.cos(idx / 12))).toFixed(4)),
  }));

  const runTrades = store.trades
    .filter((trade) => trade.strategy_id === payload.strategy_id)
    .slice(0, 40)
    .map((trade, idx) => ({
      ...trade,
      id: `${id}_tr_${idx + 1}`,
    }));

  const run: BacktestRun = {
    id,
    strategy_id: payload.strategy_id,
    period: { start: payload.start, end: payload.end },
    universe: payload.universe,
    costs_model: {
      fees_bps: payload.fees_bps,
      spread_bps: payload.spread_bps,
      slippage_bps: payload.slippage_bps,
      funding_bps: payload.funding_bps,
    },
    dataset_hash: `${Date.now().toString(16)}a9`,
    git_commit: "785ef1f",
    metrics: {
      cagr: Number((0.18 + robustScore / 220).toFixed(2)),
      max_dd: maxDd,
      sharpe,
      sortino: Number((sharpe * 1.28).toFixed(2)),
      calmar: Number((Math.abs((0.18 + robustScore / 220) / maxDd)).toFixed(2)),
      winrate: Number((0.45 + robustScore / 500).toFixed(2)),
      expectancy: Number((8 + robustScore / 4).toFixed(2)),
      avg_trade: Number((6 + robustScore / 9).toFixed(2)),
      turnover: Number((2.2 + (95 - robustScore) / 20).toFixed(2)),
      robust_score: robustScore,
    },
    status: "completed",
    artifacts_links: {
      report_json: `/api/v1/backtests/runs/${id}?format=report_json`,
      trades_csv: `/api/v1/backtests/runs/${id}?format=trades_csv`,
      equity_curve_csv: `/api/v1/backtests/runs/${id}?format=equity_curve_csv`,
    },
    created_at: now.toISOString(),
    duration_sec: 120,
    equity_curve: points,
    drawdown_curve: points.map((point) => ({ time: point.time, value: point.drawdown })),
    trades: runTrades,
  };

  if (strategy) {
    strategy.last_run_at = now.toISOString();
    strategy.updated_at = now.toISOString();
  }

  store.backtests.unshift(run);
  pushAlert({
    type: "backtest_finished",
    severity: "info",
    module: "backtest",
    message: `Backtest ${run.id} completado (${strategy?.name || payload.strategy_id}).`,
    related_id: run.id,
    data: {
      validation_mode: payload.validation_mode,
      robust_score: run.metrics.robust_score,
    },
  });
  pushLog({
    type: "backtest_finished",
    severity: "info",
    module: "backtest",
    message: `Run ${run.id} guardado con ${run.trades?.length || 0} trades.`,
    related_ids: [run.id, payload.strategy_id],
    payload: {
      period: run.period,
      universe: run.universe,
      metrics: run.metrics,
    },
  });
  saveMockStore();
  return run;
}

function filteredTrades(searchParams: URLSearchParams) {
  const store = getMockStore();
  const strategyId = searchParams.get("strategy_id");
  const symbol = searchParams.get("symbol");
  const side = searchParams.get("side");
  const timeframe = searchParams.get("timeframe");
  const reasonCode = searchParams.get("reason_code");
  const exitReason = searchParams.get("exit_reason");
  const result = searchParams.get("result");
  const dateFrom = parseDateMs(searchParams.get("date_from"));
  const dateTo = parseDateMs(searchParams.get("date_to"));
  let rows = [...store.trades];
  if (strategyId) rows = rows.filter((row) => row.strategy_id === strategyId);
  if (symbol) rows = rows.filter((row) => row.symbol === symbol);
  if (side) rows = rows.filter((row) => row.side === side);
  if (timeframe) rows = rows.filter((row) => row.timeframe === timeframe);
  if (reasonCode) rows = rows.filter((row) => row.reason_code === reasonCode);
  if (exitReason) rows = rows.filter((row) => row.exit_reason === exitReason);
  if (result === "win") rows = rows.filter((row) => row.pnl_net > 0);
  if (result === "loss") rows = rows.filter((row) => row.pnl_net < 0);
  if (result === "breakeven") rows = rows.filter((row) => row.pnl_net === 0);
  if (dateFrom !== null) rows = rows.filter((row) => new Date(row.entry_time).getTime() >= dateFrom);
  if (dateTo !== null) rows = rows.filter((row) => new Date(row.entry_time).getTime() <= dateTo);
  return rows;
}

function makeStatusPayload() {
  const store = getMockStore();
  const status: BotStatusResponse = {
    ...store.status,
    state: store.status.bot_status,
    daily_pnl: store.status.pnl.daily,
    max_dd_value: store.status.max_dd.value,
    daily_loss_value: store.status.daily_loss.value,
    last_heartbeat: store.status.updated_at,
  };
  return status;
}

async function handleStrategyUpload(req: NextRequest) {
  const store = getMockStore();
  const form = await req.formData();
  const upload = form.get("file");
  if (!upload || typeof upload === "string") {
    return NextResponse.json({ error: "No se recibió archivo ZIP." }, { status: 400 });
  }

  const fileName = upload.name || "";
  if (!fileName.toLowerCase().endsWith(".zip")) {
    return NextResponse.json({ error: "Archivo inválido. Debe ser .zip." }, { status: 400 });
  }

  let zip: JSZip;
  try {
    zip = await JSZip.loadAsync(await upload.arrayBuffer());
  } catch {
    return NextResponse.json({ error: "No se pudo leer el ZIP. Verificá el archivo." }, { status: 400 });
  }

  const names = Object.keys(zip.files);
  const findZipFile = (requiredName: string) => names.find((name) => name === requiredName || name.endsWith(`/${requiredName}`));

  const manifestPath = findZipFile("manifest.json");
  const defaultsPath = findZipFile("defaults.yaml");
  const schemaPath = findZipFile("schema.json");
  const strategyPyPath = findZipFile("strategy.py");
  const strategyTsPath = findZipFile("strategy.ts");

  const errors: string[] = [];
  if (!manifestPath) errors.push("Falta manifest.json");
  if (!defaultsPath) errors.push("Falta defaults.yaml");
  if (!schemaPath) errors.push("Falta schema.json");
  if (!strategyPyPath && !strategyTsPath) errors.push("Falta strategy.py o strategy.ts");
  if (errors.length) {
    return NextResponse.json(
      {
        error: "ZIP inválido. Estructura incompleta.",
        details: errors,
        expected: ["manifest.json", "defaults.yaml", "schema.json", "strategy.py|strategy.ts"],
      },
      { status: 400 },
    );
  }

  const manifestRaw = await zip.file(manifestPath!)!.async("string");
  const defaultsYaml = await zip.file(defaultsPath!)!.async("string");
  const schemaRaw = await zip.file(schemaPath!)!.async("string");

  let manifest: Record<string, unknown>;
  let schema: Record<string, unknown>;
  try {
    manifest = JSON.parse(manifestRaw) as Record<string, unknown>;
    schema = JSON.parse(schemaRaw) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "manifest.json o schema.json no tienen JSON válido." }, { status: 400 });
  }

  const requiredManifestKeys = ["id", "name", "version", "author", "engine", "timeframes", "supports", "inputs", "tags"];
  const missingManifestKeys = requiredManifestKeys.filter((key) => !(key in manifest));
  if (missingManifestKeys.length) {
    return NextResponse.json(
      { error: "manifest.json incompleto.", details: missingManifestKeys.map((key) => `Falta ${key}`) },
      { status: 400 },
    );
  }

  const manifestId = String(manifest.id);
  const manifestVersion = String(manifest.version);
  const strategyId = store.strategies.some((row) => row.id === manifestId) ? `${manifestId}_${Date.now().toString(16).slice(-4)}` : manifestId;

  const params = parseSimpleYaml(defaultsYaml);
  const strategy: Strategy = {
    id: strategyId,
    name: String(manifest.name),
    version: manifestVersion,
    enabled: false,
    primary: false,
    params,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    last_run_at: null,
    notes: `Estrategia subida por ZIP (${fileName}).`,
    tags: Array.isArray(manifest.tags) ? manifest.tags.map((tag) => String(tag)) : ["upload"],
    manifest: {
      id: strategyId,
      name: String(manifest.name),
      version: manifestVersion,
      author: String(manifest.author),
      engine: String(manifest.engine),
      timeframes: manifest.timeframes as { primary: string; entry: string; execution: string },
      supports: manifest.supports as { long: boolean; short: boolean },
      inputs: Array.isArray(manifest.inputs) ? manifest.inputs.map((item) => String(item)) : [],
      tags: Array.isArray(manifest.tags) ? manifest.tags.map((item) => String(item)) : [],
    },
    defaults_yaml: defaultsYaml,
    schema,
    pack_source: "upload",
  };

  store.strategies.unshift(strategy);
  saveMockStore();
  pushLog({
    type: "strategy_changed",
    severity: "info",
    module: "registry",
    message: `Strategy pack cargado: ${strategy.name} v${strategy.version}.`,
    related_ids: [strategy.id],
    payload: { file: fileName, structure_ok: true },
  });
  pushAlert({
    type: "strategy_changed",
    severity: "info",
    module: "registry",
    message: `Estrategia ${strategy.name} registrada y deshabilitada por defecto.`,
    related_id: strategy.id,
  });

  return NextResponse.json({
    ok: true,
    strategy,
    validation: {
      structure_ok: true,
      manifest_path: manifestPath,
      defaults_path: defaultsPath,
      schema_path: schemaPath,
      implementation_path: strategyPyPath || strategyTsPath,
    },
  });
}

function exportLogs<T extends object>(rows: T[], format: string, filenamePrefix: string) {
  if (format === "json") {
    return new NextResponse(JSON.stringify(rows, null, 2), {
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": `attachment; filename=${filenamePrefix}.json`,
      },
    });
  }
  return new NextResponse(toCsv(rows), {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename=${filenamePrefix}.csv`,
    },
  });
}

function updateHealthCause(cause?: string) {
  const store = getMockStore();
  store.health.cause = cause;
  store.status.cause = cause;
  saveMockStore();
}
async function handleV1(req: NextRequest, path: string[]) {
  const store = getMockStore();
  const [, resource, id, action] = path;

  if (resource === "health" && req.method === "GET") {
    return NextResponse.json(store.health);
  }

  if (resource === "bot" && id === "status" && req.method === "GET") {
    return NextResponse.json(makeStatusPayload());
  }

  if (resource === "positions" && req.method === "GET") {
    return NextResponse.json(store.positions);
  }

  if (resource === "portfolio" && req.method === "GET") {
    return NextResponse.json({
      ...store.portfolio,
      open_positions: store.positions,
    });
  }

  if (resource === "trades" && req.method === "GET") {
    if (id) {
      const trade = store.trades.find((row) => row.id === id);
      if (!trade) return NextResponse.json({ error: "Trade no encontrado." }, { status: 404 });
      return NextResponse.json(trade);
    }
    return NextResponse.json(filteredTrades(req.nextUrl.searchParams));
  }

  if (resource === "strategies") {
    if (!id && req.method === "GET") {
      return NextResponse.json(store.strategies);
    }
    if (id === "upload" && req.method === "POST") {
      return handleStrategyUpload(req);
    }
    const strategy = store.strategies.find((row) => row.id === id);
    if (!strategy) return NextResponse.json({ error: "Estrategia no encontrada." }, { status: 404 });

    if (!action && req.method === "GET") {
      return NextResponse.json({
        ...strategy,
        params_defaults: strategy.defaults_yaml || toYaml(strategy.params),
        params_schema: strategy.schema || {},
      });
    }

    if (action === "enable" && req.method === "POST") {
      const body = await readJsonBody<{ enabled?: boolean }>(req, {});
      const enabled = body.enabled ?? true;
      strategy.enabled = Boolean(enabled);
      strategy.updated_at = new Date().toISOString();
      if (enabled) {
        pushAlert({
          type: "strategy_changed",
          severity: "info",
          module: "registry",
          message: `Estrategia ${strategy.name} habilitada.`,
          related_id: strategy.id,
        });
      } else {
        pushAlert({
          type: "strategy_changed",
          severity: "warn",
          module: "registry",
          message: `Estrategia ${strategy.name} deshabilitada.`,
          related_id: strategy.id,
        });
      }
      saveMockStore();
      return NextResponse.json({ ok: true, strategy });
    }

    if (action === "disable" && req.method === "POST") {
      strategy.enabled = false;
      strategy.updated_at = new Date().toISOString();
      pushAlert({
        type: "strategy_changed",
        severity: "warn",
        module: "registry",
        message: `Estrategia ${strategy.name} deshabilitada.`,
        related_id: strategy.id,
      });
      saveMockStore();
      return NextResponse.json({ ok: true, strategy });
    }

    if (action === "primary" && req.method === "POST") {
      store.strategies.forEach((row) => {
        row.primary = false;
      });
      strategy.primary = true;
      strategy.enabled = true;
      strategy.updated_at = new Date().toISOString();
      saveMockStore();
      pushLog({
        type: "strategy_changed",
        severity: "info",
        module: "registry",
        message: `Estrategia primaria actualizada a ${strategy.id}.`,
        related_ids: [strategy.id],
      });
      return NextResponse.json({ ok: true, strategy });
    }

    if (action === "duplicate" && req.method === "POST") {
      const pieces = strategy.version.split(".");
      const patch = Number(pieces[2] || "0") + 1;
      const nextVersion = `${pieces[0] || "1"}.${pieces[1] || "0"}.${patch}`;
      const clone: Strategy = {
        ...strategy,
        id: `${strategy.id}_${Date.now().toString(16).slice(-4)}`,
        version: nextVersion,
        primary: false,
        enabled: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        notes: `Clonado desde ${strategy.id}.`,
        pack_source: "upload",
      };
      store.strategies.unshift(clone);
      saveMockStore();
      return NextResponse.json({ ok: true, strategy: clone });
    }

    if (action === "params" && (req.method === "PUT" || req.method === "POST")) {
      const body = await readJsonBody<{ params?: Record<string, unknown>; params_yaml?: string }>(req, {});
      const parsed = body.params || (body.params_yaml ? parseSimpleYaml(body.params_yaml) : null);
      if (!parsed || typeof parsed !== "object") {
        return NextResponse.json({ error: "Payload de params inválido." }, { status: 400 });
      }
      const validationErrors = validateAgainstSchema(strategy, parsed);
      if (validationErrors.length) {
        return NextResponse.json({ error: "Validación de parámetros falló.", details: validationErrors }, { status: 400 });
      }
      const diff = computeParamsDiff(strategy.params, parsed);
      strategy.params = parsed;
      strategy.defaults_yaml = toYaml(parsed);
      strategy.updated_at = new Date().toISOString();
      saveMockStore();
      pushLog({
        type: "strategy_changed",
        severity: "info",
        module: "registry",
        message: `Parámetros actualizados para ${strategy.id}.`,
        related_ids: [strategy.id],
        payload: { diff },
      });
      return NextResponse.json({ ok: true, strategy, diff });
    }
  }

  if (resource === "backtests") {
    if (id === "run" && req.method === "POST") {
      const payload = await readJsonBody<{
        strategy_id?: string;
        start?: string;
        end?: string;
        period?: { start?: string; end?: string };
        universe?: string[];
        fees_bps?: number;
        spread_bps?: number;
        slippage_bps?: number;
        funding_bps?: number;
        costs_model?: { fees_bps?: number; spread_bps?: number; slippage_bps?: number; funding_bps?: number };
        validation_mode?: string;
      }>(req, {});
      const strategyId = payload.strategy_id || store.strategies[0]?.id;
      if (!strategyId) return NextResponse.json({ error: "No hay estrategias registradas." }, { status: 400 });
      const run = buildBacktestRun({
        strategy_id: strategyId,
        start: payload.start || payload.period?.start || "2024-01-01",
        end: payload.end || payload.period?.end || "2024-12-31",
        universe: payload.universe?.length ? payload.universe : ["BTC/USDT", "ETH/USDT"],
        fees_bps: Number(payload.fees_bps ?? payload.costs_model?.fees_bps ?? 5.5),
        spread_bps: Number(payload.spread_bps ?? payload.costs_model?.spread_bps ?? 4.0),
        slippage_bps: Number(payload.slippage_bps ?? payload.costs_model?.slippage_bps ?? 3.2),
        funding_bps: Number(payload.funding_bps ?? payload.costs_model?.funding_bps ?? 1.0),
        validation_mode: payload.validation_mode || "walk-forward",
      });
      return NextResponse.json({ ok: true, run_id: run.id, run });
    }

    if (id === "runs" && !action && req.method === "GET") {
      return NextResponse.json(store.backtests);
    }

    if (id === "runs" && action && req.method === "GET") {
      const run = store.backtests.find((row) => row.id === action);
      if (!run) return NextResponse.json({ error: "Backtest no encontrado." }, { status: 404 });
      const format = req.nextUrl.searchParams.get("format");
      if (format === "trades_csv") {
        return new NextResponse(toCsv(run.trades || []), {
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
      if (format === "report_json") {
        return NextResponse.json(run);
      }
      return NextResponse.json({
        ...run,
        drawdown_curve: run.drawdown_curve || run.equity_curve.map((point) => ({ time: point.time, value: point.drawdown })),
      });
    }
  }

  if (resource === "risk" && req.method === "GET") {
    return NextResponse.json({
      ...store.risk,
      gate_checklist: store.settings.gate_checklist,
    });
  }

  if (resource === "execution" && id === "metrics" && req.method === "GET") {
    return NextResponse.json(store.execution);
  }

  if (resource === "alerts" && req.method === "GET") {
    const severity = req.nextUrl.searchParams.get("severity");
    const moduleName = req.nextUrl.searchParams.get("module");
    let rows = withTimeRangeFilter([...store.alerts], req.nextUrl.searchParams);
    if (severity) rows = rows.filter((row) => row.severity === severity);
    if (moduleName) rows = rows.filter((row) => row.module === moduleName);
    return NextResponse.json(rows);
  }

  if (resource === "logs" && req.method === "GET") {
    const severity = req.nextUrl.searchParams.get("severity");
    const moduleName = req.nextUrl.searchParams.get("module");
    let rows = withTimeRangeFilter([...store.logs], req.nextUrl.searchParams);
    if (severity) rows = rows.filter((row) => row.severity === severity);
    if (moduleName) rows = rows.filter((row) => row.module === moduleName);
    const format = req.nextUrl.searchParams.get("format");
    if (format === "csv" || format === "json") {
      return exportLogs(rows, format, `rtlab_logs_${new Date().toISOString().slice(0, 10)}`);
    }
    return NextResponse.json(rows);
  }

  if (resource === "settings") {
    if (!id && req.method === "GET") {
      return NextResponse.json(store.settings);
    }
    if (!id && req.method === "PUT") {
      const payload = await readJsonBody<Partial<typeof store.settings>>(req, {});
      const nextMode = payload.mode || store.settings.mode;
      if (nextMode === "LIVE" && store.settings.gate_checklist.some((item) => !item.done)) {
        return NextResponse.json(
          {
            error: "No se puede activar LIVE: gate checklist incompleto.",
            gate_checklist: store.settings.gate_checklist,
          },
          { status: 400 },
        );
      }

      store.settings = {
        ...store.settings,
        ...payload,
        risk_defaults: { ...store.settings.risk_defaults, ...(payload.risk_defaults || {}) },
        telegram: { ...store.settings.telegram, ...(payload.telegram || {}) },
        execution: { ...store.settings.execution, ...(payload.execution || {}) },
        credentials: { ...store.settings.credentials, ...(payload.credentials || {}) },
        feature_flags: { ...store.settings.feature_flags, ...(payload.feature_flags || {}) },
      };
      store.settings.mode = nextMode;
      store.status.updated_at = new Date().toISOString();
      saveMockStore();
      pushLog({
        type: "settings_changed",
        severity: "info",
        module: "settings",
        message: "Configuración actualizada por admin.",
        related_ids: [],
      });
      return NextResponse.json({ ok: true, settings: store.settings });
    }
    if (id === "test-alert" && req.method === "POST") {
      const alert = pushAlert({
        type: "health",
        severity: "info",
        module: "telegram",
        message: "Prueba de alerta enviada correctamente (modo mock).",
        data: { chat_id: store.settings.telegram.chat_id || "no-configurado" },
      });
      pushLog({
        type: "health",
        severity: "info",
        module: "telegram",
        message: "Test de Telegram ejecutado.",
        related_ids: [alert.id],
      });
      return NextResponse.json({ ok: true, alert });
    }
    if (id === "test-exchange" && req.method === "POST") {
      const canConnect = store.settings.mode === "PAPER" || store.settings.mode === "TESTNET" || store.settings.mode === "MOCK";
      if (!canConnect) {
        return NextResponse.json({ ok: false, message: "LIVE requiere validación manual antes de pruebas." }, { status: 400 });
      }
      pushLog({
        type: "health",
        severity: "info",
        module: "exchange",
        message: `Conexión de prueba OK (${store.settings.exchange} - ${store.settings.mode}).`,
        related_ids: [],
      });
      return NextResponse.json({
        ok: true,
        exchange: store.settings.exchange,
        mode: store.settings.mode,
        latency_ms: 124,
        capabilities: {
          fetch_ohlcv: true,
          stream_trades: true,
          stream_orderbook: true,
          place_order: store.settings.mode !== "MOCK",
          cancel_order: store.settings.mode !== "MOCK",
          account_balance: true,
        },
      });
    }
  }

  if (resource === "ws" && id === "status" && req.method === "GET") {
    return NextResponse.json({
      ok: true,
      connected: store.health.ws.connected,
      url: "/ws/v1/events",
      transport: "sse",
      last_event_at: store.health.ws.last_event_at,
    });
  }

  if (resource === "control" && req.method === "POST") {
    if (!id) return NextResponse.json({ error: "Falta acción de control." }, { status: 400 });
    if (id === "pause") {
      store.status.bot_status = "PAUSED";
      store.status.paused = true;
      store.status.updated_at = new Date().toISOString();
      saveMockStore();
      pushAlert({
        type: "health",
        severity: "warn",
        module: "control",
        message: "Bot pausado por administrador.",
      });
      return NextResponse.json({ ok: true, state: store.status.bot_status });
    }
    if (id === "resume") {
      store.status.bot_status = "RUNNING";
      store.status.paused = false;
      store.status.killed = false;
      store.status.risk_mode = "NORMAL";
      store.status.updated_at = new Date().toISOString();
      updateHealthCause(undefined);
      saveMockStore();
      pushAlert({
        type: "health",
        severity: "info",
        module: "control",
        message: "Bot reanudado por administrador.",
      });
      return NextResponse.json({ ok: true, state: store.status.bot_status });
    }
    if (id === "safe-mode") {
      const payload = await readJsonBody<{ enabled?: boolean }>(req, { enabled: true });
      const enabled = payload.enabled ?? true;
      store.status.bot_status = enabled ? "SAFE_MODE" : "RUNNING";
      store.status.risk_mode = enabled ? "SAFE" : "NORMAL";
      store.status.updated_at = new Date().toISOString();
      updateHealthCause(enabled ? "Modo seguro activo por prevención de riesgo." : undefined);
      saveMockStore();
      pushAlert({
        type: "breaker_triggered",
        severity: enabled ? "warn" : "info",
        module: "risk",
        message: enabled ? "Modo seguro activado." : "Modo seguro desactivado.",
      });
      return NextResponse.json({ ok: true, safe_mode: enabled });
    }
    if (id === "kill") {
      store.status.bot_status = "KILLED";
      store.status.killed = true;
      store.status.paused = true;
      store.status.updated_at = new Date().toISOString();
      updateHealthCause("Interruptor de emergencia ejecutado.");
      saveMockStore();
      pushAlert({
        type: "breaker_triggered",
        severity: "error",
        module: "control",
        message: "Interruptor de emergencia ejecutado.",
      });
      return NextResponse.json({ ok: true, state: store.status.bot_status });
    }
    if (id === "close-all") {
      store.positions = [];
      store.status.updated_at = new Date().toISOString();
      saveMockStore();
      pushAlert({
        type: "order_update",
        severity: "warn",
        module: "execution",
        message: "Todas las posiciones fueron cerradas por admin.",
      });
      return NextResponse.json({ ok: true });
    }
  }

  return NextResponse.json({ error: "Ruta no encontrada." }, { status: 404 });
}

export async function handleMockApi(req: NextRequest, rawPath: string[], role: UserRole) {
  const adminGate = ensureAdmin(req.method, role);
  if (adminGate) return adminGate;

  const path = normalizePath(rawPath);
  return handleV1(req, path);
}
