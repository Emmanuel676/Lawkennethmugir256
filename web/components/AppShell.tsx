"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { date } from "@/lib/format";

import { useMeta } from "./MetaProvider";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { href: "/", label: "Overview", icon: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z" },
  { href: "/borrowers", label: "Borrowers",
    icon: "M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0ZM4 21a8 8 0 0 1 16 0" },
  { href: "/lenders", label: "Lenders", icon: "M3 21h18M5 21V10l7-5 7 5v11M9 21v-6h6v6" },
  { href: "/repayments", label: "Repayments",
    icon: "M3 7h18v10H3V7Zm9 2.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM6 10v4m12-4v4" },
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

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { meta } = useMeta();

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
        <nav aria-label="Main" className="flex-1 px-3">
          <ul className="space-y-1">
            {NAV.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link href={item.href} aria-current={active ? "page" : undefined}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] font-medium transition-colors ${
                          active ? "bg-accent-soft text-accent" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
                    <NavIcon d={item.icon} />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="space-y-3 border-t border-line px-5 py-4 text-xs text-muted">
          {meta && (
            <p>
              <span className="font-semibold text-ink-2">Synthetic demo dataset</span>
              <br />
              Data as of {date(meta.dataset.as_of_date)}
              <br />
              Presentation mode · read-only
            </p>
          )}
          <ThemeToggle />
        </div>
      </aside>

      <div className="min-w-0 flex-1 lg:pl-64">
        {/* Phone and tablet header */}
        <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3 lg:hidden">
          <Link href="/" aria-label="FairLend Watch, Overview">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="FairLend Watch, lending conduct monitor" className="h-10 w-auto" width={148} height={40} />
          </Link>
          <ThemeToggle compact />
        </header>

        <TrustStrip />

        <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-4 pb-28 pt-6 sm:px-6 lg:px-8 lg:pb-12">
          {children}
        </main>
      </div>

      {/* Phone bottom bar */}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface lg:hidden">
        <ul className="grid grid-cols-4">
          {NAV.map((item) => {
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
        </ul>
      </nav>
    </div>
  );
}
