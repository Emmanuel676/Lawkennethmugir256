"""Borrowers page: filter, sort and open one borrower's full picture (Phase 4)."""

from __future__ import annotations

import streamlit as st

from src.dashboard_data import (BANDS, SORT_OPTIONS, borrower_detail, borrower_table, filter_borrowers, page_count,
                                page_slice, sort_borrowers)
from src.dashboard_ui import guarded, page_setup, points_chart, take_focus, timeline_chart
from src.money import format_money, format_money_compact, money_label

with guarded("Borrowers"):
    data, cfg = page_setup("Borrowers")
    borrowers = data.borrowers
    focus = take_focus("borrower")
    if focus is not None and focus in set(borrowers["borrower_id"]):
        # Opened from the Guided Demo: clear the filters so the borrower is in the list, then open them.
        for key in ("bands", "regions", "min_score", "min_lenders", "min_abusive", "id_search", "page"):
            st.session_state.pop(key, None)  # back to the defaults
        st.session_state["borrower_pick"] = focus

    with st.sidebar:
        st.header("Filters")
        bands = st.multiselect("Band", list(BANDS), default=list(BANDS), key="bands")
        regions = st.multiselect("Region (none selected = all)", sorted(borrowers["region"].unique()), key="regions")
        min_score = st.slider("Minimum score", 0, 100, 0, key="min_score")
        min_lenders = st.number_input("Minimum open lenders", min_value=0, value=0, step=1, key="min_lenders")
        min_abusive = st.number_input("Minimum abusive messages", min_value=0, value=0, step=1, key="min_abusive")
        id_search = st.text_input("Borrower id contains", key="id_search")
        st.header("Sort")
        sort_label = st.selectbox("Sort by", list(SORT_OPTIONS), key="sort_by")
        ascending = st.checkbox("Ascending", value=False, key="ascending")

    filtered = sort_borrowers(
        filter_borrowers(borrowers, bands=bands, regions=regions, min_score=min_score, min_open_lenders=min_lenders,
                         min_abusive_messages=min_abusive, id_search=id_search),
        sort_label, ascending)

    page_size = int(cfg["dashboard"]["table_page_size"])
    pages = page_count(len(filtered), page_size)
    st.markdown(f"**{len(filtered):,} of {len(borrowers):,} borrowers match the filters.**")
    page = st.number_input(f"Page (1 to {pages})", min_value=1, max_value=pages, value=1, step=1, key="page")
    st.dataframe(borrower_table(page_slice(filtered, page, page_size), cfg), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Open a borrower")
    if filtered.empty:
        st.info("No borrower matches the filters.")
        st.stop()

    labels = {r.borrower_id: f"{r.borrower_id}  (score {r.score:.1f}, {r.band})" for r in filtered.itertuples()}
    picked = st.selectbox("Borrower", list(labels), index=None, format_func=labels.get,
                          placeholder="Choose a borrower from the filtered list", key="borrower_pick")
    if picked is None:
        st.stop()

    detail = borrower_detail(data, picked, cfg)
    row = detail["row"]

    st.header(f"Borrower {picked}")
    cols = st.columns(5)
    cols[0].metric("Score", f"{row['score']:.1f}")
    cols[1].metric("Band", str(row["band"]))
    cols[2].metric("Open lenders", int(row["open_lenders"]))
    cols[3].metric("Total owed", format_money_compact(row["total_owed"], cfg),
                   help=f"Exact amount: {format_money(row['total_owed'], cfg)}")
    cols[4].metric("Monthly income", format_money_compact(row["monthly_income"], cfg),
                   help=f"Exact amount: {format_money(row['monthly_income'], cfg)}")
    st.caption(f"Region {row['region']}. Debt is {row['debt_to_income']:.2f} times monthly income; "
               f"{row['arrears_share']:.0%} of it is in arrears.")
    if bool(row["band_forced_by_cycling"]):
        st.warning("Placed in the medium band because of repeated cycling (borrowing to repay), "
                   "although the score alone is below the medium threshold.")

    st.subheader("Score breakdown")
    st.altair_chart(points_chart(detail["points"]), width="stretch")
    for line in detail["explanation"]:
        st.markdown(f"- {line}")

    st.subheader("Loans across all lenders")
    st.caption(f"This borrower has loans with {detail['lenders_involved']} lender(s). This cross-lender view is what no "
               "single lender can see: each lender only knows its own loans.")
    st.dataframe(detail["loans"].rename(columns={"principal": money_label("principal", cfg),
                                                 "owed": money_label("owed", cfg)}),
                 hide_index=True, width="stretch")

    st.subheader("Loan timeline")
    st.altair_chart(timeline_chart(detail["timeline"]), width="stretch")

    st.subheader("Messages received")
    messages = detail["messages"]
    if messages.empty:
        st.info("No collection messages for this borrower.")
    else:
        st.caption(f"{len(messages)} messages. Class labels come from the '{data.classifier}' classifier and are a "
                   "model's guesses. Late night and third party are facts of the message, not guesses.")
        st.dataframe(messages.drop(columns=["borrower_id"]), hide_index=True, width="stretch")
