"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { BandChart } from "@/components/charts";
import { DataTable, type Column } from "@/components/DataTable";
import {
  BandBadge, Card, ErrorState, KpiSkeletons, KpiTile, LoadingBlock, PageHeader, Skeleton, Term,
} from "@/components/ui";
import type { Overview, TopBorrower } from "@/lib/api";
import { date, int, pct, score } from "@/lib/format";
import { useDatasetApi } from "@/components/SessionProvider";

const TOP_COLUMNS: Column<TopBorrower>[] = [
  { key: "borrower_id", header: "Borrower", sortValue: (r) => r.borrower_id,
    cell: (r) => <Link href={`/borrowers/${r.borrower_id}`} className="font-medium text-accent hover:underline">{r.borrower_id}</Link> },
  { key: "score", header: "Score", align: "right", sortValue: (r) => r.score, cell: (r) => score(r.score) },
  { key: "band", header: "Band", sortValue: (r) => r.score, cell: (r) => <BandBadge band={r.band} /> },
  { key: "open_lenders", header: "Open lenders", align: "right", sortValue: (r) => r.open_lenders,
    cell: (r) => int(r.open_lenders) },
  { key: "total_owed", header: "Total owed (UGX)", align: "right", sortValue: (r) => r.total_owed.amount ?? 0,
    cell: (r) => int(r.total_owed.amount) },
  { key: "abusive_messages", header: "Labelled abusive", name: "messages labelled abusive", align: "right",
    sortValue: (r) => r.abusive_messages, cell: (r) => int(r.abusive_messages) },
];

export default function OverviewPage() {
  const { data, error, loading, reload } = useDatasetApi<Overview>("/api/overview");
  const router = useRouter();

  return (
    <>
      <PageHeader
        title="Overview"
        intro={data
          ? <>Who may be over-borrowing across lenders, and which lenders send messages labelled abusive.{" "}
            {data.dataset.kind === "demo" ? "Synthetic demo dataset" : `${data.dataset.name} (imported, passed the synthetic-only check)`}, data as of {date(data.dataset.as_of_date)}.</>
          : "Who may be over-borrowing across lenders, and which lenders send messages labelled abusive."}
      />

      {error && !data && <ErrorState message={error} onRetry={reload} />}

      {loading && !data && !error && (
        <div className="space-y-6">
          <KpiSkeletons />
          <div className="grid gap-6 xl:grid-cols-5">
            <div className="rounded-2xl border border-line bg-surface p-5 xl:col-span-2"><Skeleton className="h-64 w-full" /></div>
            <div className="rounded-2xl border border-line bg-surface p-5 xl:col-span-3"><LoadingBlock rows={7} /></div>
          </div>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile accent="navy" label="Borrowers scored" value={int(data.kpis.borrowers_scored)}
                     detail={<>across {int(data.kpis.lenders_ranked + data.kpis.lenders_unranked)} lenders</>} />
            <KpiTile accent="rose" label={<>High <Term k="band">band</Term></>} value={int(data.kpis.band_counts.high)}
                     detail={`${pct(data.kpis.band_shares.high)} of borrowers`} />
            <KpiTile accent="amber" label="Medium band" value={int(data.kpis.band_counts.medium)}
                     detail={`${pct(data.kpis.band_shares.medium)} · ${int(data.kpis.band_counts.low)} in the low band`} />
            <KpiTile accent="teal" label="Owed by the high band" value={data.kpis.owed_by_high_band.compact}
                     detail={`Exact: ${data.kpis.owed_by_high_band.exact}`}
                     help={`Owed by high-band borrowers. Exact amount: ${data.kpis.owed_by_high_band.exact}`} />
          </div>

          <div className="grid gap-6 xl:grid-cols-5">
            <Card id="bands" className="xl:col-span-2" title="Borrowers per risk band"
                  subtitle={<>Bands group the <Term k="overlap_score">overlap score</Term>.</>}>
              <BandChart bands={data.bands} />
            </Card>

            <Card id="top" className="xl:col-span-3" title="Highest-scoring borrowers"
                  subtitle={`The ${data.top_n} borrowers with the highest overlap score. Select a row to see why.`}
                  actions={<Link href="/borrowers" className="text-sm font-medium text-accent hover:underline">All borrowers →</Link>}>
              <DataTable caption={`The ${data.top_n} highest-scoring borrowers`} columns={TOP_COLUMNS}
                         rows={data.top_borrowers} rowKey={(r) => r.borrower_id} maxHeight="none"
                         onRowClick={(r) => router.push(`/borrowers/${r.borrower_id}`)}
                         rowLabel={(r) => `Borrower ${r.borrower_id}, score ${score(r.score)}, ${r.band.label} band`} />
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card id="meaning" className="lg:col-span-2" title="What this means">
              <ul className="space-y-2.5 text-[15px] leading-relaxed text-ink-2">
                <li>
                  <strong className="text-ink">{int(data.kpis.band_counts.high)} borrowers ({pct(data.kpis.band_shares.high)})</strong> are in
                  the high band. Together they owe <strong className="text-ink">{data.kpis.owed_by_high_band.compact}</strong>.
                  Their loans are spread across several lenders, which no single lender can see on its own.
                </li>
                <li>
                  <strong className="text-ink">{int(data.kpis.flagged_and_harassed)}</strong> borrowers in the medium or high band also
                  received {data.kpis.concern_min_abusive_messages} or more messages <Term k="labelled_abusive">labelled abusive</Term>.
                  They are a sensible place to start.
                </li>
                <li>
                  {pct(data.kpis.abusive_message_share)} of {int(data.kpis.messages_classified)} collection messages are labelled
                  abusive. {data.kpis.lenders_ranked} lenders are compared on the <Link href="/lenders" className="font-medium text-accent hover:underline">Lenders</Link> page;
                  {" "}{data.kpis.lenders_unranked} {data.kpis.lenders_unranked === 1 ? "is" : "are"} <Term k="too_small">too small to rank</Term>.
                </li>
                <li>
                  A high score means <em>a person should look</em>. It is not proof of over-indebtedness or misconduct.
                </li>
              </ul>
            </Card>
            <Card id="next" title="Where to go next">
              <ul className="space-y-3 text-sm">
                <li><Link href="/borrowers" className="font-medium text-accent hover:underline">Borrowers</Link>
                  <span className="text-muted"> — filter, sort and open one borrower&apos;s loans and messages.</span></li>
                <li><Link href="/lenders" className="font-medium text-accent hover:underline">Lenders</Link>
                  <span className="text-muted"> — the share of messages labelled abusive, with confidence intervals.</span></li>
                <li><Link href="/repayments" className="font-medium text-accent hover:underline">Repayments</Link>
                  <span className="text-muted"> — who pays on time, who pays late, and a follow-up list.</span></li>
              </ul>
              <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-muted">{data.coverage}</p>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
