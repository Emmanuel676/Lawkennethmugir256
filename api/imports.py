"""The Data import page's logic (Phase 12B): template, synthetic-only gate, validation, import. No HTTP here.

Everything reuses the existing code, unchanged:
  template      src.import_templates.build_xlsx_template / build_csv_templates
  gate          src.team_access.synthetic_gate: "(Demo)" lenders, "(SYNTHETIC)" messages, no phone-, ID- or
                email-like text, and the size and row limits in config.yaml (team_demo.max_upload_mb,
                team_demo.max_rows_per_file). It runs on the uploaded bytes IN MEMORY, before anything else; a
                refused upload is never validated, stored or written anywhere.
  validation    src.import_data.validate_upload (plain-language errors, warnings and notes with row numbers)
  import        src.import_data.import_upload (validates again; writes in ONE transaction only when there are no
                errors; redacts message text; labels the messages with the local classifier)

Redaction is always on here, and the permission confirmation (src.import_data.PERMISSION_TEXT) is required.
"""

from __future__ import annotations

import io
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import date

from src.datasets import DEMO, DatasetError
from src.import_data import (PERMISSION_TEXT, ImportReport, Upload, default_as_of, import_upload, read_csvs,
                             read_existing, read_xlsx, validate_upload)
from src.import_templates import build_csv_templates, build_xlsx_template
from src.team_access import synthetic_gate

from api import security
from api.store import DatasetRecord

MAX_SHOWN = 200
_import_lock = threading.Lock()  # one import at a time: two imports must not race for one dataset


class ImportRequestError(ValueError):
    """The request itself is incomplete (no files, no name...). The message is safe to show."""


@dataclass
class Outcome:
    stage: str                       # 'refused' (gate), 'invalid' (validation errors), 'valid', 'imported', 'failed'
    reasons: list[str] = field(default_factory=list)
    report: ImportReport | None = None
    message: str = ""
    dataset: str = ""
    already_known: int = 0
    suggested_as_of: str = ""

    def public(self) -> dict:
        body = {"stage": self.stage, "reasons": self.reasons, "message": self.message, "dataset": self.dataset,
                "already_known": self.already_known, "suggested_as_of": self.suggested_as_of, "report": None}
        if self.report is not None:
            r = self.report
            issue = lambda i: {"location": i.location, "message": i.message, "text": str(i)}  # noqa: E731
            body["report"] = {
                "ok": r.ok, "counts": r.counts, "as_of_date": r.as_of_date,
                "errors_total": len(r.errors), "warnings_total": len(r.warnings),
                "errors": [issue(i) for i in r.errors[:MAX_SHOWN]],
                "warnings": [issue(i) for i in r.warnings[:MAX_SHOWN]],
                "notes": [issue(i) for i in r.notes],
                "found": r.found, "already_known": r.skipped_existing_borrowers,
            }
        return body


REVIEW_PAGE_STREAMLIT = "Check a sample on the Review page before relying on the labels."
REVIEW_PAGE_WEB = "Check a sample on the Review labels page before relying on the labels."


def web_message(message: str) -> str:
    """The importer's own success message (src.import_data, unchanged) with its pointer to the Streamlit Review
    page replaced by the web app's Review labels page."""
    return message.replace(REVIEW_PAGE_STREAMLIT, REVIEW_PAGE_WEB)


def template_xlsx(cfg: dict) -> bytes:
    return build_xlsx_template(cfg)


