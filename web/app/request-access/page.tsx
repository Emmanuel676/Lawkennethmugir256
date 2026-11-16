"use client";

// Request access (Phase 14). Creates a PENDING account that an administrator approves or rejects. The answer is the
// same whether or not the email already has an account. No email is ever sent.
import { CheckCircle2, Info, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Card, PageHeader } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { sendJson } from "@/lib/api";
import { useApi } from "@/lib/useApi";

interface Options { user_types: { key: string; label: string }[]; password_min_length: number;
                    limits: { full_name: number; organisation: number; reason: number } }

const EMPTY = { full_name: "", email: "", organisation: "", user_type: "", reason: "", password: "", password_again: "", website: "" };

export default function RequestAccessPage() {
  const { data: options } = useApi<Options>("/api/access-requests/options");
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [done, setDone] = useState<string>();
  const min = options?.password_min_length ?? 10;
  const limits = options?.limits ?? { full_name: 100, organisation: 120, reason: 500 };
  const set = (key: keyof typeof EMPTY) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const body = await sendJson<{ message: string }>("POST", "/api/access-requests", form);
      setDone(body.message);
      setForm(EMPTY);
    } catch (err) {
      setError((err as Error).message);
      setForm((f) => ({ ...f, password: "", password_again: "" }));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="mx-auto max-w-xl pt-4">
        <Card>
          <div role="status" className="text-center">
            <CheckCircle2 className="mx-auto size-10 text-[var(--band-low)]" aria-hidden="true" />
            <h1 className="mt-4 text-xl font-semibold text-ink">Request received</h1>
            <p className="mt-2 text-[15px] leading-relaxed text-muted">{done}</p>
            <div className="mt-6 flex justify-center gap-2">
              <Button asChild><Link href="/overview">Explore the demo</Link></Button>
              <Button asChild variant="outline"><Link href="/signin">Sign in</Link></Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  const ready = form.full_name && form.email && form.organisation && form.user_type && form.reason &&
                form.password.length >= min && form.password === form.password_again;

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Request access"
                  intro="Accounts are for working with shared datasets. The demo itself is open to everyone without an account." />
      <div role="note" className="mb-6 flex gap-3 rounded-xl border border-line bg-surface-2 p-4 text-sm leading-relaxed text-ink-2">
        <Info className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
        <p>An administrator will see the details you give here. Your account stays <strong className="text-ink">inactive until it
          is approved</strong>. No email is sent at any point, so check back later and sign in once it is approved.</p>
      </div>
      <Card>
        <form onSubmit={submit} noValidate className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="full_name">Full name</Label>
              <Input id="full_name" autoComplete="name" maxLength={limits.full_name} value={form.full_name} onChange={(e) => set("full_name")(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" maxLength={200} value={form.email} onChange={(e) => set("email")(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="organisation">Organisation</Label>
              <Input id="organisation" autoComplete="organization" maxLength={limits.organisation} value={form.organisation} onChange={(e) => set("organisation")(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="user_type">Type of user</Label>
              <Select value={form.user_type} onValueChange={set("user_type")}>
                <SelectTrigger id="user_type" aria-required="true"><SelectValue placeholder="Choose one…" /></SelectTrigger>
                <SelectContent>
                  {(options?.user_types ?? []).map((t) => <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="reason">Reason for access</Label>
            <Textarea id="reason" maxLength={limits.reason} rows={3} value={form.reason} onChange={(e) => set("reason")(e.target.value)}
                      aria-describedby="reason-help" required />
            <p id="reason-help" className="text-xs text-muted">A sentence or two. {form.reason.length} of {limits.reason} characters.</p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="new-password" value={form.password} onChange={(e) => set("password")(e.target.value)}
                     aria-describedby="password-help" required />
              <p id="password-help" className="text-xs text-muted">At least {min} characters.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password_again">Password again</Label>
              <Input id="password_again" type="password" autoComplete="new-password" value={form.password_again}
                     onChange={(e) => set("password_again")(e.target.value)}
                     aria-invalid={form.password_again.length > 0 && form.password !== form.password_again} required />
              {form.password_again.length > 0 && form.password !== form.password_again && (
                <p className="text-xs text-[#9f1239] dark:text-[#fecdd3]">The two passwords are different.</p>
              )}
            </div>
          </div>
          {/* Honeypot: hidden from people and from assistive technology; simple bots fill it in. */}
          <div aria-hidden="true" className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden">
            <label htmlFor="website">Website</label>
            <input id="website" name="website" tabIndex={-1} autoComplete="off" value={form.website} onChange={(e) => set("website")(e.target.value)} />
          </div>
          {error && (
            <p role="alert" className="rounded-lg border border-[#fda4af] bg-[#fff1f2] px-3 py-2 text-sm text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]">{error}</p>
          )}
          <div className="flex flex-col-reverse items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted">Already approved? <Link href="/signin" className="font-medium text-accent hover:underline">Sign in</Link></p>
            <Button type="submit" disabled={busy || !ready}>
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />} Send request
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
