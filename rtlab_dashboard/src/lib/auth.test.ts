import { describe, expect, it } from "vitest";

import {
  DEFAULT_ADMIN_PASSWORD,
  DEFAULT_ADMIN_USERNAME,
  DEFAULT_AUTH_SECRET,
  DEFAULT_VIEWER_PASSWORD,
  DEFAULT_VIEWER_USERNAME,
  getAuthConfig,
  resolveRole,
} from "@/lib/auth";

function buildProdEnv(overrides: Partial<NodeJS.ProcessEnv> = {}): NodeJS.ProcessEnv {
  return {
    NODE_ENV: "production",
    AUTH_SECRET: "this-is-a-very-strong-secret-key-1234567890",
    ADMIN_USERNAME: "admin_prod",
    ADMIN_PASSWORD: "super_secure_admin_password",
    VIEWER_USERNAME: "viewer_prod",
    VIEWER_PASSWORD: "super_secure_viewer_password",
    ...overrides,
  } as NodeJS.ProcessEnv;
}

describe("getAuthConfig", () => {
  it("uses defaults in non-production", () => {
    const config = getAuthConfig({ NODE_ENV: "development" } as NodeJS.ProcessEnv);
    expect(config.secret).toBe(DEFAULT_AUTH_SECRET);
    expect(config.adminUser).toBe(DEFAULT_ADMIN_USERNAME);
    expect(config.adminPass).toBe(DEFAULT_ADMIN_PASSWORD);
    expect(config.viewerUser).toBe(DEFAULT_VIEWER_USERNAME);
    expect(config.viewerPass).toBe(DEFAULT_VIEWER_PASSWORD);
  });

  it("throws in production when AUTH_SECRET is default or weak", () => {
    expect(() => getAuthConfig(buildProdEnv({ AUTH_SECRET: DEFAULT_AUTH_SECRET }))).toThrow(
      "Invalid AUTH_SECRET in production",
    );
    expect(() => getAuthConfig(buildProdEnv({ AUTH_SECRET: "short-secret" }))).toThrow(
      "Invalid AUTH_SECRET in production",
    );
  });

  it("throws in production when default credentials are used", () => {
    expect(() =>
      getAuthConfig(
        buildProdEnv({
          ADMIN_USERNAME: DEFAULT_ADMIN_USERNAME,
          ADMIN_PASSWORD: DEFAULT_ADMIN_PASSWORD,
        }),
      ),
    ).toThrow("Default credentials are not allowed in production.");

    expect(() =>
      getAuthConfig(
        buildProdEnv({
          VIEWER_USERNAME: DEFAULT_VIEWER_USERNAME,
          VIEWER_PASSWORD: DEFAULT_VIEWER_PASSWORD,
        }),
      ),
    ).toThrow("Default credentials are not allowed in production.");
  });
});

describe("resolveRole", () => {
  it("resolves configured admin/viewer credentials", () => {
    const env = buildProdEnv();
    expect(resolveRole("admin_prod", "super_secure_admin_password", env)).toBe("admin");
    expect(resolveRole("viewer_prod", "super_secure_viewer_password", env)).toBe("viewer");
  });

  it("returns null for invalid credentials", () => {
    const env = buildProdEnv();
    expect(resolveRole("admin_prod", "wrong", env)).toBeNull();
    expect(resolveRole("unknown", "whatever", env)).toBeNull();
  });
});
