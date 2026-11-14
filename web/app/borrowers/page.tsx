"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import {
  BandBadge, Card, ChipGroup, EmptyState, ErrorState, Field, inputClass, LoadingBlock, PageHeader, Pagination, Pill, Term,
} from "@/components/ui";
import type { BandKey, BorrowerList, BorrowerRow } from "@/lib/api";
import { int, ratio, score } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const BAND_OPTIONS: { key: BandKey; label: string }[] = [
  { key: "high", label: "High" }, { key: "medium", label: "Medium" }, { key: "low", label: "Low" },
];

const COLUMNS: Column<BorrowerRow>[] = [
  { key: "borrower_id", header: "Borrower",
    cell: (r) => <Link href={`/borrowers/${r.borrower_id}`} className="font-medium text-accent hover:underline"
                       onClick={(e) => e.stopPropagation()}>{r.borrower_id}</Link> },
  { key: "score", header: "Score", align: "right", cell: (r) => score(r.score) },
  { key: "band", header: "Band",
    cell: (r) => (
      <span className="inline-flex items-center gap-1.5">
        <BandBadge band={r.band} />
        {r.placed_in_medium_by_cycling && <Pill tone="amber">cycling rule</Pill>}
      </span>) },
  { key: "region", header: "Region", cell: (r) => r.region },
  { key: "open_lenders", header: "Open lenders", align: "right", cell: (r) => int(r.open_lenders) },
  { key: "total_owed", header: "Total owed (UGX)", align: "right", cell: (r) => int(r.total_owed.amount) },
  { key: "debt_to_income", header: "Debt / income", align: "right", cell: (r) => ratio(r.debt_to_income) },
  { key: "abusive_messages", header: "Labelled abusive", align: "right", cell: (r) => int(r.abusive_messages) },
  { key: "late_night_messages", header: "Late-night msgs", align: "right", cell: (r) => int(r.late_night_messages) },
  { key: "third_party_messages", header: "Third-party msgs", align: "right", cell: (r) => int(r.third_party_messages) },
];

function list(value: string | null): string[] {
  return (value ?? "").split(",").filter(Boolean);
}

function BorrowersInner() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();

  const bands = list(search.get("bands")) as BandKey[];
  const regions = list(search.get("regions"));
  const minScore = Number(search.get("min_score") ?? 0) || 0;
  const minLenders = Number(search.get("min_open_lenders") ?? 0) || 0;
  const minAbusive = Number(search.get("min_abusive") ?? 0) || 0;
  const q = search.get("q") ?? "";
  const sort = search.get("sort") ?? "score";
  const order = (search.get("order") ?? "desc") as "asc" | "desc";
  const page = Number(search.get("page") ?? 1) || 1;

  const [qDraft, setQDraft] = useState(q);

  function update(changes: Record<string, string | number | null>, resetPage = true) {
    const next = new URLSearchParams(search.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "" || value === 0) next.delete(key);
      else next.set(key, String(value));
    }
    if (resetPage && !("page" in changes)) next.delete("page");
    const text = next.toString();
    router.replace(`${pathname}${text ? `?${text}` : ""}`, { scroll: false });
  }

  useEffect(() => {
    if (qDraft === q) return;
    const timer = setTimeout(() => update({ q: qDraft.trim() || null }), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qDraft]);

  const { data, error, loading, reload } = useApi<BorrowerList>("/api/borrowers", {
    bands: bands.join(","), regions: regions.join(","), min_score: minScore || undefined,
    min_open_lenders: minLenders || undefined, min_abusive: minAbusive || undefined, q: q || undefined,
    sort, order, page,
  });

  const filtersOn = bands.length || regions.length || minScore || minLenders || minAbusive || q;

  return (
    <>
      <PageHeader title="Borrowers"
                  intro={<>Every borrower with an <Term k="overlap_score">overlap score</Term>. Filter the list, sort any
                    column with an arrow, and open a borrower to see their loans across every lender and the messages they received.</>} />

      <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <Card id="filters" title="Filters" className="h-fit lg:sticky lg:top-16"
              actions={filtersOn ? (
                <button type="button" className="text-sm font-medium text-accent hover:underline"
                        onClick={() => { setQDraft(""); router.replace(pathname, { scroll: false }); }}>
                  Clear all
                </button>) : undefined}>
          <div className="space-y-5">
            <Field label="Borrower code contains" htmlFor="q">
              <input id="q" type="search" value={qDraft} maxLength={40} placeholder="e.g. B0042"
                     onChange={(e) => setQDraft(e.target.value)} className={inputClass} autoComplete="off" />
            </Field>
            <ChipGroup legend="Band" options={BAND_OPTIONS} value={bands}
                       onChange={(value) => update({ bands: value.join(",") || null })} />
            {data && (
              <ChipGroup legend="Region (none = all)" options={data.regions.map((r) => ({ key: r, label: r }))}
                         value={regions} onChange={(value) => update({ regions: value.join(",") || null })} />
            )}
            <Field label={`Minimum score: ${minScore}`} htmlFor="min_score">
              <input id="min_score" type="range" min={0} max={100} step={1} value={minScore}
                     onChange={(e) => update({ min_score: Number(e.target.value) })}
                     className="w-full accent-[var(--accent)]" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Min. open lenders" htmlFor="min_open_lenders">
                <input id="min_open_lenders" type="number" min={0} value={minLenders} className={inputClass}
                       onChange={(e) => update({ min_open_lenders: Math.max(0, Number(e.target.value) || 0) })} />
              </Field>
              <Field label="Min. abusive" htmlFor="min_abusive">
                <input id="min_abusive" type="number" min={0} value={minAbusive} className={inputClass}
                       onChange={(e) => update({ min_abusive: Math.max(0, Number(e.target.value) || 0) })} />
              </Field>
            </div>
          </div>
        </Card>

        <Card id="list" title={data ? `${int(data.matching)} of ${int(data.total)} borrowers match` : "Borrowers"}
              subtitle="Sorted by the column with the filled arrow. Select a row to open the borrower.">
          {error && <ErrorState message={error} onRetry={reload} />}
          {!error && loading && !data && <LoadingBlock rows={10} label="Loading borrowers" />}
          {data && !error && (
            data.items.length === 0 ? (
              <EmptyState title="No borrower matches these filters.">Try removing a filter or lowering the minimum score.</EmptyState>
            ) : (
              <div className={loading ? "opacity-60 transition-opacity" : ""} aria-busy={loading}>
                <DataTable caption="Borrowers matching the filters" columns={COLUMNS} rows={data.items}
                           rowKey={(r) => r.borrower_id}
                           onRowClick={(r) => router.push(`/borrowers/${r.borrower_id}`)}
                           rowLabel={(r) => `Borrower ${r.borrower_id}, score ${score(r.score)}, ${r.band.label} band`}
                           server={{ key: data.sort, order: data.order, sortable: data.sortable,
                                     onSort: (key, next) => update({ sort: key === "score" ? null : key, order: next === "desc" ? null : next }) }} />
                <Pagination page={data.page} pages={data.pages} label="Borrower list pages"
                            onPage={(p) => update({ page: p === 1 ? null : p }, false)} />
              </div>
            )
          )}
        </Card>
      </div>
    </>
  );
}

export default function BorrowersPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={10} label="Loading borrowers" />}>
      <BorrowersInner />
    </Suspense>
  );
}
