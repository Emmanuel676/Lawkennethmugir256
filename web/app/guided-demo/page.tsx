"use client";

import Link from "next/link";

import { useDatasetApi } from "@/components/SessionProvider";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Pill } from "@/components/ui";
import type { GuidedDemo } from "@/lib/api";

export default function GuidedDemoPage() {
  const { data, error, loading, reload } = useDatasetApi<GuidedDemo>("/api/guided-demo");

  return (
    <>
      <PageHeader title="Guided demo"
                  intro="A five-minute walkthrough: six steps, about 45 seconds each. Each step gives one sentence to say out loud, and its button opens the page already showing that case." />

      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <LoadingBlock rows={8} label="Loading the guided demo" />}

      {data && !error && !data.available && <EmptyState title="The guided demo is written for the demo dataset">{data.reason}</EmptyState>}

      {data && !error && data.available && (
        <div className="space-y-5">
          <Card id="opening" title="Say these three things at the start">
            <ol className="list-decimal space-y-1.5 pl-5 text-[15px] text-ink-2">
              {data.opening.map((line) => <li key={line}><strong className="text-ink">{line}</strong></li>)}
            </ol>
          </Card>

          <ol className="space-y-4" aria-label="Demo steps">
            {data.cases.map((c) => {
              const href = c.kind === "borrower" ? `/borrowers/${encodeURIComponent(c.id)}` : `/lenders?lender=${encodeURIComponent(c.id)}`;
              return (
                <li key={c.key}>
                  <Card>
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                      <span aria-hidden="true" className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent-soft text-lg font-bold text-accent">{c.step}</span>
                      <div className="min-w-0 flex-1">
                        <h2 className="text-base font-semibold text-ink"><span className="sr-only">Step {c.step}: </span>{c.title}</h2>
                        <p className="mt-2 text-[15px] leading-relaxed text-ink-2"><span className="font-semibold text-ink">Say: </span>{c.say}</p>
                        {c.counts && (
                          <div className="mt-3 flex flex-wrap gap-2" aria-label="Message counts behind this sentence">
                            <Pill>{c.counts.messages} messages</Pill>
                            <Pill tone="rose">{c.counts.abusive} labelled abusive</Pill>
                            <Pill tone="amber">{c.counts.abusive_late_night} of those late at night</Pill>
                            <Pill tone="amber">{c.counts.abusive_third_party} of those to other people</Pill>
                          </div>
                        )}
                      </div>
                      <Link href={href}
                            className="shrink-0 rounded-lg bg-accent px-3 py-2 text-center text-sm font-medium text-accent-ink hover:opacity-90">
                        Open on the {c.kind === "borrower" ? "Borrowers" : "Lenders"} page
                      </Link>
                    </div>
                  </Card>
                </li>
              );
            })}
          </ol>
          {data.missing.map((sentence) => <p key={sentence} className="text-sm text-muted">Step left out: {sentence}</p>)}
          <p className="text-xs text-muted">Cases are chosen by fixed rules from the computed scores and message labels
            (thresholds in the &apos;demo&apos; section of config.yaml), never from answer labels. Same data, same cases.
            The full spoken script, with timings and the hard questions, is in docs\DEMO_SCRIPT.md and docs\UI_V2.md.</p>
        </div>
      )}
    </>
  );
}
