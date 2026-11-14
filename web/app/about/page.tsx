"use client";

import { useDatasetApi } from "@/components/SessionProvider";
import { Card, ErrorState, LoadingBlock, PageHeader, Pill } from "@/components/ui";
import type { About } from "@/lib/api";
import { pct } from "@/lib/format";

export default function AboutPage() {
  const { data, error, loading, reload } = useDatasetApi<About>("/api/about");

  return (
    <>
      <PageHeader title="About FairLend Watch"
                  intro="What the system is, who it is for, how the score works, and what it cannot do." />
      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <LoadingBlock rows={10} label="Loading" />}
      {data && !error && (
        <div className="space-y-6">
          <div role="note" className="rounded-2xl border border-amber/50 bg-tint-amber p-5 text-[#7c2d12] dark:bg-[#3a2410] dark:text-[#fde6c4]">
            <p className="text-lg font-semibold">A flag is a prompt, not a verdict.</p>
            <p className="mt-1 text-sm">{data.review_line} A high score or a top rank means a person should read the file. It is
              never a finding of over-indebtedness or misconduct.</p>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card id="what" title="What it is">
              <p className="text-[15px] leading-relaxed text-ink-2"><strong className="text-ink">{data.product.name}</strong> ({data.product.tagline.toLowerCase()})
                gives a view across lenders that no single lender has. It scores each borrower for signs of over-indebtedness
                from overlapping app loans, and compares lenders by how their collection messages read. It points a person at
                files worth reading. It decides nothing.</p>
            </Card>
            <Card id="who" title="Who it is for">
              <p className="text-[15px] leading-relaxed text-ink-2">A regulator, a consumer-protection body or a lenders&apos;
                association that receives data from several lenders and wants to know whose files to open first. It is not
                for scoring individual credit decisions and it never contacts borrowers or lenders.</p>
            </Card>
          </div>

          <Card id="signals" title="The five signals in the borrower score"
                subtitle={`Each signal earns a share of its weight, reaching full points at the value shown. The weights add up to 100. Bands: low below ${data.bands.medium}, medium from ${data.bands.medium}, high from ${data.bands.high}.`}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[36rem] text-sm">
                <caption className="sr-only">The five score signals</caption>
                <thead><tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th scope="col" className="px-2 py-2">Signal</th><th scope="col" className="px-2 py-2">What it measures</th>
                  <th scope="col" className="px-2 py-2 text-right">Full points at</th><th scope="col" className="px-2 py-2 text-right">Weight</th>
                </tr></thead>
                <tbody>
                  {data.signals.map((s) => (
                    <tr key={s.key} className="border-b border-line/70 last:border-0">
                      <th scope="row" className="px-2 py-2.5 text-left font-medium text-ink">{s.signal}</th>
                      <td className="px-2 py-2.5 text-ink-2">{s.measures}</td>
                      <td className="tabular px-2 py-2.5 text-right text-ink-2">{s.full_at}</td>
                      <td className="tabular px-2 py-2.5 text-right font-semibold text-ink">{s.weight}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.cycling_rule && (
              <p className="mt-3 text-sm text-ink-2">A borrower with {data.cycling_rule.min_events} or more cycling events
                (borrowing to repay) is placed in at least the medium band, even if the score alone is lower. Their page says so.</p>
            )}
            <p className="mt-2 text-xs text-muted">All values are read from config.yaml.</p>
          </Card>

          <Card id="classes" title="What the message model labels" subtitle={data.label_note}>
            <ul className="space-y-3">
              {data.classes.map((c) => (
                <li key={c.key} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
                  <span className="flex shrink-0 flex-wrap gap-1 sm:w-64">
                    <Pill tone={c.abusive ? "rose" : "slate"}>{c.label}</Pill>
                    {c.abusive && <Pill tone="rose">counts as abusive</Pill>}
                  </span>
                  <span className="text-sm text-ink-2">{c.description}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-sm text-ink-2">Labels come from the &apos;{data.classifier}&apos; classifier, except where a person has
              checked a message on the Review labels page ({pct(data.human_share)} of messages in this dataset): there the person&apos;s
              label is used. Lenders are compared only with at least {data.min_lender_messages} messages, and ranked by the low end
              of the {Math.round(data.confidence * 100)}% confidence interval.</p>
          </Card>

          <Card id="limits" title="Limits">
            <ul className="list-disc space-y-2 pl-5 text-[15px] leading-relaxed text-ink-2">
              <li><strong className="text-ink">This is demonstration data.</strong> The people, loans, lenders and messages are made up for showing how the tool works.</li>
              <li><strong className="text-ink">Accuracy is optimistic.</strong> The built-in data was generated to be separable; other data is usually messier.</li>
              <li><strong className="text-ink">Labels are a model&apos;s guesses about wording.</strong> The model was trained on the built-in demonstration text and makes no legal judgement. Check a sample before relying on them.</li>
              <li><strong className="text-ink">Imported datasets are labelled demonstration data too.</strong> The upload check refuses phone numbers, ID numbers and email addresses; it says nothing else about where the data came from.</li>
              <li><strong className="text-ink">Some harassed borrowers have a low risk score.</strong> Their problem is the messages, not the debt: filter by messages labelled abusive on the Borrowers page.</li>
              <li><strong className="text-ink">Cycling borrowers are flagged mainly by the cycling rule,</strong> not by their score.</li>
              <li><strong className="text-ink">A person decides.</strong> A flag or a rank means someone should look. It is never a finding or a verdict.</li>
            </ul>
          </Card>
        </div>
      )}
    </>
  );
}
