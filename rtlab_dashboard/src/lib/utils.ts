import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtPct(value: number, decimals = 2) {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function fmtUsd(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function fmtNum(value: number, decimals = 2) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function toCsv<T extends object>(rows: T[]) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0] as Record<string, unknown>);
  const body = rows.map((row) =>
    headers
      .map((key) => {
        const val = (row as Record<string, unknown>)[key];
        const raw = val === null || val === undefined ? "" : String(val);
        return `"${raw.replaceAll('"', '""')}"`;
      })
      .join(","),
  );
  return [headers.join(","), ...body].join("\n");
}
