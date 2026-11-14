"use client";

import { useState } from "react";

import { LenderIntervalChart } from "@/components/charts";
import { DataTable, type Column } from "@/components/DataTable";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Pill, Skeleton, Term } from "@/components/ui";
import type { LenderDetail, LenderRow, Lenders } from "@/lib/api";
import { dateTime, int, pct, titleCase } from "@/lib/format";
import { useApi } from "@/lib/useApi";

function columns(level: string): Column<LenderRow>[] {
  return [
    { key: "rank", header: "Rank", align: "right", sortValue: (r) => r.rank ?? 999,
      cell: (r) => (r.rank ? `#${r.rank}` : <Pill>Too small</Pill>) },
    { key: "name", header: "Lender", sortValue: (r) => r.name, cell: (r) => <span className="font-medium text-ink">{r.name}</span> },
    { key: "size", header: "Size", sortValue: (r) => r.size, cell: (r) => titleCase(r.size) },
    { key: "messages", header: "Messages", align: "right", sortValue: (r) => r.messages, cell: (r) => int(r.messages) },
    { key: "abusive_share", header: "Labelled abusive", align: "right", sortValue: (r) => r.abusive_share,
      cell: (r) => <strong className="text-ink">{pct(r.abusive_share)}</strong> },
    { key: "interval", header: `${level} interval`, name: "confidence interval lower end", sortValue: (r) => r.interval_low,
      cell: (r) => `${pct(r.interval_low, 0)} to ${pct(r.interval_high, 0)}` },
    { key: "threat_share", header: "Threat", align: "right", sortValue: (r) => r.threat_share, cell: (r) => pct(r.threat_share) },
    { key: "shaming_share", header: "Shaming", align: "right", sortValue: (r) => r.shaming_share, cell: (r) => pct(r.shaming_share) },
    { key: "third_party_share", header: "Third party", align: "right", sortValue: (r) => r.third_party_share,
      cell: (r) => pct(r.third_party_share) },
    { key: "late_night_share", header: "Late night", align: "right", sortValue: (r) => r.late_night_share,
      cell: (r) => pct(r.late_night_share) },
    { key: "messages_per_borrower", header: "Msgs per borrower", align: "right", sortValue: (r) => r.messages_per_borrower,
      cell: (r) => r.messages_per_borrower.toFixed(1) },
  ];
}

function LenderPanel({ id }: { id: string }) {
  const { data, error, loading, reload } = useApi<LenderDetail>(`/api/lenders/${encodeURIComponent(id)}`);
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !data) return <LoadingBlock rows={5} label="Loading lender" />;
  return (
    <div className="space-y-5">
      <p className="text-[15px] leading-relaxed text-ink-2">{data.sentence}</p>
      {data.examples.map((group) => (
        <div key={group.class.key}>
          <h3 className="mb-2 text-sm font-semibold text-ink">Example messages labelled {group.class.label.toLowerCase()}</h3>
          {group.messages.length ? (
            <ul className="space-y-2">
              {group.messages.map((m) => (
                <li key={m.message_id} className="rounded-xl border border-line p-3">
                  <p className="text-xs text-muted">{dateTime(m.sent_at)} · to {m.recipient_type.replace("_", " ")}</p>
                  <p className="mt-1 text-[15px] leading-relaxed text-ink">{m.text}</p>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">None.</p>}
        </div>
      ))}
      <p className="text-xs text-muted">Examples were labelled by a model (the same ones every time). Read them yourself before
        drawing any conclusion. Personal details are replaced by [PHONE], [EMAIL], [ID] or [NAME].</p>
    </div>
  );
}

export default function LendersPage() {
  const { data, error, loading, reload } = useApi<Lenders>("/api/lenders");
  const [picked, setPicked] = useState<string>("");
  const level = data ? `${Math.round(data.confidence * 100)}%` : "95%";
  const all = data ? [...data.ranked, ...data.unranked] : [];

  return (
    <>
      <PageHeader title="Lenders"
                  intro={<>Lenders are ranked by the <strong>lower end</strong> of the {level} <Term k="confidence_interval">confidence
                    interval</Term> of the share of their messages <Term k="labelled_abusive">labelled abusive</Term> (threat or
                    shaming). A top rank means a person should read that lender&apos;s messages; it is not a finding of misconduct.</>} />

      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-line bg-surface p-5"><LoadingBlock rows={8} label="Loading lenders" /></div>
          <div className="rounded-2xl border border-line bg-surface p-5"><Skeleton className="h-72 w-full" /></div>
        </div>
      )}

      {data && !error && (
        <div className="space-y-6">
          <Card id="table" title="Lender comparison"
                subtitle={`${data.ranked.length} ranked · ${data.unranked.length} too small to rank (fewer than ${data.min_messages} messages). Sort any column.`}>
            {all.length ? (
              <DataTable caption="Lender comparison" columns={columns(level)} rows={all} rowKey={(r) => r.lender_id}
                         maxHeight="none" initialSort={{ key: "rank", order: "asc" }}
                         onRowClick={(r) => setPicked(r.lender_id)} rowLabel={(r) => `Open ${r.name}`} />
            ) : <EmptyState title="No lenders in this dataset." />}
            <p className="mt-3 text-xs leading-relaxed text-muted">{data.coverage}</p>
          </Card>

          <div className="grid gap-6 xl:grid-cols-5">
            <Card id="chart" className="xl:col-span-3" title="Share of messages labelled abusive, ranked lenders"
                  subtitle={`With the ${level} confidence interval for each lender.`}>
              {data.ranked.length ? <LenderIntervalChart lenders={data.ranked} confidence={data.confidence} />
                : <EmptyState title="No lender has enough messages to be ranked." />}
            </Card>
            <Card id="small" className="xl:col-span-2" title={<Term k="too_small">Too few messages to rank</Term>}>
              {data.unranked.length ? (
                <ul className="space-y-3 text-sm text-ink-2">
                  {data.unranked.map((r) => (
                    <li key={r.lender_id} className="rounded-xl border border-line p-3">
                      <p className="font-medium text-ink">{r.name} <span className="font-normal text-muted">({r.size})</span></p>
                      <p className="mt-1">{int(r.messages)} messages, minimum {data.min_messages}. Its share ({pct(r.abusive_share, 0)},
                        interval {pct(r.interval_low, 0)} to {pct(r.interval_high, 0)}) is too uncertain to compare.</p>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">Every lender has enough messages to be ranked.</p>}
            </Card>
          </div>

          <Card id="one" title="Look at one lender" subtitle="Choose a lender, or select a row in the table above.">
            <label htmlFor="lender-pick" className="sr-only">Lender</label>
            <select id="lender-pick" value={picked} onChange={(e) => setPicked(e.target.value)}
                    className="mb-4 w-full max-w-md rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink">
              <option value="">Choose a lender…</option>
              {all.map((r) => <option key={r.lender_id} value={r.lender_id}>{r.name}</option>)}
            </select>
            {picked ? <LenderPanel id={picked} /> : <p className="text-sm text-muted">No lender chosen yet.</p>}
          </Card>
        </div>
      )}
    </>
  );
}
