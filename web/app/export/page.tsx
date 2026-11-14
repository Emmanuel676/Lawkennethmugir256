"use client";

import { useState } from "react";

import { DEMO, useDatasetApi, useSession } from "@/components/SessionProvider";
import { Card, ChipGroup, ErrorState, Field, inputClass, LoadingBlock, PageHeader } from "@/components/ui";
import { apiUrl, type BandKey, type ExportSummary } from "@/lib/api";
import { int } from "@/lib/format";

const BAND_OPTIONS: { key: BandKey; label: string }[] = [
  { key: "high", label: "High" }, { key: "medium", label: "Medium" }, { key: "low", label: "Low" },
];

function Download({ href, label, name }: { href: string; label: string; name: string }) {
  return (
    <a href={href} download={name}
       className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90">
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12m0 0-4-4m4 4 4-4M4 21h16" /></svg>
      {label}
    </a>
  );
}

export default function ExportPage() {
  const { dataset } = useSession();
  const [bands, setBands] = useState<BandKey[]>(["high", "medium"]);
  const [minAbusive, setMinAbusive] = useState(0);
  const filters = { bands: bands.join(","), min_abusive: minAbusive || undefined };
  const { data, error, loading, reload } = useDatasetApi<ExportSummary>("/api/export", filters);
  const ds = dataset === DEMO ? undefined : dataset;

  return (
    <>
      <PageHeader title="Export"
                  intro={<>The same downloads as the Streamlit Export page. Each file starts with one line beginning with
                    <code className="mx-1 rounded bg-surface-2 px-1">#</code> that carries the dataset notice. Read it with
                    <code className="mx-1 rounded bg-surface-2 px-1">pandas.read_csv(path, comment=&quot;#&quot;)</code>; in Excel the notice is the first row.</>} />
      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <LoadingBlock rows={6} label="Loading export counts" />}
      {data && !error && (
        <div className="space-y-5">
          <p className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2">
            <span className="font-semibold text-ink">First line of every file: </span>#{" "}{data.notice}
          </p>

          <Card id="flagged" title="Flagged borrowers" subtitle="Borrowers in the chosen bands, with their score, band, signals and message counts.">
            <div className="grid gap-4 md:grid-cols-[1fr_14rem]">
              <ChipGroup legend="Bands to include (none = every borrower)" options={BAND_OPTIONS} value={bands} onChange={setBands} />
              <Field label="Minimum messages labelled abusive" htmlFor="min-abusive">
                <input id="min-abusive" type="number" min={0} value={minAbusive} className={inputClass}
                       onChange={(e) => setMinAbusive(Math.max(0, Number(e.target.value) || 0))} />
              </Field>
            </div>
            <p className="mt-4 text-sm font-medium text-ink" aria-live="polite">{int(data.flagged_borrowers)} borrowers will be exported.</p>
            <div className="mt-3">
              <Download href={apiUrl("/api/export/flagged-borrowers.csv", { ...filters, bands: bands.join(","), dataset: ds })}
                        label="Download flagged borrowers (CSV)" name="flagged_borrowers.csv" />
            </div>
          </Card>

          <Card id="lenders" title="Lender comparison"
                subtitle={`${int(data.lenders)} lenders (ranked and too small to rank). Labels come from the '${data.classifier}' classifier; the file says what share a person has checked.`}>
            <Download href={apiUrl("/api/export/lender-comparison.csv", { dataset: ds })} label="Download lender comparison (CSV)" name="lender_comparison.csv" />
          </Card>

          <Card id="follow" title="Repayment follow-up list"
                subtitle={`${int(data.follow_up_borrowers)} borrowers with a loan not paying or overdue but paying. A follow-up prompt, not a verdict or a credit score. Filter it on the Repayments page first if you need a subset.`}>
            <Download href={apiUrl("/api/repayments/follow-up.csv", { dataset: ds })} label="Download the follow-up list (CSV)" name="repayment_follow_up.csv" />
          </Card>

          <p className="text-xs text-muted">The demo&apos;s exports are open to everyone. An imported dataset&apos;s exports need a signed-in Viewer, Importer or Admin.</p>
        </div>
      )}
    </>
  );
}
