"""About page: what the system does, how it scores, and its limits (Phase 4)."""

from __future__ import annotations

import streamlit as st

from src.dashboard_data import class_table, gemini_summary, signal_weights
from src.dashboard_ui import guarded, logo_image, page_setup
from src.datasets import presentation_mode

with guarded("About"):
    data, cfg = page_setup("About")
    bands = cfg["risk"]["bands"]

    name, tagline = cfg["project"]["name"], cfg["project"]["tagline"]

    logo_image()
    st.subheader(f"What {name} does")
    st.markdown(
        f"**{name}** ({tagline.lower()}) gives a regulator or consumer body a view **across lenders** that no single "
        "lender has. It scores "
        "each borrower for signs of over-indebtedness from overlapping app loans, and it compares lenders by how "
        "their collection messages read. It points a person at files worth reading. It decides nothing.")

    st.subheader("The borrower risk score")
    st.markdown(
        f"Each signal earns a share of its weight, reaching full points at the value shown. The weights add up to 100. "
        f"Bands: **low** below {bands['medium']}, **medium** from {bands['medium']}, **high** from {bands['high']}.")
    st.dataframe(signal_weights(cfg), hide_index=True, width="stretch")
    if cfg["risk"]["cycling_forces_minimum_band"]:
        st.markdown(f"A borrower with {cfg['risk']['cycling_minimum_events']} or more cycling events is placed in at "
                    "least the **medium** band, even if the score alone is lower. This is marked on their page.")
    st.caption("All of these values are read from config.yaml.")

    st.subheader("The four message classes")
    st.dataframe(class_table(), hide_index=True, width="stretch")
    st.markdown(f"Labels shown in this dashboard come from the **{data.classifier}** classifier "
                f"(`classifier.primary` in config.yaml), except the {data.human_share:.1%} of messages a person has "
                "checked on the Review page: there the person's label is used. Threat and shaming count as abusive.")

    # A second opinion from Gemini on the synthetic test split, if it has been run. Read from a file only.
    # Hidden in presentation mode: the demo script does not cover it, so it should not appear on a projector.
    second = gemini_summary(cfg)
    if second is not None and not presentation_mode(cfg):
        st.subheader("Second opinion on the synthetic test set")

        def pct(value):
            return "n/a" if value is None else f"{value:.0%}"

        st.markdown(
            f"An outside model ({second.get('model', '?')}, run {second.get('created_at', '?')}) labelled the "
            f"{second['messages']} held-out **synthetic** test messages. The local classifier agreed with the true "
            f"class on {pct(second['local_vs_truth'])}, the outside model on {pct(second['gemini_vs_truth'])}, and "
            f"the two agreed with each other on {pct(second['local_vs_gemini'])}. They disagree on "
            f"{len(second['disagreeing_phrasings'])} of {second.get('phrasings', '?')} phrasings.")
        if not second.get("complete", True):
            st.caption("The last run did not finish: these figures cover only the messages answered so far.")
        st.caption("This is a second opinion on synthetic text from a small set of templates, not proof of accuracy "
                   "on real messages. It is never used for the labels in this dashboard, and real data is never sent.")

    st.subheader("Ethics and limits")
    st.markdown("""
    - **All data is synthetic.** It describes no real people, loans, lenders or messages.
    - **Accuracy is optimistic.** The data was generated to be separable; real borrowers and real messages are messier.
    - **A human decides.** A flag or a rank means someone should look. It is never a finding or a verdict.
    - **Real data needs legal clearance** before it is loaded, and it must **never be sent to the Gemini free tier**,
      where submitted content may be used to improve Google's products.
    """)

    st.subheader("Known weak spots")
    st.markdown("""
    - **Look-alike borrowers sit near the medium threshold.** Borrowers with high income and several small loans have a
      median score just under the medium cut-off, so about half of them land in medium. Small changes would swing this.
    - **Cycling borrowers are flagged mainly through the forcing rule.** Their score alone is usually low; the rule
      that lifts repeated cycling to medium does most of the work.
    - **The classifier was tested on only 16 held-out phrasings.** The 400 test messages come from 16 wordings, so the
      number to quote is "about 14 of 16 unseen phrasings handled", not "93% of 400 messages".
    - **One polite-reminder phrasing was misread as shaming every time**, and one shaming phrasing ("your colleagues
      will receive a message about your debt") was read as a threat every time.
    - **Some harassed borrowers have a low risk score.** Their problem is the messages, not the debt. Use the
      abusive-message filter on the Borrowers page to find them.
    """)
