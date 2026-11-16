"use client";

import { useState } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { RequireRole } from "@/components/RequireRole";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination, Pill } from "@/components/kit";
import type { AuditEntry, AuditPage } from "@/lib/api";
import { date, int } from "@/lib/format";
import { useApi } from "@/lib/useApi";

function when(seconds: number): string {
  const d = new Date(seconds * 1000);
  return `${date(d.toISOString())}, ${d.toTimeString().slice(0, 8)}`;
}

function details(entry: AuditEntry): string {
  const d = entry.detail as Record<string, unknown>;
  const parts: string[] = [];
  if (d.rows && typeof d.rows === "object") {
    parts.push(Object.entries(d.rows as Record<string, number>).map(([k, v]) => `${int(v)} ${v === 1 ? k.replace(/s$/, "") : k}`).join(", "));
  }
  if (typeof d.already_known === "number" && d.already_known > 0) parts.push(`${int(d.already_known)} borrower codes already known`);
  if (typeof d.reasons === "number") parts.push(`${d.reasons} reason(s) given`);
  if (typeof d.errors === "number") parts.push(`${int(d.errors)} error(s)`);
  if (typeof d.from === "string") parts.push(`${d.from} → ${d.to}`);
  if (typeof d.role === "string") parts.push(`role ${d.role}`);
  if (typeof d.minutes === "number") parts.push(`${d.minutes} minutes`);
  return parts.join(" · ");
}

const TONE: Record<string, "teal" | "amber" | "rose" | "slate"> = {
  import_new: "teal", import_add: "teal", import_refused: "amber", import_failed: "amber", dataset_delete: "rose",
  login_locked: "amber", user_disable: "rose",
};

const COLUMNS: Column<AuditEntry>[] = [
  { key: "at", header: "When", cell: (e) => <span className="tabular text-xs">{when(e.at)}</span> },
  { key: "actor", header: "Who", cell: (e) => e.actor },
  { key: "action", header: "What", cell: (e) => <Pill tone={TONE[e.action] ?? "slate"}>{e.action_label}</Pill> },
  { key: "target", header: "Dataset or user", cell: (e) => <span className="font-medium text-ink">{e.target || "—"}</span> },
  { key: "detail", header: "Details", cell: (e) => <span className="text-xs text-muted">{details(e)}</span> },
];

function AuditInner() {
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useApi<AuditPage>("/api/audit", { page, page_size: 50 });
  return (
    <Card id="audit" title={data ? `${int(data.total)} entr${data.total === 1 ? "y" : "ies"}` : "Audit log"}
          subtitle="Newest first. Entries hold who, what, when and counts only: never a password, a cell value or message text.">
      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <LoadingBlock rows={8} label="Loading the audit log" />}
      {data && !error && (data.entries.length === 0 ? <EmptyState title="Nothing has been recorded yet." /> : (
        <>
          <DataTable caption="Audit log" columns={COLUMNS} rows={data.entries} rowKey={(e) => String(e.id)} />
          <Pagination page={data.page} pages={data.pages} onPage={setPage} label="Audit log pages" />
        </>
      ))}
    </Card>
  );
}

export default function AuditPageView() {
  return (
    <>
      <PageHeader title="Audit log" lookingAt="who imported, deleted, approved or changed what, and when. No passwords and no message text." intro="Who imported, deleted or changed what, and when." />
      <RequireRole role="admin" what="read the audit log"><AuditInner /></RequireRole>
    </>
  );
}
