"""Lenders page: the ranking, the lenders too small to rank, and example messages (Phase 4)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard_data import coverage_sentence, lender_detail, lender_table, ranked_lenders, unranked_lenders
from src.dashboard_ui import guarded, lender_interval_chart, page_setup, take_focus
from src.datasets import get_active_paths, presentation_mode
from src.try_message import MAX_CHARS, NOTE, classify_one, load, model_file


@st.cache_resource(max_entries=2)
def _model(path: str, modified: int):
    return load(path)  # modified is part of the cache key only: a retrained model is loaded again


def _label_it(path: str, modified: int) -> None:
    """Runs on submit, before the page reruns: label the text, keep only the result, empty the box.

    So the typed text is not kept even in this session's memory once it has been labelled.
    """
    st.session_state["try_result"] = classify_one(_model(path, modified), st.session_state.get("try_text", ""))
    st.session_state["try_text"] = ""


with guarded("Lenders"):
    data, cfg = page_setup("Lenders")
    level = f"{cfg['lender_comparison']['confidence']:.0%}"
    minimum = int(cfg["generator"]["min_lender_messages"])

    st.markdown(
        f"Lenders are ranked by the **lower end** of the {level} confidence interval of the share of their messages "
        "labelled abusive (threat or shaming). A small lender with a few bad messages therefore cannot top the list by "
        f"luck. Lenders with fewer than {minimum} messages are not ranked at all.")
    st.caption(coverage_sentence(data))

    ranked = ranked_lenders(data)
    st.subheader("Ranked lenders")
    if ranked.empty:
        st.info("No lender has enough messages to be ranked.")
    else:
        st.dataframe(lender_table(ranked), hide_index=True, width="stretch")
        st.altair_chart(lender_interval_chart(ranked), width="stretch")

    st.subheader("Too few messages to rank")
    unranked = unranked_lenders(data)
    if unranked.empty:
        st.write("Every lender has enough messages to be ranked.")
    else:
        for row in unranked.itertuples():
            st.markdown(f"- **{row.name}** ({row.size_category}): {row.reason} - {row.n_messages} messages, "
                        f"minimum {minimum}. Its share ({row.abusive_share:.0%}, interval {row.abusive_low:.0%} to "
                        f"{row.abusive_high:.0%}) is too uncertain to compare.")

    st.divider()
    st.subheader("Look at one lender")
    names = dict(zip(data.lenders["lender_id"], data.lenders["name"]))
    focus = take_focus("lender")
    if focus is not None and focus in names:
        st.session_state["lender_pick"] = focus  # opened from the Guided Demo
    picked = st.selectbox("Lender", list(names), index=None, format_func=names.get,
                          placeholder="Choose a lender", key="lender_pick")
    if picked is not None:
        detail = lender_detail(data, picked, cfg)
        st.markdown(detail["sentence"])
        per_class = int(cfg["dashboard"]["example_messages_per_class"])
        for name, examples in detail["examples"].items():
            st.markdown(f"**Example messages labelled {name}** (up to {per_class}, the same ones every time)")
            if examples.empty:
                st.write("None.")
            else:
                st.dataframe(examples, hide_index=True, width="stretch")
        st.caption("Examples were labelled by a model. Read them yourself before drawing any conclusion.")

    # Try one message. Hidden in presentation mode: the demo script does not use it, and a live typed
    # message on a projector could get a confident wrong label that nobody has rehearsed.
    if not presentation_mode(cfg):
        st.divider()
        st.subheader("Try a message")
        path, source = model_file(cfg, get_active_paths(cfg))
        if path is None:
            st.info(source)
        else:
            with st.form("try_message"):
                st.text_area("Type or paste one message", max_chars=MAX_CHARS, key="try_text",
                             placeholder="for example: Pay today or we will tell your family.")
                st.form_submit_button("Label it", on_click=_label_it, args=(str(path), path.stat().st_mtime_ns))
            result = st.session_state.pop("try_result", None)
            if result is not None:
                if "error" in result:
                    st.info(result["error"])
                else:
                    st.markdown(f"The model would label this message **{result['label']}**.")
                    st.dataframe(pd.DataFrame({
                        "Class": list(result["probabilities"]),
                        "Probability %": [round(p * 100, 1) for p in result["probabilities"].values()]}),
                        hide_index=True, key="try_probabilities")
            st.caption(f"{NOTE} Model: {source}. Lender names are masked as in training. What you type is not "
                       "stored, not logged and not added to any dataset.")
