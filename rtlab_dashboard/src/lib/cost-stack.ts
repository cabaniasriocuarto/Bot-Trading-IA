export type ReportingMetric = {
  gross_pnl: number;
  total_cost_estimated: number;
  total_cost_realized: number;
  net_pnl: number;
  trade_count: number;
  win_rate?: number | null;
  profit_factor?: number | null;
  expectancy?: number | null;
  max_drawdown?: number | null;
  policy_source?: string;
  freshness_status?: string;
};

export type ReportingSummary = Record<
  "today" | "week" | "month" | "ytd" | "all_time",
  ReportingMetric
>;

export type ReportingSeriesItem = {
  bucket: string;
  gross_pnl: number;
  total_cost_estimated: number;
  total_cost_realized: number;
  net_pnl: number;
  trade_count: number;
};

export type ReportingSeriesResponse = {
  items: ReportingSeriesItem[];
  count: number;
  policy_source?: string;
  freshness_status?: string;
};

export type ReportingCostsBreakdown = {
  exchange_fee_estimated?: number;
  exchange_fee_realized?: number;
  spread_estimated?: number;
  spread_realized?: number;
  slippage_estimated?: number;
  slippage_realized?: number;
  funding_realized?: number;
  borrow_interest_realized?: number;
  rebates_or_discounts?: number;
  gross_pnl?: number;
  net_pnl?: number;
  total_cost_estimated?: number;
  total_cost_realized?: number;
  total_cost_pct_of_gross_pnl?: number;
  alert_status?: "ok" | "warn" | "block" | string;
  policy_source?: string;
  freshness_status?: string;
  commission_components?: ReportingCommissionComponents;
};

export type ReportingCommissionComponent = {
  key?:
    | "standard_commission"
    | "tax_commission"
    | "special_commission"
    | string;
  label?: string;
  value?: number | null;
  asset?: string | null;
  rates?: Record<string, number>;
  source?: string;
  source_endpoint?: string;
  family?: string;
  environment?: string;
  symbol?: string | null;
  observed_at?: string | null;
  fetched_at?: string | null;
  freshness?: string;
  status?: string;
  provenance?: string;
  estimated_vs_realized?: string;
  detail?: string;
};

export type ReportingCommissionComponents = {
  contract_version?: string;
  source?: string;
  items?: ReportingCommissionComponent[];
};

export type ReportingTrade = {
  trade_cost_id?: string;
  trade_ref?: string;
  run_id?: string | null;
  venue?: string;
  family?: string;
  environment?: string;
  symbol?: string;
  strategy_id?: string | null;
  bot_id?: string | null;
  executed_at?: string;
  exchange_fee_estimated?: number;
  exchange_fee_realized?: number | null;
  fee_asset?: string | null;
  spread_estimated?: number;
  spread_realized?: number | null;
  slippage_estimated?: number;
  slippage_realized?: number | null;
  funding_estimated?: number;
  funding_realized?: number | null;
  borrow_interest_estimated?: number;
  borrow_interest_realized?: number | null;
  total_cost_estimated?: number;
  total_cost_realized?: number;
  gross_pnl?: number;
  net_pnl?: number;
  cost_source?: Record<string, unknown>;
  cost_source_json?: Record<string, unknown> | string;
  provenance?: Record<string, unknown>;
  provenance_json?: Record<string, unknown> | string;
};

export type ReportingTradesResponse = {
  items: ReportingTrade[];
  count: number;
  limit: number;
  offset: number;
  policy_source?: string;
};

export type ReportingExportManifest = {
  export_id?: string;
  export_type?: string;
  report_scope?: string;
  generated_at?: string;
  generated_by?: string;
  row_count?: number;
  artifact_path?: string;
  success?: boolean;
  error_message?: string | null;
};

export type ReportingExportsResponse = {
  items: ReportingExportManifest[];
  policy_source?: string;
};

export type ReportingState = {
  summary: ReportingSummary | null;
  daily: ReportingSeriesResponse | null;
  monthly: ReportingSeriesResponse | null;
  breakdown: ReportingCostsBreakdown | null;
  trades: ReportingTradesResponse | null;
  exports: ReportingExportsResponse | null;
};

