import { NextRequest, NextResponse } from "next/server";

import { getSessionFromRequest } from "@/lib/auth";
import { handleMockApi } from "@/lib/mock-api";
import { shouldUseMockApi } from "@/lib/security";

export const dynamic = "force-dynamic";

async function proxyToBackend(
  req: NextRequest,
  path: string[],
  session: { role: "admin" | "viewer"; username: string },
) {
  const backend = process.env.BACKEND_API_URL;
  if (!backend) {
    return NextResponse.json({ error: "BACKEND_API_URL no está configurado." }, { status: 500 });
  }

  const target = `${backend.replace(/\/$/, "")}/api/${path.join("/")}${req.nextUrl.search}`;
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer();

  const headers = new Headers(req.headers);
  headers.set("x-rtlab-role", session.role);
  headers.set("x-rtlab-user", session.username);
  headers.delete("host");
  headers.delete("content-length");

  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body,
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);
  const buffer = await upstream.arrayBuffer();
  return new NextResponse(buffer, { status: upstream.status, headers: responseHeaders });
}

async function handle(req: NextRequest, path: string[]) {
  const session = await getSessionFromRequest(req);
  if (!session) {
    return NextResponse.json({ error: "No autorizado" }, { status: 401 });
  }

  if (shouldUseMockApi()) {
    return handleMockApi(req, path, session.role);
  }

  try {
    return await proxyToBackend(req, path, session);
  } catch {
    if (process.env.ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR !== "false") {
      return handleMockApi(req, path, session.role);
    }
    return NextResponse.json({ error: "Backend no disponible." }, { status: 502 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return handle(req, path);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return handle(req, path);
}

export async function PUT(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return handle(req, path);
}
