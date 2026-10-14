"""Edge cases (Phase 5.2): odd datasets must give a friendly message on every page, never a traceback.

Each case is a small hand-made REAL dataset written straight into a dataset folder (so it can be
odd in ways the importer would refuse, such as having no rows at all), labelled with the local
classifier, made active, and then every relevant page is run headless.
"""

from __future__ import annotations

import copy
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import db
from src.classify_messages import classify_dataset
from src.dashboard_data import featured_cases, load_all
from src.dashboard_ui import CONFIG_VARIABLE
from src.datasets import REAL_NOTICE, create_dataset, get_dataset_paths, set_active
from src.lender_comparison import compare_lenders
from src.predictions import now_utc, upsert_predictions

from worlds import build_classified_world, write_config

ROOT = Path(__file__).resolve().parents[1]
ALL_PAGES = ["app.py"] + sorted(f"pages/{p.name}" for p in (ROOT / "pages").glob("*.py"))
MAIN_PAGES = ["app.py", "pages/0_Guided_Demo.py", "pages/1_Borrowers.py", "pages/2_Lenders.py", "pages/3_Export.py"]
AS_OF = "2026-10-01"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """A small classified demo (for the saved model) shared by every case."""
    cfg, _ = build_classified_world(tmp_path_factory.mktemp("edge_world"), n_borrowers=300)
    return cfg


@pytest.fixture
def cfg(base, tmp_path, monkeypatch):
    custom = copy.deepcopy(base)
    custom["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    custom["paths"]["active_dataset_file"] = str(tmp_path / "active.txt")
    custom["app"]["log_file"] = str(tmp_path / "logs" / "app.log")
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(custom, tmp_path / "config.yaml")))
    monkeypatch.delenv("FAIRLEND_PRESENT", raising=False)
    return custom


def make_dataset(cfg, name, lenders=(), borrowers=(), loans=(), messages=(), transactions=(), classify=True,
                 all_labels=None):
    """Write a real dataset directly (rows in database column order), label it, make it active."""
    info = create_dataset(cfg, name, "edge case", AS_OF)
    conn = db.create_database(info.paths.lending_db, db.LENDING_SCHEMA)
    with conn:
        for table, rows in (("lenders", lenders), ("borrowers", borrowers), ("loans", loans),
                            ("transactions", transactions), ("messages", messages)):
            db.insert_rows(conn, table, [dict(zip(db.COLUMNS[table], row)) for row in rows])
        conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)",
                         [("synthetic", "false"), ("notice", REAL_NOTICE), ("as_of_date", AS_OF)])
    conn.close()
    if classify:
        classify_dataset(cfg, info.paths)
    if all_labels:
        conn = sqlite3.connect(str(info.paths.predictions_db))
        upsert_predictions(conn, [{"message_id": m[0], "classifier": "local", "model": "edge",
                                   "predicted_class": all_labels, "confidence": 0.9, "created_at": now_utc()}
                                  for m in messages])
        conn.close()
    set_active(cfg, info.slug)
    return info.paths


def run(page: str) -> AppTest:
    return AppTest.from_file(str(ROOT / page), default_timeout=120).run()


def assert_friendly(at: AppTest, page: str) -> None:
    assert not at.exception, (page, [e.value for e in at.exception])
    assert not any("Something went wrong" in e.value for e in at.error), (page, [e.value for e in at.error])


def assert_pages(pages) -> list[AppTest]:
    runs = []
    for page in pages:
        at = run(page)
        assert_friendly(at, page)
        runs.append(at)
    return runs


def lender(i, size="small"):
    return (f"L{i}", f"Lender {i}", size)


def borrower(i, income=300000):
    return (f"B{i}", "Central", income, "2025-01-01")


def loan(i, b, lender_id, status="active", owed=100000, issued="2026-08-01", due="2026-09-01"):
    return (f"LN{i}", f"B{b}", lender_id, 100000, 0 if status == "repaid" else owed, issued, due, status)


def message(i, lender_id, b, text="Reminder: your loan is due.", sent="2026-09-01 10:00:00", to="borrower"):
    return (f"M{i}", lender_id, f"B{b}", to, sent, text)


