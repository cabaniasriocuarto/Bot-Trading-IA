import { z } from "zod";

import type {
  BotInstance,
  BotRegistryContractResponse,
  BotRegistryDomainType,
  BotRiskProfile,
} from "@/lib/types";

export type BotRegistryDraft = {
  display_name: string;
  alias: string;
  description: string;
  domain_type: BotRegistryDomainType;
  universe_name: string;
  universe: string[];
  pool_strategy_ids: string[];
  max_live_symbols: string | number;
  capital_base_usd: string | number;
  max_total_exposure_pct: string | number;
  max_asset_exposure_pct: string | number;
  risk_profile: BotRiskProfile;
  risk_per_trade_pct: string | number;
  max_daily_loss_pct: string | number;
  max_drawdown_pct: string | number;
  max_positions: string | number;
};

export type BotRegistryFormData = {
  display_name: string;
  alias: string;
  description: string;
  domain_type: BotRegistryDomainType;
  universe_name: string;
  universe: string[];
  pool_strategy_ids: string[];
  max_live_symbols: number;
  capital_base_usd: number;
  max_total_exposure_pct: number;
  max_asset_exposure_pct: number;
  risk_profile: BotRiskProfile;
  risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  max_positions: number;
};

export const EMPTY_BOT_REGISTRY_DRAFT: BotRegistryDraft = {
  display_name: "",
  alias: "",
  description: "",
  domain_type: "spot",
  universe_name: "",
  universe: [],
  pool_strategy_ids: [],
  max_live_symbols: "1",
  capital_base_usd: "",
  max_total_exposure_pct: "",
  max_asset_exposure_pct: "",
  risk_profile: "medium",
  risk_per_trade_pct: "",
  max_daily_loss_pct: "",
  max_drawdown_pct: "",
  max_positions: "",
};

