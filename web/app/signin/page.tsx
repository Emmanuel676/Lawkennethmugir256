"use client";

import { Clock, Loader2, LogIn } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { SHADOW } from "@/components/kit";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/form";
import { ApiError, ROLE_LABEL } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function SignInPage() {
  const { user, signIn, signOut, ready } = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    setPending(false);
    try {
      await signIn(email, password);
      setPassword("");
      router.push("/datasets");
    } catch (err) {
      setPassword("");
      setPending(err instanceof ApiError && err.status === 403);
      setError((err as Error).message || "Email or password not recognised.");
    } finally {
      setBusy(false);
    }
  }

  if (ready && user) {
    return (
      <div className={cn("mx-auto max-w-md rounded-2xl border border-line bg-surface p-8 text-center", SHADOW)}>
        <h1 className="text-xl font-semibold text-ink">You are signed in</h1>
        <p className="mt-2 text-sm text-muted">{user.email} · {ROLE_LABEL[user.role]}</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button asChild><Link href="/datasets">Datasets</Link></Button>
          <Button variant="outline" onClick={() => signOut()}>Sign out</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md pt-2 sm:pt-8">
      <div className={cn("rounded-2xl border border-line bg-surface p-6 sm:p-8", SHADOW)}>
        <h1 className="text-[26px] font-semibold tracking-tight text-ink">Sign in</h1>
        <p className="mt-1.5 text-sm text-muted">For shared datasets, the Data import page and administration. The demo needs no account.</p>
        <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="current-password" required value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && (
            <p role="alert" className={cn("flex gap-2 rounded-lg border px-3 py-2 text-sm",
              pending ? "border-amber/50 bg-tint-amber text-[#7c2d12] dark:bg-[#3a2410] dark:text-[#fde6c4]"
                      : "border-[#fda4af] bg-[#fff1f2] text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]")}>
              {pending && <Clock className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
              <span>{error}</span>
            </p>
          )}
          <Button type="submit" className="w-full" disabled={busy || !email || !password}>
            {busy ? <Loader2 className="animate-spin" aria-hidden="true" /> : <LogIn aria-hidden="true" />}
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-5 text-sm text-muted">No account yet? <Link href="/request-access" className="font-medium text-accent hover:underline">Request access</Link>.
          An administrator approves every account; no email is sent.</p>
        <p className="mt-3 text-xs leading-relaxed text-muted">After 5 wrong passwords, sign-in for that account pauses for 10 minutes. Forgot your password? Ask your administrator.</p>
      </div>
    </div>
  );
}
