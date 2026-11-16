"use client";

// Shared page building blocks. Phase 14: Lucide icons, the Radix tooltip (shadcn/ui) for terms, count-up number
// tiles, layered shadows and a one-line "what you are looking at" under each page title.
import { AlertTriangle, ArrowLeft, ArrowRight, Eye, Inbox, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import type { Band } from "@/lib/api";
import { cn } from "@/lib/utils";

import { useMeta } from "./MetaProvider";
import { CountUp } from "./count-up";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

export const SHADOW = "shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.12)]";

export function PageHeader({ title, intro, lookingAt, children }: {
  title: string; intro?: ReactNode; lookingAt?: ReactNode; children?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-[26px] font-semibold tracking-tight text-ink sm:text-[30px]">{title}</h1>
        {intro && <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-muted">{intro}</p>}
        {lookingAt && (
          <p className="mt-3 inline-flex max-w-3xl items-start gap-2 rounded-lg bg-accent-soft/70 px-3 py-1.5 text-[13px] leading-snug text-ink-2">
            <Eye className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden="true" />
            <span><span className="font-semibold text-ink">What you are looking at: </span>{lookingAt}</span>
          </p>
        )}
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
             className={cn("min-w-0 rounded-2xl border border-line bg-surface p-4 sm:p-6", SHADOW, className)}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 id={id ? `${id}-title` : undefined} className="text-base font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm leading-relaxed text-muted">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function KpiTile({ label, value, detail, help, accent = "teal", compact = false, id }: {
  label: ReactNode; value: string; detail?: ReactNode; help?: string; accent?: "teal" | "amber" | "navy" | "rose";
  compact?: boolean; id?: string;
}) {
  const bar = { teal: "bg-[var(--band-low)]", amber: "bg-amber", navy: "bg-navy dark:bg-slate-300",
                rose: "bg-[var(--band-high)]" }[accent];
  return (
    <div id={id} className={cn("relative min-w-0 overflow-hidden rounded-2xl border border-line bg-surface p-4 sm:p-5", SHADOW)} title={help}>
      <span aria-hidden="true" className={cn("absolute inset-y-0 left-0 w-1", bar)} />
      <p className="text-sm font-medium text-muted">{label}</p>
      <p className={cn("tabular mt-1.5 whitespace-nowrap font-semibold leading-tight tracking-tight text-ink",
                       compact ? "text-2xl" : "text-[28px] sm:text-[32px]")}>
        <CountUp value={value} />
      </p>
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
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset", BAND_STYLE[band.key])}>
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
    <span className={cn("inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", style)}>
      {children}
    </span>
  );
}

/** A term with an explanation on hover, keyboard focus or tap (Radix tooltip), e.g. <Term k="cycling">cycling</Term>. */
export function Term({ k, children }: { k: string; children: ReactNode }) {
  const { glossary } = useMeta();
  const text = glossary[k];
  if (!text) return <>{children}</>;
  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>
        <button type="button" className="cursor-help border-b border-dotted border-current font-inherit text-inherit">
          {children}
          <span className="sr-only"> (what this means)</span>
        </button>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={cn("skeleton", className)} />;
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
        <div key={i} className={cn("rounded-2xl border border-line bg-surface p-5", SHADOW)}>
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
    <div role="alert" className="flex gap-3 rounded-2xl border border-[#fda4af] bg-[#fff1f2] p-5 text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]">
      <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div>
        <p className="font-semibold">We could not load this right now.</p>
        <p className="mt-1 text-sm">{message}</p>
        {onRetry && (
          <Button size="sm" variant="destructive" className="mt-3" onClick={onRetry}>
            <RotateCw aria-hidden="true" /> Try again
          </Button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-surface/60 px-6 py-12 text-center">
      <span className="mx-auto grid size-12 place-items-center rounded-full bg-surface-2 text-muted">
        <Inbox className="size-6" aria-hidden="true" />
      </span>
      <p className="mt-4 font-medium text-ink">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Pagination({ page, pages, onPage, label }: {
  page: number; pages: number; onPage: (page: number) => void; label: string;
}) {
  if (pages <= 1) return null;
  return (
    <nav aria-label={label} className="mt-4 flex items-center justify-between gap-3">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ArrowLeft aria-hidden="true" /> Previous
      </Button>
      <span className="tabular text-sm text-muted">Page {page} of {pages}</span>
      <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next <ArrowRight aria-hidden="true" />
      </Button>
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
                    className={cn("rounded-full border px-3 py-1 text-sm font-medium transition-colors focus-visible:outline-2",
                      on ? "border-accent bg-accent text-accent-ink shadow-[0_2px_8px_-3px_rgba(15,118,110,0.6)]"
                         : "border-line bg-surface text-ink-2 hover:bg-surface-2")}>
              {option.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export const inputClass =
  "h-10 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted " +
  "shadow-[inset_0_1px_1px_rgba(15,23,42,0.04)] focus:border-accent";

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
