"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { ROLE_LABEL, type Role } from "@/lib/api";
import { date } from "@/lib/format";

import { useMeta } from "./MetaProvider";
import { DEMO, useCurrentDataset, useSession } from "./SessionProvider";
import { ThemeToggle } from "./ThemeToggle";

interface NavItem { href: string; label: string; icon: string; role?: Role }

const MAIN: NavItem[] = [
  { href: "/", label: "Overview", icon: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z" },
  { href: "/borrowers", label: "Borrowers", icon: "M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0ZM4 21a8 8 0 0 1 16 0" },
  { href: "/lenders", label: "Lenders", icon: "M3 21h18M5 21V10l7-5 7 5v11M9 21v-6h6v6" },
  { href: "/repayments", label: "Repayments",
    icon: "M3 7h18v10H3V7Zm9 2.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM6 10v4m12-4v4" },
];
const PRESENT: NavItem[] = [
  { href: "/guided-demo", label: "Guided demo", icon: "M5 3l14 9-14 9V3Z" },
  { href: "/export", label: "Export", icon: "M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" },
  { href: "/about", label: "About", icon: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-14h.01M11 12h1v5h1" },
];
const MANAGE: NavItem[] = [
  { href: "/datasets", label: "Datasets", role: "viewer",
    icon: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" },
  { href: "/import", label: "Import data", role: "importer", icon: "M12 3v12m0-12-4 4m4-4 4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" },
  { href: "/review", label: "Review labels", role: "importer", icon: "M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9" },
  { href: "/users", label: "Users", role: "admin",
    icon: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" },
  { href: "/audit", label: "Audit log", role: "admin", icon: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 9 2 2 4-4" },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function NavIcon({ d }: { d: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

export function TrustStrip() {
  const { trustLine } = useMeta();
  return (
    <div role="note" aria-label="About this data"
         className="sticky top-0 z-30 border-b border-amber/40 bg-tint-amber text-[#7c2d12] dark:bg-[#3a2410] dark:text-[#fde6c4]">
      <p className="mx-auto flex max-w-7xl items-center gap-2 px-4 py-2 text-sm font-medium sm:px-6 lg:px-8">
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor"
             strokeWidth="2"><path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></svg>
        <span>{trustLine}</span>
      </p>
    </div>
  );
}

/** Which dataset the pages show. Signed-out visitors see the demo only. */
export function DatasetSwitcher({ id }: { id: string }) {
  const { user, dataset, setDataset, datasets } = useSession();
  const current = useCurrentDataset();
  if (!user) {
    return (
      <p className="text-xs text-muted">
        <span className="block font-semibold text-ink-2">Demonstration data (built in)</span>
        Sign in to see shared datasets.
      </p>
    );
  }
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Dataset</label>
      <select id={id} value={dataset} onChange={(e) => setDataset(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface px-2.5 py-2 text-sm text-ink">
        {datasets.map((d) => (
          <option key={d.slug} value={d.slug}>{d.slug === DEMO ? "Demonstration data (built in)" : `${d.name} (demonstration data)`}</option>
        ))}
      </select>
      <p className="mt-1 text-xs text-muted">{current.kind === "imported" ? "Demonstration data, imported." : "Demonstration data, built in."}</p>
    </div>
  );
}

function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, signOut, ready } = useSession();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!ready) return <div className="h-9" aria-hidden="true" />;
  if (!user) {
    return (
      <Link href="/signin" className="inline-flex items-center justify-center rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-ink hover:opacity-90">
        Sign in
      </Link>
    );
  }
  return (
    <div ref={box} className="relative">
      <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}
              className="flex w-full items-center gap-2 rounded-lg border border-line px-2.5 py-2 text-left text-sm hover:bg-surface-2">
        <span aria-hidden="true" className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold uppercase text-accent">
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
      {open && (
        <div role="menu" className={`absolute z-50 w-60 rounded-xl border border-line bg-surface p-2 shadow-lg ${compact ? "right-0 top-full mt-2" : "bottom-full left-0 mb-2"}`}>
          <p className="px-2 pb-2 text-xs text-muted">Signed in as <span className="font-medium text-ink-2">{user.email}</span><br />
            Role: <span className="font-medium text-ink-2">{ROLE_LABEL[user.role]}</span></p>
          <button type="button" role="menuitem"
                  onClick={async () => { setOpen(false); await signOut(); router.push("/"); }}
                  className="w-full rounded-lg px-2 py-2 text-left text-sm font-medium text-ink-2 hover:bg-surface-2">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function NavList({ items, pathname, onPick }: { items: NavItem[]; pathname: string; onPick?: () => void }) {
  return (
    <ul className="space-y-1">
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <li key={item.href}>
            <Link href={item.href} aria-current={active ? "page" : undefined} onClick={onPick}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] font-medium transition-colors ${
                    active ? "bg-accent-soft text-accent" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
              <NavIcon d={item.icon} />
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { can, user } = useSession();
  const current = useCurrentDataset();
  const [more, setMore] = useState(false);
  const manage = MANAGE.filter((item) => !item.role || can(item.role));

  useEffect(() => setMore(false), [pathname]);

  return (
    <div className="min-h-screen lg:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:shadow">
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-surface lg:fixed lg:inset-y-0 lg:flex">
        <div className="px-5 pb-4 pt-6">
          <Link href="/" aria-label="FairLend Watch, Overview">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="FairLend Watch, lending conduct monitor" className="h-auto w-full" width={460} height={124} />
          </Link>
        </div>
        <nav aria-label="Main" className="flex-1 overflow-y-auto px-3">
          <NavList items={MAIN} pathname={pathname} />
          <p className="mb-1 mt-5 px-3 text-xs font-semibold uppercase tracking-wide text-muted">Present</p>
          <NavList items={PRESENT} pathname={pathname} />
          {manage.length > 0 && (
            <>
              <p className="mb-1 mt-5 px-3 text-xs font-semibold uppercase tracking-wide text-muted">Manage</p>
              <NavList items={manage} pathname={pathname} />
            </>
          )}
        </nav>
        <div className="space-y-3 border-t border-line px-5 py-4">
          <DatasetSwitcher id="dataset-desktop" />
          {current.as_of_date && <p className="text-xs text-muted">Data as of {date(current.as_of_date)}</p>}
          <UserMenu />
          <ThemeToggle />
        </div>
      </aside>

      <div className="min-w-0 flex-1 lg:pl-64">
        {/* Phone and tablet header */}
        <header className="flex items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3 lg:hidden">
          <Link href="/" aria-label="FairLend Watch, Overview" className="shrink-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="FairLend Watch, lending conduct monitor" className="h-10 w-auto" width={148} height={40} />
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle compact />
            <UserMenu compact />
          </div>
        </header>

        <TrustStrip />

        {user && current.slug !== DEMO && (
          <div className="border-b border-line bg-surface">
            <p className="mx-auto max-w-7xl px-4 py-1.5 text-xs text-muted sm:px-6 lg:px-8">
              Showing <span className="font-semibold text-ink-2">{current.name}</span>. {current.label}{" "}
              <Link href="/datasets" className="font-medium text-accent hover:underline">Change dataset</Link>
            </p>
          </div>
        )}

        <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-4 pb-28 pt-6 sm:px-6 lg:px-8 lg:pb-12">
          {children}
        </main>
      </div>

      {/* Phone bottom bar: the four pages, plus More (datasets, import, users, audit, account) */}
      {more && (
        <div id="more-menu" className="fixed inset-x-0 bottom-[60px] z-40 max-h-[70vh] overflow-y-auto border-t border-line bg-surface px-4 pb-4 pt-3 shadow-[0_-8px_24px_rgba(15,23,42,0.12)] lg:hidden">
          <div className="mb-3"><DatasetSwitcher id="dataset-phone" /></div>
          <NavList items={PRESENT} pathname={pathname} onPick={() => setMore(false)} />
          {manage.length > 0 ? <div className="mt-2 border-t border-line pt-2"><NavList items={manage} pathname={pathname} onPick={() => setMore(false)} /></div>
            : <p className="mt-2 text-sm text-muted">Sign in to see shared datasets and, depending on your role, import data.</p>}
        </div>
      )}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface lg:hidden">
        <ul className="grid grid-cols-5">
          {MAIN.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <li key={item.href}>
                <Link href={item.href} aria-current={active ? "page" : undefined}
                      className={`flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium ${
                        active ? "text-accent" : "text-muted"}`}>
                  <NavIcon d={item.icon} />
                  {item.label}
                </Link>
              </li>
            );
          })}
          <li>
            <button type="button" aria-expanded={more} aria-controls="more-menu" onClick={() => setMore((v) => !v)}
                    className={`flex w-full flex-col items-center gap-1 py-2.5 text-[11px] font-medium ${
                      more || [...manage, ...PRESENT].some((m) => isActive(pathname, m.href)) ? "text-accent" : "text-muted"}`}>
              <NavIcon d="M4 6h16M4 12h16M4 18h16" />
              More
            </button>
          </li>
        </ul>
      </nav>
    </div>
  );
}
