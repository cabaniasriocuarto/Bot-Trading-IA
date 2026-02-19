import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, verifySessionToken } from "@/lib/auth";
import { sanitizeNextPath } from "@/lib/security";

const PUBLIC_PATHS = ["/login", "/api/auth/login", "/api/auth/logout"];

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

function isAsset(pathname: string) {
  return pathname.startsWith("/_next") || pathname === "/favicon.ico";
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (isAsset(pathname) || isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (token) {
    const session = await verifySessionToken(token);
    if (session) return NextResponse.next();
  }

  if (pathname.startsWith("/api")) {
    const res = NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    if (token) {
      res.cookies.set({
        name: SESSION_COOKIE,
        value: "",
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: 0,
      });
    }
    return res;
  }

  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("next", sanitizeNextPath(`${pathname}${req.nextUrl.search}`));
  const redirect = NextResponse.redirect(loginUrl);
  if (token) {
    redirect.cookies.set({
      name: SESSION_COOKIE,
      value: "",
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 0,
    });
  }
  return redirect;
}

export const config = {
  matcher: ["/((?!.*\\..*|_next).*)"],
};
