import type { BotLifecycleOperationalItem, BotLifecycleOperationalModel } from "@/lib/types";

export type LifecycleOperationalBadgeVariant = "success" | "warn" | "danger" | "neutral";

export type LifecycleOperationalAuditItem = {
  symbol: string;
  runtimeSymbolId: string;
  selectionKey: string;
  netDecisionKey: string;
  selectedStrategyId: string | null;
  decisionLabel: string;
  baseLifecycleState: string;
  operationalStatus: string;
  lifecycleState: string;
  progressionAllowed: boolean;
  issues: string[];
};

export type LifecycleOperationalSummary = {
  status: string;
  statusVariant: LifecycleOperationalBadgeVariant;
  executionReady: boolean;
  progressionAllowed: boolean;
  allowedSymbols: string[];
  rejectedSymbols: string[];
  progressingSymbols: string[];
  blockedSymbols: string[];
  pausedSymbols: string[];
  items: LifecycleOperationalAuditItem[];
  errors: string[];
};

export type LifecycleOperationalUniverseStatus = "allowed" | "rejected" | "progressing" | "paused" | "unknown";

export type LifecycleOperationalUniverseItem = {
  symbol: string;
  status: LifecycleOperationalUniverseStatus;
  statusLabel: string;
  statusVariant: LifecycleOperationalBadgeVariant;
  progressionAllowed: boolean;
  runtimeSymbolId: string;
  selectedStrategyId: string | null;
  issues: string[];
};

export type LifecycleOperationalUniverseSummary = {
  symbols: LifecycleOperationalUniverseItem[];
  allowedCount: number;
  rejectedCount: number;
  progressingCount: number;
  pausedCount: number;
  untrackedCount: number;
};

export function lifecycleOperationalStatusVariant(status: string | null | undefined): LifecycleOperationalBadgeVariant {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "valid") return "success";
  if (normalized === "warning") return "warn";
  if (normalized === "error") return "danger";
  return "neutral";
}

export function summarizeLifecycleOperational(
  model: BotLifecycleOperationalModel | null | undefined,
): LifecycleOperationalSummary | null {
  if (!model) return null;

  return {
    status: String(model.status || "unknown"),
    statusVariant: lifecycleOperationalStatusVariant(model.status),
    executionReady: Boolean(model.execution_ready),
    progressionAllowed: Boolean(model.progression_allowed),
    allowedSymbols: normalizeSymbolList(model.allowed_trade_symbols),
    rejectedSymbols: normalizeSymbolList(model.rejected_trade_symbols),
    progressingSymbols: normalizeSymbolList(model.progressing_symbols),
    blockedSymbols: normalizeSymbolList(model.blocked_symbols),
    pausedSymbols: Object.entries(model.lifecycle_operational_by_symbol || {})
      .filter(([, status]) => String(status || "").trim().toLowerCase() === "paused")
      .map(([symbol]) => normalizeSymbol(symbol))
      .filter(Boolean)
      .sort((left, right) => left.localeCompare(right)),
    items: [...(model.items || [])]
      .map((item) => ({
        symbol: normalizeSymbol(item.symbol),
        runtimeSymbolId: String(item.runtime_symbol_id || "").trim(),
        selectionKey: String(item.selection_key || "").trim(),
        netDecisionKey: String(item.net_decision_key || "").trim(),
        selectedStrategyId: String(item.selected_strategy_id || "").trim() || null,
        decisionLabel: getDecisionLabel(item),
        baseLifecycleState: String(item.base_lifecycle_state || "unknown").trim().toLowerCase(),
        operationalStatus: String(item.operational_status || "unknown").trim().toLowerCase(),
        lifecycleState: String(item.lifecycle_state || "unknown").trim().toLowerCase(),
        progressionAllowed: Boolean(item.progression_allowed),
        issues: (item.errors || [])
          .map((issue) => String(issue.reason_code || issue.message || "").trim())
          .filter(Boolean),
      }))
      .sort((left, right) => left.symbol.localeCompare(right.symbol)),
    errors: normalizeTextList(model.errors),
  };
}

