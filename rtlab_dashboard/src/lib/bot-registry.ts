import { z } from "zod";

import type { BotInstance } from "@/lib/types";

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
});

export type BotRegistryDraft = z.input<typeof botRegistryFormSchema>;
export type BotRegistryFormData = z.output<typeof botRegistryFormSchema>;

export const DEFAULT_BOT_REGISTRY_DRAFT: BotRegistryDraft = {
  display_name: "",
  alias: "",
  description: "",
  domain_type: "spot",
};

export function normalizeBotRegistryDraft(draft: BotRegistryDraft): BotRegistryFormData {
  return botRegistryFormSchema.parse(draft);
}

export function buildBotRegistryDraft(bot?: Partial<BotInstance> | null): BotRegistryDraft {
  return {
    display_name: String(bot?.display_name || bot?.name || "").trim(),
    alias: String(bot?.alias || "").trim(),
    description: String(bot?.description || "").trim(),
    domain_type: bot?.domain_type === "futures" ? "futures" : "spot",
  };
}

export function getBotDisplayName(bot: Pick<BotInstance, "display_name" | "name">): string {
  const displayName = String(bot.display_name || "").trim();
  if (displayName) return displayName;
  return String(bot.name || "").trim() || "Bot";
}

