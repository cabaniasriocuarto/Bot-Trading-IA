import { SignJWT, jwtVerify } from "jose";
import { NextRequest } from "next/server";

import type { Role, SessionUser } from "@/lib/types";

export const SESSION_COOKIE = "rtlab_session";

interface SessionToken extends SessionUser {
  exp: number;
}

const encoder = new TextEncoder();

function secretKey() {
  const secret = process.env.AUTH_SECRET || "change-this-in-production";
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

export function resolveRole(username: string, password: string): Role | null {
  const adminUser = process.env.ADMIN_USERNAME || "admin";
  const adminPass = process.env.ADMIN_PASSWORD || "admin123!";
  const viewerUser = process.env.VIEWER_USERNAME || "viewer";
  const viewerPass = process.env.VIEWER_PASSWORD || "viewer123!";

  if (username === adminUser && password === adminPass) return "admin";
  if (username === viewerUser && password === viewerPass) return "viewer";
  return null;
}

