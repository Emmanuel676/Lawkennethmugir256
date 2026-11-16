"use client";

// The public landing page (Phase 14). Honest by design: a prototype shown on demonstration data. It claims no impact,
// no accuracy on live data and no users. The preview numbers are read from the API. Signed-in users go to /overview.
import {
  ArrowRight, Building2, EyeOff, FileSpreadsheet, Hash, HeartHandshake, Landmark, Layers, ListChecks,
  MessageSquareWarning, Repeat, ShieldCheck, UserCheck, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Logo } from "@/components/AppShell";
import { Skeleton, SHADOW } from "@/components/kit";
import { CountUp, MotionProvider, Reveal } from "@/components/motion";
import { useSession } from "@/components/SessionProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import type { Overview } from "@/lib/api";
import { int, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { cn } from "@/lib/utils";

function Section({ id, eyebrow, title, intro, children, className = "" }: {
  id: string; eyebrow: string; title: string; intro?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cn("mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-20", className)}>
      <Reveal>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</p>
        <h2 id={`${id}-title`} className="mt-2 max-w-2xl text-[28px] font-semibold leading-tight tracking-tight text-ink sm:text-[34px]">{title}</h2>
        {intro && <p className="mt-3 max-w-2xl text-[16px] leading-relaxed text-muted">{intro}</p>}
      </Reveal>
      <div className="mt-10">{children}</div>
    </section>
  );
}

function Panel({ icon: Icon, title, children, tone = "teal", delay = 0 }: {
  icon: LucideIcon; title: string; children: ReactNode; tone?: "teal" | "amber" | "rose" | "navy"; delay?: number;
}) {
  const chip = {
    teal: "bg-[#e6f2f1] text-[#0f766e] dark:bg-[#042f2e] dark:text-[#5eead4]",
    amber: "bg-[#fef3e2] text-[#b45309] dark:bg-[#451a03] dark:text-[#fcd34d]",
    rose: "bg-[#ffe4e6] text-[#be123c] dark:bg-[#4c0519] dark:text-[#fda4af]",
    navy: "bg-[#e2e8f0] text-[#0f172a] dark:bg-[#1e293b] dark:text-[#e2e8f0]",
  }[tone];
  return (
    <Reveal delay={delay} className={cn("h-full rounded-2xl border border-line bg-surface p-6", SHADOW)}>
      <span className={cn("grid size-11 place-items-center rounded-xl", chip)}><Icon className="size-5" aria-hidden="true" /></span>
      <h3 className="mt-4 text-[17px] font-semibold tracking-tight text-ink">{title}</h3>
      <p className="mt-2 text-[15px] leading-relaxed text-muted">{children}</p>
    </Reveal>
  );
}

/** Three lenders, each seeing one loan, feeding one coded borrower: the idea of the tool, drawn in code. */
function HeroIllustration() {
  const lenders = [
    { y: 34, label: "Lender A", tone: "var(--band-low)" },
    { y: 112, label: "Lender B", tone: "var(--band-medium)" },
    { y: 190, label: "Lender C", tone: "var(--band-high)" },
  ];
  return (
    <svg viewBox="0 0 420 250" role="img" aria-labelledby="hero-svg-title" className="h-auto w-full">
      <title id="hero-svg-title">Three lenders each see one loan; matched by a code, the borrower's whole picture appears in one place.</title>
      <defs>
        <linearGradient id="link" x1="0" x2="1">
          <stop offset="0" stopColor="var(--line)" />
          <stop offset="1" stopColor="var(--accent)" />
        </linearGradient>
      </defs>
      {lenders.map((l) => (
        <g key={l.label}>
          <path d={`M150 ${l.y + 22} C 220 ${l.y + 22}, 220 125, 280 125`} fill="none" stroke="url(#link)" strokeWidth="2.5" strokeDasharray="5 5" />
          <rect x="10" y={l.y} width="140" height="44" rx="12" fill="var(--surface)" stroke="var(--line)" />
          <rect x="22" y={l.y + 14} width="16" height="16" rx="4" fill={l.tone} />
          <text x="48" y={l.y + 27} fontSize="13" fontWeight="600" fill="var(--ink)">{l.label}</text>
          <text x="48" y={l.y + 39} fontSize="10" fill="var(--muted)">sees 1 loan</text>
        </g>
      ))}
      <g>
        <rect x="280" y="80" width="130" height="90" rx="16" fill="var(--surface)" stroke="var(--accent)" strokeWidth="2" />
        <text x="296" y="106" fontSize="11" fill="var(--muted)">Borrower code</text>
        <text x="296" y="124" fontSize="14" fontWeight="700" fill="var(--ink)" fontFamily="ui-monospace, monospace">B-3f9a…</text>
        <rect x="296" y="136" width="98" height="22" rx="11" fill="var(--accent-soft)" />
        <text x="345" y="151" fontSize="11" fontWeight="600" fill="var(--accent)" textAnchor="middle">3 open loans</text>
      </g>
    </svg>
  );
}

