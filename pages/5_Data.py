"""Data page: manage datasets, import your own data, download templates, check data health (Phase 4B)."""

from __future__ import annotations

import hashlib
from datetime import date

import pandas as pd
import streamlit as st

from src.classify_messages import NoModelError, train_local_model
from src.dashboard_data import data_health
from src.dashboard_ui import guarded, page_setup, presentation_block
from src.datasets import (DEMO, DatasetError, dataset_counts, delete_dataset, get_active_name, get_dataset,
                          list_datasets, restore_demo, saved_model_exists, set_active)
from src.import_data import (PERMISSION_TEXT, TOKEN_WORDS, default_as_of, import_upload, read_csvs, read_existing,
                             read_xlsx, redaction_preview, validate_upload)
from src.redaction import TOKENS, build_redactor, possible_names
from src.import_templates import build_csv_templates, build_xlsx_template

with guarded("Data"):
    data, cfg = page_setup("Data", require_data=False)
    presentation_block(cfg)
    MAX_SHOWN = 200

    flash = st.session_state.pop("data_flash", None)
    if flash:
        (st.success if flash[0] == "ok" else st.error)(flash[1])


    def finish(level: str, message: str) -> None:
        """Remember a message, then rerun so the sidebar, banner and data follow the change."""
        st.session_state["data_flash"] = (level, message)
        st.rerun()


    tab_datasets, tab_import, tab_templates, tab_health = st.tabs(["Datasets", "Import", "Templates", "Data health"])

    # --- Datasets -------------------------------------------------------------------------------------------------
    with tab_datasets:
        active = get_active_name(cfg)
        datasets = list_datasets(cfg)
        rows = []
        for info in datasets:
            counts = dataset_counts(info.paths)
            rows.append({
                "Active": "active" if info.slug == active else "",
                "Name": info.name, "Slug": info.slug,
                "Kind": "demo (synthetic)" if info.kind == "demo" else "real (confidential)",
                "Created": info.created_at, "As of": info.as_of_date, "Source": info.source_description,
                "Lenders": counts["lenders"], "Borrowers": counts["borrowers"], "Loans": counts["loans"],
                "Messages": counts["messages"],
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.info("There are no datasets. Restore the demo below or import your own data on the Import tab.")

        st.subheader("Switch dataset")
        slugs = [d.slug for d in datasets]
        if slugs:
            choice = st.selectbox("Dataset to use", slugs, index=slugs.index(active) if active in slugs else 0,
                                  key="switch_choice")
            if st.button("Make this the active dataset", key="switch_button"):
                set_active(cfg, choice)
                finish("ok", f"'{choice}' is now the active dataset.")

        st.subheader("Delete a dataset")
        deletable = [s for s in slugs if s != active]
        if not deletable:
            st.write("Only the active dataset exists. The active dataset cannot be deleted; switch to another first.")
        else:
            target = st.selectbox("Dataset to delete", deletable, key="delete_choice")
            typed = st.text_input(f"Type the dataset name to confirm: {target}", key="delete_typed")
            confirm_demo = False
            if target == DEMO:
                st.warning("The demo is the synthetic data the classifier is trained on. Deleting it keeps the saved "
                           "classifier; 'Restore demo' rebuilds it.")
                confirm_demo = st.checkbox("Yes, delete the demo dataset", key="delete_demo_confirm")
                if not saved_model_exists(cfg):
                    st.error("No saved classifier exists yet, so the demo cannot be deleted. Save it first:")
                    if st.button("Train and save the classifier now", key="train_model"):
                        try:
                            _, n_train = train_local_model(cfg)
                            finish("ok", f"Classifier trained on {n_train:,} demo messages and saved.")
                        except NoModelError as error:
                            finish("error", str(error))
            if st.button("Delete permanently", key="delete_button", type="primary"):
                try:
                    finish("ok", delete_dataset(cfg, target, typed, confirm_demo))
                except DatasetError as error:
                    st.error(str(error))

        st.subheader("Restore demo")
        st.write("Rebuild the synthetic demo dataset with the generator and label its messages (15 to 35 seconds, "
                 "no network). Real datasets are not touched.")
        if st.button("Restore demo", key="restore_demo"):
            with st.spinner("Rebuilding the demo..."):
                try:
                    finish("ok", restore_demo(cfg))
                except (DatasetError, NoModelError) as error:
                    finish("error", str(error))

    # --- Import ---------------------------------------------------------------------------------------------------
    with tab_import:
        st.markdown("Bring in data from the field: one Excel workbook with sheets **lenders, borrowers, loans, "
                    "transactions, messages**, or the same five tables as CSV files. Download a template first "
                    "(Templates tab). Nothing is written until the check finds no errors.")
        st.caption(f"All amounts (monthly_income, principal, amount_outstanding, amount) are in Ugandan shillings "
                   f"({cfg['currency']['code']}), whole shillings with no decimals. 'UGX 200,000', '200,000/=' and "
                   "'200 000' are understood; '200k' is not.")
        mode = st.radio("What do you want to do?", ["new", "add"], horizontal=True, key="import_mode",
                        format_func={"new": "Create a new dataset", "add": "Add to an existing real dataset"}.get)
        name = source = notes = target = ""
        if mode == "new":
            name = st.text_input("Dataset name", key="import_name", placeholder="for example Field data Gulu 2026")
            source = st.text_input("Where the data came from", key="import_source",
                                   placeholder="for example Two lenders, shared under agreement of 3 May 2026")
            notes = st.text_area("Notes (optional)", key="import_notes")
        else:
            real = [d for d in list_datasets(cfg) if d.kind == "real"]
            if not real:
                st.info("There is no real dataset yet. Create a new one first. Adding to the demo is not allowed.")
            else:
                target = st.selectbox("Add to", [d.slug for d in real], key="import_target")

        file_type = st.radio("File type", ["xlsx", "csv"], horizontal=True, key="import_format",
                             format_func={"xlsx": "One Excel workbook", "csv": "Five CSV files"}.get)
        files: dict[str, bytes] = {}
        if file_type == "xlsx":
            uploaded = st.file_uploader("Workbook (.xlsx)", type=["xlsx"], key="upload_xlsx")
            if uploaded is not None:
                files = {uploaded.name: uploaded.getvalue()}
        else:
            uploaded_many = st.file_uploader("CSV files (lenders.csv, borrowers.csv, loans.csv, transactions.csv, "
                                             "messages.csv; comma, semicolon or tab separated)", type=["csv", "txt"], accept_multiple_files=True, key="upload_csv")
            files = {f.name: f.getvalue() for f in uploaded_many or []}

        if not files:
            st.info("Upload your file(s) to continue.")
        else:
            upload = read_xlsx(next(iter(files.values()))) if file_type == "xlsx" else read_csvs(files)
            digest = hashlib.sha256()
            for file_name in sorted(files):
                digest.update(file_name.encode("utf-8") + files[file_name])
            fingerprint = digest.hexdigest()

            day_first = st.checkbox("Dates in my files are day/month/year", key="import_day_first",
                                    value=bool(cfg["onboarding"]["day_first_default"]),
                                    help="Uganda writes the day first (31/08/2026). Untick if your files write the month "
                                         "first; dates that could be read either way are then refused.")
            suggested = default_as_of(upload, day_first) or date.today()
            as_of = st.date_input("As-of date ('today' for this data; suggested: the latest date found in it)",
                                  value=suggested, key=f"as_of_{fingerprint[:12]}")
            redact = st.checkbox("Redact message text: replace phone numbers, email addresses, ID numbers and listed "
                                 "names with [PHONE], [EMAIL], [ID] and [NAME]",
                                 value=bool(cfg["onboarding"]["redact_by_default"]), key="import_redact")
            redactor = build_redactor(cfg)
            name_note = (f"The name list has {redactor.name_count} name(s)." if redactor.name_count
                         else " ".join(redactor.notes))
            st.caption("Names cannot be detected automatically: only names in the name list "
                       f"({cfg['privacy']['name_list_file']}, one per line) are replaced. {name_note}")

            with st.expander("Redaction preview (up to 20 messages, before anything is stored)", expanded=redact):
                preview_table, found = redaction_preview(upload, cfg, 20)
                columns = st.columns(len(TOKENS))
                for column, token in zip(columns, TOKENS):
                    column.metric(f"[{token}]", f"{found[token]:,}")
                if preview_table.empty:
                    st.write("No messages to preview.")
                else:
                    st.dataframe(preview_table, hide_index=True, width="stretch", key="redaction_preview")
                    st.caption("Counts are for every message in the upload. Messages where something would be replaced "
                               "are shown first. This preview is shown on this screen only and never saved."
                               + ("" if redact else " Redaction is OFF: the original text would be stored."))
            permission = st.checkbox(PERMISSION_TEXT, key="import_permission")

            check_key = (fingerprint, mode, target if mode == "add" else name.strip(), as_of.isoformat(), redact,
                         day_first)
            if st.button("Validate", key="validate_button"):
                existing = None
                if mode == "add" and target:
                    existing = read_existing(get_dataset(cfg, target).paths.lending_db)
                st.session_state["import_check"] = (check_key, validate_upload(upload, cfg, as_of, existing, day_first))
            stored = st.session_state.get("import_check")
            report = stored[1] if stored and stored[0] == check_key else None

            if report is None:
                st.caption("Press Validate to check the files. Import becomes possible when there are no errors.")
            else:
                st.dataframe(pd.DataFrame([report.counts]), hide_index=True)
                if report.ok:
                    st.success("No errors found.")
                else:
                    st.error(f"{len(report.errors)} error(s) found. Fix them in your files and upload again. "
                             "Nothing has been written.")
                    for issue in report.errors[:MAX_SHOWN]:
                        st.markdown(f"- {issue}")
                    if len(report.errors) > MAX_SHOWN:
                        st.markdown(f"- ... and {len(report.errors) - MAX_SHOWN} more")
                if report.warnings:
                    with st.expander(f"{len(report.warnings)} warning(s) (these do not block the import)",
                                     expanded=report.ok):
                        for issue in report.warnings[:MAX_SHOWN]:
                            st.markdown(f"- {issue}")
                for issue in report.notes:
                    st.info(str(issue))
                action = "will be replaced" if redact else "will be KEPT (redaction is off)"
                found_text = ", ".join(f"{report.found[t]} {TOKEN_WORDS[t]}" for t in TOKENS)
                st.write(f"Found in message text: {found_text}. They {action}.")

                with st.expander("Possible names to add to the name list"):
                    st.markdown("**Names cannot be detected automatically.** These are the most frequent capitalised "
                                "words that are not at the start of a sentence, not a lender's name and not in the "
                                "stop list (`privacy.possible_names.stop_words`). Most will not be names, and many "
                                "names will not be here. If you see names, add them to "
                                f"`{cfg['privacy']['name_list_file']}` (one per line), then upload again.")
                    lender_names = report.clean["lenders"]["name"].dropna().tolist()
                    candidates = possible_names(report.clean["messages"]["text"].dropna().astype(str), cfg,
                                                lender_names)
                    if candidates.empty:
                        st.write("No candidates found.")
                    else:
                        st.dataframe(candidates.rename(columns={"word": "Word", "messages": "Messages",
                                                                "in_name_list": "Already in the name list"}),
                                     hide_index=True, key="possible_names")

            ready = (report is not None and report.ok and permission
                     and ((mode == "new" and name.strip()) or (mode == "add" and target)))
            if report is not None and report.ok and not permission:
                st.warning("Tick the permission box to import.")
            if st.button("Import", key="import_button", disabled=not ready, type="primary"):
                with st.spinner("Importing and labelling the messages..."):
                    result = import_upload(upload, cfg, mode=mode, permission_confirmed=permission, redact=redact,
                                           as_of=as_of, dataset_name=name, source_description=source, notes=notes,
                                           target=target, day_first=day_first)
                if result.ok:
                    st.session_state.pop("import_check", None)
                    st.session_state["last_import"] = result.dataset
                    finish("ok", result.message + " Switch to it on the Datasets tab or in the sidebar.")
                else:
                    st.error(result.message)

    # --- Templates ---------------------------------------------------------------------------------------------------
    with tab_templates:
        st.markdown(f"Amounts are in **Ugandan shillings ({cfg['currency']['code']})**, whole shillings. "
                    "Fill one of these in. Each sheet or file has one shaded example row (its ids start with "
                    f"**{cfg['onboarding']['example_id_prefix']}**): delete it before importing. Columns with a fixed "
                    "list of values have dropdowns in the workbook.")
        st.download_button("Download the Excel template", data=build_xlsx_template(cfg),
                           file_name="fairlend_import_template.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="tpl_xlsx")
        st.markdown("Or the five CSV templates:")
        for file_name, content in build_csv_templates(cfg).items():
            st.download_button(f"Download {file_name}", data=content, file_name=file_name, mime="text/csv",
                               key=f"tpl_{file_name}")
        st.markdown("**Borrower codes.** Never put names, phone numbers or ID numbers in borrower_id. Each lender "
                    "turns its phone or ID column into codes with `python -m src.make_borrower_codes` using the "
                    "**same secret salt**, so the same person gets the same code at every lender.")

    # --- Data health ------------------------------------------------------------------------------------------------------
    with tab_health:
        health = data_health(cfg)
        if health.get("unreadable"):
            st.error("The active dataset's data file cannot be read (damaged or empty). Import it again or "
                     "switch to another dataset.")
        elif not health["available"]:
            st.info("The active dataset has no data yet.")
        else:
            st.markdown(f"Active dataset: **{data.dataset_name}**. Lenders with fewer than {health['minimum']} messages "
                        "cannot be ranked.")
            st.dataframe(health["per_lender"], hide_index=True, width="stretch")
            st.metric("Borrowers who appear at two or more lenders",
                      f"{health['shared_borrowers']:,} of {health['borrowers']:,}")
            st.markdown("If this is zero or tiny, the overlap detector has nothing to find: check that every lender "
                        "used the same borrower codes.")
