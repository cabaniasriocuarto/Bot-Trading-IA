import { getBotDisplayName } from "@/lib/bot-registry";
import type { BotInstance } from "@/lib/types";

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
