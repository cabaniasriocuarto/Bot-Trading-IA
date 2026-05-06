"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardTitle,
} from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiGet } from "@/lib/client-api";
import {
  commissionCoverageRows,
  componentRows,
  num,
  sourceLabel,
  statusVariant,
  type ReportingCostsBreakdown,
  type ReportingExportsResponse,
  type ReportingSeriesItem,
  type ReportingSeriesResponse,
  type ReportingState,
  type ReportingSummary,
  type ReportingTradesResponse,
} from "@/lib/cost-stack";

const emptyState: ReportingState = {
  summary: null,
  daily: null,
  monthly: null,
  breakdown: null,
  trades: null,
  exports: null,
};

function fmtUsd(value: unknown): string {
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(num(value));
}

function fmtPct(value: unknown): string {
  return `${num(value).toFixed(2)}%`;
}

function fmtDate(value: unknown): string {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("es-AR");
}

function valueCell(value: unknown): string {
  return typeof value === "number" ? fmtUsd(value) : String(value ?? "-");
}

export default function ReportingPage() {
  const [state, setState] = useState<ReportingState>(emptyState);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string>("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [summary, daily, monthly, breakdown, trades, exports] =
        await Promise.all([
          apiGet<ReportingSummary>("/api/v1/reporting/performance/summary"),
          apiGet<ReportingSeriesResponse>(
            "/api/v1/reporting/performance/daily",
          ),
          apiGet<ReportingSeriesResponse>(
            "/api/v1/reporting/performance/monthly",
          ),
          apiGet<ReportingCostsBreakdown>("/api/v1/reporting/costs/breakdown"),
          apiGet<ReportingTradesResponse>("/api/v1/reporting/trades?limit=50"),
          apiGet<ReportingExportsResponse>(
            "/api/v1/reporting/exports?limit=20",
          ),
        ]);
      setState({ summary, daily, monthly, breakdown, trades, exports });
      setUpdatedAt(new Date().toISOString());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No se pudo cargar Cost Stack / Reporting.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const allTime = state.summary?.all_time;
  const breakdown = state.breakdown;
  const components = useMemo(
    () => componentRows(breakdown, state.trades),
    [breakdown, state.trades],
  );
  const coverageRows = useMemo(
    () => commissionCoverageRows(breakdown),
    [breakdown],
  );
  const recentDaily = state.daily?.items?.slice(-5).reverse() ?? [];
  const recentMonthly = state.monthly?.items?.slice(-4).reverse() ?? [];

  return (
    <div className="space-y-5">
      <section className="rounded-3xl border border-cyan-400/30 bg-[linear-gradient(135deg,rgba(8,47,73,0.72),rgba(15,23,42,0.88)),radial-gradient(circle_at_top_right,rgba(250,204,21,0.16),transparent_36%)] p-6 shadow-2xl shadow-cyan-950/30">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge variant="info">Read-only</Badge>
              <Badge variant="neutral">Fuente: /api/v1/reporting/*</Badge>
              <Badge
                variant={statusVariant(
                  breakdown?.freshness_status || "unknown",
                )}
              >
                freshness: {breakdown?.freshness_status || "unknown"}
              </Badge>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-cyan-200">
                Cost Stack / Reporting
              </p>
              <h1 className="mt-2 text-3xl font-black tracking-tight text-white md:text-4xl">
                Costos Binance visibles, sin tocar ejecucion
              </h1>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                Consolida el reporting ya disponible para gross/net PnL, fees,
                spread, slippage, funding, borrow interest, ledger de trades y
                manifiesto de exports. Esta pantalla no ejecuta ordenes, no
                consulta Binance privado y no modifica datos.
              </p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 text-right text-xs text-slate-300">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load()}
              disabled={loading}
            >
              {loading ? "Actualizando..." : "Actualizar"}
            </Button>
            <span>Ultima lectura: {updatedAt ? fmtDate(updatedAt) : "-"}</span>
            <span>Periodo backend: all_time + daily/monthly</span>
          </div>
        </div>
        {error ? (
          <p className="mt-4 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </p>
        ) : null}
      </section>

      <section className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="Gross PnL" value={fmtUsd(allTime?.gross_pnl)} />
        <Metric
          label="Net PnL"
          value={fmtUsd(allTime?.net_pnl)}
          accent={num(allTime?.net_pnl) >= 0 ? "good" : "bad"}
        />
        <Metric
          label="Costos estimados"
          value={fmtUsd(allTime?.total_cost_estimated)}
        />
        <Metric
          label="Costos realizados"
          value={fmtUsd(allTime?.total_cost_realized)}
        />
        <Metric label="Trades" value={String(allTime?.trade_count ?? 0)} />
        <Metric
          label="% costo / gross"
          value={fmtPct(breakdown?.total_cost_pct_of_gross_pnl)}
        />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <Card>
          <CardTitle>Breakdown de costos</CardTitle>
          <CardDescription>
            Estimado vs realizado por componente. Los campos sin contrato
            aparecen como pendientes, no como cero inventado.
          </CardDescription>
          <CardContent className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Componente</TH>
                  <TH>Estimado</TH>
                  <TH>Realizado</TH>
                  <TH>Diferencia</TH>
                  <TH>Fuente</TH>
                  <TH>Estado</TH>
                </TR>
              </THead>
              <TBody>
                {components.map((row) => {
                  const diff =
                    typeof row.estimated === "number" &&
                    typeof row.realized === "number"
                      ? row.realized - row.estimated
                      : null;
                  return (
                    <TR key={row.component}>
                      <TD className="font-semibold">{row.component}</TD>
                      <TD>{valueCell(row.estimated)}</TD>
                      <TD>{valueCell(row.realized)}</TD>
                      <TD>{diff == null ? "-" : fmtUsd(diff)}</TD>
                      <TD className="text-slate-400">{row.source}</TD>
                      <TD>
                        <Badge variant={statusVariant(row.status)}>
                          {row.status}
                        </Badge>
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Cobertura Binance</CardTitle>
          <CardDescription>
            Estado honesto del contrato disponible hoy en main.
          </CardDescription>
          <CardContent className="space-y-3">
            {coverageRows.map((row) => (
              <div
                key={row.label}
                className="rounded-xl border border-slate-800 bg-slate-900/50 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-100">
                    {row.label}
                  </span>
                  <Badge variant={statusVariant(row.status)}>
                    {row.status}
                  </Badge>
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-400">
                  {row.detail}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardTitle>Series recientes</CardTitle>
          <CardDescription>
            Lectura read-only de performance diaria y mensual.
          </CardDescription>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <SeriesBlock title="Diario" rows={recentDaily} />
            <SeriesBlock title="Mensual" rows={recentMonthly} />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Exports</CardTitle>
          <CardDescription>
            Manifiesto disponible por backend. La descarga directa queda
            pendiente hasta tener contrato seguro de artifact.
          </CardDescription>
          <CardContent className="space-y-2">
            {state.exports?.items?.length ? (
              state.exports.items.map((row) => (
                <div
                  key={row.export_id || row.artifact_path}
                  className="rounded-xl border border-slate-800 bg-slate-900/50 p-3 text-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">
                      {row.export_id || "export"}
                    </span>
                    <Badge
                      variant={row.success === false ? "danger" : "success"}
                    >
                      {row.export_type || "archivo"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {fmtDate(row.generated_at)} · filas {row.row_count ?? 0} ·
                    scope {row.report_scope || "-"}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {row.artifact_path || "artifact path no expuesto"}
                  </p>
                </div>
              ))
            ) : (
              <EmptyNote
                title="Sin exports generados"
                text="El backend de XLSX/PDF existe, pero todavia no hay manifiestos para listar o descargar desde UI."
              />
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardTitle>Ledger de trades reportados</CardTitle>
        <CardDescription>
          Hasta 50 filas desde `/api/v1/reporting/trades`. No usa bulk actions
          ni mutaciones.
        </CardDescription>
        <CardContent className="overflow-x-auto">
          {state.trades?.items?.length ? (
            <Table>
              <THead>
                <TR>
                  <TH>Fecha</TH>
                  <TH>Simbolo</TH>
                  <TH>Familia</TH>
                  <TH>Strategy / Bot</TH>
                  <TH>Gross</TH>
                  <TH>Net</TH>
                  <TH>Fees</TH>
                  <TH>Spread</TH>
                  <TH>Slippage</TH>
                  <TH>Funding</TH>
                  <TH>Borrow</TH>
                  <TH>Fuente</TH>
                </TR>
              </THead>
              <TBody>
                {state.trades.items.map((row) => (
                  <TR
                    key={
                      row.trade_cost_id ||
                      row.trade_ref ||
                      `${row.symbol}-${row.executed_at}`
                    }
                  >
                    <TD>{fmtDate(row.executed_at)}</TD>
                    <TD className="font-semibold">{row.symbol || "-"}</TD>
                    <TD>{row.family || "-"}</TD>
                    <TD>{row.strategy_id || row.bot_id || "-"}</TD>
                    <TD>{fmtUsd(row.gross_pnl)}</TD>
                    <TD
                      className={
                        num(row.net_pnl) >= 0
                          ? "text-emerald-300"
                          : "text-rose-300"
                      }
                    >
                      {fmtUsd(row.net_pnl)}
                    </TD>
                    <TD>
                      {fmtUsd(
                        row.exchange_fee_realized ?? row.exchange_fee_estimated,
                      )}
                    </TD>
                    <TD>
                      {fmtUsd(row.spread_realized ?? row.spread_estimated)}
                    </TD>
                    <TD>
                      {fmtUsd(row.slippage_realized ?? row.slippage_estimated)}
                    </TD>
                    <TD>
                      {fmtUsd(row.funding_realized ?? row.funding_estimated)}
                    </TD>
                    <TD>
                      {fmtUsd(
                        row.borrow_interest_realized ??
                          row.borrow_interest_estimated,
                      )}
                    </TD>
                    <TD className="max-w-[180px] truncate text-slate-400">
                      {sourceLabel(row)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          ) : (
            <EmptyNote
              title="Sin ledger de reporting"
              text="Cuando Paper/Testnet/Live o backtests materialicen filas, se veran aca gross/net PnL y costos por componente."
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "good" | "bad";
}) {
  const tone =
    accent === "good"
      ? "text-emerald-300"
      : accent === "bad"
        ? "text-rose-300"
        : "text-white";
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-black ${tone}`}>{value}</p>
    </Card>
  );
}

function SeriesBlock({
  title,
  rows,
}: {
  title: string;
  rows: ReportingSeriesItem[];
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
      <p className="text-xs uppercase tracking-wide text-slate-400">{title}</p>
      <div className="mt-3 space-y-2">
        {rows.length ? (
          rows.map((row) => (
            <div
              key={`${title}-${row.bucket}`}
              className="flex items-center justify-between gap-3 text-sm"
            >
              <span className="text-slate-300">{row.bucket}</span>
              <span
                className={
                  num(row.net_pnl) >= 0 ? "text-emerald-300" : "text-rose-300"
                }
              >
                {fmtUsd(row.net_pnl)} · {row.trade_count} trades
              </span>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500">Sin serie disponible.</p>
        )}
      </div>
    </div>
  );
}

function EmptyNote({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/30 p-4">
      <p className="font-semibold text-slate-100">{title}</p>
      <p className="mt-1 text-sm text-slate-400">{text}</p>
    </div>
  );
}
