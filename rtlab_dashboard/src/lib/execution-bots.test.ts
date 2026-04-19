import { describe, expect, it } from "vitest";

import {
  botRegistryStatusVariant,
  botRuntimeStatusVariant,
  getExecutionBotLabel,
  isExecutionBotArchived,
  matchesExecutionBotStatusFilter,
} from "@/lib/execution-bots";

describe("execution-bots", () => {
  it("trata archived como estado de registry y no como runtime status", () => {
    const archivedBot = {
      status: "active",
      registry_status: "archived",
    } as const;
    const activeBot = {
      status: "active",
      registry_status: "active",
    } as const;

    expect(isExecutionBotArchived(archivedBot)).toBe(true);
    expect(matchesExecutionBotStatusFilter(archivedBot, "archived")).toBe(true);
    expect(matchesExecutionBotStatusFilter(archivedBot, "active")).toBe(false);
    expect(matchesExecutionBotStatusFilter(activeBot, "active")).toBe(true);
  });

  it("arma labels de selección con identidad canónica", () => {
    const label = getExecutionBotLabel({
      id: "BOT-000123",
      bot_id: "BOT-000123",
      display_name: "Bot Momentum Spot",
      name: "Legacy Name",
      mode: "paper",
      status: "active",
      registry_status: "active",
    });

    expect(label).toContain("Bot Momentum Spot");
    expect(label).toContain("BOT-000123");
    expect(label).toContain("runtime:active");
    expect(label).toContain("registry:active");
  });

  it("expone badges separados para runtime y registry", () => {
    expect(botRuntimeStatusVariant("active")).toBe("success");
    expect(botRuntimeStatusVariant("paused")).toBe("warn");
    expect(botRuntimeStatusVariant("unknown")).toBe("neutral");
    expect(botRegistryStatusVariant("active")).toBe("success");
    expect(botRegistryStatusVariant("archived")).toBe("neutral");
  });
});
