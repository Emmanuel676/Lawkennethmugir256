"""Repayments page: who pays on time, who pays late, who is not paying, and a follow-up list (Phase 10).

A follow-up prompt, not a verdict or a credit score. All logic is in src/repayments.py. Like the Export page, it
works in presentation mode, where only the demo dataset can be shown.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.dashboard_data import BANDS, data_signature
from src.dashboard_ui import CHART_BAR, CHART_TEXT, _theme, config_path, guarded, page_setup
from src.money import format_money, format_money_compact, money_label
from src import repayments as rp


@st.cache_resource(show_spinner="Working out repayment statuses...", max_entries=4)
def _cached(path: str | None, signature: tuple, _cfg: dict, _scores: pd.DataFrame, _lenders: pd.DataFrame) -> dict:
    # signature is part of the cache key only: it changes when a database file changes.
    return rp.load(_cfg, _scores, _lenders)


with guarded("Repayments"):
    data, cfg = page_setup("Repayments")
    settings = cfg["repayments"]
    lenders = (data.loans[["lender_id", "lender_name"]].drop_duplicates().rename(columns={"lender_name": "name"})
               .sort_values("lender_id"))
    result = _cached(config_path(), data_signature(cfg), cfg, data.borrowers, lenders)
    head = result["headline"]

    st.info(f"**{rp.PROMPT}** It shows repayment events so a person knows whose file to open. It says nothing about "
            "anyone's creditworthiness.")
    if result["lump"]:
        st.caption("In this dataset every loan was repaid in one payment, so 'overdue but paying' is rare here. The "
                   "daily-repayment story (part payments, grace, borrowers who stop paying) is shown on the synthetic "
                   "sample packs: see docs\\ONBOARDING_DEMO.md.")

    st.subheader("Loans by repayment status")
    shares, counts = head["shares"], head["counts"]
    row1, row2 = st.columns(3), st.columns(3)
    for column, status in zip(row1, ("on_time", "late_within_grace", "late_beyond_grace")):
        column.metric(rp.LABELS[status], f"{shares[status]:.1%}", f"{counts[status]:,} loans", delta_color="off")
    for column, status in zip(row2[:2], ("not_paying", "unknown")):
        column.metric(rp.LABELS[status], f"{shares[status]:.1%}", f"{counts[status]:,} loans", delta_color="off")
    row2[2].metric("Owed, unpaid loans", format_money_compact(head["owed_unpaid"], cfg),
                   help=(f"Exact amount still owed on all unpaid loans: {format_money(head['owed_unpaid'], cfg)}. "
                         f"Of this, {format_money(head['owed_follow_up'], cfg)} is on loans not paying or overdue."))
    st.caption(
        f"Shares of all {head['loans']:,} loans. Also: {counts['current']:,} current (not yet due), "
        f"{counts['in_grace']:,} past due but within the {settings['grace_days']} grace days, and "
        f"{counts['overdue_paying']:,} overdue but still paying (a linked repayment in the last "
        f"{settings['not_paying_after_days']} days). 'Unknown' means repaid with no linked repayment, so the date it was "
        "cleared cannot be known; it is never guessed.")

    st.subheader("Status mix per lender")
    mix = result["lender_mix"]
    minimum = int(settings["min_loans_to_compare"])
    mix = mix.assign(label=[f"{n}{'' if ok else ' (too small to compare)'}" for n, ok in zip(mix["name"], mix["comparable"])])
    long = mix.melt(id_vars=["label", "loans"], value_vars=[f"share_{s}" for s in rp.STATUSES],
                    var_name="status", value_name="share")
    long["status"] = long["status"].str.removeprefix("share_").map(rp.LABELS)
    long["percent"] = (long["share"] * 100).round(1)
    chart = alt.Chart(long).mark_bar().encode(
        x=alt.X("percent:Q", stack="normalize", title="Share of the lender's loans", axis=alt.Axis(format="%")),
        y=alt.Y("label:N", sort=mix["label"].tolist(), title=None, axis=alt.Axis(labelLimit=260)),
        color=alt.Color("status:N", sort=[rp.LABELS[s] for s in rp.STATUSES], title="Status",
                        scale=alt.Scale(scheme="tableau10")),
        order=alt.Order("status_order:Q"),
        tooltip=["label", "status", alt.Tooltip("percent:Q", title="% of loans"), alt.Tooltip("loans:Q", format=",")],
    ).transform_calculate(status_order="indexof(" + str([rp.LABELS[s] for s in rp.STATUSES]) + ", datum.status)")
    st.altair_chart(chart.properties(height=max(160, 30 * len(mix))), width="stretch")
    st.caption(f"Lenders with fewer than {minimum} loans are marked 'too small to compare'. The table gives the same "
               "figures as words and numbers.")
    table = pd.DataFrame({"Lender": mix["label"], "Loans": mix["loans"]})
    for status in rp.STATUSES:
        table[rp.LABELS[status]] = (mix[f"share_{status}"] * 100).round(1)
    st.dataframe(table, hide_index=True, width="stretch")

    st.subheader("Unpaid loans by days past due")
    buckets = result["ageing"]
    bars = alt.Chart(buckets).encode(
        x=alt.X("bucket:N", sort=buckets["bucket"].tolist(), title="Days past due"),
        y=alt.Y("loans:Q", title="Unpaid loans"), tooltip=["bucket", alt.Tooltip("loans:Q", format=","),
                                                         alt.Tooltip("owed:Q", format=",", title="Owed (UGX)")])
    st.altair_chart((bars.mark_bar(color=CHART_BAR)
                     + bars.mark_text(dy=-6, color=CHART_TEXT[_theme()]).encode(text=alt.Text("loans:Q", format=",")))
                    .properties(height=240), width="stretch")
    st.dataframe(pd.DataFrame({"Days past due": buckets["bucket"], "Unpaid loans": buckets["loans"],
                               money_label("Owed", cfg): buckets["owed"]}), hide_index=True, width="stretch")

    st.subheader("Follow-up list")
    rollup = result["rollup"]
    st.caption("Borrowers (by code only) with at least one loan not paying or overdue but paying, with the cross-lender "
               "context from the risk score. This list is for a person to work through. It is not a ranking of "
               "borrowers, not a verdict and not a credit score.")
    overdue_names = sorted({n for s in rollup["overdue_lenders"] for n in s.split("; ") if n})
    c1, c2, c3 = st.columns(3)
    pick_lenders = c1.multiselect("Lender (none = all)", overdue_names, key="rp_lenders")
    pick_status = c2.multiselect("Status (none = all)", [rp.LABELS[s] for s in rp.FOLLOW_UP], key="rp_status")
    pick_bands = c3.multiselect("Risk band (none = all)", list(BANDS), key="rp_bands")
    c4, c5 = st.columns([3, 1])
    sort_label = c4.selectbox("Sort by", list(rp.FOLLOW_UP_SORTS), key="rp_sort")
    ascending = c5.checkbox("Ascending", value=False, key="rp_ascending")
    by_label = {rp.LABELS[s]: s for s in rp.FOLLOW_UP}
    rows = rp.follow_up(rollup, lenders=pick_lenders, statuses=[by_label[s] for s in pick_status], bands=pick_bands,
                        sort_label=sort_label, ascending=ascending)
    st.markdown(f"**{len(rows):,} borrowers in the follow-up list.**")
    st.dataframe(rp.follow_up_table(rows), hide_index=True, width="stretch")
    st.download_button("Download the follow-up list (CSV)", data=rp.follow_up_csv(rows, data.notice),
                       file_name="repayment_follow_up.csv", mime="text/csv", key="download_follow_up")
    st.caption("The file starts with one '#' line carrying the dataset notice and the words 'follow-up prompt, not a "
               "verdict or a credit score'. Read it with pandas.read_csv(path, comment=\"#\").")

    worst = rollup["worst_status"].value_counts()
    with st.expander("Borrowers by their worst loan status"):
        st.dataframe(pd.DataFrame({"Worst loan status": [rp.LABELS[s] for s in rp.STATUSES],
                                   "Borrowers": [int(worst.get(s, 0)) for s in rp.STATUSES]}),
                     hide_index=True, width="stretch")
        st.caption("A borrower's status is the worst among their loans. 'Unknown' ranks just above 'on time', so missing "
                   "information is never shown as a good record.")

    st.subheader("Known limits")
    for line in rp.LIMITS:
        st.markdown(f"- {line}")
