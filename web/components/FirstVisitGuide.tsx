"use client";

// A short guide on the first visit to /overview (Phase 14). Dismissing it is remembered in this browser only.
import { BarChart3, Hash, ListOrdered, PlayCircle, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { SHADOW } from "./kit";
import { Button } from "./ui/button";

const KEY = "fairlend-guide-dismissed";

const STEPS = [
  { icon: Hash, href: "#kpis", title: "The number tiles", text: "How many borrowers were scored, how many sit in the high and medium bands, and what the high band owes." },
  { icon: BarChart3, href: "#bands", title: "The risk bands", text: "Low, Medium and High group the score. A band is a prompt for a person to look, not a verdict." },
  { icon: ListOrdered, href: "#top", title: "The highest-scoring borrowers", text: "Open one to see their loans across every lender and why each point was added." },
  { icon: PlayCircle, href: "/guided-demo", title: "The Guided demo", text: "Six chosen cases with one sentence each, if you are presenting or short of time." },
];

export function FirstVisitGuide() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      setShow(localStorage.getItem(KEY) !== "1");
    } catch {
      setShow(true);
    }
  }, []);

  function dismiss() {
    setShow(false);
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      /* not remembered in private mode */
    }
  }

  if (!show) return null;
  return (
    <section aria-labelledby="guide-title"
             className={`relative mb-6 overflow-hidden rounded-2xl border border-[color-mix(in_oklab,var(--accent)_30%,var(--line))] bg-surface p-5 sm:p-6 ${SHADOW}`}>
      <div aria-hidden="true" className="pointer-events-none absolute -right-16 -top-16 size-48 rounded-full bg-accent-soft blur-2xl" />
      <div className="relative flex items-start justify-between gap-3">
        <div>
          <p className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-accent">
            <Sparkles className="size-3.5" aria-hidden="true" /> First time here?
          </p>
          <h2 id="guide-title" className="mt-1 text-lg font-semibold tracking-tight text-ink">Four things to look at on this page</h2>
        </div>
        <Button variant="ghost" size="icon" onClick={dismiss} aria-label="Dismiss the guide"><X aria-hidden="true" /></Button>
      </div>
      <ol className="relative mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {STEPS.map((step, i) => (
          <li key={step.title}>
            <Link href={step.href} className="flex h-full gap-3 rounded-xl border border-line bg-bg/60 p-3.5 transition-colors hover:border-accent hover:bg-accent-soft/40">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent"><step.icon className="size-4" aria-hidden="true" /></span>
              <span>
                <span className="block text-sm font-semibold text-ink"><span className="sr-only">Step {i + 1}: </span>{step.title}</span>
                <span className="mt-0.5 block text-[13px] leading-snug text-muted">{step.text}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
      <div className="relative mt-4 flex justify-end">
        <Button variant="outline" size="sm" onClick={dismiss}>Got it, hide this</Button>
      </div>
    </section>
  );
}
