import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveRoleViaBackend } from "@/lib/auth-backend";

const ORIGINAL_FETCH = global.fetch;

function buildTestEnv(overrides: Partial<NodeJS.ProcessEnv> = {}): NodeJS.ProcessEnv {
  return {
    NODE_ENV: "test",
    BACKEND_API_URL: "https://api.example.com",
    ...overrides,
  } as NodeJS.ProcessEnv;
}

describe("resolveRoleViaBackend", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    global.fetch = ORIGINAL_FETCH;
  });

  it("returns null when BACKEND_API_URL is not configured", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    const res = await resolveRoleViaBackend(
      "Wadmin",
      "secret",
      buildTestEnv({ BACKEND_API_URL: undefined }),
    );
    expect(res).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("uses backend role when backend login succeeds", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ token: "abc", role: "admin" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    const res = await resolveRoleViaBackend("Wadmin", "secret", buildTestEnv());

    expect(res).toEqual({ ok: true, role: "admin" });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(
      "https://api.example.com/api/v1/auth/login",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("maps invalid credentials from backend as 401", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid credentials" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    const res = await resolveRoleViaBackend("Wadmin", "wrong", buildTestEnv());

    expect(res).toEqual({ ok: false, status: 401, error: "Invalid credentials" });
  });

  it("fails closed when backend returns an unknown role", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ token: "abc", role: "operator" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    const res = await resolveRoleViaBackend("Wadmin", "secret", buildTestEnv());

    expect(res).toEqual({
      ok: false,
      status: 502,
      error: "Respuesta de autenticacion invalida del backend.",
    });
  });

  it("returns 502 when backend is unreachable", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network")) as typeof fetch;

    const res = await resolveRoleViaBackend("Wadmin", "secret", buildTestEnv());

    expect(res).toEqual({ ok: false, status: 502, error: "Backend no disponible." });
  });
});
