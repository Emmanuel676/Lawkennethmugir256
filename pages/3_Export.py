"""Export page: download the flagged borrowers and the lender comparison as CSV (Phase 4)."""

from __future__ import annotations

import streamlit as st

from src.dashboard_data import BANDS, filter_borrowers, flagged_borrowers_csv, lender_comparison_csv
from src.dashboard_ui import guarded, page_setup

with guarded("Export"):
    data, cfg = page_setup("Export")

    st.markdown(
        "Each file starts with one line beginning with `#` that carries the synthetic-data notice. To read a file with "
        "pandas use `pandas.read_csv(path, comment=\"#\")`. In Excel the notice appears as the first row.")

    st.subheader("Flagged borrowers")
    bands = st.multiselect("Bands to include", list(BANDS), default=["high", "medium"], key="export_bands")
    min_abusive = st.number_input("Minimum abusive messages", min_value=0, value=0, step=1, key="export_min_abusive")
    chosen = filter_borrowers(data.borrowers, bands=bands, min_abusive_messages=min_abusive)
    if not bands:
        st.info("No band selected, so every borrower is included.")
    st.write(f"{len(chosen):,} borrowers will be exported.")
    st.download_button("Download flagged borrowers (CSV)", data=flagged_borrowers_csv(chosen, data.notice),
                       file_name="flagged_borrowers.csv", mime="text/csv", key="download_borrowers")

    st.subheader("Lender comparison")
    st.write(f"{len(data.lenders):,} lenders will be exported (ranked and unranked). "
             f"Labels come from the '{data.classifier}' classifier.")
    st.download_button("Download lender comparison (CSV)",
                       data=lender_comparison_csv(data.lenders, data.classifier, data.notice, data.human_share),
                       file_name="lender_comparison.csv", mime="text/csv", key="download_lenders")
