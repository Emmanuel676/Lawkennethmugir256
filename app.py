"""FairLend Watch dashboard - Overview page (Phase 4).

Run it from the project folder:

    streamlit run app.py --server.address localhost

The other pages (Borrowers, Lenders, Export, About) live in pages/. All numbers
come from src/dashboard_data.py, which reads lending.db and predictions.db only.
Flags prompt a human to look; they are not findings. All data is synthetic.
"""

from __future__ import annotations

import streamlit as st

from src.dashboard_data import (band_distribution, coverage_sentence, overview_kpis, ranked_lenders,
                                top_borrowers)
from src.dashboard_ui import band_chart, guarded, lender_interval_chart, page_setup
from src.money import format_money, money_label

with guarded("Overview"):
    data, cfg = page_setup("Overview")
    kpis = overview_kpis(data, cfg)

    kind = "real, confidential" if data.real else "demo, synthetic"
    st.caption(f"Dataset: {data.dataset_name} ({kind}). Data as of {data.as_of_date}. {coverage_sentence(data)}")

    st.subheader("Headline numbers")
    row1 = st.columns(4)
    row1[0].metric("Borrowers scored", f"{kpis['borrowers_scored']:,}")
    for column, band in zip(row1[1:], ("high", "medium", "low")):
        column.metric(f"Band: {band}", f"{kpis['band_counts'][band]:,}", f"{kpis['band_shares'][band]:.1%} of borrowers",
                      delta_color="off")
    row2 = st.columns(4)
    row2[0].metric("Owed by high-band borrowers", format_money(kpis["owed_by_high_band"], cfg))
    row2[1].metric("Messages classified", f"{kpis['messages_classified']:,}",
                   f"{kpis['abusive_message_share']:.1%} labelled abusive", delta_color="off")
    row2[2].metric("Lenders ranked", f"{kpis['lenders_ranked']}", f"{kpis['lenders_unranked']} too small to rank",
                   delta_color="off")
    row2[3].metric("Flagged AND harassed", f"{kpis['flagged_and_harassed']:,}",
                   f"medium/high band and {kpis['concern_min_abusive_messages']}+ abusive messages", delta_color="off")

    left, right = st.columns(2)
    with left:
        st.subheader("Borrowers per band")
        st.altair_chart(band_chart(band_distribution(data)), width="stretch")
    with right:
        top_n = int(cfg["dashboard"]["top_n"])
        st.subheader(f"Highest-risk borrowers (top {top_n})")
        top = top_borrowers(data, top_n).rename(columns={
            "borrower_id": "Borrower", "score": "Score", "band": "Band", "open_lenders": "Open lenders",
            "total_owed": money_label("Total owed", cfg), "abusive_messages": "Abusive msgs"})
        st.dataframe(top, hide_index=True, width="stretch")
        st.caption("Open the Borrowers page to see why each borrower scored as they did.")

    st.subheader("Lenders: share of messages labelled abusive")
    ranked = ranked_lenders(data)
    if ranked.empty:
        st.info(f"No lender has enough messages to be ranked yet (minimum {cfg['generator']['min_lender_messages']}). "
                "See the Lenders page.")
    else:
        st.altair_chart(lender_interval_chart(ranked), width="stretch")
    st.caption("The bar is the share; the black line is its "
               f"{cfg['lender_comparison']['confidence']:.0%} confidence interval. Lenders are ranked by the lower end "
               "of that line, so a small lender cannot top the list by luck. Lenders with too few messages are left out; "
               "see the Lenders page.")

    st.subheader("How to use this")
    st.markdown(
        "Start with the highest-risk borrowers and the lenders at the top of the ranking. Open a borrower on the "
        "**Borrowers** page to see their loans across every lender and the messages they received, and open a lender "
        "on the **Lenders** page to read example messages. A high score or a top rank means *a person should look*. "
        "It is not proof of over-indebtedness or misconduct. **Export** gives the same lists as CSV files, and "
        "**About** explains the score, the message classes and the known weak spots."
    )
