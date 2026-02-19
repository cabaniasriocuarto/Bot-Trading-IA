"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { sanitizeNextPath } from "@/lib/security";

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
      setError(body.error || "No se pudo iniciar sesión.");
      setLoading(false);
      return;
    }

    const next = sanitizeNextPath(search.get("next"));
    router.replace(next);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.2),transparent_35%),#020617] p-4">
      <Card className="w-full max-w-md fade-in-up">
        <CardTitle className="text-2xl">Ingreso RTLab Control</CardTitle>
        <CardDescription className="mt-1">Usá credenciales viewer/admin definidas en variables de entorno.</CardDescription>
        <CardContent>
          <form className="space-y-3" onSubmit={onSubmit}>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">Usuario</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin o viewer" required />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">Contraseña</label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="********" required />
            </div>
            {error ? <p className="text-sm text-rose-300">{error}</p> : null}
            <Button className="w-full" disabled={loading}>
              {loading ? "Ingresando..." : "Ingresar"}
            </Button>
          </form>
          <p className="mt-4 text-xs text-slate-500">Usá las credenciales configuradas.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function LoginFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.2),transparent_35%),#020617] p-4">
      <Card className="w-full max-w-md">
        <CardTitle className="text-2xl">Ingreso RTLab Control</CardTitle>
        <CardDescription className="mt-1">Cargando acceso...</CardDescription>
      </Card>
    </div>
  );
}
