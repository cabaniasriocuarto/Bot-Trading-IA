import * as React from "react";

import { cn } from "@/lib/utils";

const variants = {
  neutral: "bg-slate-800 text-slate-200 border border-slate-700",
  success: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40",
  warn: "bg-amber-500/20 text-amber-300 border border-amber-500/40",
  danger: "bg-rose-500/20 text-rose-300 border border-rose-500/40",
  info: "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40",
};

export function Badge({
  className,
  variant = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: keyof typeof variants }) {
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold", variants[variant], className)}
      {...props}
    />
  );
}

