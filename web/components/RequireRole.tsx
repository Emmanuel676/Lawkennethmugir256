"use client";

import { Ban, Lock } from "lucide-react";

import Link from "next/link";
import type { ReactNode } from "react";

import { ROLE_LABEL, type Role } from "@/lib/api";

import { useSession } from "./SessionProvider";
import { LoadingBlock } from "./kit";

/** Shows its children only to a signed-in user with at least `role`; otherwise a friendly explanation. */
export function RequireRole({ role, what, children }: { role: Role; what: string; children: ReactNode }) {
  const { ready, user, can } = useSession();
  if (!ready) return <LoadingBlock rows={4} label="Checking your sign-in" />;
  if (!user) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border border-line bg-surface p-8 text-center">
        <Lock className="mx-auto size-9 text-muted" aria-hidden="true" strokeWidth={1.6} />
        <h2 className="mt-3 text-lg font-semibold text-ink">Sign in to {what}</h2>
        <p className="mt-1 text-sm text-muted">The built-in demo is open to everyone. Shared datasets and tools need an
          account, which an Admin creates for you.</p>
        <Link href="/signin" className="mt-5 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-ink">
          Sign in
        </Link>
      </div>
    );
  }
  if (!can(role)) {
    return (
      <div role="alert" className="mx-auto max-w-lg rounded-2xl border border-line bg-surface p-8 text-center">
        <Ban className="mx-auto size-9 text-muted" aria-hidden="true" strokeWidth={1.6} />
        <h2 className="mt-3 text-lg font-semibold text-ink">You do not have permission to {what}</h2>
        <p className="mt-1 text-sm text-muted">This needs the {ROLE_LABEL[role]} role or above. You are signed in as a{" "}
          {ROLE_LABEL[user.role]}. Ask an Admin if you need more access.</p>
        <Link href="/overview" className="mt-5 inline-block rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2">
          Back to the overview
        </Link>
      </div>
    );
  }
  return <>{children}</>;
}
