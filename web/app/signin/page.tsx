"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useSession } from "@/components/SessionProvider";
import { inputClass } from "@/components/ui";
import { ROLE_LABEL } from "@/lib/api";

export default function SignInPage() {
  const { user, signIn, signOut, ready } = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await signIn(email, password);
      setPassword("");
      router.push("/datasets");
    } catch (err) {
      setPassword("");
      setError((err as Error).message || "Email or password not recognised.");
    } finally {
      setBusy(false);
    }
  }

  if (ready && user) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-line bg-surface p-8 text-center">
        <h1 className="text-xl font-semibold text-ink">You are signed in</h1>
        <p className="mt-2 text-sm text-muted">{user.email} · {ROLE_LABEL[user.role]}</p>
        <div className="mt-5 flex justify-center gap-2">
          <Link href="/datasets" className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink">Datasets</Link>
          <button type="button" onClick={() => signOut()}
                  className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2">
            Sign out
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md pt-4 sm:pt-10">
      <div className="rounded-2xl border border-line bg-surface p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Sign in</h1>
        <p className="mt-1.5 text-sm text-muted">For shared datasets, the Data import page and administration. The
          built-in demo needs no account.</p>
        <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-ink-2">Email</label>
            <input id="email" type="email" autoComplete="username" required value={email}
                   onChange={(e) => setEmail(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-ink-2">Password</label>
            <input id="password" type="password" autoComplete="current-password" required value={password}
                   onChange={(e) => setPassword(e.target.value)} className={inputClass} />
          </div>
          {error && (
            <p role="alert" className="rounded-lg border border-[#fda4af] bg-[#fff1f2] px-3 py-2 text-sm text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy || !email || !password}
                  className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-5 text-xs leading-relaxed text-muted">Accounts are created by an Admin. There is no sign-up and
          no password-reset email: ask your Admin. After 5 wrong passwords, sign-in for that account pauses for 10 minutes.</p>
      </div>
    </div>
  );
}