def standard(n_borrowers=8, n_lenders=2, per_borrower=3):
    lenders = [lender(i) for i in range(1, n_lenders + 1)]
    borrowers = [borrower(i) for i in range(1, n_borrowers + 1)]
    loans = [loan(i, i, f"L{(i % n_lenders) + 1}") for i in range(1, n_borrowers + 1)]
    messages = [message(f"{b}_{k}", f"L{(b % n_lenders) + 1}", b) for b in range(1, n_borrowers + 1)
                for k in range(per_borrower)]
    return lenders, borrowers, loans, messages


# --- The cases -----------------------------------------------------------------------------------------------

def test_an_empty_dataset_on_every_page(cfg):
    make_dataset(cfg, "Empty", classify=True)
    data = load_all(cfg)
    assert data.status == "empty" and "has no borrowers" in data.message
    for at, page in zip(assert_pages(ALL_PAGES), ALL_PAGES):
        if page not in ("pages/5_Data.py", "pages/4_About.py", "pages/6_Review.py"):
            assert any("has no borrowers" in e.value for e in at.error), page


def test_a_lender_with_no_loans_and_one_with_no_messages(cfg):
    lenders, borrowers, loans, messages = standard()
    lenders += [lender(3), lender(4)]
    messages.append(message("x", "L3", 1))           # L3: messages but no loans
    make_dataset(cfg, "Lonely lenders", lenders, borrowers, loans, messages)  # L4: neither
    runs = assert_pages(MAIN_PAGES)
    at = runs[3]  # Lenders page
    at.selectbox(key="lender_pick").set_value("L3").run()
    assert_friendly(at, "lenders drill-down")
    assert "L4" not in list(load_all(cfg).lenders["lender_id"])  # a lender with no messages is not compared


def test_a_borrower_with_no_loans(cfg):
    lenders, borrowers, loans, messages = standard()
    borrowers.append(borrower(99))
    make_dataset(cfg, "No loans", lenders, borrowers, loans, messages)
    data = load_all(cfg)
    row = data.borrowers.set_index("borrower_id").loc["B99"]
    assert row["score"] == 0 and row["band"] == "low"
    at = assert_pages(["pages/1_Borrowers.py"])[0]
    at.selectbox(key="borrower_pick").set_value("B99").run()
    assert_friendly(at, "borrower with no loans")
    assert any("No collection messages" in i.value for i in at.info)


def test_a_dataset_with_one_lender_only(cfg):
    make_dataset(cfg, "One lender", *standard(n_lenders=1))
    data = load_all(cfg)
    assert len(data.lenders) == 1
    assert_pages(MAIN_PAGES)


def test_all_loans_repaid(cfg):
    lenders, borrowers, loans, messages = standard()
    loans = [loan(i, i, f"L{(i % 2) + 1}", status="repaid") for i in range(1, 9)]
    make_dataset(cfg, "All repaid", lenders, borrowers, loans, messages)
    data = load_all(cfg)
    assert (data.borrowers["total_owed"] == 0).all() and (data.borrowers["band"] == "low").all()
    assert_pages(MAIN_PAGES)
    assert any("No borrower is in the high band" in m for m in featured_cases(data, cfg)["missing"])


@pytest.mark.parametrize("label", ["normal", "threat"])
def test_all_messages_in_one_class(cfg, label):
    lenders, borrowers, loans, messages = standard(per_borrower=10)
    make_dataset(cfg, f"One class {label}", lenders, borrowers, loans, messages, all_labels=label)
    data = load_all(cfg)
    assert set(data.messages["predicted_class"]) == {label}
    runs = assert_pages(MAIN_PAGES)
    at = runs[3]
    at.selectbox(key="lender_pick").set_value("L1").run()
    assert_friendly(at, "one-class drill-down")


def test_zero_abusive_messages_everywhere(cfg):
    lenders, borrowers, loans, messages = standard(per_borrower=10)
    make_dataset(cfg, "Calm", lenders, borrowers, loans, messages, all_labels="firm_pressure")
    data = load_all(cfg)
    assert data.borrowers["abusive_messages"].sum() == 0
    assert (data.lenders["abusive_share"] == 0).all()
    assert_pages(MAIN_PAGES)
    assert any("No borrower received abusive messages" in m for m in featured_cases(data, cfg)["missing"])