function LivePreview() {
  const { data, error, loading } = useApi<Overview>("/api/overview");
  if (error) {
    return <p className="rounded-2xl border border-dashed border-line p-6 text-sm text-muted">The live preview is not available right now. Open the demo to try again.</p>;
  }
  if (loading || !data) {
    return (
      <div role="status" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <span className="sr-only">Loading the live preview…</span>
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-28 w-full rounded-2xl" />)}
      </div>
    );
  }
  const k = data.kpis;
  const tiles = [
    { label: "Borrowers scored", value: int(k.borrowers_scored), note: "in the demonstration data" },
    { label: "High band", value: int(k.band_counts.high), note: `${pct(k.band_shares.high)} of borrowers` },
    { label: "Medium band", value: int(k.band_counts.medium), note: `${pct(k.band_shares.medium)} of borrowers` },
    { label: "Messages labelled abusive", value: pct(k.abusive_message_share), note: `of ${int(k.messages_classified)} collection messages` },
  ];
  const total = k.borrowers_scored || 1;
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((t, i) => (
          <Reveal key={t.label} delay={i * 0.05} className={cn("rounded-2xl border border-line bg-surface p-5", SHADOW)}>
            <p className="text-sm font-medium text-muted">{t.label}</p>
            <p className="tabular mt-1.5 text-[32px] font-semibold leading-tight tracking-tight text-ink"><CountUp value={t.value} /></p>
            <p className="mt-1 text-sm text-muted">{t.note}</p>
          </Reveal>
        ))}
      </div>
      <div className="mt-6" role="img"
           aria-label={`Of ${int(k.borrowers_scored)} borrowers, ${int(k.band_counts.high)} are in the high band, ${int(k.band_counts.medium)} in the medium band and ${int(k.band_counts.low)} in the low band.`}>
        <div className="flex h-3 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full bg-[var(--band-high)]" style={{ width: `${(100 * k.band_counts.high) / total}%` }} />
          <div className="h-full bg-[var(--band-medium)]" style={{ width: `${(100 * k.band_counts.medium) / total}%`, marginLeft: 2 }} />
          <div className="h-full bg-[var(--band-low)]" style={{ width: `${(100 * k.band_counts.low) / total}%`, marginLeft: 2 }} />
        </div>
        <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          <span><span aria-hidden="true" className="mr-1 inline-block size-2.5 rounded-sm bg-[var(--band-high)] align-middle" />▲ High {int(k.band_counts.high)}</span>
          <span><span aria-hidden="true" className="mr-1 inline-block size-2.5 rounded-sm bg-[var(--band-medium)] align-middle" />◆ Medium {int(k.band_counts.medium)}</span>
          <span><span aria-hidden="true" className="mr-1 inline-block size-2.5 rounded-sm bg-[var(--band-low)] align-middle" />● Low {int(k.band_counts.low)}</span>
        </p>
      </div>
      <p className="mt-5 text-sm text-muted">Read live from the demonstration data behind the demo. A band is a prompt for a person to look, not a verdict.</p>
    </div>
  );
}

