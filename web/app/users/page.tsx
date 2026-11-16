"use client";

import { Check, Clock, KeyRound, UserPlus, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Pill } from "@/components/kit";
import { RequireRole } from "@/components/RequireRole";
import { useSession } from "@/components/SessionProvider";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/form";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/sonner";
import { ROLE_LABEL, sendJson, type Role, type User, type UserList } from "@/lib/api";
import { date } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const ROLES: Role[] = ["viewer", "importer", "admin"];
const ROLE_HELP: Record<Role, string> = {
  viewer: "reads every dataset",
  importer: "Viewer, plus adds datasets and reviews labels",
  admin: "Importer, plus manages users, deletes datasets and reads the audit log",
};

function when(seconds: number): string {
  const d = new Date(seconds * 1000);
  return `${date(d.toISOString())}, ${d.toTimeString().slice(0, 5)}`;
}

function NewUserForm({ minimum, onDone }: { minimum: number; onDone: () => void }) {
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
      toast.success(`Created ${user.email} as ${ROLE_LABEL[user.role]}.`, { description: "Give them the password in person or by phone." });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 md:grid-cols-[1fr_12rem_1fr_auto] md:items-end">
      <div className="space-y-1.5"><Label htmlFor="nu-email">Email</Label>
        <Input id="nu-email" type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
      <div className="space-y-1.5"><Label htmlFor="nu-role">Role</Label>
        <Select value={role} onValueChange={(v) => setRole(v as Role)}>
          <SelectTrigger id="nu-role"><SelectValue /></SelectTrigger>
          <SelectContent>{ROLES.map((r) => <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>)}</SelectContent>
        </Select></div>
      <div className="space-y-1.5"><Label htmlFor="nu-password">First password (at least {minimum} characters)</Label>
        <Input id="nu-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
      <Button type="submit" disabled={busy || !email || password.length < minimum}><UserPlus aria-hidden="true" /> Create user</Button>
      {error && <p role="alert" className="text-sm text-[#9f1239] dark:text-[#fecdd3] md:col-span-4">{error}</p>}
      <p className="text-xs text-muted md:col-span-4">{ROLES.map((r) => `${ROLE_LABEL[r]}: ${ROLE_HELP[r]}`).join(". ")}.</p>
    </form>
  );
}

