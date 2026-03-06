import type { Role } from "@/lib/types";

export type BackendAuthResult =
  | { ok: true; role: Role }
  | { ok: false; status: number; error: string }
  | null;

const BACKEND_LOGIN_PATH = "/api/v1/auth/login";

function readErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  const error = (payload as { error?: unknown }).error;
  if (typeof error === "string" && error.trim()) {
    return error.trim();
  }
  return fallback;
}

export async function resolveRoleViaBackend(
  username: string,
  password: string,
  env: NodeJS.ProcessEnv = process.env,
): Promise<BackendAuthResult> {
  const backend = (env.BACKEND_API_URL || "").trim();
  if (!backend) {
    return null;
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${backend.replace(/\/$/, "")}${BACKEND_LOGIN_PATH}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: 502, error: "Backend no disponible." };
  }

  let payload: unknown = null;
  try {
    payload = await upstream.json();
  } catch {
    payload = null;
  }

  if (!upstream.ok) {
    if (upstream.status === 401) {
      return {
        ok: false,
        status: 401,
        error: readErrorMessage(payload, "Credenciales invalidas."),
      };
    }
    if (upstream.status === 429) {
      return {
        ok: false,
        status: 429,
        error: readErrorMessage(payload, "Demasiados intentos de login."),
      };
    }
    return {
      ok: false,
      status: 502,
      error: readErrorMessage(payload, "Backend no disponible."),
    };
  }

  const role = (payload as { role?: unknown } | null)?.role;
  if (role === "admin" || role === "viewer") {
    return { ok: true, role };
  }
  return { ok: false, status: 502, error: "Respuesta de autenticacion invalida del backend." };
}
