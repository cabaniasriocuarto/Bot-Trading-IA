import { NextRequest, NextResponse } from "next/server";

import { resolveRole, SESSION_COOKIE, signSessionToken } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as { username?: string; password?: string };
  const username = (body.username || "").trim();
  const password = body.password || "";

  if (!username || !password) {
    return NextResponse.json({ error: "Usuario y contraseña son obligatorios." }, { status: 400 });
  }

  let role = null;
  try {
    role = resolveRole(username, password);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Configuración de autenticación inválida.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
  if (!role) {
    return NextResponse.json({ error: "Credenciales inválidas." }, { status: 401 });
  }

  let token = "";
  try {
    token = await signSessionToken({ username, role });
  } catch (error) {
    const message = error instanceof Error ? error.message : "No se pudo crear la sesión.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
  const res = NextResponse.json({ ok: true, user: { username, role } });
  res.cookies.set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return res;
}
