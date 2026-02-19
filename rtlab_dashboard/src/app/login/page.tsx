"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginPageContent />
    </Suspense>
  );
}

function LoginPageContent() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const router = useRouter();
  const search = useSearchParams();

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      setError(body.error || "Login failed");
      setLoading(false);
      return;
    }

    const next = search.get("next") || "/";
    router.push(next);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.2),transparent_35%),#020617] p-4">
      <Card className="w-full max-w-md fade-in-up">
        <CardTitle className="text-2xl">RTLab Control Login</CardTitle>
        <CardDescription className="mt-1">Use viewer/admin credentials configured in environment variables.</CardDescription>
        <CardContent>
          <form className="space-y-3" onSubmit={onSubmit}>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">Username</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin or viewer" required />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">Password</label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="********" required />
            </div>
            {error ? <p className="text-sm text-rose-300">{error}</p> : null}
            <Button className="w-full" disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
            </Button>
          </form>
          <p className="mt-4 text-xs text-slate-500">
            Default fallback users: <code>admin/admin123!</code> and <code>viewer/viewer123!</code>.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function LoginFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.2),transparent_35%),#020617] p-4">
      <Card className="w-full max-w-md">
        <CardTitle className="text-2xl">RTLab Control Login</CardTitle>
        <CardDescription className="mt-1">Loading login...</CardDescription>
      </Card>
    </div>
  );
}