def template_csv_zip(cfg: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in build_csv_templates(cfg).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _plain(reason: str) -> str:
    """The gate's wording was written for Phase 11 team sessions; say 'this app' here instead."""
    return (reason.replace("Team demo sessions accept", "This app accepts")
            .replace("team demo sessions accept", "this app accepts"))


def gate(files: dict[str, bytes], file_type: str, cfg: dict) -> list[str]:
    """The synthetic-only gate on the uploaded bytes in memory. Empty list = it may go on to validation."""
    if file_type not in ("xlsx", "csv"):
        raise ImportRequestError("Choose the file type: one Excel workbook (xlsx) or five CSV files (csv).")
    if not files:
        raise ImportRequestError("Upload your file(s) first.")
    if file_type == "xlsx" and len(files) != 1:
        raise ImportRequestError("Upload exactly one Excel workbook (.xlsx).")
    try:
        return [_plain(reason) for reason in synthetic_gate(files, file_type, cfg)]
    except Exception as error:  # an unreadable file is a refusal, never a crash (no value is repeated)
        return [f"The file(s) could not be read ({type(error).__name__}). Use the template and save as "
                + ("an Excel workbook (.xlsx)." if file_type == "xlsx" else "CSV files.")]


def _upload(files: dict[str, bytes], file_type: str) -> Upload:
    return read_xlsx(next(iter(files.values()))) if file_type == "xlsx" else read_csvs(files)


def _as_of(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ImportRequestError("Write the as-of date as YYYY-MM-DD, for example 2026-10-01.") from None


def check(files: dict[str, bytes], file_type: str, *, engine_cfg: dict, mode: str, target_lending=None,
          as_of: str | None = None, day_first: bool = True) -> Outcome:
    """Gate, then validate. Writes nothing in any case."""
    reasons = gate(files, file_type, engine_cfg)
    if reasons:
        return Outcome("refused", reasons=reasons, message="This upload was refused by the synthetic-only check. "
                                                            "Nothing was stored.")
    upload = _upload(files, file_type)
    suggested = default_as_of(upload, day_first)
    existing = read_existing(target_lending) if mode == "add" and target_lending is not None else None
    report = validate_upload(upload, engine_cfg, _as_of(as_of) or suggested, existing, day_first)
    return Outcome("valid" if report.ok else "invalid", report=report,
                   suggested_as_of=suggested.isoformat() if suggested else "",
                   message="No errors found." if report.ok else
                   f"{len(report.errors)} error(s) found. Fix them in your files and upload again. Nothing was written.")


def run_import(files: dict[str, bytes], file_type: str, *, engine_cfg: dict, mode: str, name: str = "",
               notes: str = "", source: str = "", target: str = "", as_of: str | None = None, day_first: bool = True,
               permission: bool = False, actor: str, catalog, files_store, classify: bool = True) -> Outcome:
    """Gate, then import with the existing importer (which validates again). On success the catalog is updated."""
    if not permission:
        raise ImportRequestError(f"Tick the permission box to import: '{PERMISSION_TEXT}'.")
    if mode not in ("new", "add"):
        raise ImportRequestError("Choose whether to create a new dataset or add to an existing one.")
    if mode == "new" and not str(name).strip():
        raise ImportRequestError("Give the new dataset a name.")
    if mode == "add" and (not target or target == DEMO):
        raise ImportRequestError("Choose an imported dataset to add to. The demo cannot be changed.")
    reasons = gate(files, file_type, engine_cfg)
    if reasons:
        return Outcome("refused", reasons=reasons, message="This upload was refused by the synthetic-only check. "
                                                            "Nothing was stored.")
    with _import_lock:
        if mode == "add" and catalog.get(target) is None:
            raise ImportRequestError("There is no imported dataset with that name to add to.")
        upload = _upload(files, file_type)
        suggested = default_as_of(upload, day_first)
        try:
            result = import_upload(upload, engine_cfg, mode=mode, permission_confirmed=True, redact=True,
                                   as_of=_as_of(as_of) or suggested, dataset_name=name, source_description=source,
                                   notes=notes, target=target, classify=classify, day_first=day_first)
        except DatasetError as error:
            return Outcome("failed", message=str(error))
        if not result.ok:
            stage = "invalid" if result.report is not None and not result.report.ok else "failed"
            return Outcome(stage, report=result.report, message=result.message)
        slug = result.dataset
        counts = files_store.counts(engine_cfg, slug)
        at = security.now()
        if mode == "new":
            catalog.add(DatasetRecord(slug=slug, name=str(name).strip(), notes=str(notes).strip(),
                                      source=str(source).strip(), added_by=actor, added_at=at, updated_at=at,
                                      as_of_date=result.report.as_of_date, counts=counts))
        else:
            catalog.touch(slug, counts, result.report.as_of_date)
        return Outcome("imported", report=result.report, message=web_message(result.message), dataset=slug,
                       already_known=int(result.report.skipped_existing_borrowers))