def test_ties_in_the_lender_ranking_are_broken_by_lender_id(base):
    """Identical lenders rank in lender_id order (sort keys: interval low, share, then lender_id)."""
    messages = pd.DataFrame({
        "message_id": [f"M{i}" for i in range(300)],
        "lender_id": ["L3"] * 100 + ["L1"] * 100 + ["L2"] * 100,
        "borrower_id": ["B1"] * 300, "recipient_type": ["borrower"] * 300, "sent_at": ["2026-09-01 10:00:00"] * 300})
    labels = pd.DataFrame({"message_id": messages["message_id"],
                           "predicted_class": (["threat"] * 20 + ["normal"] * 80) * 3})
    names = pd.DataFrame({"lender_id": ["L1", "L2", "L3"], "name": ["C", "B", "A"]})
    for order in (names, names.iloc[::-1]):
        table = compare_lenders(messages.sample(frac=1, random_state=4), labels, order, base)
        assert table["lender_id"].tolist() == ["L1", "L2", "L3"]
        assert table["rank"].tolist() == [1, 2, 3]


def test_very_long_messages_emoji_and_non_latin_text(cfg):
    lenders, borrowers, loans, messages = standard()
    messages += [message("long", "L1", 1, "Pay now. " * 2000),
                 message("emoji", "L1", 1, "Lipa sasa \U0001F4B0\U0001F621 au tutakuja nyumbani"),
                 message("ar", "L2", 2, "ادفع الآن أو سنخبر عائلتك"),
                 message("lug", "L2", 2, "Sasula ebbanja lyo leero. Ŋŋ ẽ")]
    make_dataset(cfg, "Unicode", lenders, borrowers, loans, messages)
    assert_pages(MAIN_PAGES)
    at = run("pages/1_Borrowers.py")
    at.selectbox(key="borrower_pick").set_value("B1").run()
    assert_friendly(at, "unicode borrower")


def test_loans_and_messages_dated_after_the_as_of_date(cfg):
    lenders, borrowers, loans, messages = standard()
    loans.append(loan(50, 1, "L1", issued="2027-01-01", due="2027-02-01"))
    messages.append(message("future", "L1", 1, sent="2027-01-05 23:30:00"))
    make_dataset(cfg, "Future", lenders, borrowers, loans, messages)
    assert load_all(cfg).ok
    assert_pages(MAIN_PAGES)


def test_the_active_datasets_files_deleted_by_hand(cfg):
    paths = make_dataset(cfg, "Deleted", *standard())
    paths.lending_db.unlink()
    data = load_all(cfg)
    assert data.status == "missing" and "has no data file" in data.message
    for at in assert_pages(MAIN_PAGES):
        assert any("has no data file" in e.value for e in at.error)
    shutil.rmtree(paths.lending_db.parent)  # the whole folder gone: the app falls back to the demo
    at = assert_pages(["app.py"])[0]
    assert any("SYNTHETIC" in w.value for w in at.warning)


def test_stale_predictions(cfg):
    paths = make_dataset(cfg, "Stale", *standard())
    conn = sqlite3.connect(str(paths.lending_db))
    conn.execute("UPDATE messages SET text = 'changed by hand' WHERE message_id = 'M1_0'")
    conn.commit()
    conn.close()
    assert load_all(cfg).status == "stale"
    for at in assert_pages(MAIN_PAGES):
        assert any("different version of this dataset" in e.value for e in at.error)


@pytest.mark.parametrize("content", [b"", b"this is not a database at all" * 50])
@pytest.mark.parametrize("which", ["lending_db", "predictions_db"])
def test_a_corrupt_or_empty_database_file(cfg, content, which):
    paths = make_dataset(cfg, "Broken", *standard())
    getattr(paths, which).write_bytes(content)
    data = load_all(cfg)
    assert data.status == "unreadable" and "cannot be read" in data.message
    for at in assert_pages(ALL_PAGES):
        assert not at.exception
    at = run("pages/5_Data.py")
    assert_friendly(at, "data page with a broken file")


def test_featured_cases_never_crash_on_odd_data(cfg):
    make_dataset(cfg, "Empty again")
    result = featured_cases(load_all(cfg), cfg)
    assert result["cases"] == [] and len(result["missing"]) == 6
