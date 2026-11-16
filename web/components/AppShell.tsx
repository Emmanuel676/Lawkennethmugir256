"use client";

import {
  Building2, ClipboardCheck, Database, Download, Info, LayoutDashboard, Menu, PlayCircle, ScrollText,
  Upload, UserRound, Users, Wallet, type LucideIcon,
} from "lucide-react";
import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import type { Role } from "@/lib/api";
import { date } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useMeta } from "./MetaProvider";
import { DEMO, useCurrentDataset, useSession } from "./SessionProvider";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/button";

interface NavItem { href: string; label: string; icon: LucideIcon; role?: Role }

const MAIN: NavItem[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/borrowers", label: "Borrowers", icon: UserRound },
  { href: "/lenders", label: "Lenders", icon: Building2 },
  { href: "/repayments", label: "Repayments", icon: Wallet },
];
const PRESENT: NavItem[] = [
  { href: "/guided-demo", label: "Guided demo", icon: PlayCircle },
  { href: "/export", label: "Export", icon: Download },
  { href: "/about", label: "About", icon: Info },
];
const MANAGE: NavItem[] = [
  { href: "/datasets", label: "Datasets", role: "viewer", icon: Database },
  { href: "/import", label: "Import data", role: "importer", icon: Upload },
  { href: "/review", label: "Review labels", role: "importer", icon: ClipboardCheck },
  { href: "/users", label: "Users", role: "admin", icon: Users },
  { href: "/audit", label: "Audit log", role: "admin", icon: ScrollText },
];

/** Pages with the public frame (no sidebar): the landing page. */
const PUBLIC_PAGES = new Set(["/"]);

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** The trust message, kept quiet (Phase 14d): one small muted line at the foot of every page, not a sticky banner. */
export function TrustLine({ className = "" }: { className?: string }) {
  const { trustLine } = useMeta();
  return <p className={cn("text-xs leading-relaxed text-muted", className)}>{trustLine}</p>;
}

// The signed-in menus (Radix select and dropdown) load only for signed-in users, after the page has rendered.
const DatasetSelect = dynamic(() => import("./ShellMenus").then((m) => m.DatasetSelect),
                              { ssr: false, loading: () => <div className="h-[74px]" aria-hidden="true" /> });
const AccountMenu = dynamic(() => import("./ShellMenus").then((m) => m.AccountMenu),
                            { ssr: false, loading: () => <div className="h-11" aria-hidden="true" /> });

/** Which dataset the pages show. Signed-out visitors see the built-in demonstration data only. */
export function DatasetSwitcher({ id }: { id: string }) {
  const { user } = useSession();
  if (!user) {
    return (
      <p className="text-xs text-muted">
        <span className="block font-semibold text-ink-2">Demonstration data (built in)</span>
        Sign in to see shared datasets.
      </p>
    );
  }
  return <DatasetSelect id={id} />;
}

function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, ready } = useSession();
  if (!ready) return <div className="h-9" aria-hidden="true" />;
  if (!user) {
    return <Button asChild size="sm" className={compact ? "" : "w-full"}><Link href="/signin">Sign in</Link></Button>;
  }
  return <AccountMenu compact={compact} />;
}