function ResetDialog({ user, minimum, onClose, onDone }: { user: User | undefined; minimum: number; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    try {
      await sendJson<User>("POST", `/api/users/${user.id}/password`, { password });
      toast.success(`New password set for ${user.email}.`, { description: "Their open sessions were signed out." });
      setPassword("");
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Dialog open={Boolean(user)} onOpenChange={(open) => { if (!open) { setPassword(""); setError(undefined); onClose(); } }}>
      <DialogContent>
        <DialogTitle>Reset the password of {user?.email}</DialogTitle>
        <DialogDescription>Give the new password to the person yourself. Changing it signs them out everywhere.</DialogDescription>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <div className="space-y-1.5"><Label htmlFor="rp">New password (at least {minimum} characters)</Label>
            <Input id="rp" type="password" autoFocus autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          {error && <p role="alert" className="text-sm text-[#9f1239] dark:text-[#fecdd3]">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={password.length < minimum}>Set password</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PendingRequests({ pending, onChanged }: { pending: User[]; onChanged: () => void }) {
  const [busy, setBusy] = useState<number>();
  async function act(user: User, action: "approve" | "reject", role?: Role) {
    setBusy(user.id);
    try {
      if (action === "approve") {
        await sendJson<User>("POST", `/api/users/${user.id}/approve`, { role });
        toast.success(`${user.email} approved as ${ROLE_LABEL[role!]}.`, { description: "They can sign in now. No email was sent; let them know yourself." });
      } else {
        await sendJson("POST", `/api/users/${user.id}/reject`);
        toast.success(`The request from ${user.email} was rejected and deleted.`);
      }
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(undefined);
    }
  }
  if (!pending.length) {
    return <EmptyState title="No pending requests.">New requests from the Request access page appear here. Nothing is emailed.</EmptyState>;
  }
  return (
    <ul className="space-y-4" aria-label="Pending requests">
      {pending.map((u) => (
        <li key={u.id} className="rounded-2xl border border-line bg-surface p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2">
                <span className="text-base font-semibold text-ink">{u.full_name || u.email}</span>
                <Pill tone="amber"><Clock className="mr-1 size-3" aria-hidden="true" />Waiting since {when(u.requested_at)}</Pill>
              </p>
              <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                <div><dt className="inline text-muted">Email: </dt><dd className="inline text-ink-2">{u.email}</dd></div>
                <div><dt className="inline text-muted">Organisation: </dt><dd className="inline text-ink-2">{u.organisation}</dd></div>
                <div><dt className="inline text-muted">Type: </dt><dd className="inline text-ink-2">{u.user_type_label}</dd></div>
              </dl>
              <p className="mt-3 rounded-lg bg-surface-2 p-3 text-sm leading-relaxed text-ink-2"><span className="sr-only">Reason: </span>{u.reason}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              {/* The email follows the visible words as screen-reader text, so the accessible name starts with what is
                  on screen (speech input) and still says whose request it is. */}
              <Button size="sm" disabled={busy === u.id} onClick={() => act(u, "approve", "viewer")}>
                <Check aria-hidden="true" /> Approve as Viewer<span className="sr-only">: {u.email}</span></Button>
              <Button size="sm" variant="secondary" disabled={busy === u.id} onClick={() => act(u, "approve", "importer")}>
                <Check aria-hidden="true" /> Approve as Importer<span className="sr-only">: {u.email}</span></Button>
              <Button size="sm" variant="destructive-outline" disabled={busy === u.id} onClick={() => act(u, "reject")}>
                <X aria-hidden="true" /> Reject<span className="sr-only">: the request from {u.email}</span></Button>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function UsersInner() {
  const { user: me } = useSession();
  const { data, error, loading, reload } = useApi<UserList>("/api/users");
  const [resetting, setResetting] = useState<User>();

  async function change(user: User, body: { role?: Role; disabled?: boolean }, done: string) {
    try {
      await sendJson<User>("PATCH", `/api/users/${user.id}`, body);
      toast.success(done);
      reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const minimum = data?.password_min_length ?? 10;
  const columns: Column<User>[] = [
    { key: "email", header: "Email", sortValue: (u) => u.email,
      cell: (u) => <span className="font-medium text-ink">{u.email}{u.id === me?.id && <span className="ml-1 text-xs text-muted">(you)</span>}</span> },
    { key: "role", header: "Role", sortValue: (u) => u.role,
      cell: (u) => (
        <Select value={u.role} disabled={u.id === me?.id}
                onValueChange={(v) => change(u, { role: v as Role }, `${u.email} is now ${ROLE_LABEL[v as Role]}. They need to sign in again.`)}>
          <SelectTrigger aria-label={`Role of ${u.email}`} className="h-8 w-32"><SelectValue /></SelectTrigger>
          <SelectContent>{ROLES.map((r) => <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>)}</SelectContent>
        </Select>) },
    { key: "status", header: "Status", sortValue: (u) => (u.disabled ? 2 : u.locked ? 1 : 0),
      cell: (u) => u.disabled ? <Pill tone="rose">Disabled</Pill> : u.locked ? <Pill tone="amber">Sign-in paused</Pill> : <Pill tone="teal">Active</Pill> },
    { key: "created", header: "Created", sortValue: (u) => u.created_at,
      cell: (u) => <span className="text-xs">{date(new Date(u.created_at * 1000).toISOString())} by {u.created_by}</span> },
    { key: "actions", header: "Actions",
      cell: (u) => (
        <span className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setResetting(u)}><KeyRound aria-hidden="true" /> Reset password</Button>
          {u.id !== me?.id && (
            <Button size="sm" variant="outline" onClick={() => change(u, { disabled: !u.disabled }, `${u.email} was ${u.disabled ? "enabled" : "disabled"}.`)}>
              {u.disabled ? "Enable" : "Disable"}
            </Button>
          )}
        </span>) },
  ];

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading && !data) return <LoadingBlock rows={6} label="Loading users" />;
  if (!data) return null;

  return (
    <Tabs defaultValue={data.pending.length ? "pending" : "users"} className="space-y-5">
      <TabsList aria-label="Users and requests">
        <TabsTrigger value="users">Users ({data.users.length})</TabsTrigger>
        <TabsTrigger value="pending">Pending requests ({data.pending.length})</TabsTrigger>
      </TabsList>
      <TabsContent value="users" className="space-y-6">
        <Card id="new" title="Add a user" subtitle="Give new users their first password yourself. Nothing is emailed.">
          <NewUserForm minimum={minimum} onDone={reload} />
        </Card>
        <Card id="list" title={`${data.users.length} user(s)`}>
          <DataTable caption="Users" columns={columns} rows={data.users} rowKey={(u) => String(u.id)} maxHeight="none"
                     initialSort={{ key: "email", order: "asc" }} />
        </Card>
      </TabsContent>
      <TabsContent value="pending">
        <Card id="pending" title="Pending requests"
              subtitle="From the public Request access page. These accounts cannot sign in until you approve them. Rejecting deletes the request. No email is sent either way.">
          <PendingRequests pending={data.pending} onChanged={reload} />
        </Card>
      </TabsContent>
      <ResetDialog user={resetting} minimum={minimum} onClose={() => setResetting(undefined)} onDone={() => { setResetting(undefined); reload(); }} />
    </Tabs>
  );
}

export default function UsersPage() {
  return (
    <>
      <PageHeader title="Users" intro="Create accounts, approve access requests, set roles, reset passwords and disable users."
                  lookingAt="every account, and the access requests waiting for an administrator." />
      <RequireRole role="admin" what="manage users"><UsersInner /></RequireRole>
    </>
  );
}
