"use client";

import { Eye, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { RequireRole } from "@/components/RequireRole";
import { DEMO, useSession } from "@/components/SessionProvider";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Pill } from "@/components/kit";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/form";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { toast } from "@/components/ui/sonner";
import { sendJson, type DatasetEntry, type DatasetList } from "@/lib/api";
import { date, int } from "@/lib/format";
import { useApi } from "@/lib/useApi";

function when(seconds: number | null): string {
  if (!seconds) return "built in";
  const d = new Date(seconds * 1000);
  return `${date(d.toISOString())}, ${d.toTimeString().slice(0, 5)}`;
}

function DeleteDialog({ entry, onClose, onDeleted }: {
  entry: DatasetEntry | undefined; onClose: () => void; onDeleted: (message: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (!entry) return;
    setBusy(true);
    setError(undefined);
    try {
      const body = await sendJson<{ message: string }>("DELETE", `/api/datasets/${encodeURIComponent(entry.slug)}`,
                                                       { confirm_name: typed });
      setTyped("");
      onDeleted(body.message);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={Boolean(entry)} onOpenChange={(open) => { if (!open) { setTyped(""); setError(undefined); onClose(); } }}>
      <DialogContent>
        <DialogTitle>Delete “{entry?.name}”?</DialogTitle>
        <DialogDescription>This removes the dataset and all its files for every user. It cannot be undone. The built-in
          demonstration data is never affected.</DialogDescription>
        <div className="mt-4 space-y-1.5">
          <Label htmlFor="confirm-name">Type the dataset name to confirm: <span className="font-semibold text-ink">{entry?.name}</span></Label>
          <Input id="confirm-name" autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </div>
        {error && <p role="alert" className="mt-2 text-sm text-[#9f1239] dark:text-[#fecdd3]">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="button" variant="destructive" onClick={remove} disabled={busy || typed.trim() !== entry?.name}>
            <Trash2 aria-hidden="true" /> {busy ? "Deleting…" : "Delete dataset"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function DatasetsInner() {
  const router = useRouter();
  const { dataset, setDataset, reloadDatasets } = useSession();
  const { data, error, loading, reload } = useApi<DatasetList>("/api/datasets");
  const [deleting, setDeleting] = useState<DatasetEntry>();
  const [notice, setNotice] = useState<string>();

  const imported = data?.datasets.filter((d) => d.slug !== DEMO) ?? [];

  return (
    <>
      <PageHeader title="Datasets"
                  intro="Shared datasets: every signed-in user sees the same list. Choose which one the Overview, Borrowers, Lenders and Repayments pages show. The built-in demo is the default and cannot be changed or deleted."
                  lookingAt="every dataset you can open, who added it and how big it is.">
        {data?.can_import && (
          <Button asChild><Link href="/import"><Plus aria-hidden="true" /> Add a dataset</Link></Button>
        )}
      </PageHeader>

      {notice && (
        <p role="status" className="mb-4 rounded-xl border border-[#99d5cf] bg-[#e6f2f1] px-4 py-3 text-sm text-[#115e59] dark:border-[#115e59] dark:bg-[#042f2e] dark:text-[#99f6e4]">
          {notice}
        </p>
      )}
      {error && <ErrorState message={error} onRetry={reload} />}
      {!error && loading && !data && <LoadingBlock rows={4} label="Loading datasets" />}

      {data && !error && (
        <div className="space-y-4">
          {data.datasets.map((d) => {
            const active = d.slug === dataset;
            return (
              <Card key={d.slug} className={active ? "ring-2 ring-accent" : ""}>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-base font-semibold text-ink">{d.name}</h2>
                      {d.kind === "demo" ? <Pill tone="teal">Demonstration data · built in</Pill> : <Pill tone="amber">Demonstration data · imported</Pill>}
                      {active && <Pill>Showing now</Pill>}
                    </div>
                    <p className="mt-1 text-sm text-muted">{d.kind === "demo" ? d.notes : d.label}</p>
                    {d.kind === "imported" && d.notes && <p className="mt-1 text-sm text-ink-2">{d.notes}</p>}
                    <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
                      {(["lenders", "borrowers", "loans", "messages"] as const).map((k) => (
                        <div key={k}><dt className="text-xs uppercase tracking-wide text-muted">{k}</dt>
                          <dd className="tabular font-medium text-ink">{int(d.counts[k])}</dd></div>
                      ))}
                    </dl>
                    <p className="mt-3 text-xs text-muted">
                      {d.kind === "demo" ? "Built in" : <>Added by {d.added_by} on {when(d.added_at)}
                        {d.imports > 1 && <> · {d.imports} imports, last {when(d.updated_at)}</>}</>}
                      {d.as_of_date && <> · data as of {date(d.as_of_date)}</>}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <Button size="sm" disabled={active} onClick={() => { setDataset(d.slug); router.push("/overview"); }}>
                      <Eye aria-hidden="true" /> {active ? "Showing" : "Show this dataset"}
                    </Button>
                    {d.deletable && (
                      <Button size="sm" variant="destructive-outline" onClick={() => setDeleting(d)}>
                        <Trash2 aria-hidden="true" /> Delete
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
          {imported.length === 0 && (
            <EmptyState title="No imported datasets yet.">
              {data.can_import ? <>Use <Link href="/import" className="font-medium text-accent hover:underline">Import data</Link> to add one, for example a sample pack.</>
                : "An Importer or Admin can add one."}
            </EmptyState>
          )}
        </div>
      )}

      <DeleteDialog entry={deleting} onClose={() => setDeleting(undefined)}
                    onDeleted={(message) => {
                      if (deleting?.slug === dataset) setDataset(DEMO);
                      setDeleting(undefined);
                      setNotice(message);
                      toast.success(message);
                      reload();
                      reloadDatasets();
                    }} />
    </>
  );
}

export default function DatasetsPage() {
  return (
    <RequireRole role="viewer" what="see the shared datasets">
      <DatasetsInner />
    </RequireRole>
  );
}
