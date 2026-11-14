"use client";

import { useState } from "react";

import { AgeingChart, StatusChart } from "@/components/charts";
import { DataTable, type Column } from "@/components/DataTable";
import {
  BandBadge, Card, ChipGroup, EmptyState, ErrorState, KpiSkeletons, KpiTile, LoadingBlock, PageHeader, Pagination, Pill,
  Skeleton, Term,
} from "@/components/ui";
import { apiUrl, type FollowUp, type FollowUpRow, type Repayments } from "@/lib/api";
import { int, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type MixRow = Repayments["lender_mix"][number];

const FOLLOW_COLUMNS: Column<FollowUpRow>[] = [
  { key: "borrower_id", header: "Borrower code", cell: (r) => <span className="font-medium text-ink">{r.borrower_id}</span> },
  { key: "status", header: "Worst status",
    cell: (r) => <Pill tone={r.status.key === "not_paying" ? "rose" : "amber"}>{r.status.label}</Pill> },
  { key: "days_past_due", header: "Days past due", align: "right", cell: (r) => int(r.days_past_due) },
  { key: "owed_overdue", header: "Owed, overdue (UGX)", align: "right", cell: (r) => int(r.owed_overdue.amount) },
  { key: "owed_all_loans", header: "Owed, all loans (UGX)", align: "right", cell: (r) => int(r.owed_all_loans.amount) },
  { key: "loans_overdue", header: "Loans overdue", align: "right", cell: (r) => int(r.loans_overdue) },
  { key: "lenders_overdue", header: "Lenders overdue", cell: (r) => r.lenders_overdue },
  { key: "band", header: "Risk band", cell: (r) => <BandBadge band={r.band} /> },
  { key: "open_lenders", header: "Open lenders", align: "right", cell: (r) => int(r.open_lenders) },
];

function mixColumns(statuses: Repayments["statuses"]): Column<MixRow>[] {
  return [
    { key: "name", header: "Lender", sortValue: (r) => r.name,
      cell: (r) => (
        <span className="inline-flex items-center gap-2">
          <span className="font-medium text-ink">{r.name}</span>
          {!r.comparable && <Pill>Too small to compare</Pill>}
        </span>) },
    { key: "loans", header: "Loans", align: "right", sortValue: (r) => r.loans, cell: (r) => int(r.loans) },
    ...statuses.map((s): Column<MixRow> => ({
      key: s.key, header: s.label, align: "right", sortValue: (r) => r.shares[s.key] ?? 0,
      cell: (r) => pct(r.shares[s.key]),
    })),
  ];
}

function FollowUpList({ total }: { total: number }) {
  const [lenders, setLenders] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [bands, setBands] = useState<string[]>([]);
  const [sort, setSort] = useState("days_past_due");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const params = { lenders: lenders.join("|"), statuses: statuses.join(","), bands: bands.join(","), sort, order };
  const { data, error, loading, reload } = useApi<FollowUp>("/api/repayments/follow-up", { ...params, page });

  function reset<T>(setter: (v: T) => void) {
    return (value: T) => { setter(value); setPage(1); };
  }

  return (
    <Card id="follow-up" title="Follow-up list"
          subtitle={<>Borrowers (by code only) with at least one loan not paying or overdue but paying, with the cross-lender
            context from the risk score. A list for a person to work through: not a ranking of borrowers, not a verdict and not a
            credit score.</>}
          actions={
            <a href={apiUrl("/api/repayments/follow-up.csv", params)} download="repayment_follow_up.csv"
               className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-ink hover:opacity-90">
              <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v12m0 0-4-4m4 4 4-4M4 21h16" /></svg>
              Download CSV
            </a>}>
      {data && (
        <div className="mb-4 grid gap-4 md:grid-cols-3">
          <ChipGroup legend="Status (none = all)" options={data.options.statuses} value={statuses} onChange={reset(setStatuses)} />
          <ChipGroup legend="Risk band (none = all)" options={data.options.bands} value={bands} onChange={reset(setBands)} />
          <div className="min-w-0">
            <label htmlFor="fu-lender" className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              Lender overdue (none = all)
            </label>
            <select id="fu-lender" value={lenders[0] ?? ""}
                    onChange={(e) => reset(setLenders)(e.target.value ? [e.target.value] : [])}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink">
              <option value="">All lenders</option>
              {data.options.lenders.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </div>
        </div>
      )}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <LoadingBlock rows={8} label="Loading the follow-up list" />}
      {data && !error && (
        <>
          <p className="mb-3 text-sm font-medium text-ink" aria-live="polite">
            {int(data.matching)} borrowers in the follow-up list{data.matching !== total && ` (of ${int(total)})`}.
          </p>
          {data.items.length === 0 ? (
            <EmptyState title="No borrower matches these filters.">Remove a filter to see more of the list.</EmptyState>
          ) : (
            <div className={loading ? "opacity-60 transition-opacity" : ""} aria-busy={loading}>
              <DataTable caption="Follow-up list" columns={FOLLOW_COLUMNS} rows={data.items} rowKey={(r) => r.borrower_id}
                         server={{ key: data.sort, order: data.order, sortable: data.sortable,
                                   onSort: (key, next) => { setSort(key); setOrder(next); setPage(1); } }} />
              <Pagination page={data.page} pages={data.pages} onPage={setPage} label="Follow-up list pages" />
            </div>
          )}
          <p className="mt-3 text-xs text-muted">The CSV starts with one &apos;#&apos; line carrying the synthetic-data notice and the
            words &apos;follow-up prompt, not a verdict or a credit score&apos;. Read it with pandas.read_csv(path, comment=&quot;#&quot;).</p>
        </>
      )}
    </Card>
  );
}

export default function RepaymentsPage() {
  const { data, error, loading, reload } = useApi<Repayments>("/api/repayments");
  const share = (key: string) => data?.statuses.find((s) => s.key === key);

  return (
    <>
      <PageHeader title="Repayments"
                  intro="Who pays on time, who pays late, and who is not paying, so a person knows whose file to open. It says nothing about anyone's creditworthiness." />

      <div role="note" className="mb-6 rounded-xl border border-amber/50 bg-tint-amber p-4 text-sm leading-relaxed text-[#7c2d12] dark:bg-[#3a2410] dark:text-[#fde6c4]">
        <p className="font-semibold">{data?.trust_line ?? "Synthetic data. A flag is a prompt for a human to look, not a verdict."}</p>
        <p className="mt-1">{data?.prompt ?? "Follow-up prompt, not a verdict or a credit score."}{" "}
          {data?.owed_note ?? "The total owed includes loans that are not yet due."}</p>
      </div>

      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && (
        <div className="space-y-6"><KpiSkeletons />
          <div className="rounded-2xl border border-line bg-surface p-5"><Skeleton className="h-72 w-full" /></div></div>
      )}

      {data && !error && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile accent="teal" label="On time" value={pct(share("on_time")?.share)} detail={`${int(share("on_time")?.loans)} loans`} />
            <KpiTile accent="amber" label={<>Late within <Term k="grace_period">grace</Term></>}
                     value={pct(share("late_within_grace")?.share)} detail={`${int(share("late_within_grace")?.loans)} loans`} />
            <KpiTile accent="rose" label="Not paying" value={pct(share("not_paying")?.share)}
                     detail={`${int(share("not_paying")?.loans)} loans`} />
            <KpiTile accent="navy" label="Owed, unpaid loans" value={data.owed_unpaid.compact}
                     detail={<>Includes loans not yet due. {data.owed_follow_up.compact} is on loans not paying or overdue.</>}
                     help={`Exact: ${data.owed_unpaid.exact}`} />
          </div>

          {data.lump && (
            <p className="text-sm text-muted">In this dataset every loan was repaid in one payment, so &apos;overdue but paying&apos; is
              rare here. The daily-repayment story is shown on the synthetic sample packs (docs\ONBOARDING_DEMO.md).</p>
          )}

          <div className="grid gap-6 xl:grid-cols-2">
            <Card id="status" title="Loans by repayment status"
                  subtitle={`Shares of all ${int(data.loans)} loans. Grace is ${data.grace_days} days; 'not paying' means past due plus grace with no linked repayment in ${data.not_paying_after_days} days.`}>
              <StatusChart statuses={data.statuses} />
            </Card>
            <Card id="ageing" title="Unpaid loans by days past due" subtitle="Every unpaid loan, including those not yet due.">
              <AgeingChart buckets={data.ageing} />
              <div className="mt-4">
                <DataTable caption="Unpaid loans by days past due" rowKey={(r) => r.bucket} rows={data.ageing} maxHeight="none"
                           columns={[
                             { key: "bucket", header: "Days past due", cell: (r) => r.bucket },
                             { key: "loans", header: "Unpaid loans", align: "right", cell: (r) => int(r.loans) },
                             { key: "owed", header: "Owed (UGX)", align: "right", cell: (r) => int(r.owed.amount) },
                           ]} />
              </div>
            </Card>
          </div>

          <FollowUpList total={data.follow_up_borrowers} />

          <Card id="mix" title="Status mix per lender"
                subtitle={`Share of each lender's loans in each status. Lenders with fewer than ${data.min_loans_to_compare} loans are marked too small to compare.`}>
            <DataTable caption="Repayment status mix per lender" columns={mixColumns(data.statuses)} rows={data.lender_mix}
                       rowKey={(r) => r.lender_id} maxHeight="none" />
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card id="worst" title="Borrowers by their worst loan status"
                  subtitle="'Unknown' ranks just above 'on time', so missing information is never shown as a good record.">
              <DataTable caption="Borrowers by worst loan status" rows={data.worst_status} rowKey={(r) => r.key} maxHeight="none"
                         columns={[
                           { key: "label", header: "Worst loan status", cell: (r) => r.label },
                           { key: "borrowers", header: "Borrowers", align: "right", cell: (r) => int(r.borrowers) },
                         ]} />
            </Card>
            <Card id="limits" title="Known limits">
              <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-ink-2">
                {data.limits.map((line) => <li key={line}>{line}</li>)}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
