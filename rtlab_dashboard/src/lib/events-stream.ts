import { NextRequest, NextResponse } from "next/server";

import { getMockStore, pushAlert, pushLog, rotateExecutionSeries, saveMockStore } from "@/lib/mock-store";
import { shouldUseMockApi } from "@/lib/security";

interface SessionInfo {
  role: "admin" | "viewer";
  username: string;
}

type EventSeverity = "debug" | "info" | "warn" | "error";

interface RtlabEvent {
  type:
    | "trade_open"
    | "trade_close"
    | "breaker_triggered"
    | "api_error"
    | "health"
    | "fill"
    | "order_update"
    | "strategy_changed"
    | "backtest_finished";
  ts: string;
  severity: EventSeverity;
  module: string;
  data: Record<string, unknown>;
}

function toSseEvent(event: RtlabEvent) {
  return {
    ...event,
  };
}

async function proxyEventStream(req: NextRequest, session: SessionInfo, upstreamPath: string) {
  const backend = (process.env.BACKEND_API_URL || "").trim();
  if (!backend) {
    return NextResponse.json({ error: "BACKEND_API_URL no esta configurado." }, { status: 500 });
  }
  const target = `${backend.replace(/\/$/, "")}${upstreamPath}${req.nextUrl.search}`;
  const headers = new Headers(req.headers);
  const internalProxyToken = (process.env.INTERNAL_PROXY_TOKEN || "").trim();
  if (!internalProxyToken) {
    return NextResponse.json(
      { error: "INTERNAL_PROXY_TOKEN no está configurado en el BFF." },
      { status: 500 },
    );
  }
  headers.set("Accept", "text/event-stream");
  headers.set("x-rtlab-role", session.role);
  headers.set("x-rtlab-user", session.username);
  headers.delete("x-rtlab-proxy-token");
  headers.set("x-rtlab-proxy-token", internalProxyToken);
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
      const send = (payload: RtlabEvent) => {
        const normalized = toSseEvent(payload);
        controller.enqueue(encoder.encode(`event: ${normalized.type}\n`));
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(normalized)}\n\n`));
      };

      const connected: RtlabEvent = {
        type: "health",
        ts: new Date().toISOString(),
        severity: "info",
        module: "stream",
        data: { connected: true, mode: "MOCK", transport: "sse" },
      };
      send(connected);

      const interval = setInterval(() => {
        const store = getMockStore();
        rotateExecutionSeries();
        store.health.ws.connected = true;
        store.health.ws.last_event_at = new Date().toISOString();
        store.status.updated_at = new Date().toISOString();
        saveMockStore();

        const statusEvent: RtlabEvent = {
          type: "health",
          ts: new Date().toISOString(),
          severity: "info",
          module: "health",
          data: {
            state: store.status.bot_status,
            daily_pnl: store.status.pnl.daily,
            dd: store.status.max_dd.value,
            ws_connected: true,
          },
        };
        send(statusEvent);
        pushLog({
          type: statusEvent.type,
          severity: statusEvent.severity,
          module: statusEvent.module,
          message: "Heartbeat de estado emitido.",
          related_ids: [],
          payload: statusEvent.data,
        });

        const random = Math.random();
        if (random > 0.68) {
          const breaker: RtlabEvent = {
            type: "breaker_triggered",
            ts: new Date().toISOString(),
            severity: "warn",
            module: "risk",
            data: {
              reason: "spread_guard",
              spread_bps: Number((7 + Math.random() * 3).toFixed(2)),
              threshold_bps: 10,
            },
          };
          send(breaker);
          pushAlert({
            type: breaker.type,
            severity: "warn",
            module: breaker.module,
            message: "Alerta de spread en zona preventiva.",
            data: breaker.data,
          });
          pushLog({
            type: breaker.type,
            severity: breaker.severity,
            module: breaker.module,
            message: "Breaker preventivo registrado.",
            related_ids: [],
            payload: breaker.data,
          });
        } else if (random > 0.36) {
          const fill: RtlabEvent = {
            type: "fill",
            ts: new Date().toISOString(),
            severity: "info",
            module: "execution",
            data: {
              symbol: "BTC/USDT",
              side: random > 0.5 ? "long" : "short",
              qty: 0.12,
              price: 102000 + Math.floor(Math.random() * 800),
            },
          };
          send(fill);
          pushLog({
            type: fill.type,
            severity: fill.severity,
            module: fill.module,
            message: "Fill recibido en stream.",
            related_ids: [],
            payload: fill.data,
          });
        } else {
          const apiError: RtlabEvent = {
            type: "api_error",
            ts: new Date().toISOString(),
            severity: "error",
            module: "exchange",
            data: {
              endpoint: "/fapi/v1/depth",
              status: 429,
              retry_in_ms: 500,
            },
          };
          send(apiError);
          pushAlert({
            type: apiError.type,
            severity: "error",
            module: apiError.module,
            message: "Rate limit detectado en endpoint de orderbook.",
            data: apiError.data,
          });
          pushLog({
            type: apiError.type,
            severity: apiError.severity,
            module: apiError.module,
            message: "Error de API emitido por stream.",
            related_ids: [],
            payload: apiError.data,
          });
        }
      }, 3500);

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

export async function createEventsResponse(
  req: NextRequest,
  session: SessionInfo,
  options: { upstreamPath: string },
) {
  if (shouldUseMockApi()) {
    return createMockEventStream(req);
  }

  try {
    return await proxyEventStream(req, session, options.upstreamPath);
  } catch {
    if (process.env.ENABLE_MOCK_FALLBACK_ON_BACKEND_ERROR === "true") {
      return createMockEventStream(req);
    }
    return NextResponse.json({ error: "No se pudo conectar al stream del backend." }, { status: 502 });
  }
}
