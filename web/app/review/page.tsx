"use client";

import { Download, Play } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { RequireRole } from "@/components/RequireRole";
import { DEMO, useCurrentDataset, useSession } from "@/components/SessionProvider";
import { Card, EmptyState, ErrorState, inputClass, KpiTile, LoadingBlock, PageHeader, Pill } from "@/components/kit";
import { apiUrl, getJson, sendJson, type ReviewMessage, type ReviewSummary } from "@/lib/api";
import { dateTime, int, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const CLASS_LABEL: Record<string, string> = {
  normal: "Normal", firm_pressure: "Firm pressure", threat: "Threat", shaming_third_party: "Shaming or third party",
};

function Reviewer({ slug, summary, onSaved }: { slug: string; summary: ReviewSummary; onSaved: () => void }) {
  const [kind, setKind] = useState("random");
  const [size, setSize] = useState(summary.default_size);
  const [reviewer, setReviewer] = useState("");
  const [queue, setQueue] = useState<string[]>([]);
  const [pos, setPos] = useState(0);
  const [item, setItem] = useState<ReviewMessage>();
  const [flash, setFlash] = useState<{ text: string; tone: "ok" | "error" }>();
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (id: string) => {
    setItem(undefined);
    try {
      setItem(await getJson<ReviewMessage>(`/api/review/message/${encodeURIComponent(id)}`, { dataset: slug }));
    } catch (err) {
      setFlash({ text: (err as Error).message, tone: "error" });
    }
  }, [slug]);

  useEffect(() => {
    if (pos < queue.length) void load(queue[pos]);
    else setItem(undefined);
  }, [pos, queue, load]);

  async function start() {
    setBusy(true);
    setFlash(undefined);
    try {
      const body = await sendJson<{ ids: string[] }>("POST", "/api/review/batch", { dataset: slug, kind, size });
      setQueue(body.ids);
      setPos(0);
      if (!body.ids.length) setFlash({ text: "Every message has been reviewed already.", tone: "ok" });
    } catch (err) {
      setFlash({ text: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function save(label: string) {
    if (!item) return;
    setBusy(true);
    try {
      const result = await sendJson<{ saved: string; model_label: string | null; agreed: boolean }>(
        "POST", "/api/review/label", { dataset: slug, message_id: item.message_id, label, kind, reviewer: reviewer || null });
      const said = result.model_label ? CLASS_LABEL[result.model_label] ?? result.model_label : "no label";
      setFlash({ text: `Saved as ${CLASS_LABEL[label]}. The model ${result.agreed ? "agreed" : `had said ${said}`}.`, tone: "ok" });
      setPos((p) => p + 1);
      onSaved();
    } catch (err) {
      setFlash({ text: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  const finished = queue.length > 0 && pos >= queue.length;
  return (
    <Card id="review" title="Review messages" subtitle="Your label replaces the model's label everywhere for this dataset. Skipped messages are not stored and may come up again.">
      <div className="grid gap-4 md:grid-cols-[1fr_9rem_12rem_auto] md:items-end">
        <fieldset>
          <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Batch</legend>
          <div className="flex flex-col gap-1.5">
            {Object.entries(summary.kinds).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm text-ink">
                <input type="radio" name="kind" className="h-4 w-4 accent-[var(--accent)]" checked={kind === key} onChange={() => setKind(key)} />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <div><label htmlFor="size" className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">Messages</label>
          <input id="size" type="number" min={1} max={500} value={size} onChange={(e) => setSize(Math.min(500, Math.max(1, Number(e.target.value) || 1)))} className={inputClass} /></div>
        <div><label htmlFor="reviewer" className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">Your initials or a code</label>
          <input id="reviewer" maxLength={20} value={reviewer} onChange={(e) => setReviewer(e.target.value)} className={inputClass} placeholder="optional" /></div>
        <Button onClick={start} disabled={busy}><Play aria-hidden="true" /> Start a new batch</Button>
      </div>
      <p className="mt-2 text-xs text-muted">Do the random check first: it is the only fair measure of how often the model is right.</p>

      {flash && (
        <p role={flash.tone === "error" ? "alert" : "status"} className={`mt-4 rounded-lg px-3 py-2 text-sm ${flash.tone === "ok"
          ? "border border-[#99d5cf] bg-[#e6f2f1] text-[#115e59] dark:border-[#115e59] dark:bg-[#042f2e] dark:text-[#99f6e4]"
          : "border border-[#fda4af] bg-[#fff1f2] text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]"}`}>{flash.text}</p>
      )}

      {queue.length > 0 && !finished && (
        <div className="mt-5 rounded-xl border border-line p-4" aria-live="polite">
          {!item ? <LoadingBlock rows={2} label="Loading the message" /> : (
            <>
              <p className="text-xs text-muted">Message {pos + 1} of {queue.length} · {item.lender} · {dateTime(item.sent_at)} · sent to the {item.recipient_type.replace("_", " ")}</p>
              <blockquote className="mt-2 whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-[15px] leading-relaxed text-ink">{item.text}</blockquote>
              {summary.show_model_label && item.model_label && (
                <p className="mt-2 text-xs text-muted">The model&apos;s label: {CLASS_LABEL[item.model_label] ?? item.model_label}</p>
              )}
              <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Choose the label for this message">
                {summary.classes.map((c) => (
                  <Button key={c} variant="outline" disabled={busy} onClick={() => save(c)}>
                    {CLASS_LABEL[c] ?? c}
                  </Button>
                ))}
                <Button variant="ghost" disabled={busy} onClick={() => setPos((p) => p + 1)}>Not sure / skip</Button>
              </div>
            </>
          )}
        </div>
      )}
      {finished && <p className="mt-4 text-sm font-medium text-ink">Batch finished. Start a new one when you are ready.</p>}
    </Card>
  );
}

function ReviewInner() {
  const { dataset } = useSession();
  const current = useCurrentDataset();
  const { data, error, loading, reload } = useApi<ReviewSummary>("/api/review", { dataset });

  if (dataset === DEMO || (data && !data.available)) {
    return (
      <EmptyState title="The demo dataset cannot be reviewed here">
        {data?.reason ?? "The demo dataset cannot be changed, so its labels cannot be reviewed. Choose an imported dataset."}{" "}
        <Link href="/datasets" className="font-medium text-accent hover:underline">Choose an imported dataset</Link>.
      </EmptyState>
    );
  }
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading && !data) return <LoadingBlock rows={6} label="Loading review progress" />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <p className="text-sm text-ink-2">Reviewing <span className="font-semibold text-ink">{current.name}</span>. The labels come from a model
        trained on the built-in demonstration text; on other text it can often be wrong. Labels a person has checked replace the model&apos;s label
        on every page and are recorded in the audit log.</p>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiTile accent="teal" label="Labels a person has checked" value={int(data.reviewed)} detail={`of ${int(data.messages)} messages (${pct(data.share_reviewed)})`} />
        <KpiTile accent="navy" label="Random check" value={int(data.per_batch.random ?? 0)} />
        <KpiTile accent="amber" label="Hard cases" value={int(data.per_batch.hard ?? 0)} />
        <KpiTile accent="rose" label="Model right (random check)" value={data.accuracy.ok && data.accuracy.accuracy !== null ? pct(data.accuracy.accuracy, 0) : "not yet"}
                 detail={data.accuracy.ok && data.accuracy.low !== null && data.accuracy.high !== null ? `range ${pct(data.accuracy.low, 0)} to ${pct(data.accuracy.high, 0)}` : `${data.accuracy.n} checked so far`} />
      </div>
      <Card id="accuracy" title="Measured accuracy of the current model" subtitle="Random check only: hard cases are picked on purpose and would make the model look worse than it is.">
        <p className="text-sm text-ink-2">{data.accuracy.sentence}</p>
        {data.accuracy.per_class.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {data.accuracy.per_class.map((r) => (
              <Pill key={r.class}>{CLASS_LABEL[r.class] ?? r.class}: {r.model_right} of {r.checked} right</Pill>
            ))}
          </div>
        )}
      </Card>
      <Reviewer slug={dataset} summary={data} onSaved={reload} />
      <Card id="export" title="Export the labels a person has checked">
        <a href={apiUrl("/api/review/export.csv", { dataset })} download
           className={buttonVariants({ variant: "outline", className: data.reviewed ? "" : "pointer-events-none opacity-40" })}
           aria-disabled={!data.reviewed}><Download aria-hidden="true" /> Download reviewed labels (CSV)</a>
        <p className="mt-2 text-xs text-muted">The file starts with a &apos;#&apos; notice line and includes the message text as stored (redacted at import).</p>
      </Card>
    </div>
  );
}

export default function ReviewPage() {
  return (
    <>
      <PageHeader title="Review labels" lookingAt="a sample of the model's message labels for a person to check, and how often the model was right."
                  intro="Check a sample of the model's message labels on an imported dataset. Your label is a person's judgement about the wording, not a legal finding." />
      <RequireRole role="importer" what="review labels"><ReviewInner /></RequireRole>
    </>
  );
}
