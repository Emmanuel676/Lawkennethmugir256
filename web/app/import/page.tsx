"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { RequireRole } from "@/components/RequireRole";
import { useSession } from "@/components/SessionProvider";
import { Card, ErrorState, inputClass, LoadingBlock, PageHeader, Pill } from "@/components/ui";
import { apiUrl, sendForm, type ImportInfo, type ImportOutcome, type Issue } from "@/lib/api";
import { int } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Mode = "new" | "add";
type FileType = "csv" | "xlsx";
const TABLES = ["lenders", "borrowers", "loans", "transactions", "messages"];
const radio = "h-4 w-4 accent-[var(--accent)]";

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <div className="flex gap-4">
        <span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-bold text-accent">{n}</span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-ink"><span className="sr-only">Step {n}: </span>{title}</h2>
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </Card>
  );
}

function IssueList({ items, total, tone }: { items: Issue[]; total: number; tone: "error" | "warning" | "note" }) {
  const color = { error: "text-[#881337] dark:text-[#fecdd3]", warning: "text-[#7c2d12] dark:text-[#fde6c4]",
                  note: "text-ink-2" }[tone];
  return (
    <>
      <ul className={`max-h-80 list-disc space-y-1 overflow-y-auto pl-5 text-sm ${color}`}>
        {items.map((issue, i) => <li key={i}>{issue.text}</li>)}
      </ul>
      {total > items.length && <p className="mt-1 text-xs text-muted">… and {int(total - items.length)} more.</p>}
    </>
  );
}

