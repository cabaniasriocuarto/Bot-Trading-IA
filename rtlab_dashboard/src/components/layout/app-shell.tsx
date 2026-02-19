"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  CandlestickChart,
  Cog,
  LayoutDashboard,
  LineChart,
  LogOut,
  Shield,
  SplitSquareVertical,
  Wallet,
} from "lucide-react";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/strategies", label: "Strategies", icon: SplitSquareVertical },
  { href: "/backtests", label: "Backtests", icon: LineChart },
  { href: "/trades", label: "Trades", icon: CandlestickChart },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/risk", label: "Risk", icon: Shield },
  { href: "/execution", label: "Execution", icon: Activity },
  { href: "/alerts", label: "Alerts & Logs", icon: AlertTriangle },
  { href: "/settings", label: "Settings", icon: Cog },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useSession();

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.2),_transparent_34%),radial-gradient(circle_at_bottom_right,_rgba(251,191,36,0.12),_transparent_40%),#020617] text-slate-100">
      <div className="mx-auto flex max-w-[1500px] gap-6 px-4 py-4 md:px-6">
        <aside className="hidden w-64 shrink-0 rounded-2xl border border-slate-800 bg-slate-950/60 p-4 lg:block">
          <div className="mb-6 space-y-1">
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-300">RTLab</p>
            <h1 className="text-xl font-bold tracking-tight">Strategy Console</h1>
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                    active ? "bg-cyan-500/20 text-cyan-300" : "text-slate-300 hover:bg-slate-800",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-3">
            <div className="flex items-center gap-2">
              <Badge variant="info">Live Dashboard</Badge>
              {user?.role === "admin" ? <Badge variant="warn">admin</Badge> : <Badge>viewer</Badge>}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-400">{user?.username || "unknown"}</span>
              <Button variant="outline" size="sm" onClick={logout}>
                <LogOut className="mr-1 h-4 w-4" />
                Logout
              </Button>
            </div>
          </header>

          <div className="mb-4 flex gap-2 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/50 p-2 lg:hidden">
            {navItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "whitespace-nowrap rounded-lg px-3 py-2 text-sm",
                    active ? "bg-cyan-500/20 text-cyan-300" : "text-slate-300 hover:bg-slate-800",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>

          <main>{children}</main>
        </div>
      </div>
    </div>
  );
}

