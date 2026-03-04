import { describe, expect, it } from "vitest";

import { sanitizeNextPath, shouldFallbackToMockOnBackendError, shouldUseMockApi } from "@/lib/security";

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

  it("does not auto-enable mock in production when backend is missing", () => {
    expect(
      shouldUseMockApi({
        NODE_ENV: "production",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
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

describe("shouldFallbackToMockOnBackendError", () => {
  it("blocks fallback in protected environments", () => {
    expect(
      shouldFallbackToMockOnBackendError({
        NODE_ENV: "production",
        ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR: "true",
        USE_MOCK_API: "true",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
    expect(
      shouldFallbackToMockOnBackendError({
        NODE_ENV: "development",
        APP_ENV: "staging",
        ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR: "true",
        USE_MOCK_API: "true",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
  });

  it("respects explicit disable of mock API", () => {
    expect(
      shouldFallbackToMockOnBackendError({
        NODE_ENV: "development",
        ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR: "true",
        USE_MOCK_API: "false",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
  });

  it("allows fallback only in non-protected environments when explicitly enabled", () => {
    expect(
      shouldFallbackToMockOnBackendError({
        NODE_ENV: "development",
        APP_ENV: "local",
        ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR: "true",
      } as NodeJS.ProcessEnv),
    ).toBe(true);
    expect(
      shouldFallbackToMockOnBackendError({
        NODE_ENV: "development",
        APP_ENV: "local",
        ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR: "false",
      } as NodeJS.ProcessEnv),
    ).toBe(false);
  });
});