export type ReportingComponentRow = {
  component: string;
  estimated: number | string | undefined;
  realized: number | string | undefined;
  source: string;
  status: string;
};

export type ReportingCoverageRow = {
  label: string;
  status: string;
  detail: string;
};

export function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export function sourceLabel(row: ReportingTrade): string {
  const source =
    row.cost_source_json ??
    row.cost_source ??
    row.provenance_json ??
    row.provenance;
  if (typeof source === "string") return source.slice(0, 42) || "-";
  if (source && typeof source === "object") {
    const kind =
      source.source_kind ??
      source.raw_source_type ??
      source.reconciliation_status;
    return kind ? String(kind) : "reporting_bridge";
  }
  return "reporting_bridge";
}

export function statusVariant(
  status: string,
): "success" | "warn" | "danger" | "info" | "neutral" {
  const normalized = status.toLowerCase();
  if (["ok", "fresh", "disponible", "pass"].includes(normalized))
    return "success";
  if (["parcial", "stale", "warn", "pendiente"].includes(normalized))
    return "warn";
  if (["block", "fail", "error"].includes(normalized)) return "danger";
  if (["unknown", "no aplica"].includes(normalized)) return "info";
  return "neutral";
}

export function hasRealizedEvidence(
  trades: ReportingTradesResponse | null,
  field: keyof ReportingTrade,
): boolean {
  return Boolean(trades?.items?.some((row) => row[field] != null));
}

export function realizedValue(
  breakdownValue: number | undefined,
  trades: ReportingTradesResponse | null,
  field: keyof ReportingTrade,
): number | "sin evidencia" | undefined {
  const hasEvidence = hasRealizedEvidence(trades, field);
  if (!hasEvidence && num(breakdownValue) === 0) return "sin evidencia";
  return breakdownValue;
}

export function realizedStatus(
  breakdownValue: number | undefined,
  trades: ReportingTradesResponse | null,
  field: keyof ReportingTrade,
): "PENDIENTE" | "DISPONIBLE" {
  return hasRealizedEvidence(trades, field) || num(breakdownValue) !== 0
    ? "DISPONIBLE"
    : "PENDIENTE";
}

export function commissionItems(
  breakdown: ReportingCostsBreakdown | null,
): ReportingCommissionComponent[] {
  return breakdown?.commission_components?.items ?? [];
}

export function commissionComponent(
  breakdown: ReportingCostsBreakdown | null,
  key: "standard_commission" | "tax_commission" | "special_commission",
): ReportingCommissionComponent | undefined {
  const items = commissionItems(breakdown).filter((item) => item.key === key);
  return (
    items.find(
      (item) =>
        item.status === "supported" &&
        (item.value != null || Object.keys(item.rates ?? {}).length > 0),
    ) ??
    items.find((item) => item.family === "spot") ??
    items[0]
  );
}

export function commissionStatusLabel(
  component?: ReportingCommissionComponent,
): string {
  const status = String(component?.status ?? "").toLowerCase();
  const hasRates = Object.keys(component?.rates ?? {}).length > 0;
  if (status === "supported" && hasRates) return "DISPONIBLE";
  if (status === "supported") return "SOPORTADO";
  if (status === "not_applicable") return "NO APLICA";
  if (status === "unsupported") return "NO SOPORTADO";
  if (status === "stale") return "PENDIENTE";
  return "PENDIENTE";
}

export function commissionRatesText(
  component?: ReportingCommissionComponent,
): string {
  const entries = Object.entries(component?.rates ?? {});
  if (entries.length)
    return entries.map(([role, value]) => `${role}: ${value}`).join(" / ");
  if (component?.value != null) return String(component.value);
  if (component?.status === "supported") return "soportado; valor pendiente";
  if (component?.status === "not_applicable") return "no aplica";
  if (component?.status === "unsupported") return "no soportado";
  return "pendiente";
}

