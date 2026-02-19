import { describe, expect, it } from "vitest";

import { sanitizeNextPath, shouldUseMockApi } from "@/lib/security";

describe("sanitizeNextPath", () => {
  it("returns fallback when path is missing", () => {
    expect(sanitizeNextPath(undefined)).toBe("/");
    expect(sanitizeNextPath(null, "/dashboard")).toBe("/dashboard");
  });

  it("accepts internal absolute path with query and hash", () => {
    expect(sanitizeNextPath("/overview?tab=pnl#top")).toBe("/overview?tab=pnl#top");
  });

  it("rejects external or malformed values", () => {
    expect(sanitizeNextPath("https://evil.com")).toBe("/");
    expect(sanitizeNextPath("//evil.com/path")).toBe("/");
    expect(sanitizeNextPath("/safe\n/set-cookie")).toBe("/");
    expect(sanitizeNextPath("javascript:alert(1)")).toBe("/");
  });
});

describe("shouldUseMockApi", () => {
  it("respects explicit flag", () => {
    expect(
      shouldUseMockApi({
        NODE_ENV: "production",
        USE_MOCK_API: "true",
        BACKEND_API_URL: "https://api.example.com",
      } as NodeJS.ProcessEnv),
    ).toBe(true);
    expect(
      shouldUseMockApi({
        NODE_ENV: "development",
        USE_MOCK_API: "false",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
  });

  it("auto-enables mock when backend is missing (including production)", () => {
    expect(
      shouldUseMockApi({
        NODE_ENV: "production",
      } as NodeJS.ProcessEnv),
    ).toBe(true);
    expect(
      shouldUseMockApi({
        NODE_ENV: "production",
        BACKEND_API_URL: "https://api.example.com",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
  });

  it("uses mock by default whenever backend is missing", () => {
    expect(
      shouldUseMockApi({
        NODE_ENV: "development",
      } as NodeJS.ProcessEnv),
    ).toBe(true);
    expect(
      shouldUseMockApi({
        NODE_ENV: "development",
        BACKEND_API_URL: "https://api.example.com",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
  });
});
