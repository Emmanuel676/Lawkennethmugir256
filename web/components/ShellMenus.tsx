"use client";

// The signed-in parts of the sidebar: the dataset switcher (Radix select) and the account menu (Radix dropdown).
// AppShell loads this file only for signed-in users, after the page has rendered (Phase 14), so visitors who are not
// signed in never download these components.
import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId } from "react";

import { ROLE_LABEL } from "@/lib/api";

import { DEMO, useCurrentDataset, useSession } from "./SessionProvider";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

export function DatasetSelect({ id }: { id: string }) {
  const { dataset, setDataset, datasets } = useSession();
  const current = useCurrentDataset();
  const labelId = useId();
  return (
    <div>
      <p id={labelId} className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Dataset</p>
      <Select value={dataset} onValueChange={setDataset}>
        <SelectTrigger id={id} aria-labelledby={labelId} className="h-9"><SelectValue /></SelectTrigger>
        <SelectContent>
          {datasets.map((d) => (
            <SelectItem key={d.slug} value={d.slug}>
              {d.slug === DEMO ? "Demonstration data (built in)" : `${d.name} (demonstration data)`}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="mt-1 text-xs text-muted">{current.kind === "imported" ? "Demonstration data, imported." : "Demonstration data, built in."}</p>
    </div>
  );
}

export function AccountMenu({ compact = false }: { compact?: boolean }) {
  const { user, signOut } = useSession();
  const router = useRouter();
  if (!user) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button"
                className="flex w-full items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-2 text-left text-sm shadow-[0_1px_2px_rgba(15,23,42,0.05)] hover:bg-surface-2 focus-visible:outline-2">
          <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold uppercase text-accent">
            {user.email.slice(0, 1)}
          </span>
          {!compact && (
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-ink">{user.email}</span>
              <span className="block text-xs text-muted">{ROLE_LABEL[user.role]}</span>
            </span>
          )}
          <span className="sr-only">Account menu for {user.email}, role {ROLE_LABEL[user.role]}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={compact ? "end" : "start"} side={compact ? "bottom" : "top"}>
        <DropdownMenuLabel>
          Signed in as <span className="font-medium text-ink-2">{user.email}</span><br />
          Role: <span className="font-medium text-ink-2">{ROLE_LABEL[user.role]}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={async () => { await signOut(); router.push("/"); }}>
          <LogOut aria-hidden="true" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
