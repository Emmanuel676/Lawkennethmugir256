"use client";

import { useState, type FormEvent } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { RequireRole } from "@/components/RequireRole";
import { useSession } from "@/components/SessionProvider";
import { Card, ErrorState, inputClass, LoadingBlock, PageHeader, Pill } from "@/components/ui";
import { ROLE_LABEL, sendJson, type Role, type User, type UserList } from "@/lib/api";
import { date } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const ROLE_HELP: Record<Role, string> = {
  viewer: "reads every dataset",
  importer: "Viewer, plus adds datasets",
  admin: "Importer, plus manages users, deletes datasets and reads the audit log",
};

function Message({ text, tone }: { text: string; tone: "ok" | "error" }) {
  return (
    <p role={tone === "error" ? "alert" : "status"}
       className={`rounded-lg px-3 py-2 text-sm ${tone === "ok"
         ? "border border-[#99d5cf] bg-[#e6f2f1] text-[#115e59] dark:border-[#115e59] dark:bg-[#042f2e] dark:text-[#99f6e4]"
         : "border border-[#fda4af] bg-[#fff1f2] text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]"}`}>
      {text}
    </p>
  );
}

function NewUserForm({ minimum, onDone }: { minimum: number; onDone: (text: string) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const user = await sendJson<User>("POST", "/api/users", { email, role, password });
      setEmail("");
      setPassword("");
      onDone(`Created ${user.email} as ${ROLE_LABEL[user.role]}. Give them the password in person or by phone.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 md:grid-cols-[1fr_12rem_1fr_auto] md:items-end">
      <div><label htmlFor="nu-email" className="mb-1.5 block text-sm font-medium text-ink-2">Email</label>
        <input id="nu-email" type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} /></div>
      <div><label htmlFor="nu-role" className="mb-1.5 block text-sm font-medium text-ink-2">Role</label>
        <select id="nu-role" value={role} onChange={(e) => setRole(e.target.value as Role)} className={inputClass}>
          {(["viewer", "importer", "admin"] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
        </select></div>
      <div><label htmlFor="nu-password" className="mb-1.5 block text-sm font-medium text-ink-2">First password (at least {minimum} characters)</label>
        <input id="nu-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} /></div>
      <button type="submit" disabled={busy || !email || password.length < minimum}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-40">
        {busy ? "Creating…" : "Create user"}
      </button>
      {error && <div className="md:col-span-4"><Message text={error} tone="error" /></div>}
      <p className="text-xs text-muted md:col-span-4">{(["viewer", "importer", "admin"] as Role[]).map((r) => `${ROLE_LABEL[r]}: ${ROLE_HELP[r]}`).join(". ")}.</p>
    </form>
  );
}

function ResetDialog({ user, minimum, onClose, onDone }: {
  user: User; minimum: number; onClose: () => void; onDone: (text: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await sendJson<User>("POST", `/api/users/${user.id}/password`, { password });
      onDone(`New password set for ${user.email}. Their open sessions were signed out.`);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="reset-title" className="fixed inset-0 z-50 grid place-items-center bg-navy/50 p-4"
         onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-xl">
        <h2 id="reset-title" className="text-lg font-semibold text-ink">Reset the password of {user.email}</h2>
        <label htmlFor="rp" className="mt-4 block text-sm font-medium text-ink-2">New password (at least {minimum} characters)</label>
        <input id="rp" type="password" autoFocus autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)}
               className={`${inputClass} mt-1.5`} />
        {error && <div className="mt-2"><Message text={error} tone="error" /></div>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2">Cancel</button>
          <button type="submit" disabled={password.length < minimum} className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink disabled:opacity-40">Set password</button>
        </div>
      </form>
    </div>
  );
}

function UsersInner() {
  const { user: me } = useSession();
  const { data, error, loading, reload } = useApi<UserList>("/api/users");
  const [message, setMessage] = useState<{ text: string; tone: "ok" | "error" }>();
  const [resetting, setResetting] = useState<User>();

  async function change(user: User, body: { role?: Role; disabled?: boolean }, done: string) {
    try {
      await sendJson<User>("PATCH", `/api/users/${user.id}`, body);
      setMessage({ text: done, tone: "ok" });
      reload();
    } catch (err) {
      setMessage({ text: (err as Error).message, tone: "error" });
    }
  }

  const minimum = data?.password_min_length ?? 10;
  const columns: Column<User>[] = [
    { key: "email", header: "Email", sortValue: (u) => u.email,
      cell: (u) => <span className="font-medium text-ink">{u.email}{u.id === me?.id && <span className="ml-1 text-xs text-muted">(you)</span>}</span> },
    { key: "role", header: "Role", sortValue: (u) => u.role,
      cell: (u) => (
        <select aria-label={`Role of ${u.email}`} value={u.role} disabled={u.id === me?.id}
                onChange={(e) => change(u, { role: e.target.value as Role }, `${u.email} is now ${ROLE_LABEL[e.target.value as Role]}. They need to sign in again.`)}
                className="rounded-lg border border-line bg-surface px-2 py-1 text-sm text-ink disabled:opacity-60">
          {(["viewer", "importer", "admin"] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
        </select>) },
    { key: "status", header: "Status", sortValue: (u) => (u.disabled ? 2 : u.locked ? 1 : 0),
      cell: (u) => u.disabled ? <Pill tone="rose">Disabled</Pill> : u.locked ? <Pill tone="amber">Sign-in paused</Pill> : <Pill tone="teal">Active</Pill> },
    { key: "created", header: "Created", sortValue: (u) => u.created_at,
      cell: (u) => <span className="text-xs">{date(new Date(u.created_at * 1000).toISOString())} by {u.created_by}</span> },
    { key: "actions", header: "Actions",
      cell: (u) => (
        <span className="flex gap-2">
          <button type="button" onClick={() => setResetting(u)} className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2">Reset password</button>
          {u.id !== me?.id && (
            <button type="button" onClick={() => change(u, { disabled: !u.disabled }, `${u.email} was ${u.disabled ? "enabled" : "disabled"}.`)}
                    className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2">
              {u.disabled ? "Enable" : "Disable"}
            </button>
          )}
        </span>) },
  ];

  return (
    <div className="space-y-6">
      <Card id="new" title="Add a user" subtitle="There is no public sign-up and no password-reset email. Give new users their first password yourself.">
        <NewUserForm minimum={minimum} onDone={(text) => { setMessage({ text, tone: "ok" }); reload(); }} />
      </Card>
      {message && <Message text={message.text} tone={message.tone} />}
      <Card id="list" title={data ? `${data.users.length} user(s)` : "Users"}>
        {error && <ErrorState message={error} onRetry={reload} />}
        {!error && loading && !data && <LoadingBlock rows={4} label="Loading users" />}
        {data && !error && (
          <DataTable caption="Users" columns={columns} rows={data.users} rowKey={(u) => String(u.id)} maxHeight="none"
                     initialSort={{ key: "email", order: "asc" }} />
        )}
      </Card>
      {resetting && <ResetDialog user={resetting} minimum={minimum} onClose={() => setResetting(undefined)}
                                 onDone={(text) => { setResetting(undefined); setMessage({ text, tone: "ok" }); reload(); }} />}
    </div>
  );
}

export default function UsersPage() {
  return (
    <>
      <PageHeader title="Users" intro="Create accounts, set roles, reset passwords and disable users. Changing a role or a password signs that user out." />
      <RequireRole role="admin" what="manage users"><UsersInner /></RequireRole>
    </>
  );
}
