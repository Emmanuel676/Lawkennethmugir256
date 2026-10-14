"""Guided Demo page: a 5-minute walkthrough of six featured cases (Phase 5.2).

The cases are picked by featured_cases() in src/dashboard_data.py, by rules from the computed
signals only. Each button opens the right page already focused on that case. The full spoken
script is docs/DEMO_SCRIPT.md.
"""

from __future__ import annotations

import streamlit as st

from src.dashboard_data import featured_cases
from src.dashboard_ui import focus_on, guarded, page_setup

with guarded("Guided Demo"):
    data, cfg = page_setup("Guided Demo")
    st.markdown("A five-minute walkthrough: **six steps, about 45 seconds each**. Each step says one sentence to say "
                "out loud, and its button opens the page already showing that case. The full script with timings "
                "and the hard questions is in `docs/DEMO_SCRIPT.md`.")
    st.markdown("Say these three things out loud at the start: **the data is synthetic**; **the accuracy figures "
                "are optimistic** because the data was built to be separable; **a person decides**, the tool only "
                "points at files worth reading.")

    if data.real:
        st.info("The guided demo is written for the demo dataset. A real dataset is active: switch to the demo in "
                "the sidebar (or start the app in presentation mode) before presenting.")
        st.stop()

    featured = featured_cases(data, cfg)
    for case in featured["cases"]:
        with st.container(border=True):
            st.markdown(f"### {case['step']}. {case['title']}")
            st.markdown(f"**Say:** {case['say']}")
            where = "Borrowers" if case["kind"] == "borrower" else "Lenders"
            if st.button(f"Open on the {where} page", key=f"go_{case['key']}"):
                focus_on(case["kind"], case["id"], case["page"])
    for sentence in featured["missing"]:
        st.caption(f"Step left out: {sentence}")
    st.caption("Cases are chosen by fixed rules from the computed scores and message labels (thresholds in the "
               "'demo' section of config.yaml), never from answer labels. Same data, same cases.")