export default function LandingPage() {
  const { ready, user } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (ready && user) router.replace("/overview");
  }, [ready, user, router]);

  return (
    <MotionProvider>
    <div className="bg-bg">
      {/* Public header */}
      <header className="border-b border-line/70 bg-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3 sm:px-8">
          <Link href="/" aria-label="FairLend Watch, home"><Logo className="h-10 w-auto" width={148} height={40} /></Link>
          <nav aria-label="Site" className="flex items-center gap-1 sm:gap-2">
            <Link href="/guided-demo" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2 sm:inline-block">Guided demo</Link>
            <Link href="/about" className="hidden rounded-lg px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2 sm:inline-block">About</Link>
            <ThemeToggle compact />
            <Button asChild size="sm" variant="outline"><Link href="/signin">Sign in</Link></Button>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section aria-labelledby="hero-title" className="relative overflow-hidden">
        <div aria-hidden="true" className="hero-grid hero-grid-fade absolute inset-0" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-16 sm:px-8 sm:pt-24 lg:grid-cols-[1.15fr_0.85fr]">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-ink-2 shadow-[0_1px_2px_rgba(15,23,42,0.05)]">
              <span className="size-1.5 rounded-full bg-accent" aria-hidden="true" />
              A prototype, shown on demonstration data
            </p>
            <h1 id="hero-title" className="mt-5 text-[38px] font-semibold leading-[1.08] tracking-[-0.02em] text-ink sm:text-[52px] lg:text-[58px]">
              One view across lenders, to see who is <span className="text-accent">over-stretched</span> and which collection messages go too far.
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-muted">
              FairLend Watch is a lending conduct monitor: it matches borrowers across lenders by a code, explains every
              flag it raises, and leaves the decision to a person.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg"><Link href="/overview">Explore the demo <ArrowRight aria-hidden="true" /></Link></Button>
              <Button asChild size="lg" variant="outline"><Link href="/request-access">Request access</Link></Button>
            </div>
          </div>
          <div className={cn("rounded-3xl border border-line bg-surface/90 p-5 backdrop-blur sm:p-7", SHADOW)}>
            <HeroIllustration />
          </div>
        </div>
      </section>

      {/* The problem */}
      <Section id="problem" eyebrow="The problem" title="Each lender sees only its own loans."
               intro="Some of the harm in digital lending only shows up when the records of several lenders are put side by side.">
        <div className="grid gap-5 md:grid-cols-3">
          <Panel icon={Layers} title="Several loans at once" tone="teal">
            A borrower can hold loans from many apps at the same time. No single lender sees the whole stack.
          </Panel>
          <Panel icon={Repeat} title="Borrowing from one lender to repay another" tone="amber" delay={0.06}>
            A new loan taken days after clearing another can mean borrowing to repay, a sign worth a closer look.
          </Panel>
          <Panel icon={MessageSquareWarning} title="Abusive collection messages" tone="rose" delay={0.12}>
            Threats, shaming and messages to a borrower&apos;s contacts are easy to miss when they are spread across lenders.
          </Panel>
        </div>
      </Section>

      {/* How it works */}
      <div className="border-y border-line bg-surface/60">
        <Section id="how" eyebrow="How it works" title="Four steps, and a person at the end.">
          <ol className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { icon: FileSpreadsheet, title: "Lenders' records in", text: "Loans, repayments and collection messages arrive in a fixed template, one lender at a time." },
              { icon: Hash, title: "Borrowers matched by a code", text: "The same person gets the same code at every lender, so their loans line up without a name." },
              { icon: ListChecks, title: "Every flag explained", text: "Each score shows the points behind it, and each message label can be read and checked." },
              { icon: UserCheck, title: "A person decides", text: "The tool points at files worth reading. A trained person reads them and decides what happens." },
            ].map((step, i) => (
              <Reveal as="li" key={step.title} delay={i * 0.06} className={cn("relative rounded-2xl border border-line bg-surface p-6", SHADOW)}>
                <span className="absolute right-5 top-5 text-sm font-semibold text-muted" aria-hidden="true">{i + 1}</span>
                <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><step.icon className="size-5" aria-hidden="true" /></span>
                <h3 className="mt-4 text-[17px] font-semibold tracking-tight text-ink"><span className="sr-only">Step {i + 1}: </span>{step.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-muted">{step.text}</p>
              </Reveal>
            ))}
          </ol>
        </Section>
      </div>

      {/* Live preview */}
      <Section id="preview" eyebrow="Live preview" title="What the demo shows right now."
               intro="These numbers are read from the demonstration data the moment you open this page.">
        <LivePreview />
        <div className="mt-8"><Button asChild variant="secondary"><Link href="/overview">Open the full demo <ArrowRight aria-hidden="true" /></Link></Button></div>
      </Section>

      {/* Who it is for */}
      <div className="border-y border-line bg-surface/60">
        <Section id="who" eyebrow="Who it is for" title="Built for the people who look after fair lending.">
          <div className="grid gap-5 md:grid-cols-3">
            <Panel icon={Landmark} title="Regulators and consumer-protection bodies" tone="navy">
              A view across the lenders they oversee, to decide whose files to open first.
            </Panel>
            <Panel icon={Building2} title="Responsible lenders" tone="teal" delay={0.06}>
              A way to show their own collection practice compares well, and to learn where it does not.
            </Panel>
            <Panel icon={HeartHandshake} title="Borrowers, who are protected" tone="amber" delay={0.12}>
              People stretched across many loans, or pressed by harsh messages, are found sooner by those who can help.
            </Panel>
          </div>
        </Section>
      </div>

      {/* Trust points */}
      <Section id="trust" eyebrow="Built with care" title="Privacy and fairness are part of the design.">
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { icon: Hash, title: "Codes instead of names", text: "Borrowers are matched by a code. Names are never needed." },
            { icon: EyeOff, title: "Personal details removed", text: "Phone numbers, emails and ID numbers are replaced in message text before anything is stored." },
            { icon: ListChecks, title: "Every flag explained", text: "Scores show their points; labels can be read and checked by a person." },
            { icon: ShieldCheck, title: "A human decides", text: "A flag is a prompt for a human to look, not a verdict." },
          ].map((t, i) => (
            <Reveal as="li" key={t.title} delay={i * 0.05} className="rounded-2xl border border-line p-5">
              <t.icon className="size-5 text-accent" aria-hidden="true" />
              <h3 className="mt-3 font-semibold text-ink">{t.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{t.text}</p>
            </Reveal>
          ))}
        </ul>
        <Reveal className={cn("mt-12 flex flex-col items-start justify-between gap-5 rounded-3xl border border-line bg-surface p-7 sm:flex-row sm:items-center sm:p-9", SHADOW)}>
          <div>
            <h3 className="text-xl font-semibold tracking-tight text-ink">See it for yourself</h3>
            <p className="mt-1 text-[15px] text-muted">The demo is open to everyone. Accounts for shared datasets are approved by an administrator.</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button asChild><Link href="/overview">Explore the demo</Link></Button>
            <Button asChild variant="outline"><Link href="/request-access">Request access</Link></Button>
          </div>
        </Reveal>
      </Section>

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
