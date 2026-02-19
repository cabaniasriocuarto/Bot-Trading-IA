"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiGet, apiPost } from "@/lib/client-api";

interface SettingsResponse {
  active_profile: "PAPER" | "TESTNET" | "LIVE";
  feature_flags: Record<string, boolean>;
  exchange_default: string;
}

export default function SettingsPage() {
  const { role } = useSession();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [liveCooldownUntil, setLiveCooldownUntil] = useState(0);

  useEffect(() => {
    const load = async () => {
      const data = await apiGet<SettingsResponse>("/api/settings");
      setSettings(data);
    };
    void load();
  }, []);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await apiPost("/api/settings", {
        active_profile: settings.active_profile,
        feature_flags: settings.feature_flags,
      });
    } finally {
      setSaving(false);
    }
  };

  if (!settings) return <p className="text-sm text-slate-400">Loading settings...</p>;
  const liveOnCooldown = Date.now() < liveCooldownUntil;

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Settings (Admin)</CardTitle>
        <CardDescription>Profiles, exchange preferences, feature flags and secret placeholders.</CardDescription>
      </Card>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Profile Management</CardTitle>
          <CardDescription>PAPER / TESTNET / LIVE with safety lock before LIVE.</CardDescription>
          <CardContent className="space-y-3">
            <Select
              value={settings.active_profile}
              onChange={(e) => {
                const next = e.target.value as SettingsResponse["active_profile"];
                if (next === "LIVE") {
                  if (liveOnCooldown) {
                    window.alert("LIVE action is in cooldown. Wait a few seconds and retry.");
                    return;
                  }
                  const ok = window.confirm("Enable LIVE profile? This is a critical action.");
                  if (!ok) return;
                  const ok2 = window.confirm("Second confirmation: switch to LIVE now?");
                  if (!ok2) return;
                  setLiveCooldownUntil(Date.now() + 10_000);
                }
                setSettings((prev) => (prev ? { ...prev, active_profile: next } : prev));
              }}
              disabled={role !== "admin"}
            >
              <option value="PAPER">PAPER</option>
              <option value="TESTNET">TESTNET</option>
              <option value="LIVE">LIVE</option>
            </Select>
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300">
              Active profile:{" "}
              <Badge variant={settings.active_profile === "LIVE" ? "danger" : settings.active_profile === "TESTNET" ? "warn" : "success"}>
                {settings.active_profile}
              </Badge>
            </div>
            {liveOnCooldown ? <p className="text-xs text-amber-300">Critical action cooldown active for LIVE profile controls.</p> : null}
            <Button disabled={role !== "admin" || saving || liveOnCooldown} onClick={save}>
              {saving ? "Saving..." : "Save Profile"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Exchange Config</CardTitle>
          <CardDescription>Binance default + Bybit plugin selection by config.</CardDescription>
          <CardContent className="space-y-3">
            <Select defaultValue={settings.exchange_default} disabled={role !== "admin"}>
              <option value="binance">Binance (default)</option>
              <option value="bybit">Bybit plugin</option>
              <option value="okx">OKX plugin</option>
            </Select>
            <p className="text-sm text-slate-400">
              Exchange API keys never appear in this UI. Credentials are managed only in backend secret manager / env vars.
            </p>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>Credential Placeholders</CardTitle>
          <CardDescription>UI accepts placeholders only. No real secrets are shown or persisted here.</CardDescription>
          <CardContent className="space-y-2">
            <Input placeholder="EXCHANGE_KEY (placeholder only)" disabled />
            <Input placeholder="EXCHANGE_SECRET (placeholder only)" disabled />
            <Input placeholder="TELEGRAM_BOT_TOKEN (placeholder only)" disabled />
            <Input placeholder="TELEGRAM_CHAT_ID (placeholder only)" disabled />
          </CardContent>
        </Card>

        <Card>
          <CardTitle>Feature Flags</CardTitle>
          <CardDescription>Enable/disable optional modules.</CardDescription>
          <CardContent className="space-y-2">
            {Object.entries(settings.feature_flags).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
                <span className="text-sm text-slate-200">{key}</span>
                <button
                  disabled={role !== "admin"}
                  onClick={() =>
                    setSettings((prev) =>
                      prev
                        ? {
                            ...prev,
                            feature_flags: { ...prev.feature_flags, [key]: !prev.feature_flags[key] },
                          }
                        : prev,
                    )
                  }
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    value ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-700 text-slate-300"
                  }`}
                >
                  {value ? "ON" : "OFF"}
                </button>
              </div>
            ))}
            <Button disabled={role !== "admin" || saving} onClick={save}>
              Save Feature Flags
            </Button>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
