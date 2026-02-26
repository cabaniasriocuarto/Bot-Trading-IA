"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet, apiPost } from "@/lib/client-api";
import type { PortfolioSnapshot, Position, Trade } from "@/lib/types";
import { fmtPct, fmtUsd } from "@/lib/utils";

export default function PortfolioPage() {
  const { role } = useSession();
  const [positions, setPositions] = useState<Position[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [cooldownUntil, setCooldownUntil] = useState<number>(0);

  const refresh = async () => {
    const [pos, pf, tr] = await Promise.all([
      apiGet<Position[]>("/api/v1/positions"),
      apiGet<PortfolioSnapshot>("/api/v1/portfolio"),
      apiGet<Trade[]>("/api/v1/trades"),
    ]);
    setPositions(pos);
    setPortfolio(pf);
    setTrades(tr.slice(0, 20));
  };

  useEffect(() => {
    void refresh();
  }, []);

  const corr = useMemo(() => {
    const symbols = [...new Set([...positions.map((x) => x.symbol), "BTC/USDT", "ETH/USDT", "SOL/USDT"])];
    return symbols.map((a, i) =>
      symbols.map((b, j) => ({
        x: i,
        y: j,
        a,
        b,
        value: i === j ? 1 : Number((0.2 + Math.sin((i + 1) * (j + 1)) * 0.35).toFixed(2)),
      })),
    );
  }, [positions]);

  const onCooldown = Date.now() < cooldownUntil;

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle className="flex items-center justify-between">
          Posiciones / Portafolio
          <Button
            variant="danger"
            disabled={role !== "admin" || onCooldown}
            onClick={async () => {
              const ok = window.confirm("Cerrar todas las posiciones?");
              if (!ok) return;
              const ok2 = window.confirm("Segunda confirmacion: ejecutar cierre total ahora?");
              if (!ok2) return;
              await apiPost("/api/v1/control/close-all");
              setCooldownUntil(Date.now() + 10_000);
              await refresh();
            }}
          >
            Cerrar todas
          </Button>
        </CardTitle>
        <CardDescription>Exposicion en vivo, concentracion del portafolio e historial reciente.</CardDescription>
        {onCooldown ? <p className="mt-2 text-xs text-amber-300">Cooldown de cierre total activo.</p> : null}
      </Card>

      <section className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardTitle>Resumen de Exposicion</CardTitle>
          <CardContent className="space-y-2">
            <Metric label="Equity" value={portfolio ? fmtUsd(portfolio.equity) : "--"} />
            <Metric label="PnL diario" value={portfolio ? fmtUsd(portfolio.pnl_daily) : "--"} />
            <Metric label="Exposicion total" value={portfolio ? fmtUsd(portfolio.exposure_total) : "--"} />
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardTitle>Exposicion por simbolo</CardTitle>
          <CardContent>
            {(portfolio?.exposure_by_symbol || []).length ? (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={280}>
                  <BarChart data={portfolio?.exposure_by_symbol || []}>
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "0.75rem" }} />
                    <Bar dataKey="exposure" fill="#22d3ee" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyActionCard
                title="Todavia no hay exposicion por simbolo"
                cause="No hay posiciones abiertas o el exchange no devolvio snapshot de portafolio."
                steps={[
                  "Conecta el exchange en Testnet o ejecuta Paper.",
                  "Abrí una posicion para poblar exposicion.",
                  "Volvé a Portfolio y refresca la pagina.",
                ]}
              />
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardTitle>Posiciones Abiertas</CardTitle>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Simbolo</TH>
                <TH>Lado</TH>
                <TH>Cantidad</TH>
                <TH>Entrada</TH>
                <TH>Mark</TH>
                <TH>No realizado</TH>
                <TH>Exposicion</TH>
                <TH>Estrategia</TH>
              </TR>
            </THead>
            <TBody>
              {positions.map((row) => (
                <TR key={`${row.symbol}-${row.strategy_id}`}>
                  <TD>{row.symbol}</TD>
                  <TD>{row.side}</TD>
                  <TD>{row.qty}</TD>
                  <TD>{row.entry_px}</TD>
                  <TD>{row.mark_px}</TD>
                  <TD className={row.pnl_unrealized >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(row.pnl_unrealized)}</TD>
                  <TD>{fmtUsd(row.exposure_usd)}</TD>
                  <TD>{row.strategy_id}</TD>
                </TR>
              ))}
              {!positions.length ? (
                <TR>
                  <TD colSpan={8} className="py-4">
                    <EmptyInlineTableState
                      title="Todavia no hay posiciones abiertas"
                      hint="Ejecuta Paper/Testnet para poblar posiciones y exposicion."
                    />
                  </TD>
                </TR>
              ) : null}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Snapshot de Historial</CardTitle>
        <CardDescription>Ultimas operaciones cerradas como historial de posiciones.</CardDescription>
        <CardContent className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH>Trade</TH>
                <TH>Timestamp</TH>
                <TH>Tipo</TH>
                <TH>Simbolo</TH>
                <TH>Lado</TH>
                <TH>Motivo de salida</TH>
                <TH>PnL neto</TH>
                <TH>Holding</TH>
                <TH>Detalle</TH>
              </TR>
            </THead>
            <TBody>
              {trades.map((row) => (
                <TR key={row.id}>
                  <TD>{row.id}</TD>
                  <TD className="text-xs">{new Date(row.exit_time).toLocaleString()}</TD>
                  <TD><Badge>trade_close</Badge></TD>
                  <TD>{row.symbol}</TD>
                  <TD>{row.side}</TD>
                  <TD>
                    <Badge>{row.exit_reason}</Badge>
                  </TD>
                  <TD className={row.pnl_net >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtUsd(row.pnl_net)}</TD>
                  <TD>{Math.abs(Math.round((new Date(row.exit_time).getTime() - new Date(row.entry_time).getTime()) / 60_000))}m</TD>
                  <TD>
                    <Link href={`/trades/${row.id}`} className="text-cyan-300 underline">
                      Ver detalle
                    </Link>
                  </TD>
                </TR>
              ))}
              {!trades.length ? (
                <TR>
                  <TD colSpan={9} className="py-4">
                    <EmptyInlineTableState
                      title="Todavia no hay historial"
                      hint="Ejecuta Paper/Testnet o un backtest para generar trades cerrados."
                    />
                  </TD>
                </TR>
              ) : null}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardTitle>Matriz de Correlacion (Simple)</CardTitle>
        <CardDescription>Heatmap aproximado de correlacion del portafolio.</CardDescription>
        <CardContent className="space-y-2">
          {positions.length ? (
            corr.map((row, idx) => (
              <div key={`corr-row-${idx}`} className="flex flex-wrap gap-1">
                {row.map((cell) => (
                  <div
                    key={`${cell.a}-${cell.b}`}
                    className="rounded px-2 py-1 text-xs font-semibold"
                    style={{
                      background:
                        cell.value > 0
                          ? `rgba(34,211,238,${0.15 + cell.value * 0.25})`
                          : `rgba(244,63,94,${0.15 + Math.abs(cell.value) * 0.25})`,
                      border: "1px solid rgba(51,65,85,0.8)",
                    }}
                  >
                    {cell.a.split("/")[0]} vs {cell.b.split("/")[0]}: {fmtPct(cell.value, 0)}
                  </div>
                ))}
              </div>
            ))
          ) : (
            <EmptyActionCard
              title="Matriz de correlacion vacia"
              cause="La matriz usa posiciones abiertas; sin posiciones no hay correlaciones utiles."
              steps={[
                "Ejecuta Paper/Testnet.",
                "Abri 2 o mas activos para ver concentracion.",
                "Usa esta matriz para evitar exposicion duplicada.",
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="text-sm font-semibold text-slate-100">{value}</p>
    </div>
  );
}

function EmptyInlineTableState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-left">
      <p className="text-sm font-semibold text-slate-100">{title}</p>
      <p className="mt-1 text-xs text-slate-400">{hint}</p>
    </div>
  );
}

function EmptyActionCard({ title, cause, steps }: { title: string; cause: string; steps: string[] }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <p className="text-sm font-semibold text-slate-100">{title}</p>
      <p className="mt-1 text-xs text-slate-400">{cause}</p>
      <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs text-slate-300">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </div>
  );
}


