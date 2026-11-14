"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { PointsChart } from "@/components/charts";
import { DataTable, type Column } from "@/components/DataTable";
import {
  BandBadge, Card, EmptyState, ErrorState, KpiSkeletons, KpiTile, LoadingBlock, PageHeader, Pill, Term,
} from "@/components/ui";
import type { BorrowerDetail } from "@/lib/api";
import { date, dateTime, int, pct, ratio, score, titleCase } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Loan = BorrowerDetail["loans"][number];
type Message = BorrowerDetail["messages"][number];

const LOAN_COLUMNS: Column<Loan>[] = [
  { key: "loan_id", header: "Loan", sortValue: (r) => r.loan_id, cell: (r) => r.loan_id },
  { key: "lender", header: "Lender", sortValue: (r) => r.lender, cell: (r) => r.lender },
  { key: "principal", header: "Principal (UGX)", align: "right", sortValue: (r) => r.principal.amount ?? 0,
    cell: (r) => int(r.principal.amount) },
  { key: "owed", header: "Still owed (UGX)", align: "right", sortValue: (r) => r.owed.amount ?? 0,
    cell: (r) => int(r.owed.amount) },
  { key: "issue_date", header: "Issued", sortValue: (r) => r.issue_date, cell: (r) => date(r.issue_date) },
  { key: "due_date", header: "Due", sortValue: (r) => r.due_date, cell: (r) => date(r.due_date) },
  { key: "status", header: "Status", sortValue: (r) => r.status,
    cell: (r) => <Pill tone={r.status.includes("arrears") ? "amber" : r.status === "repaid" ? "teal" : "slate"}>{titleCase(r.status)}</Pill> },
];

function MessageCard({ m }: { m: Message }) {
  return (
    <li className="rounded-xl border border-line p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="font-medium text-ink-2">{m.lender}</span>
        <span aria-hidden="true">·</span>
        <time dateTime={m.sent_at.replace(" ", "T")}>{dateTime(m.sent_at)}</time>
        <span className="ml-auto flex flex-wrap gap-1.5">
          <Pill tone={m.label.abusive ? "rose" : "slate"}>
            {m.label.abusive ? `Labelled abusive: ${m.label.label}` : `Labelled ${m.label.label.toLowerCase()}`}
          </Pill>
          {m.late_night && <Pill tone="amber">Late night</Pill>}
          {m.third_party && <Pill tone="amber">Sent to a third party</Pill>}
        </span>
      </div>
      <p className="mt-2 text-[15px] leading-relaxed text-ink">{m.text}</p>
    </li>
  );
}

export default function BorrowerPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = decodeURIComponent(params.id);
  const { data, error, loading, reload } = useApi<BorrowerDetail>(`/api/borrowers/${encodeURIComponent(id)}`);

  const back = (
    <button type="button" onClick={() => (window.history.length > 1 ? router.back() : router.push("/borrowers"))}
            className="rounded-lg border border-line px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2">
      ← Back to borrowers
    </button>
  );

  return (
    <>
      <PageHeader title={`Borrower ${id}`}
                  intro={data ? <>Region {data.region}. Loans with {data.lenders_involved} lender(s). This cross-lender view
                    is what no single lender can see.</> : undefined}>
        {back}
      </PageHeader>

      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <div className="space-y-6"><KpiSkeletons /><LoadingBlock rows={8} /></div>}

      {data && !error && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <KpiTile compact accent="navy" label={<Term k="overlap_score">Score</Term>} value={score(data.score)}
                     detail={<span className="inline-flex items-center gap-1.5">Band <BandBadge band={data.band} /></span>} />
            <KpiTile compact accent="teal" label="Open lenders" value={int(data.open_lenders)} />
            <KpiTile compact accent="amber" label="Total owed" value={data.total_owed.compact} detail={data.total_owed.exact} />
            <KpiTile compact accent="teal" label="Monthly income" value={data.monthly_income.compact} detail={data.monthly_income.exact} />
            <KpiTile compact accent="rose" label={<Term k="labelled_abusive">Labelled abusive</Term>} value={int(data.abusive_messages)}
                     detail="messages received" />
          </div>

          {data.placed_in_medium_by_cycling && (
            <div role="note" className="rounded-xl border border-amber/50 bg-tint-amber p-4 text-sm text-[#7c2d12] dark:bg-[#3a2410] dark:text-[#fde6c4]">
              Placed in the medium band because of repeated <Term k="cycling">cycling</Term> (borrowing to repay), although the
              score alone is below the medium threshold.
            </div>
          )}

          <div className="grid gap-6 xl:grid-cols-2">
            <Card id="why" title="Why this borrower scored as they did"
                  subtitle={`Debt is ${ratio(data.debt_to_income)} times monthly income; ${pct(data.arrears_share, 0)} of it is in arrears.`}>
              {data.explanation.length ? (
                <ul className="space-y-2 text-[15px] leading-relaxed text-ink-2">
                  {data.explanation.map((line) => (
                    <li key={line} className="flex gap-2">
                      <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--series)]" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">No signal added points for this borrower.</p>}
              <p className="mt-4 text-xs text-muted">This explains why a person should look. It is not a verdict.</p>
            </Card>
            <Card id="points" title="Score breakdown" subtitle="Points from each signal, out of the most it can add.">
              <PointsChart points={data.points} />
            </Card>
          </div>

          <Card id="loans" title="Loans across all lenders" subtitle="Each lender only knows its own loans.">
            {data.loans.length ? (
              <DataTable caption={`Loans of borrower ${id}`} columns={LOAN_COLUMNS} rows={data.loans}
                         rowKey={(r) => r.loan_id} maxHeight="28rem" initialSort={{ key: "issue_date", order: "asc" }} />
            ) : <EmptyState title="No loans recorded for this borrower." />}
          </Card>

          <Card id="messages" title={`Messages received (${data.messages.length})`}
                subtitle={<>Labels come from the &apos;{data.classifier}&apos; classifier and are a model&apos;s guesses. Late night
                  and third party are facts of the message. Personal details in the text are replaced by [PHONE], [EMAIL], [ID] or [NAME].</>}>
            {data.messages.length ? (
              <ul className="max-h-[36rem] space-y-3 overflow-y-auto pr-1">
                {data.messages.map((m) => <MessageCard key={m.message_id} m={m} />)}
              </ul>
            ) : <EmptyState title="No collection messages for this borrower." />}
          </Card>

          <p className="text-sm"><Link href="/borrowers" className="font-medium text-accent hover:underline">← All borrowers</Link></p>
        </div>
      )}
    </>
  );
}