function Result({ outcome }: { outcome: ImportOutcome }) {
  const report = outcome.report;
  if (outcome.stage === "refused") {
    return (
      <div role="alert" className="rounded-xl border border-[#fda4af] bg-[#fff1f2] p-4 text-[#881337] dark:border-[#9f1239] dark:bg-[#2a0a12] dark:text-[#fecdd3]">
        <p className="font-semibold">Upload refused. Nothing was stored.</p>
        <p className="mt-1 text-sm">This app accepts only data that passes the synthetic-only check: lender names end in
          “(Demo)”, messages end in “(SYNTHETIC)”, nothing looks like a phone number, an ID number or an email address,
          and the size and row limits are kept.</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{outcome.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      </div>
    );
  }
  if (!report) {
    return <p role="alert" className="text-sm text-[#9f1239] dark:text-[#fecdd3]">{outcome.message}</p>;
  }
  return (
    <div className="space-y-4">
      {report.ok ? (
        <p role="status" className="rounded-xl border border-[#99d5cf] bg-[#e6f2f1] px-4 py-3 text-sm font-medium text-[#115e59] dark:border-[#115e59] dark:bg-[#042f2e] dark:text-[#99f6e4]">
          No errors found. {report.warnings_total ? `${report.warnings_total} warning(s) do not block the import.` : "No warnings."}
        </p>
      ) : (
        <div role="alert" className="rounded-xl border border-[#fda4af] bg-[#fff1f2] p-4 dark:border-[#9f1239] dark:bg-[#2a0a12]">
          <p className="font-semibold text-[#881337] dark:text-[#fecdd3]">{report.errors_total} error(s) found. Fix them in your
            files and upload again. Nothing was written.</p>
          <div className="mt-2"><IssueList items={report.errors} total={report.errors_total} tone="error" /></div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] text-sm">
          <caption className="sr-only">Rows found in the upload</caption>
          <thead><tr>{TABLES.map((t) => <th key={t} scope="col" className="border-b border-line px-2 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-muted">{t}</th>)}</tr></thead>
          <tbody><tr>{TABLES.map((t) => <td key={t} className="tabular px-2 py-1.5 font-medium text-ink">{int(report.counts[t] ?? 0)}</td>)}</tr></tbody>
        </table>
      </div>
      {report.warnings_total > 0 && (
        <details className="rounded-xl border border-line p-3">
          <summary className="cursor-pointer text-sm font-medium text-ink">{report.warnings_total} warning(s) (these do not block the import)</summary>
          <div className="mt-2"><IssueList items={report.warnings} total={report.warnings_total} tone="warning" /></div>
        </details>
      )}
      {report.notes.length > 0 && <IssueList items={report.notes} total={report.notes.length} tone="note" />}
    </div>
  );
}

function ImportInner() {
  const router = useRouter();
  const { setDataset, reloadDatasets } = useSession();
  const info = useApi<ImportInfo>("/api/imports/info");
  const [mode, setMode] = useState<Mode>("new");
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [notes, setNotes] = useState("");
  const [target, setTarget] = useState("");
  const [fileType, setFileType] = useState<FileType>("csv");
  const [files, setFiles] = useState<File[]>([]);
  const [asOf, setAsOf] = useState("");
  const [dayFirst, setDayFirst] = useState(true);
  const [permission, setPermission] = useState(false);
  const [checked, setChecked] = useState<{ key: string; outcome: ImportOutcome }>();
  const [done, setDone] = useState<ImportOutcome>();
  const [busy, setBusy] = useState<"check" | "import">();
  const [error, setError] = useState<string>();
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (info.data) setDayFirst(info.data.day_first_default);
  }, [info.data]);

  const key = useMemo(() => JSON.stringify([mode, target, fileType, asOf, dayFirst,
    files.map((f) => [f.name, f.size, f.lastModified])]), [mode, target, fileType, asOf, dayFirst, files]);
  const current = checked && checked.key === key ? checked.outcome : undefined;
  const sizeMb = files.reduce((n, f) => n + f.size, 0) / 1024 / 1024;
  const tooBig = info.data ? sizeMb > info.data.limits.max_upload_mb : false;

  function form(): FormData {
    const data = new FormData();
    for (const file of files) data.append("files", file, file.name);
    data.append("file_type", fileType);
    data.append("mode", mode);
    data.append("day_first", dayFirst ? "true" : "false");
    if (asOf) data.append("as_of", asOf);
    if (mode === "new") {
      data.append("name", name.trim());
      data.append("source", source.trim());
      data.append("notes", notes.trim());
    } else {
      data.append("target", target);
    }
    data.append("permission", permission ? "true" : "false");
    return data;
  }

  async function check() {
    setBusy("check");
    setError(undefined);
    setDone(undefined);
    try {
      const outcome = await sendForm<ImportOutcome>("/api/imports/check", form());
      if (!asOf && outcome.suggested_as_of) setAsOf(outcome.suggested_as_of);
      const keyAfter = JSON.stringify([mode, target, fileType, asOf || outcome.suggested_as_of, dayFirst,
        files.map((f) => [f.name, f.size, f.lastModified])]);
      setChecked({ key: keyAfter, outcome });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(undefined);
    }
  }

  async function runImport() {
    setBusy("import");
    setError(undefined);
    try {
      const outcome = await sendForm<ImportOutcome>("/api/imports", form());
      if (outcome.stage === "imported") {
        setDone(outcome);
        setChecked(undefined);
        setFiles([]);
        if (fileInput.current) fileInput.current.value = "";
        reloadDatasets();
        info.reload();
      } else {
        setChecked({ key, outcome });
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(undefined);
    }
  }

  if (info.error) return <ErrorState message={info.error} onRetry={info.reload} />;
  if (!info.data) return <LoadingBlock rows={6} label="Loading the import page" />;
  const targets = info.data.targets;
  const ready = Boolean(current?.stage === "valid" && permission && !tooBig &&
                        (mode === "new" ? name.trim() : target));

  return (
    <div className="space-y-5">
      <Step n={1} title="Download a template">
        <p className="text-sm text-muted">One Excel workbook with the sheets lenders, borrowers, loans, transactions and
          messages, or the same five tables as CSV files. Amounts are whole Ugandan shillings (UGX).</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={apiUrl("/api/imports/template", { format: "xlsx" })} download
             className="rounded-lg border border-line px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2">Excel workbook (.xlsx)</a>
          <a href={apiUrl("/api/imports/template", { format: "csv" })} download
             className="rounded-lg border border-line px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2">Five CSV files (.zip)</a>
        </div>
        <p className="mt-3 text-xs text-muted">To try it, use the synthetic sample pack: run <code className="rounded bg-surface-2 px-1">.\dev.ps1 -SamplePack</code>,
          then upload the five CSV files in <code className="rounded bg-surface-2 px-1">sample_pack\baseline\lender_A</code>.</p>
      </Step>

      <Step n={2} title="Choose where the data goes">
        <fieldset className="space-y-2">
          <legend className="sr-only">Import mode</legend>
          <label className="flex items-center gap-2 text-sm text-ink"><input type="radio" className={radio} checked={mode === "new"} onChange={() => setMode("new")} /> Create a new dataset</label>
          <label className={`flex items-center gap-2 text-sm ${targets.length ? "text-ink" : "text-muted"}`}>
            <input type="radio" className={radio} checked={mode === "add"} disabled={!targets.length} onChange={() => setMode("add")} />
            Add another lender&apos;s files to an imported dataset{!targets.length && " (none yet)"}
          </label>
        </fieldset>
        {mode === "new" ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div><label htmlFor="ds-name" className="mb-1.5 block text-sm font-medium text-ink-2">Dataset name</label>
              <input id="ds-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} className={inputClass}
                     placeholder="for example SYNTHETIC sample baseline" /></div>
            <div><label htmlFor="ds-source" className="mb-1.5 block text-sm font-medium text-ink-2">Where the data came from</label>
              <input id="ds-source" value={source} maxLength={200} onChange={(e) => setSource(e.target.value)} className={inputClass}
                     placeholder="for example synthetic sample pack" /></div>
            <div className="md:col-span-2"><label htmlFor="ds-notes" className="mb-1.5 block text-sm font-medium text-ink-2">Notes (optional)</label>
              <textarea id="ds-notes" value={notes} maxLength={1000} rows={2} onChange={(e) => setNotes(e.target.value)} className={inputClass} /></div>
          </div>
        ) : (
          <div className="mt-4 max-w-md"><label htmlFor="ds-target" className="mb-1.5 block text-sm font-medium text-ink-2">Add to</label>
            <select id="ds-target" value={target} onChange={(e) => setTarget(e.target.value)} className={inputClass}>
              <option value="">Choose a dataset…</option>
              {targets.map((t) => <option key={t.slug} value={t.slug}>{t.name}</option>)}
            </select>
            <p className="mt-1 text-xs text-muted">A borrower code already in the dataset is expected (the same person at
              another lender) and is kept. The demo cannot be changed.</p></div>
        )}
      </Step>

      <Step n={3} title="Upload and check">
        <fieldset className="flex flex-wrap gap-4">
          <legend className="sr-only">File type</legend>
          <label className="flex items-center gap-2 text-sm text-ink"><input type="radio" className={radio} checked={fileType === "csv"} onChange={() => { setFileType("csv"); setFiles([]); }} /> Five CSV files</label>
          <label className="flex items-center gap-2 text-sm text-ink"><input type="radio" className={radio} checked={fileType === "xlsx"} onChange={() => { setFileType("xlsx"); setFiles([]); }} /> One Excel workbook</label>
        </fieldset>
        <label htmlFor="files" className="mt-4 block text-sm font-medium text-ink-2">
          {fileType === "csv" ? "CSV files (lenders.csv, borrowers.csv, loans.csv, transactions.csv, messages.csv)" : "Workbook (.xlsx)"}
        </label>
        <input id="files" ref={fileInput} type="file" multiple={fileType === "csv"} accept={fileType === "csv" ? ".csv,.txt" : ".xlsx"}
               onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
               className="mt-1.5 block w-full text-sm text-ink-2 file:mr-3 file:rounded-lg file:border-0 file:bg-accent-soft file:px-3 file:py-2 file:text-sm file:font-medium file:text-accent" />
        {files.length > 0 && (
          <p className={`mt-1 text-xs ${tooBig ? "font-medium text-[#9f1239] dark:text-[#fecdd3]" : "text-muted"}`}>
            {files.length} file(s), {sizeMb.toFixed(1)} MB{tooBig && `: over the ${info.data.limits.max_upload_mb} MB limit`}.
          </p>
        )}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div><label htmlFor="as-of" className="mb-1.5 block text-sm font-medium text-ink-2">As-of date (“today” for this data)</label>
            <input id="as-of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className={inputClass} />
            <p className="mt-1 text-xs text-muted">Leave empty to use the latest date found in the files.</p></div>
          <label className="flex items-start gap-2 pt-7 text-sm text-ink">
            <input type="checkbox" className={`${radio} mt-0.5`} checked={dayFirst} onChange={(e) => setDayFirst(e.target.checked)} />
            Dates in my files are day/month/year (31/08/2026)
          </label>
        </div>
        <p className="mt-3 text-xs text-muted">Message text is always redacted: phone numbers, emails, ID numbers and listed
          names become [PHONE], [EMAIL], [ID] and [NAME]. Every upload must pass the synthetic-only check first; a refused
          upload is never stored. Limits: {info.data.limits.max_upload_mb} MB, {int(info.data.limits.max_rows_per_file)} rows per file.</p>
        <button type="button" onClick={check} disabled={!files.length || tooBig || busy !== undefined || (mode === "add" && !target)}
                className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-40">
          {busy === "check" ? "Checking…" : "Check the files"}
        </button>
        {error && <p role="alert" className="mt-3 text-sm text-[#9f1239] dark:text-[#fecdd3]">{error}</p>}
        {current && <div className="mt-4" aria-live="polite"><Result outcome={current} /></div>}
        {checked && !current && <p className="mt-3 text-sm text-muted">The files or settings changed since the last check. Check again.</p>}
      </Step>

      <Step n={4} title="Import">
        <label className="flex items-start gap-2 text-sm text-ink">
          <input type="checkbox" className={`${radio} mt-0.5`} checked={permission} onChange={(e) => setPermission(e.target.checked)} />
          {info.data.permission_text}
        </label>
        <button type="button" onClick={runImport} disabled={!ready || busy !== undefined}
                className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-40">
          {busy === "import" ? "Importing and labelling the messages…" : "Import"}
        </button>
        {!ready && !done && <p className="mt-2 text-xs text-muted">Import becomes possible after a check with no errors, with the box ticked
          {mode === "new" ? " and a dataset name" : " and a dataset chosen"}.</p>}
        {done && (
          <div role="status" className="mt-4 rounded-xl border border-[#99d5cf] bg-[#e6f2f1] p-4 text-[#115e59] dark:border-[#115e59] dark:bg-[#042f2e] dark:text-[#99f6e4]">
            <p className="font-semibold">Imported dataset. Passed the synthetic-only check.</p>
            <p className="mt-1 text-sm">{done.message}</p>
            {done.already_known > 0 && <p className="mt-1 text-sm"><Pill tone="teal">{int(done.already_known)} borrower codes already known</Pill> The same people were already in the dataset from another lender.</p>}
            <p className="mt-1 text-xs">The check does not prove the data is synthetic. A flag is a prompt for a human to look, not a verdict.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={() => { setDataset(done.dataset); router.push("/"); }}
                      className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-ink">Show this dataset</button>
              <button type="button" onClick={() => { setMode("add"); setTarget(done.dataset); setDone(undefined); setPermission(false); }}
                      className="rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink-2">Add another lender&apos;s files</button>
              <Link href="/datasets" className="rounded-lg border border-line bg-surface px-3 py-2 text-sm font-medium text-ink-2">All datasets</Link>
            </div>
          </div>
        )}
      </Step>
    </div>
  );
}

export default function ImportPage() {
  return (
    <>
      <PageHeader title="Import data"
                  intro="Add a shared dataset in four steps. Nothing is saved until the check finds no errors, and only data that passes the synthetic-only check is accepted." />
      <RequireRole role="importer" what="import data">
        <ImportInner />
      </RequireRole>
    </>
  );
}
