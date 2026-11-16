"use client";

// The public landing page (Phase 14, restyled in Phase 14b). Honest by design: a prototype shown on demonstration
// data. It claims no impact, no accuracy on live data and no users. Every number is read from the API (the same values
// the Overview shows). Signed-in users go to /overview. No chart library here: the preview is drawn with plain markup.
import {
  ArrowRight, Building2, CheckCircle2, Database, EyeOff, FileSpreadsheet, Hash, HeartHandshake, Landmark,
  LayoutDashboard, ListChecks, PlayCircle, ShieldCheck, Upload, UserCheck, UserRound, Users, Wallet, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Logo } from "@/components/AppShell";
import { CountUp, MotionProvider, Reveal } from "@/components/motion";
import { useSession } from "@/components/SessionProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import type { Overview } from "@/lib/api";
import { int, pct, score } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { cn } from "@/lib/utils";

/** A loading placeholder (local, so the landing page does not load the dashboard's page kit). */
function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={cn("skeleton", className)} />;
}

// Soft, layered shadows shared by every card on this page.
const CARD = "rounded-2xl border border-line bg-surface shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_32px_-14px_rgba(15,23,42,0.18)]";
const GRADIENT = "bg-linear-to-r from-[#0f766e] to-[#b45309] bg-clip-text text-transparent dark:from-[#2dd4bf] dark:to-[#fbbf24]";

type OverviewState = { data: Overview | undefined; error: string | undefined; loading: boolean };

// --- The product preview (drawn in code) --------------------------------------------------------------------------------

const PREVIEW_NAV: { label: string; icon: LucideIcon; active?: boolean }[] = [
  { label: "Overview", icon: LayoutDashboard, active: true },
  { label: "Borrowers", icon: UserRound },
  { label: "Lenders", icon: Building2 },
  { label: "Repayments", icon: Wallet },
  { label: "Guided demo", icon: PlayCircle },
];
const PREVIEW_MANAGE: { label: string; icon: LucideIcon }[] = [
  { label: "Datasets", icon: Database },
  { label: "Import data", icon: Upload },
  { label: "Users", icon: Users },
];

// Every size decision below follows the preview's OWN width (CSS container queries), not the window's, so nothing in it
// is ever clipped, cut with an ellipsis or wrapped: tiles go 2 x 2 when four in a row would be narrower than 150 px,
// the chart and the list stack when side by side would be too tight, and the list drops its lenders column first.
function tilesFrom(data: Overview) {
  const k = data.kpis;
  return [
    { label: "Borrowers", value: int(k.borrowers_scored), note: `${int(k.lenders_ranked + k.lenders_unranked)} lenders`, edge: "bg-navy dark:bg-slate-300" },
    { label: "High band", value: int(k.band_counts.high), note: `${pct(k.band_shares.high)} of all`, edge: "bg-[var(--band-high)]" },
    { label: "Medium band", value: int(k.band_counts.medium), note: `${pct(k.band_shares.medium)} of all`, edge: "bg-[var(--band-medium)]" },
    { label: "Owed by high band", value: k.owed_by_high_band.compact, note: "unpaid loans", edge: "bg-[var(--band-low)]" },
  ];
}

function PreviewTiles({ data }: { data: Overview }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 @min-[640px]/preview:grid-cols-4">
      {tilesFrom(data).map((t) => (
        <div key={t.label} data-tile className="relative min-w-0 rounded-xl border border-line bg-surface py-3 pl-3.5 pr-3">
          <span aria-hidden="true" className={cn("absolute inset-y-2 left-0 w-1 rounded-r-full", t.edge)} />
          <p className="whitespace-nowrap text-[11px] font-medium text-muted">{t.label}</p>
          <p className="tabular mt-0.5 whitespace-nowrap text-[17px] font-semibold leading-tight tracking-tight text-ink @min-[400px]/preview:text-lg">
            <CountUp value={t.value} />
          </p>
          <p className="whitespace-nowrap text-[10.5px] text-muted">{t.note}</p>
        </div>
      ))}
    </div>
  );
}

