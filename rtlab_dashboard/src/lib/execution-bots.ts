import { getBotDisplayName } from "@/lib/bot-registry";
import type { BotInstance, BotLifecycleOperationalItem } from "@/lib/types";

export type ExecutionBotStatusFilter = "all" | "active" | "paused" | "archived";

type ExecutionBotIdentity = Pick<BotInstance, "id" | "bot_id" | "display_name" | "name" | "mode" | "status" | "registry_status">;

export function isExecutionBotArchived(bot: Pick<BotInstance, "registry_status"> | null | undefined): boolean {
  return String(bot?.registry_status || "active").trim().toLowerCase() === "archived";
}

export function matchesExecutionBotStatusFilter(bot: Pick<BotInstance, "status" | "registry_status">, filter: ExecutionBotStatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "archived") return isExecutionBotArchived(bot);
  return !isExecutionBotArchived(bot) && String(bot.status || "").trim().toLowerCase() === filter;
}

export function getExecutionBotLabel(bot: ExecutionBotIdentity): string {
  const stableId = String(bot.bot_id || bot.id || "").trim() || String(bot.id || "").trim();
  const runtimeStatus = String(bot.status || "").trim().toLowerCase() || "unknown";
  const registryStatus = isExecutionBotArchived(bot) ? "archived" : "active";
  return `${getBotDisplayName(bot)} | ${stableId} | ${String(bot.mode || "").toUpperCase()} | runtime:${runtimeStatus} | registry:${registryStatus}`;
}

export function botRuntimeStatusVariant(status: string | null | undefined): "success" | "warn" | "neutral" {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "active") return "success";
  if (normalized === "paused") return "warn";
  return "neutral";
}

export function botRegistryStatusVariant(status: string | null | undefined): "success" | "neutral" {
  return String(status || "active").trim().toLowerCase() === "archived" ? "neutral" : "success";
}

export type LifecycleOperationalSymbolAction = {
  label: "Pausar símbolo" | "Reanudar símbolo";
  nextStatus: "active" | "paused";
};

export function getLifecycleOperationalSymbolAction(
  item: Pick<BotLifecycleOperationalItem, "symbol" | "operational_status" | "base_lifecycle_state">,
  allowedTradeSymbols: readonly string[],
): LifecycleOperationalSymbolAction | null {
  const symbol = String(item.symbol || "").trim().toUpperCase();
  if (!symbol) return null;
  if (String(item.operational_status || "").trim().toLowerCase() === "paused") {
    return { label: "Reanudar símbolo", nextStatus: "active" };
  }
  const allowedSet = new Set(allowedTradeSymbols.map((entry) => String(entry || "").trim().toUpperCase()).filter(Boolean));
  if (!allowedSet.has(symbol)) return null;
  if (String(item.base_lifecycle_state || "").trim().toLowerCase() !== "progressing") return null;
  return { label: "Pausar símbolo", nextStatus: "paused" };
}

export function buildLifecycleOperationalPatch(
  currentMapping: Record<string, string> | null | undefined,
  symbol: string,
  nextStatus: "active" | "paused" | string,
): Record<string, "paused"> {
  const out: Record<string, "paused"> = {};
  for (const [rawSymbol, rawStatus] of Object.entries(currentMapping || {})) {
    const normalizedSymbol = String(rawSymbol || "").trim().toUpperCase();
    const normalizedStatus = String(rawStatus || "").trim().toLowerCase();
    if (!normalizedSymbol || normalizedStatus !== "paused") continue;
    out[normalizedSymbol] = "paused";
  }

  const normalizedTarget = String(symbol || "").trim().toUpperCase();
  if (!normalizedTarget) return sortPausedSymbolMap(out);

  if (String(nextStatus || "").trim().toLowerCase() === "paused") {
    out[normalizedTarget] = "paused";
  } else {
    delete out[normalizedTarget];
  }

  return sortPausedSymbolMap(out);
}

function sortPausedSymbolMap(mapping: Record<string, "paused">): Record<string, "paused"> {
  return Object.fromEntries(
    Object.entries(mapping).sort(([left], [right]) => left.localeCompare(right)),
  ) as Record<string, "paused">;
}
