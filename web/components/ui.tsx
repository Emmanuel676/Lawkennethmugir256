"use client";

import { useId, useState, type ReactNode } from "react";

import type { Band } from "@/lib/api";
import { useMeta } from "./MetaProvider";

export function PageHeader({ title, intro, children }: { title: string; intro?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {intro && <p className="mt-1.5 max-w-3xl text-[15px] leading-relaxed text-muted">{intro}</p>}
      </div>
      {children && <div className="flex shrink-0 flex-wrap gap-2">{children}</div>}
    </div>
  );
}

export function Card({ title, subtitle, actions, children, className = "", id }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section id={id} aria-labelledby={title && id ? `${id}-title` : undefined}
             className={`min-w-0 rounded-2xl border border-line bg-surface p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] sm:p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 id={id ? `${id}-title` : undefined} className="text-base font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function KpiTile({ label, value, detail, help, accent = "teal", compact = false }: {
  label: ReactNode; value: string; detail?: ReactNode; help?: string; accent?: "teal" | "amber" | "navy" | "rose";
  compact?: boolean;
}) {
  const bar = { teal: "bg-[var(--band-low)]", amber: "bg-amber", navy: "bg-navy dark:bg-slate-300",
                rose: "bg-[var(--band-high)]" }[accent];
  return (
    <div className="relative min-w-0 overflow-hidden rounded-2xl border border-line bg-surface p-4 sm:p-5" title={help}>
      <span aria-hidden="true" className={`absolute inset-y-0 left-0 w-1 ${bar}`} />
      <p className="text-sm font-medium text-muted">{label}</p>
      <p className={`tabular mt-1.5 whitespace-nowrap font-semibold leading-tight tracking-tight text-ink ${compact ? "text-2xl" : "text-[28px] sm:text-3xl"}`}>{value}</p>
      {detail && <p className="mt-1 text-sm text-muted">{detail}</p>}
    </div>
  );
}

const BAND_STYLE: Record<string, string> = {
  high: "bg-[#ffe4e6] text-[#9f1239] ring-[#fda4af] dark:bg-[#4c0519] dark:text-[#fecdd3] dark:ring-[#9f1239]",
  medium: "bg-[#fef3e2] text-[#92400e] ring-[#fcd34d] dark:bg-[#451a03] dark:text-[#fde68a] dark:ring-[#92400e]",
  low: "bg-[#e6f2f1] text-[#115e59] ring-[#99d5cf] dark:bg-[#042f2e] dark:text-[#99f6e4] dark:ring-[#115e59]",
};
const BAND_SHAPE: Record<string, string> = { high: "▲", medium: "◆", low: "●" };

/** A band is always a word (Low, Medium, High) with a colour and a shape, never colour alone. */
export function BandBadge({ band }: { band: Band | null | undefined }) {
  if (!band) return <span className="text-muted">n/a</span>;
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${BAND_STYLE[band.key] ?? ""}`}>
      <span aria-hidden="true" className="text-[9px]">{BAND_SHAPE[band.key]}</span>
      {band.label}
    </span>
  );
}

export function Pill({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "amber" | "teal" | "rose" }) {
  const style = {
    slate: "bg-surface-2 text-ink-2 ring-line",
    amber: "bg-[#fef3e2] text-[#92400e] ring-[#fcd34d] dark:bg-[#451a03] dark:text-[#fde68a] dark:ring-[#92400e]",
    teal: "bg-[#e6f2f1] text-[#115e59] ring-[#99d5cf] dark:bg-[#042f2e] dark:text-[#99f6e4] dark:ring-[#115e59]",
    rose: "bg-[#ffe4e6] text-[#9f1239] ring-[#fda4af] dark:bg-[#4c0519] dark:text-[#fecdd3] dark:ring-[#9f1239]",
  }[tone];
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}>
      {children}
    </span>
  );
}

/** A term with a keyboard- and hover-accessible explanation, e.g. <Term k="cycling">cycling</Term>. */
export function Term({ k, children }: { k: string; children: ReactNode }) {
  const { glossary } = useMeta();
  const [open, setOpen] = useState(false);
  const id = useId();
  const text = glossary[k];
  if (!text) return <>{children}</>;
  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="cursor-help border-b border-dotted border-current font-inherit text-inherit"
      >
        {children}
        <span className="sr-only"> (what this means)</span>
      </button>
      {open && (
        <span role="tooltip" id={id}
              className="absolute left-1/2 top-full z-50 mt-2 w-64 max-w-[80vw] -translate-x-1/2 rounded-lg border border-line bg-surface p-3 text-left text-[13px] font-normal normal-case leading-snug tracking-normal text-ink-2 shadow-lg">
          {text}
        </span>
      )}
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton ${className}`} />;
}

export function LoadingBlock({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-9 w-full" />)}
    </div>
  );
}

export function KpiSkeletons({ count = 4 }: { count?: number }) {
  return (
    <div role="status" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <span className="sr-only">Loading headline numbers…</span>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-2xl border border-line bg-surface p-5">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="mt-3 h-8 w-24" />
          <Skeleton className="mt-3 h-4 w-36" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-2xl border border-[#fda4af] bg-[#fff1f2] p-5 text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]">
      <p className="font-semibold">We could not load this right now.</p>
      <p className="mt-1 text-sm">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}
                className="mt-3 rounded-lg bg-[#9f1239] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#881337]">
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line px-6 py-10 text-center">
      <svg aria-hidden="true" viewBox="0 0 24 24" className="mx-auto h-8 w-8 text-muted" fill="none" stroke="currentColor"
           strokeWidth="1.5"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <p className="mt-3 font-medium text-ink">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Pagination({ page, pages, onPage, label }: {
  page: number; pages: number; onPage: (page: number) => void; label: string;
}) {
  if (pages <= 1) return null;
  const button = "rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink-2 hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <nav aria-label={label} className="mt-4 flex items-center justify-between gap-3">
      <button type="button" className={button} disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Previous
      </button>
      <span className="tabular text-sm text-muted">Page {page} of {pages}</span>
      <button type="button" className={button} disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next →
      </button>
    </nav>
  );
}

export function ChipGroup<T extends string>({ legend, options, value, onChange }: {
  legend: string; options: { key: T; label: string }[]; value: T[]; onChange: (value: T[]) => void;
}) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const on = value.includes(option.key);
          return (
            <button key={option.key} type="button" aria-pressed={on}
                    onClick={() => onChange(on ? value.filter((v) => v !== option.key) : [...value, option.key])}
                    className={`rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
                      on ? "border-accent bg-accent text-accent-ink" : "border-line text-ink-2 hover:bg-surface-2"}`}>
              {option.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export const inputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent";

export function Field({ label, children, htmlFor }: { label: string; children: ReactNode; htmlFor: string }) {
  return (
    <div className="min-w-0">
      <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
        {label}
      </label>
      {children}
    </div>
  );
}