function PreviewBands({ data }: { data: Overview }) {
  const max = Math.max(...data.bands.map((b) => b.borrowers), 1);
  const colour: Record<string, string> = { high: "bg-[var(--band-high)]", medium: "bg-[var(--band-medium)]", low: "bg-[var(--band-low)]" };
  const shape: Record<string, string> = { high: "▲", medium: "◆", low: "●" };
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface p-3.5" role="img"
         aria-label={`Borrowers per risk band: ${data.bands.map((b) => `${b.label} ${int(b.borrowers)}`).join(", ")}.`}>
      <p className="whitespace-nowrap text-xs font-semibold text-ink">Borrowers per risk band</p>
      <div className="mt-3 flex h-28 items-end gap-3 border-b border-line px-1">
        {data.bands.map((b) => (
          <div key={b.key} className="flex flex-1 flex-col items-center justify-end gap-1">
            <span className="tabular whitespace-nowrap text-[10.5px] font-semibold text-ink">{int(b.borrowers)}</span>
            <div className={cn("w-full max-w-10 rounded-t-md", colour[b.key])} style={{ height: `${Math.max(4, (88 * b.borrowers) / max)}px` }} />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-3 px-1">
        {data.bands.map((b) => (
          <span key={b.key} className="flex-1 whitespace-nowrap text-center text-[10.5px] text-muted"><span aria-hidden="true">{shape[b.key]} </span>{b.label}</span>
        ))}
      </div>
    </div>
  );
}

function PreviewTop({ data }: { data: Overview }) {
  return (
    <div className="@container/top min-w-0 rounded-xl border border-line bg-surface p-3.5">
      <p className="whitespace-nowrap text-xs font-semibold text-ink">Highest-scoring borrowers</p>
      <ul className="mt-2 divide-y divide-line/70">
        {data.top_borrowers.slice(0, 4).map((b) => (
          <li key={b.borrower_id} className="flex items-center justify-between gap-2 whitespace-nowrap py-1.5 text-[11.5px]">
            <span className="font-medium text-accent">{b.borrower_id}</span>
            <span className="tabular text-ink-2">{score(b.score)}</span>
            <span className="rounded-full bg-[#ffe4e6] px-1.5 py-px text-[10px] font-semibold text-[#9f1239] dark:bg-[#4c0519] dark:text-[#fecdd3]">
              <span aria-hidden="true">▲ </span>{b.band.label}
            </span>
            {/* The first thing to go when space is short: never cut, only hidden. */}
            <span data-lenders className="tabular hidden text-muted @min-[250px]/top:inline">{b.open_lenders} lenders</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PreviewLoading({ compact = false }: { compact?: boolean }) {
  return (
    <div role="status" className="space-y-2.5">
      <span className="sr-only">Loading the preview…</span>
      <div className="grid grid-cols-2 gap-2.5 @min-[640px]/preview:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[74px] rounded-xl" />)}
      </div>
      <Skeleton className="h-[170px] rounded-xl" />
      {!compact && <Skeleton className="h-[130px] rounded-xl" />}
    </div>
  );
}

function PreviewFallback() {
  return (
    <div className="grid h-full min-h-[220px] place-items-center rounded-xl border border-dashed border-line p-6 text-center">
      <p className="max-w-xs text-sm text-muted">The live preview is starting up. Open the demo in a moment to see the
        numbers.</p>
    </div>
  );
}

const FRAME_SHADOW =
  "shadow-[0_2px_6px_rgba(15,23,42,0.05),0_28px_60px_-24px_rgba(15,23,42,0.35)] dark:shadow-[0_2px_6px_rgba(0,0,0,0.3),0_28px_60px_-24px_rgba(0,0,0,0.75)]";

/** Desktop: a framed mini-dashboard, fully inside the content area, with a sidebar from 1200 px of window width. */
function ProductPreview({ state }: { state: OverviewState }) {
  const { data, error, loading } = state;
  return (
    <div data-testid="hero-preview" aria-label="A preview of the dashboard, with numbers read from the demonstration data"
         role="group" className={cn("w-full overflow-hidden rounded-[20px] border border-line bg-surface", FRAME_SHADOW)}>
      {/* Window bar */}
      <div className="flex items-center gap-1.5 border-b border-line bg-surface-2/70 px-4 py-2.5" aria-hidden="true">
        <span className="size-2.5 rounded-full bg-[#fda4af]" /><span className="size-2.5 rounded-full bg-[#fcd34d]" /><span className="size-2.5 rounded-full bg-[#99d5cf]" />
        <span className="ml-3 whitespace-nowrap rounded-md bg-surface px-2.5 py-0.5 text-[10.5px] text-muted">fairlend-watch / overview</span>
      </div>
      <div className="flex">
        {/* Mini sidebar: 150 px, shown only when the window is at least 1200 px wide. */}
        <nav aria-label="Preview of the menu" className="hidden w-[150px] shrink-0 border-r border-line bg-surface px-2 py-3 min-[1200px]:block">
          <ul className="space-y-0.5">
            {PREVIEW_NAV.map((item) => (
              <li key={item.label} aria-current={item.active ? "page" : undefined}
                  className={cn("flex items-center gap-2 whitespace-nowrap rounded-lg px-2 py-1.5 text-[12px] font-medium",
                    item.active ? "bg-accent-soft text-accent" : "text-ink-2")}>
                <item.icon className="size-3.5 shrink-0" aria-hidden="true" />{item.label}
              </li>
            ))}
          </ul>
          <p className="mb-1 mt-4 px-2 text-[9.5px] font-semibold uppercase tracking-[0.1em] text-muted">Manage</p>
          <ul className="space-y-0.5">
            {PREVIEW_MANAGE.map((item) => (
              <li key={item.label} className="flex items-center gap-2 whitespace-nowrap rounded-lg px-2 py-1.5 text-[12px] font-medium text-ink-2">
                <item.icon className="size-3.5 shrink-0" aria-hidden="true" />{item.label}
              </li>
            ))}
          </ul>
        </nav>
        {/* Content: a size container, so its parts follow the space they really have. */}
        <div className="@container/preview min-w-0 flex-1 space-y-2.5 bg-bg p-3.5">
          <p className="text-sm font-semibold text-ink">Overview</p>
          {error ? <PreviewFallback /> : loading || !data ? <PreviewLoading /> : (
            <>
              <PreviewTiles data={data} />
              <div className="grid gap-2.5 @min-[540px]/preview:grid-cols-[1fr_1.15fr]">
                <PreviewBands data={data} />
                <PreviewTop data={data} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** Phone and tablet: a simpler card with the tiles and the bands only. */
function ProductPreviewCompact({ state }: { state: OverviewState }) {
  const { data, error, loading } = state;
  return (
    <div data-testid="hero-preview-compact" role="group" aria-label="A preview of the dashboard, with numbers read from the demonstration data"
         className={cn(CARD, "@container/preview space-y-2.5 p-3.5")}>
      <p className="text-sm font-semibold text-ink">Overview</p>
      {error ? <PreviewFallback /> : loading || !data ? <PreviewLoading compact /> : (
        <>
          <PreviewTiles data={data} />
          <PreviewBands data={data} />
        </>
      )}
    </div>
  );
}

// --- Page sections ---------------------------------------------------------------------------------------------------

function SectionHead({ id, eyebrow, title, intro }: { id: string; eyebrow: string; title: string; intro?: ReactNode }) {
  return (
    <Reveal>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</p>
      <h2 id={`${id}-title`} className="mt-2 max-w-2xl text-[30px] font-semibold leading-tight tracking-[-0.015em] text-ink sm:text-[36px]">{title}</h2>
      {intro && <p className="mt-3 max-w-2xl text-[16px] leading-relaxed text-muted">{intro}</p>}
    </Reveal>
  );
}

function StatsBand({ state }: { state: OverviewState }) {
  const k = state.data?.kpis;
  const stats = [
    { value: k ? int(k.borrowers_scored) : null, label: "borrowers scored" },
    { value: k ? int(k.lenders_ranked + k.lenders_unranked) : null, label: "demonstration lenders compared" },
    { value: "5", label: "signals behind every score" },
    { value: "3", label: "roles: Viewer, Importer, Admin" },
  ];
  return (
    <section aria-label="The demo in numbers" className="border-y border-line bg-surface">
      <dl className="mx-auto grid max-w-6xl grid-cols-2 px-5 sm:px-8 lg:grid-cols-4">
        {/* Thin dividers: a 2 × 2 grid on a phone, one row of four on a desktop. */}
        {stats.map((s, i) => (
          <div key={s.label} className={cn("border-line px-2 py-7 text-center sm:py-9",
            i < 2 && "border-b lg:border-b-0", i % 2 === 0 && "border-r", i === 1 && "lg:border-r")}>
            <dt className="sr-only">{s.label}</dt>
            <dd>
              <span className="tabular block text-[34px] font-semibold leading-none tracking-tight text-ink sm:text-[40px]">
                {s.value === null ? (state.error ? "–" : <Skeleton className="mx-auto h-9 w-24" />) : <CountUp value={s.value} />}
              </span>
              <span aria-hidden="true" className="mt-2 block text-sm text-muted">{s.label}</span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ProblemCard({ number, tone, title, children, delay = 0 }: {
  number: number; tone: "teal" | "amber" | "rose"; title: string; children: ReactNode; delay?: number;
}) {
  const square = {
    teal: "bg-[#0f766e] text-white shadow-[0_6px_16px_-6px_rgba(15,118,110,0.7)]",
    amber: "bg-[#b45309] text-white shadow-[0_6px_16px_-6px_rgba(180,83,9,0.7)]",
    rose: "bg-[#be123c] text-white shadow-[0_6px_16px_-6px_rgba(190,18,60,0.7)]",
  }[tone];
  return (
    <Reveal as="li" delay={delay} className={cn(CARD, "h-full p-7")}>
      <span aria-hidden="true" className={cn("grid size-10 place-items-center rounded-xl text-base font-bold", square)}>{number}</span>
      <h3 className="mt-5 text-lg font-semibold tracking-tight text-ink"><span className="sr-only">{number}. </span>{title}</h3>
      <p className="mt-2 text-[15px] leading-relaxed text-muted">{children}</p>
    </Reveal>
  );
}

function IconCard({ icon: Icon, title, children, delay = 0, as = "div" }: {
  icon: LucideIcon; title: string; children: ReactNode; delay?: number; as?: "div" | "li";
}) {
  return (
    <Reveal as={as} delay={delay} className={cn(CARD, "h-full p-7")}>
      <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><Icon className="size-5" aria-hidden="true" /></span>
      <h3 className="mt-5 text-[17px] font-semibold tracking-tight text-ink">{title}</h3>
      <p className="mt-2 text-[15px] leading-relaxed text-muted">{children}</p>
    </Reveal>
  );
}

export default function LandingPage() {
  const { ready, user } = useSession();
  const router = useRouter();
  const overview = useApi<Overview>("/api/overview");
  const state: OverviewState = { data: overview.data, error: overview.error, loading: overview.loading };

  useEffect(() => {
    if (ready && user) router.replace("/overview");
  }, [ready, user, router]);

  return (
    <MotionProvider>
      <div className="bg-bg">
        {/* Header */}
        <header className="relative z-10 border-b border-line/70 bg-surface/85 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3 sm:px-8">
            <Link href="/" aria-label="FairLend Watch, home" className="shrink-0"><Logo className="h-10 w-auto" width={148} height={40} /></Link>
            <nav aria-label="Site" className="hidden items-center gap-1 md:flex">
              <a href="#how" className="rounded-lg px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink">How it works</a>
              <Link href="/guided-demo" className="rounded-lg px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink">Guided demo</Link>
              <Link href="/about" className="rounded-lg px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink">About</Link>
            </nav>
            <div className="flex items-center gap-2">
              <ThemeToggle compact />
              <Button asChild size="sm" variant="outline"><Link href="/signin">Sign in</Link></Button>
              <Button asChild size="sm" className="hidden shadow-[0_8px_20px_-8px_rgba(15,118,110,0.7)] sm:inline-flex">
                <Link href="/request-access">Request access</Link>
              </Button>
            </div>
          </div>
        </header>

        {/* Hero */}
        <section aria-labelledby="hero-title" className="relative">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
          {/* A soft teal and amber glow, top right; behind everything, never under the text column. */}
          <div aria-hidden="true" className="pointer-events-none absolute -right-40 -top-40 size-[640px] rounded-full bg-[#0f766e]/14 blur-[110px] dark:bg-[#2dd4bf]/12" />
          <div aria-hidden="true" className="pointer-events-none absolute -top-24 right-[18%] size-[420px] rounded-full bg-[#d97706]/12 blur-[110px] dark:bg-[#fbbf24]/8" />
          </div>
          <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 pb-16 pt-14 sm:px-8 sm:pt-20 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-12 lg:pb-24 lg:pt-24">
            <div className="min-w-0">
              <p className="inline-flex items-center gap-2 rounded-full border border-[color-mix(in_oklab,var(--accent)_28%,transparent)] bg-accent-soft px-3 py-1 text-xs font-semibold text-accent">
                <span aria-hidden="true" className="size-1.5 rounded-full bg-accent" />
                Lending conduct monitor · prototype
              </p>
              <h1 id="hero-title" className="mt-6 text-[42px] font-semibold leading-[1.05] tracking-[-0.025em] text-ink sm:text-[54px] lg:text-[50px] xl:text-[56px]">
                Fair lending needs <span className={GRADIENT}>the whole picture.</span>
              </h1>
              <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-muted">
                FairLend Watch puts lenders&apos; records side by side, matched by a borrower code instead of a name. It
                shows who may be over-stretched across several lenders and which collection messages go too far, explains
                every flag, and leaves the decision to a person. A prototype, shown on demonstration data.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Button asChild size="lg" className="shadow-[0_10px_24px_-10px_rgba(15,118,110,0.75)]">
                  <Link href="/overview">Explore the demo <ArrowRight aria-hidden="true" /></Link>
                </Button>
                <Button asChild size="lg" variant="outline"><Link href="/request-access">Request access</Link></Button>
              </div>
              <ul className="mt-8 flex flex-col gap-2.5 text-sm font-medium text-ink-2 sm:flex-row sm:flex-wrap sm:gap-x-6 sm:gap-y-2.5">
                {["No names stored", "Every flag explained", "A human decides"].map((point) => (
                  <li key={point} className="flex items-center gap-2 whitespace-nowrap">
                    <CheckCircle2 className="size-[18px] text-accent" aria-hidden="true" />{point}
                  </li>
                ))}
              </ul>
            </div>
            <div className="min-w-0">
              <div className="hidden lg:block"><ProductPreview state={state} /></div>
              <div className="lg:hidden"><ProductPreviewCompact state={state} /></div>
            </div>
          </div>
        </section>

        <StatsBand state={state} />

        {/* The problem */}
        <section id="problem" aria-labelledby="problem-title" className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
          <SectionHead id="problem" eyebrow="The problem" title="Each lender sees only its own loans."
                       intro="Some of the harm in digital lending only shows up when the records of several lenders are put side by side." />
          <ol className="mt-12 grid gap-6 md:grid-cols-3">
            <ProblemCard number={1} tone="teal" title="Several loans at once">
              A borrower can hold loans from many apps at the same time. No single lender sees the whole stack.
            </ProblemCard>
            <ProblemCard number={2} tone="amber" title="Borrowing to repay" delay={0.06}>
              A new loan taken days after clearing another can mean borrowing from one lender to repay another, a sign
              worth a closer look.
            </ProblemCard>
            <ProblemCard number={3} tone="rose" title="Harsh collection" delay={0.12}>
              Threats, shaming and messages to a borrower&apos;s contacts are easy to miss when they are spread across
              lenders.
            </ProblemCard>
          </ol>
        </section>

        {/* How it works */}
        <section id="how" aria-labelledby="how-title" className="scroll-mt-6 border-y border-line bg-surface/60">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
            <SectionHead id="how" eyebrow="How it works" title="Four steps, and a person at the end." />
            <ol className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { icon: FileSpreadsheet, title: "Lenders' records in", text: "Loans, repayments and collection messages arrive in a fixed template, one lender at a time." },
                { icon: Hash, title: "Borrowers matched by a code", text: "The same person gets the same code at every lender, so their loans line up without a name." },
                { icon: ListChecks, title: "Every flag explained", text: "Each score shows the points behind it, and each message label can be read and checked." },
                { icon: UserCheck, title: "A person decides", text: "The tool points at files worth reading. A trained person reads them and decides what happens." },
              ].map((step, i) => (
                <Reveal as="li" key={step.title} delay={i * 0.06} className={cn(CARD, "relative h-full p-7")}>
                  <span className="absolute right-6 top-6 text-sm font-semibold text-muted" aria-hidden="true">0{i + 1}</span>
                  <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><step.icon className="size-5" aria-hidden="true" /></span>
                  <h3 className="mt-5 text-[17px] font-semibold tracking-tight text-ink"><span className="sr-only">Step {i + 1}: </span>{step.title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted">{step.text}</p>
                </Reveal>
              ))}
            </ol>
          </div>
        </section>

        {/* Who it is for */}
        <section id="who" aria-labelledby="who-title" className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
          <SectionHead id="who" eyebrow="Who it is for" title="Built for the people who look after fair lending." />
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            <IconCard icon={Landmark} title="Regulators and consumer-protection bodies">
              A view across the lenders they oversee, to decide whose files to open first.
            </IconCard>
            <IconCard icon={Building2} title="Responsible lenders" delay={0.06}>
              A way to show their own collection practice compares well, and to learn where it does not.
            </IconCard>
            <IconCard icon={HeartHandshake} title="Borrowers, who are protected" delay={0.12}>
              People stretched across many loans, or pressed by harsh messages, are found sooner by those who can help.
            </IconCard>
          </div>
        </section>

        {/* Trust points */}
        <section id="trust" aria-labelledby="trust-title" className="border-t border-line bg-surface/60">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
            <SectionHead id="trust" eyebrow="Built with care" title="Privacy and fairness are part of the design." />
            <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <IconCard as="li" icon={Hash} title="Codes instead of names">Borrowers are matched by a code. Names are never needed.</IconCard>
              <IconCard as="li" icon={EyeOff} title="Personal details removed" delay={0.05}>Phone numbers, emails and ID numbers are replaced in message text before anything is stored.</IconCard>
              <IconCard as="li" icon={ListChecks} title="Every flag explained" delay={0.1}>Scores show their points; labels can be read and checked by a person.</IconCard>
              <IconCard as="li" icon={ShieldCheck} title="A human decides" delay={0.15}>A flag is a prompt for a human to look, not a verdict.</IconCard>
            </ul>
            <Reveal className={cn(CARD, "relative mt-14 flex flex-col items-start justify-between gap-6 overflow-hidden p-8 sm:flex-row sm:items-center sm:p-10")}>
              <div aria-hidden="true" className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-[#0f766e]/10 blur-3xl dark:bg-[#2dd4bf]/10" />
              <div className="relative">
                <h3 className="text-2xl font-semibold tracking-tight text-ink">See it for yourself</h3>
                <p className="mt-1.5 text-[15px] text-muted">The demo is open to everyone. Accounts for shared datasets are approved by an administrator.</p>
              </div>
              <div className="relative flex flex-col gap-3 sm:flex-row">
                <Button asChild className="shadow-[0_10px_24px_-10px_rgba(15,118,110,0.75)]"><Link href="/overview">Explore the demo <ArrowRight aria-hidden="true" /></Link></Button>
                <Button asChild variant="outline"><Link href="/request-access">Request access</Link></Button>
              </div>
            </Reveal>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-line bg-surface">
          <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-8">
            <p>FairLend Watch · a prototype shown on demonstration data.</p>
            <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-2">
              <Link href="/about" className="font-medium text-ink-2 hover:text-accent">About</Link>
              <Link href="/guided-demo" className="font-medium text-ink-2 hover:text-accent">Guided demo</Link>
              <Link href="/signin" className="font-medium text-ink-2 hover:text-accent">Sign in</Link>
            </nav>
          </div>
        </footer>
      </div>
    </MotionProvider>
  );
}