export function commissionCoverageRows(
  breakdown: ReportingCostsBreakdown | null,
): ReportingCoverageRow[] {
  const byKey = (
    key: "standard_commission" | "tax_commission" | "special_commission",
    label: string,
  ) => {
    const items = commissionItems(breakdown).filter((item) => item.key === key);
    const selected = commissionComponent(breakdown, key);
    const families =
      Array.from(
        new Set(items.map((item) => item.family).filter(Boolean)),
      ).join(", ") || "sin familia";
    const status = commissionStatusLabel(selected);
    const detail =
      selected?.detail ?? "Contrato pendiente de snapshot backend.";
    const pendingSuffix =
      status === "SOPORTADO"
        ? " Valor pendiente hasta tener snapshot autenticado; no se inventa cero."
        : status === "NO SOPORTADO" || status === "NO APLICA"
          ? " Se mantiene como pendiente/no soportado para familias sin campo oficial."
          : "";
    return {
      label,
      status,
      detail: `${detail} Familias: ${families}.${pendingSuffix}`,
    };
  };

  return [
    byKey("standard_commission", "standardCommission"),
    byKey("tax_commission", "taxCommission"),
    byKey("special_commission", "specialCommission"),
    {
      label: "funding",
      status: "PARCIAL",
      detail:
        "Disponible en reporting/execution cuando aplica a futures o snapshots.",
    },
    {
      label: "borrow_interest",
      status: "PARCIAL",
      detail:
        "Disponible para margin cuando execution/reporting lo materializa.",
    },
    {
      label: "spread / slippage",
      status: "DISPONIBLE",
      detail: "Reporting distingue estimado y realizado si hay datos.",
    },
    {
      label: "gross_pnl / net_pnl",
      status: "DISPONIBLE",
      detail: "Visible en resumen, breakdown y ledger.",
    },
  ];
}

export function commissionBreakdownRow(
  breakdown: ReportingCostsBreakdown | null,
  key: "tax_commission" | "special_commission",
  component: string,
): ReportingComponentRow {
  const selected = commissionComponent(breakdown, key);
  return {
    component,
    estimated: commissionRatesText(selected),
    realized: "metadata de tasa; no fee realizado",
    source: selected?.source_endpoint || selected?.source || "Binance contract",
    status: commissionStatusLabel(selected),
  };
}

export function componentRows(
  breakdown: ReportingCostsBreakdown | null,
  trades: ReportingTradesResponse | null,
): ReportingComponentRow[] {
  return [
    {
      component: "Fees / commission",
      estimated: breakdown?.exchange_fee_estimated,
      realized: realizedValue(
        breakdown?.exchange_fee_realized,
        trades,
        "exchange_fee_realized",
      ),
      source: "trade_cost_ledger",
      status: realizedStatus(
        breakdown?.exchange_fee_realized,
        trades,
        "exchange_fee_realized",
      ),
    },
    {
      component: "Spread",
      estimated: breakdown?.spread_estimated,
      realized: realizedValue(
        breakdown?.spread_realized,
        trades,
        "spread_realized",
      ),
      source: "reporting bridge",
      status: realizedStatus(
        breakdown?.spread_realized,
        trades,
        "spread_realized",
      ),
    },
    {
      component: "Slippage",
      estimated: breakdown?.slippage_estimated,
      realized: realizedValue(
        breakdown?.slippage_realized,
        trades,
        "slippage_realized",
      ),
      source: "reporting bridge",
      status: realizedStatus(
        breakdown?.slippage_realized,
        trades,
        "slippage_realized",
      ),
    },
    {
      component: "Funding",
      estimated: "no expuesto",
      realized: realizedValue(
        breakdown?.funding_realized,
        trades,
        "funding_realized",
      ),
      source: "futures/reporting",
      status: realizedStatus(
        breakdown?.funding_realized,
        trades,
        "funding_realized",
      ),
    },
    {
      component: "Borrow interest",
      estimated: "no expuesto",
      realized: realizedValue(
        breakdown?.borrow_interest_realized,
        trades,
        "borrow_interest_realized",
      ),
      source: "margin/reporting",
      status: realizedStatus(
        breakdown?.borrow_interest_realized,
        trades,
        "borrow_interest_realized",
      ),
    },
    commissionBreakdownRow(breakdown, "tax_commission", "Tax commission"),
    commissionBreakdownRow(
      breakdown,
      "special_commission",
      "Special commission",
    ),
  ];
}
