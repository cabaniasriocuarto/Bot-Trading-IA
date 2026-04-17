import { z } from "zod";

import type { BotInstance } from "@/lib/types";

export const BOT_REGISTRY_MAX_POOL_STRATEGIES = 15;

export const botRegistryFormSchema = z.object({
  display_name: z
    .string()
    .trim()
    .min(3, "El nombre visible debe tener al menos 3 caracteres.")
    .max(80, "El nombre visible no puede superar 80 caracteres."),
  alias: z
    .string()
    .trim()
    .max(40, "El alias no puede superar 40 caracteres.")
    .transform((value) => value || ""),
  description: z
    .string()
    .trim()
    .max(280, "La descripción no puede superar 280 caracteres.")
    .transform((value) => value || ""),
  domain_type: z.enum(["spot", "futures"]),
  universe_name: z
    .string()
    .trim()
    .min(1, "El universo válido es requerido."),
  universe: z
    .array(z.string().trim().min(1, "Cada símbolo asignado debe ser válido."))
    .min(1, "Debes asignar al menos 1 símbolo válido."),
  pool_strategy_ids: z
    .array(z.string().trim().min(1, "Cada estrategia del pool debe ser válida."))
    .min(1, "Debes asignar al menos 1 estrategia válida al pool.")
    .max(BOT_REGISTRY_MAX_POOL_STRATEGIES, `El pool no puede superar ${BOT_REGISTRY_MAX_POOL_STRATEGIES} estrategias.`),
  max_live_symbols: z.coerce.number().int().gte(1, "El cap live debe ser >= 1.").lte(12, "El cap live no puede superar 12."),
  capital_base_usd: z.coerce.number().gt(0, "El capital base debe ser > 0."),
  max_total_exposure_pct: z.coerce
    .number()
    .gt(0, "La exposición total debe ser > 0.")
    .lte(100, "La exposición total no puede superar 100%."),
  max_asset_exposure_pct: z.coerce
    .number()
    .gt(0, "La exposición por activo debe ser > 0.")
    .lte(100, "La exposición por activo no puede superar 100%."),
  risk_profile: z.enum(["conservative", "medium", "aggressive"]),
  risk_per_trade_pct: z.coerce
    .number()
    .gt(0, "El riesgo por trade debe ser > 0.")
    .lte(100, "El riesgo por trade no puede superar 100%."),
  max_daily_loss_pct: z.coerce
    .number()
    .gt(0, "La pérdida diaria máxima debe ser > 0.")
    .lte(100, "La pérdida diaria máxima no puede superar 100%."),
  max_drawdown_pct: z.coerce
    .number()
    .gt(0, "El drawdown máximo debe ser > 0.")
    .lte(100, "El drawdown máximo no puede superar 100%."),
  max_positions: z.coerce.number().int().gte(1, "Las posiciones máximas deben ser >= 1."),
}).superRefine((value, ctx) => {
  const seenSymbols = new Set<string>();
  const duplicateSymbols = new Set<string>();
  for (const rawSymbol of value.universe) {
    const symbol = String(rawSymbol || "").trim().toUpperCase();
    if (!symbol) continue;
    if (seenSymbols.has(symbol)) duplicateSymbols.add(symbol);
    seenSymbols.add(symbol);
  }
  if (duplicateSymbols.size) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["universe"],
      message: `No puede haber símbolos duplicados: ${Array.from(duplicateSymbols).join(", ")}`,
    });
  }
  const seenStrategies = new Set<string>();
  const duplicateStrategies = new Set<string>();
  for (const rawStrategyId of value.pool_strategy_ids) {
    const strategyId = String(rawStrategyId || "").trim();
    if (!strategyId) continue;
    if (seenStrategies.has(strategyId)) duplicateStrategies.add(strategyId);
    seenStrategies.add(strategyId);
  }
  if (duplicateStrategies.size) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["pool_strategy_ids"],
      message: `No puede haber estrategias duplicadas en el pool: ${Array.from(duplicateStrategies).join(", ")}`,
    });
  }
  if (value.max_live_symbols > value.universe.length) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["max_live_symbols"],
      message: "El cap live no puede superar la cantidad de símbolos asignados.",
    });
  }
  if (value.max_asset_exposure_pct > value.max_total_exposure_pct) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["max_asset_exposure_pct"],
      message: "La exposición por activo no puede superar la exposición total.",
    });
  }
});

export type BotRegistryDraft = z.input<typeof botRegistryFormSchema>;
export type BotRegistryFormData = z.output<typeof botRegistryFormSchema>;

export const DEFAULT_BOT_REGISTRY_DRAFT: BotRegistryDraft = {
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
};

function asDraftNumber(value: unknown, fallback: string): string {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return fallback;
  return String(numeric);
}

function asDraftUniverse(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item || "").trim().toUpperCase())
    .filter((item) => item.length > 0);
}

function asDraftStrategyPool(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0);
}

export function normalizeBotRegistryDraft(draft: BotRegistryDraft): BotRegistryFormData {
  const normalizedDraft = {
    ...draft,
    universe_name: String(draft.universe_name || "").trim(),
    universe: asDraftUniverse(draft.universe),
    pool_strategy_ids: asDraftStrategyPool(draft.pool_strategy_ids),
  };
  return botRegistryFormSchema.parse(normalizedDraft);
}

export function buildBotRegistryDraft(bot?: Partial<BotInstance> | null): BotRegistryDraft {
  const assignedUniverse = asDraftUniverse(bot?.universe);
  return {
    display_name: String(bot?.display_name || bot?.name || "").trim(),
    alias: String(bot?.alias || "").trim(),
    description: String(bot?.description || "").trim(),
    domain_type: bot?.domain_type === "futures" ? "futures" : "spot",
    universe_name: String(bot?.universe_name || "").trim(),
    universe: assignedUniverse,
    pool_strategy_ids: asDraftStrategyPool(bot?.pool_strategy_ids),
    max_live_symbols: asDraftNumber(bot?.max_live_symbols, assignedUniverse.length ? String(Math.min(assignedUniverse.length, 12)) : "1"),
    capital_base_usd: asDraftNumber(bot?.capital_base_usd, "10000"),
    max_total_exposure_pct: asDraftNumber(bot?.max_total_exposure_pct, "65"),
    max_asset_exposure_pct: asDraftNumber(bot?.max_asset_exposure_pct, "25"),
    risk_profile: bot?.risk_profile === "conservative" || bot?.risk_profile === "aggressive" ? bot.risk_profile : "medium",
    risk_per_trade_pct: asDraftNumber(bot?.risk_per_trade_pct, "0.5"),
    max_daily_loss_pct: asDraftNumber(bot?.max_daily_loss_pct, "3"),
    max_drawdown_pct: asDraftNumber(bot?.max_drawdown_pct, "15"),
    max_positions: asDraftNumber(bot?.max_positions, "10"),
  };
}

export function getBotDisplayName(bot: Pick<BotInstance, "display_name" | "name">): string {
  const displayName = String(bot.display_name || "").trim();
  if (displayName) return displayName;
  return String(bot.name || "").trim() || "Bot";
}