function asDraftNumber(value: unknown, fallback: number): string {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return String(fallback);
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

function asDomainType(value: unknown, contract: BotRegistryContractResponse): BotRegistryDomainType {
  const normalized = String(value || "").trim().toLowerCase();
  if (contract.enums.domain_types.includes(normalized as BotRegistryDomainType)) {
    return normalized as BotRegistryDomainType;
  }
  return contract.defaults.domain_type;
}

function asRiskProfile(value: unknown, contract: BotRegistryContractResponse): BotRiskProfile {
  const normalized = String(value || "").trim().toLowerCase();
  if (contract.enums.risk_profiles.includes(normalized as BotRiskProfile)) {
    return normalized as BotRiskProfile;
  }
  return contract.defaults.risk_profile;
}

function buildBotRegistryFormSchema(contract: BotRegistryContractResponse) {
  const domainTypes = new Set(contract.enums.domain_types);
  const riskProfiles = new Set(contract.enums.risk_profiles);
  const limits = contract.limits;
  return z.object({
    display_name: z
      .string()
      .trim()
      .min(limits.display_name_min_length, `El nombre visible debe tener al menos ${limits.display_name_min_length} caracteres.`)
      .max(limits.display_name_max_length, `El nombre visible no puede superar ${limits.display_name_max_length} caracteres.`),
    alias: z
      .string()
      .trim()
      .max(limits.alias_max_length, `El alias no puede superar ${limits.alias_max_length} caracteres.`)
      .transform((value) => value || ""),
    description: z
      .string()
      .trim()
      .max(limits.description_max_length, `La descripción no puede superar ${limits.description_max_length} caracteres.`)
      .transform((value) => value || ""),
    domain_type: z
      .string()
      .trim()
      .transform((value) => value.toLowerCase())
      .refine((value): value is BotRegistryDomainType => domainTypes.has(value as BotRegistryDomainType), {
        message: `domain_type debe ser ${contract.enums.domain_types.map((item) => `'${item}'`).join(" o ")}`,
      }),
    universe_name: z
      .string()
      .trim()
      .min(1, "El universo válido es requerido."),
    universe: z
      .array(z.string().trim().min(1, "Cada símbolo asignado debe ser válido."))
      .min(limits.universe_min_size, `Debes asignar al menos ${limits.universe_min_size} símbolo válido.`),
    pool_strategy_ids: z
      .array(z.string().trim().min(1, "Cada estrategia del pool debe ser válida."))
      .min(limits.pool_strategy_ids_min_size, `Debes asignar al menos ${limits.pool_strategy_ids_min_size} estrategia válida al pool.`)
      .max(limits.max_pool_strategies, `El pool no puede superar ${limits.max_pool_strategies} estrategias.`),
    max_live_symbols: z.coerce
      .number()
      .int()
      .gte(limits.max_live_symbols_min, `El cap live debe ser >= ${limits.max_live_symbols_min}.`)
      .lte(limits.max_live_symbols, `El cap live no puede superar ${limits.max_live_symbols}.`),
    capital_base_usd: z.coerce
      .number()
      .gt(limits.capital_base_usd_min, `El capital base debe ser > ${limits.capital_base_usd_min}.`),
    max_total_exposure_pct: z.coerce
      .number()
      .gt(limits.percentage_min, "La exposición total debe ser > 0.")
      .lte(limits.percentage_max, `La exposición total no puede superar ${limits.percentage_max}%.`),
    max_asset_exposure_pct: z.coerce
      .number()
      .gt(limits.percentage_min, "La exposición por activo debe ser > 0.")
      .lte(limits.percentage_max, `La exposición por activo no puede superar ${limits.percentage_max}%.`),
    risk_profile: z
      .string()
      .trim()
      .transform((value) => value.toLowerCase())
      .refine((value): value is BotRiskProfile => riskProfiles.has(value as BotRiskProfile), {
        message: `risk_profile debe ser ${contract.enums.risk_profiles.map((item) => `'${item}'`).join(" o ")}`,
      }),
    risk_per_trade_pct: z.coerce
      .number()
      .gt(limits.percentage_min, "El riesgo por trade debe ser > 0.")
      .lte(limits.percentage_max, `El riesgo por trade no puede superar ${limits.percentage_max}%.`),
    max_daily_loss_pct: z.coerce
      .number()
      .gt(limits.percentage_min, "La pérdida diaria máxima debe ser > 0.")
      .lte(limits.percentage_max, `La pérdida diaria máxima no puede superar ${limits.percentage_max}%.`),
    max_drawdown_pct: z.coerce
      .number()
      .gt(limits.percentage_min, "El drawdown máximo debe ser > 0.")
      .lte(limits.percentage_max, `El drawdown máximo no puede superar ${limits.percentage_max}%.`),
    max_positions: z.coerce
      .number()
      .int()
      .gte(limits.max_positions_min, `Las posiciones máximas deben ser >= ${limits.max_positions_min}.`),
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
}

export function buildDefaultBotRegistryDraft(contract: BotRegistryContractResponse): BotRegistryDraft {
  return {
    display_name: String(contract.defaults.display_name || "").trim(),
    alias: String(contract.defaults.alias || "").trim(),
    description: String(contract.defaults.description || "").trim(),
    domain_type: contract.defaults.domain_type,
    universe_name: String(contract.defaults.universe_name || "").trim(),
    universe: asDraftUniverse(contract.defaults.universe),
    pool_strategy_ids: asDraftStrategyPool(contract.defaults.pool_strategy_ids),
    max_live_symbols: asDraftNumber(contract.defaults.max_live_symbols, contract.defaults.max_live_symbols),
    capital_base_usd: asDraftNumber(contract.defaults.capital_base_usd, contract.defaults.capital_base_usd),
    max_total_exposure_pct: asDraftNumber(contract.defaults.max_total_exposure_pct, contract.defaults.max_total_exposure_pct),
    max_asset_exposure_pct: asDraftNumber(contract.defaults.max_asset_exposure_pct, contract.defaults.max_asset_exposure_pct),
    risk_profile: contract.defaults.risk_profile,
    risk_per_trade_pct: asDraftNumber(contract.defaults.risk_per_trade_pct, contract.defaults.risk_per_trade_pct),
    max_daily_loss_pct: asDraftNumber(contract.defaults.max_daily_loss_pct, contract.defaults.max_daily_loss_pct),
    max_drawdown_pct: asDraftNumber(contract.defaults.max_drawdown_pct, contract.defaults.max_drawdown_pct),
    max_positions: asDraftNumber(contract.defaults.max_positions, contract.defaults.max_positions),
  };
}

export function normalizeBotRegistryDraft(
  draft: BotRegistryDraft,
  contract: BotRegistryContractResponse,
): BotRegistryFormData {
  const normalizedDraft = {
    ...draft,
    domain_type: String(draft.domain_type || "").trim().toLowerCase(),
    risk_profile: String(draft.risk_profile || "").trim().toLowerCase(),
    universe_name: String(draft.universe_name || "").trim(),
    universe: asDraftUniverse(draft.universe),
    pool_strategy_ids: asDraftStrategyPool(draft.pool_strategy_ids),
  };
  return buildBotRegistryFormSchema(contract).parse(normalizedDraft) as BotRegistryFormData;
}

export function buildBotRegistryDraft(
  bot: Partial<BotInstance> | null | undefined,
  contract: BotRegistryContractResponse,
): BotRegistryDraft {
  const assignedUniverse = asDraftUniverse(bot?.universe);
  const defaults = contract.defaults;
  return {
    display_name: String(bot?.display_name || bot?.name || "").trim(),
    alias: String(bot?.alias || "").trim(),
    description: String(bot?.description || "").trim(),
    domain_type: asDomainType(bot?.domain_type, contract),
    universe_name: String(bot?.universe_name || "").trim(),
    universe: assignedUniverse,
    pool_strategy_ids: asDraftStrategyPool(bot?.pool_strategy_ids),
    max_live_symbols: asDraftNumber(
      bot?.max_live_symbols,
      assignedUniverse.length ? Math.min(assignedUniverse.length, contract.limits.max_live_symbols) : defaults.max_live_symbols,
    ),
    capital_base_usd: asDraftNumber(bot?.capital_base_usd, defaults.capital_base_usd),
    max_total_exposure_pct: asDraftNumber(bot?.max_total_exposure_pct, defaults.max_total_exposure_pct),
    max_asset_exposure_pct: asDraftNumber(bot?.max_asset_exposure_pct, defaults.max_asset_exposure_pct),
    risk_profile: asRiskProfile(bot?.risk_profile, contract),
    risk_per_trade_pct: asDraftNumber(bot?.risk_per_trade_pct, defaults.risk_per_trade_pct),
    max_daily_loss_pct: asDraftNumber(bot?.max_daily_loss_pct, defaults.max_daily_loss_pct),
    max_drawdown_pct: asDraftNumber(bot?.max_drawdown_pct, defaults.max_drawdown_pct),
    max_positions: asDraftNumber(bot?.max_positions, defaults.max_positions),
  };
}

export function getBotRegistryContractMaxPoolStrategies(contract: BotRegistryContractResponse): number {
  return Number(contract.limits.max_pool_strategies || 0);
}

export function getBotRegistryContractMaxLiveSymbols(contract: BotRegistryContractResponse): number {
  return Number(contract.limits.max_live_symbols || 0);
}

export function getBotDisplayName(bot: Pick<BotInstance, "display_name" | "name">): string {
  const displayName = String(bot.display_name || "").trim();
  if (displayName) return displayName;
  return String(bot.name || "").trim() || "Bot";
}
