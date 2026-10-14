"""Review page: a person checks the classifier's labels on real data (Phase 5.1).

All logic lives in src/review.py. Human labels are stored in the dataset's own
predictions file and win over the model's label everywhere in the dashboard.
"""

from __future__ import annotations

import streamlit as st

from src.config import MESSAGE_CLASSES
from src.dashboard_data import CLASS_DESCRIPTIONS
from src.dashboard_ui import guarded, page_setup, presentation_block
from src.datasets import DEMO, get_active_paths
from src.review import (ReviewError, human_labels, measured_accuracy, message_for_review, missing_for_retrain,
                        next_batch, progress, retrain, retrained_model_info, reviewed_labels_csv, save_label)

with guarded("Review"):
    data, cfg = page_setup("Review")
    presentation_block(cfg)
    review = cfg["classifier"]["review"]
    paths = get_active_paths(cfg)
    KIND_LABELS = {"random": "Random check (measures accuracy fairly)", "hard": "Hard cases (helps retraining)"}

    flash = st.session_state.pop("review_flash", None)
    if flash:
        (st.success if flash[0] == "ok" else st.error)(flash[1])

    if data.dataset == DEMO:
        st.info("This is the demo dataset. It has answer labels elsewhere, so its accuracy is measured with "
                "`python -m src.evaluate_classifier`. Review is meant for REAL datasets; you can try the page here, "
                "but retraining is switched off for the demo.")

    st.markdown("The message labels come from a model trained on **synthetic** text. On real messages it can be wrong "
                "often. Check a sample here: your label replaces the model's label everywhere in the dashboard, and a "
                "random check tells you how often the model is right.")
    with st.expander("The four classes (full definitions on the [About page](/About))", expanded=False):
        for name in MESSAGE_CLASSES:
            st.markdown(f"- **{name}**: {CLASS_DESCRIPTIONS[name]}")

    # --- Progress and measured accuracy ----------------------------------------------------------------------------
    state = progress(paths)
    row = st.columns(4)
    # The total goes under the number, so a long "12,345 of 26,780" is never cut off in a narrow tile.
    row[0].metric("Messages reviewed", f"{state['reviewed']:,}",
                  f"of {state['messages']:,} ({state['share_reviewed']:.1%})", delta_color="off")
    row[1].metric("Random check", f"{state['per_batch']['random']:,}")
    row[2].metric("Hard cases", f"{state['per_batch']['hard']:,}")
    row[3].metric("Checked by a person", f"{data.human_share:.1%}",
                  help="Share of all message labels in this dataset that a person has checked; those labels "
                       "replace the model's label everywhere.")
    st.dataframe(state["table"].rename_axis("batch").reset_index(), hide_index=True, key="progress_table")

    with st.container(border=True):
        st.markdown("**Measured accuracy of the current model** (random check only)")
        accuracy = measured_accuracy(paths, cfg)
        st.write(accuracy["sentence"])
        if accuracy["ok"]:
            per_class = accuracy["per_class"].assign(
                recall=lambda f: (f["recall"] * 100).round(0), low=lambda f: (f["low"] * 100).round(0),
                high=lambda f: (f["high"] * 100).round(0))
            st.dataframe(per_class.rename(columns={"class": "Class", "checked": "Checked", "model_right": "Model right",
                                                   "recall": "Recall %", "low": "Range low %", "high": "Range high %"}),
                         hide_index=True, key="accuracy_table")
        st.caption("Only the random-check batch counts here: hard cases are picked on purpose and would make the model "
                   "look worse than it is.")

    # --- Reviewing ---------------------------------------------------------------------------------------------------
    st.subheader("Review messages")
    left, middle, right = st.columns([2, 1, 1])
    kind = left.radio("Batch", list(KIND_LABELS), format_func=KIND_LABELS.get, key="batch_kind", horizontal=True)
    size = middle.number_input("Messages in a batch", min_value=1, max_value=500,
                               value=int(review["sample_size_default"]), key="batch_size")
    reviewer = right.text_input("Your initials or code", key="reviewer", max_chars=20,
                                help="Initials or a code only. A name is never needed.")

    if st.button("Start a new batch", key="start_batch"):
        try:
            ids = next_batch(paths, kind, int(size), int(review["seed"]))
            st.session_state["review_queue"] = {"dataset": paths.name, "kind": kind, "ids": ids, "pos": 0}
            if not ids:
                st.session_state["review_flash"] = ("ok", "Every message has been reviewed already.")
            st.rerun()
        except ReviewError as error:
            st.error(str(error))

    queue = st.session_state.get("review_queue")
    if queue and queue["dataset"] != paths.name:
        queue = None  # the dataset was switched: that batch belongs to another dataset
    if queue and queue["pos"] < len(queue["ids"]):
        message_id = queue["ids"][queue["pos"]]
        item = message_for_review(paths, message_id)
        st.markdown(f"**Message {queue['pos'] + 1} of {len(queue['ids'])}** ({KIND_LABELS[queue['kind']].split(' (')[0]})"
                    f" · {item['lender']} · {item['sent_at']} · sent to the {item['recipient_type'].replace('_', ' ')}")
        with st.container(border=True):
            st.text(item["text"])
        if review["show_prediction_before_label"] and item["model_label"]:
            st.caption(f"The model's label: {item['model_label']}")
        buttons = st.columns(len(MESSAGE_CLASSES) + 1)
        chosen = None
        for column, name in zip(buttons, MESSAGE_CLASSES):
            if column.button(name, key=f"label_{name}", width="stretch"):
                chosen = name
        skipped = buttons[-1].button("Not sure / skip", key="label_skip", width="stretch")
        if chosen:
            try:
                save_label(paths, message_id, chosen, queue["kind"], reviewer)
                said = item["model_label"] or "no label"
                agree = "agreed" if said == chosen else "had said " + said
                st.session_state["review_flash"] = ("ok", f"Saved as {chosen}. The model {agree}.")
                queue["pos"] += 1
                st.rerun()
            except ReviewError as error:
                st.error(str(error))
        elif skipped:
            queue["pos"] += 1  # skipped messages are not stored and may come up again in a later batch
            st.rerun()
    elif queue:
        st.success("Batch finished. Start a new one when you are ready.")
    else:
        st.caption("Start a batch. Do the random check first: it is the only fair measure of accuracy.")

    # --- Retraining --------------------------------------------------------------------------------------------------
    st.subheader("Retrain on your labels")
    human = human_labels(paths)
    missing = missing_for_retrain(human, cfg)
    own = retrained_model_info(paths)
    if own:
        st.write(f"This dataset has its own retrained model ({own.get('n_human', '?')} human labels, trained "
                 f"{own.get('trained_at', '?')} UTC). New labels are made with it.")
    if data.dataset == DEMO:
        st.write("Retraining is switched off for the demo; its demo-trained model is never overwritten.")
    elif missing:
        st.write("Not possible yet. Still needed: " + "; ".join(missing) + ".")
    else:
        st.write(f"Trains on your {len(human)} labels" + (f" plus the demo's synthetic messages at weight "
                                                           f"{review['demo_weight']}" if review["include_demo_in_retrain"]
                                                           else "") + ", checks itself by cross-validation on your "
                 "labels only, then re-labels this dataset.")
    if st.button("Retrain", key="retrain_button", disabled=data.dataset == DEMO or bool(missing)):
        with st.spinner("Retraining and re-labelling..."):
            report = retrain(cfg, paths)
        st.session_state["retrain_report"] = (paths.name, report)
    stored = st.session_state.get("retrain_report")
    if stored and stored[0] == paths.name:
        report = stored[1]
        (st.success if report.ok else st.error)(report.message)
        if report.lines:
            st.code("\n".join(report.lines), language=None)

    # --- Export --------------------------------------------------------------------------------------------------------
    st.subheader("Export reviewed labels")
    st.download_button("Download reviewed labels (CSV)", data=reviewed_labels_csv(paths, data.notice),
                       file_name=f"reviewed_labels_{paths.name}.csv", mime="text/csv", key="export_reviewed",
                       disabled=human.empty)
    st.caption("The file starts with a '#' notice line (read it with pandas.read_csv(..., comment='#')). It includes "
               "the message text as stored, which is redacted if redaction was on at import. Real data is confidential.")
