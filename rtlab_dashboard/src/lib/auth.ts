import { SignJWT, jwtVerify } from "jose";
import { NextRequest } from "next/server";

import type { Role, SessionUser } from "@/lib/types";
import { isProductionEnv } from "@/lib/security";

export const SESSION_COOKIE = "rtlab_session";
export const DEFAULT_AUTH_SECRET = "change-this-in-production";
export const DEFAULT_ADMIN_USERNAME = "admin";
export const DEFAULT_ADMIN_PASSWORD = "admin123!";
export const DEFAULT_VIEWER_USERNAME = "viewer";
export const DEFAULT_VIEWER_PASSWORD = "viewer123!";

interface SessionToken extends SessionUser {
  exp: number;
}

export interface AuthConfig {
  secret: string;
  adminUser: string;
  adminPass: string;
  viewerUser: string;
  viewerPass: string;
}

const encoder = new TextEncoder();

function assertProductionConfig(config: AuthConfig) {
  if (config.secret === DEFAULT_AUTH_SECRET || config.secret.length < 32) {
    throw new Error("Invalid AUTH_SECRET in production. Use a strong random secret with at least 32 characters.");
  }

  if (!config.adminUser || !config.adminPass || !config.viewerUser || !config.viewerPass) {
    throw new Error("Missing auth credentials in production.");
  }

  if (
    (config.adminUser === DEFAULT_ADMIN_USERNAME && config.adminPass === DEFAULT_ADMIN_PASSWORD) ||
    (config.viewerUser === DEFAULT_VIEWER_USERNAME && config.viewerPass === DEFAULT_VIEWER_PASSWORD)
  ) {
    throw new Error("Default credentials are not allowed in production.");
  }
}

export function getAuthConfig(env: NodeJS.ProcessEnv = process.env): AuthConfig {
  const config: AuthConfig = {
    secret: env.AUTH_SECRET || DEFAULT_AUTH_SECRET,
    adminUser: env.ADMIN_USERNAME || DEFAULT_ADMIN_USERNAME,
    adminPass: env.ADMIN_PASSWORD || DEFAULT_ADMIN_PASSWORD,
    viewerUser: env.VIEWER_USERNAME || DEFAULT_VIEWER_USERNAME,
    viewerPass: env.VIEWER_PASSWORD || DEFAULT_VIEWER_PASSWORD,
  };

  if (isProductionEnv(env)) {
    assertProductionConfig(config);
  }

  return config;
}

function secretKey(env: NodeJS.ProcessEnv = process.env) {
  const secret = getAuthConfig(env).secret;
  return encoder.encode(secret);
}

export async function signSessionToken(user: SessionUser) {
  return new SignJWT({ username: user.username, role: user.role })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("12h")
    .sign(secretKey());
}

export async function verifySessionToken(token: string): Promise<SessionToken | null> {
  try {
    const { payload } = await jwtVerify(token, secretKey());
    if (payload.username && payload.role && payload.exp) {
      return {
        username: String(payload.username),
        role: payload.role as Role,
        exp: Number(payload.exp),
      };
    }
    return null;
  } catch {
    return null;
  }
}

export async function getSessionFromRequest(req: NextRequest): Promise<SessionToken | null> {
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  return verifySessionToken(token);
}

export function resolveRole(username: string, password: string, env: NodeJS.ProcessEnv = process.env): Role | null {
  const config = getAuthConfig(env);
  const adminUser = config.adminUser;
  const adminPass = config.adminPass;
  const viewerUser = config.viewerUser;
  const viewerPass = config.viewerPass;

  if (username === adminUser && password === adminPass) return "admin";
  if (username === viewerUser && password === viewerPass) return "viewer";
  return null;
}
