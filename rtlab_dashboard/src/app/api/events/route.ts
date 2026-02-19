import { NextRequest, NextResponse } from "next/server";

import { getSessionFromRequest } from "@/lib/auth";
import { getMockStore } from "@/lib/mock-store";
import { shouldUseMockApi } from "@/lib/security";

export const dynamic = "force-dynamic";

async function proxyEvents(req: NextRequest, session: { role: "admin" | "viewer"; username: string }) {
  const backend = process.env.BACKEND_API_URL;
  if (!backend) {
    return NextResponse.json({ error: "BACKEND_API_URL is not set." }, { status: 500 });
  }
  const target = `${backend.replace(/\/$/, "")}/api/events${req.nextUrl.search}`;
  const headers = new Headers(req.headers);
  headers.set("Accept", "text/event-stream");
  headers.set("x-rtlab-role", session.role);
  headers.set("x-rtlab-user", session.username);
  headers.delete("host");
  headers.delete("content-length");

  const upstream = await fetch(target, {
    method: "GET",
    headers,
    cache: "no-store",
  });
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

function createMockEventStream(req: NextRequest) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const send = (event: string, payload: unknown) => {
        controller.enqueue(encoder.encode(`event: ${event}\n`));
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}\n\n`));
      };

      send("connected", { ts: new Date().toISOString(), mode: "mock" });

      const interval = setInterval(() => {
        const store = getMockStore();
        send("status", {
          ts: new Date().toISOString(),
          bot_status: store.status.bot_status,
          pnl_daily: store.status.pnl.daily,
          dd: store.status.max_dd.value,
        });

        if (Math.random() > 0.72 && store.alerts[0]) {
          send("alert", store.alerts[0]);
        }
      }, 3000);

      req.signal.addEventListener("abort", () => {
        clearInterval(interval);
        controller.close();
      });
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}

export async function GET(req: NextRequest) {
  const session = await getSessionFromRequest(req);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (shouldUseMockApi()) {
    return createMockEventStream(req);
  }
  return proxyEvents(req, session);
}