function NavList({ items, pathname, onPick }: { items: NavItem[]; pathname: string; onPick?: () => void }) {
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link href={item.href} aria-current={active ? "page" : undefined} onClick={onPick}
                  className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-[15px] font-medium transition-colors",
                    active ? "bg-accent-soft text-accent shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--accent)_20%,transparent)]"
                           : "text-ink-2 hover:bg-surface-2 hover:text-ink")}>
              <Icon className="size-[18px] shrink-0" aria-hidden="true" strokeWidth={1.9} />
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function Logo({ className = "h-auto w-full", width = 460, height = 124 }: { className?: string; width?: number; height?: number }) {
  return <Image src="/logo.svg" alt="FairLend Watch, lending conduct monitor" className={className} width={width} height={height} priority />;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { can, user } = useSession();
  const current = useCurrentDataset();
  const [more, setMore] = useState(false);
  const manage = MANAGE.filter((item) => !item.role || can(item.role));

  useEffect(() => setMore(false), [pathname]);

  const skip = (
    <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:shadow">
      Skip to content
    </a>
  );

  if (PUBLIC_PAGES.has(pathname)) {
    return (
      <div className="min-h-screen">
        {skip}
        <main id="main" tabIndex={-1}>{children}</main>
      </div>
    );
  }

  return (
    <div className="min-h-screen lg:flex">
      {skip}
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-surface lg:fixed lg:inset-y-0 lg:flex">
        <div className="px-5 pb-4 pt-6">
          <Link href="/" aria-label="FairLend Watch, home"><Logo /></Link>
        </div>
        <nav aria-label="Main" className="flex-1 overflow-y-auto px-3">
          <NavList items={MAIN} pathname={pathname} />
          <p className="mb-1 mt-5 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Present</p>
          <NavList items={PRESENT} pathname={pathname} />
          {manage.length > 0 && (
            <>
              <p className="mb-1 mt-5 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Manage</p>
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
          <Link href="/" aria-label="FairLend Watch, home" className="shrink-0">
            <Logo className="h-10 w-auto" width={148} height={40} />
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle compact />
            <UserMenu compact />
          </div>
        </header>


        {user && current.slug !== DEMO && (
          <div className="border-b border-line bg-surface">
            <p className="mx-auto max-w-7xl px-4 py-1.5 text-xs text-muted sm:px-6 lg:px-8">
              Showing <span className="font-semibold text-ink-2">{current.name}</span>. {current.label}{" "}
              <Link href="/datasets" className="font-medium text-accent hover:underline">Change dataset</Link>
            </p>
          </div>
        )}

        <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-4 pb-10 pt-7 sm:px-6 lg:px-8 lg:pb-10">
          {children}
        </main>
        {/* Room below for the phone's bottom bar. */}
        <footer className="mx-auto max-w-7xl px-4 pb-24 sm:px-6 lg:px-8 lg:pb-8">
          <TrustLine className="border-t border-line pt-4" />
        </footer>
      </div>

      {/* Phone bottom bar: the four pages, plus More (dataset switcher, Present and Manage pages) */}
      {more && (
        <div id="more-menu" className="fixed inset-x-0 bottom-[60px] z-40 max-h-[70vh] overflow-y-auto border-t border-line bg-surface px-4 pb-4 pt-3 shadow-[0_-12px_32px_-12px_rgba(15,23,42,0.25)] animate-in fade-in-0 slide-in-from-bottom-4 lg:hidden">
          <div className="mb-3"><DatasetSwitcher id="dataset-phone" /></div>
          <NavList items={PRESENT} pathname={pathname} onPick={() => setMore(false)} />
          {manage.length > 0 ? <div className="mt-2 border-t border-line pt-2"><NavList items={manage} pathname={pathname} onPick={() => setMore(false)} /></div>
            : <p className="mt-2 text-sm text-muted">Sign in to see shared datasets and, depending on your role, import data.</p>}
        </div>
      )}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur lg:hidden">
        <ul className="grid grid-cols-5">
          {MAIN.map((item) => {
            const active = isActive(pathname, item.href);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link href={item.href} aria-current={active ? "page" : undefined}
                      className={cn("flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium", active ? "text-accent" : "text-muted")}>
                  <Icon className="size-5" aria-hidden="true" strokeWidth={1.9} />
                  {item.label}
                </Link>
              </li>
            );
          })}
          <li>
            <button type="button" aria-expanded={more} aria-controls="more-menu" onClick={() => setMore((v) => !v)}
                    className={cn("flex w-full flex-col items-center gap-1 py-2.5 text-[11px] font-medium",
                      more || [...manage, ...PRESENT].some((m) => isActive(pathname, m.href)) ? "text-accent" : "text-muted")}>
              <Menu className="size-5" aria-hidden="true" strokeWidth={1.9} />
              More
            </button>
          </li>
        </ul>
      </nav>
    </div>
  );
}