export function summarizeLifecycleOperationalUniverse(
  model: BotLifecycleOperationalModel | null | undefined,
  universe: readonly string[] | null | undefined,
): LifecycleOperationalUniverseSummary | null {
  const summary = summarizeLifecycleOperational(model);
  if (!summary) return null;

  const requestedSymbols = normalizeSymbolListPreserveOrder(universe);
  const displaySymbols = requestedSymbols.length
    ? requestedSymbols
    : normalizeSymbolList([
        ...summary.allowedSymbols,
        ...summary.rejectedSymbols,
        ...summary.progressingSymbols,
        ...summary.pausedSymbols,
        ...summary.items.map((item) => item.symbol),
      ]);

  const allowedSymbols = new Set(summary.allowedSymbols);
  const rejectedSymbols = new Set(summary.rejectedSymbols);
  const progressingSymbols = new Set(summary.progressingSymbols);
  const pausedSymbols = new Set(summary.pausedSymbols);
  const itemsBySymbol = new Map(summary.items.map((item) => [item.symbol, item] as const));

  const symbols = displaySymbols.map((symbol) => {
    const item = itemsBySymbol.get(symbol);
    const status = getUniverseStatus(symbol, allowedSymbols, rejectedSymbols, progressingSymbols, pausedSymbols);
    return {
      symbol,
      status,
      statusLabel: getUniverseStatusLabel(status),
      statusVariant: getUniverseStatusVariant(status),
      progressionAllowed: item?.progressionAllowed ?? (status === "progressing" || status === "allowed"),
      runtimeSymbolId: item?.runtimeSymbolId || "",
      selectedStrategyId: item?.selectedStrategyId || null,
      issues: item?.issues || [],
    };
  });

  return {
    symbols,
    allowedCount: displaySymbols.filter((symbol) => allowedSymbols.has(symbol)).length,
    rejectedCount: displaySymbols.filter((symbol) => rejectedSymbols.has(symbol)).length,
    progressingCount: displaySymbols.filter((symbol) => progressingSymbols.has(symbol)).length,
    pausedCount: displaySymbols.filter((symbol) => pausedSymbols.has(symbol)).length,
    untrackedCount: symbols.filter((item) => item.status === "unknown").length,
  };
}

function getDecisionLabel(item: Pick<BotLifecycleOperationalItem, "decision_action" | "decision_side">): string {
  const action = String(item.decision_action || "").trim().toLowerCase();
  if (action === "trade") return String(item.decision_side || "").trim().toUpperCase() || "trade";
  if (action === "flat") return "flat";
  return "sin decision";
}

function normalizeSymbolList(symbols: readonly string[] | null | undefined): string[] {
  return Array.from(
    new Set((symbols || []).map((symbol) => normalizeSymbol(symbol)).filter(Boolean)),
  ).sort((left, right) => left.localeCompare(right));
}

function normalizeTextList(values: readonly (string | null | undefined)[] | null | undefined): string[] {
  return (values || [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

function getUniverseStatus(
  symbol: string,
  allowedSymbols: ReadonlySet<string>,
  rejectedSymbols: ReadonlySet<string>,
  progressingSymbols: ReadonlySet<string>,
  pausedSymbols: ReadonlySet<string>,
): LifecycleOperationalUniverseStatus {
  if (pausedSymbols.has(symbol)) return "paused";
  if (progressingSymbols.has(symbol)) return "progressing";
  if (allowedSymbols.has(symbol)) return "allowed";
  if (rejectedSymbols.has(symbol)) return "rejected";
  return "unknown";
}

function getUniverseStatusLabel(status: LifecycleOperationalUniverseStatus): string {
  switch (status) {
    case "paused":
      return "paused";
    case "progressing":
      return "progressing";
    case "allowed":
      return "allowed";
    case "rejected":
      return "rejected";
    default:
      return "sin dato";
  }
}

function getUniverseStatusVariant(status: LifecycleOperationalUniverseStatus): LifecycleOperationalBadgeVariant {
  switch (status) {
    case "paused":
      return "warn";
    case "progressing":
    case "allowed":
      return "success";
    case "rejected":
      return "neutral";
    default:
      return "neutral";
  }
}

function normalizeSymbol(value: unknown): string {
  return String(value || "").trim().toUpperCase();
}

function normalizeSymbolListPreserveOrder(symbols: readonly string[] | null | undefined): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const symbol of symbols || []) {
    const normalized = normalizeSymbol(symbol);
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    ordered.push(normalized);
  }
  return ordered;
}
