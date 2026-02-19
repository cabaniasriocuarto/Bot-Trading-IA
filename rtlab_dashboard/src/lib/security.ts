export function isProductionEnv(env: NodeJS.ProcessEnv = process.env) {
  return env.NODE_ENV === "production";
}

export function shouldUseMockApi(env: NodeJS.ProcessEnv = process.env) {
  const explicit = env.USE_MOCK_API;
  if (explicit === "true") return true;
  if (explicit === "false") return false;

  return !env.BACKEND_API_URL;
}

export function sanitizeNextPath(candidate: string | null | undefined, fallback = "/") {
  if (!candidate) return fallback;
  const value = candidate.trim();
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\n") || value.includes("\r")) {
    return fallback;
  }

  try {
    const parsed = new URL(value, "http://localhost");
    if (parsed.origin !== "http://localhost") return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}
