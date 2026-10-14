"""Phase 8A: the try-a-message box on the Lenders page."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.classify_messages import save_dataset_model
from src.config import MESSAGE_CLASSES, PROJECT_ROOT
from src.dashboard_ui import CONFIG_VARIABLE
from src.datasets import DEMO, get_dataset_paths, set_active
from src.try_message import MAX_CHARS, NOTE, classify_one, load, model_file

from leak_check import forbidden_mentions
from worlds import build_classified_world

ROOT = Path(__file__).resolve().parents[1]
TYPED = "Pay Sunbird Credit today or Zq7 visits your home tonight"  # 'Zq7' marks this exact text


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return build_classified_world(tmp_path_factory.mktemp("try_world"), n_borrowers=300)


@pytest.fixture
def model(world):
    cfg, _ = world
    path, _ = model_file(cfg, get_dataset_paths(cfg, DEMO))
    return load(path)


def test_a_message_gets_one_class_and_four_probabilities(model):
    result = classify_one(model, "We know where you live. Pay now or we will come to your home tonight.")
    assert result["label"] in MESSAGE_CLASSES
    assert set(result["probabilities"]) == set(MESSAGE_CLASSES)
    assert sum(result["probabilities"].values()) == pytest.approx(1.0)
    assert result["label"] == max(result["probabilities"], key=result["probabilities"].get)


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_input_is_handled(model, text):
    assert classify_one(model, text) == {"error": "Type a message first."}


def test_overlong_input_is_refused(model):
    assert "longer than" in classify_one(model, "a" * (MAX_CHARS + 1))["error"]


def test_lender_names_are_masked_as_in_training(model):
    plain = classify_one(model, "Pay lendername today or we will tell your family.")
    for variant in ("Pay Sunbird Credit today or we will tell your family.",
                    "Pay SUNBIRD CREDIT today or we will tell your family.",
                    "Pay redstone loans today or we will tell your family."):
        assert classify_one(model, variant) == plain
    assert model.named_steps["mask"].brands  # the masker inside the model carries the training brand names


def test_the_dataset_model_is_used_when_there_is_one(world, model, tmp_path):
    cfg, _ = world
    demo_path, source = model_file(cfg, get_dataset_paths(cfg, DEMO))
    assert demo_path == Path(cfg["paths"]["local_model"]) and "synthetic" in source
    from src.datasets import create_dataset
    import copy
    custom = copy.deepcopy(cfg)
    custom["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    info = create_dataset(custom, "Field T", "test")
    assert model_file(custom, info.paths)[0] == demo_path  # no own model yet: the saved one
    save_dataset_model(info.paths, model, {"model_id": "test"})
    path, source = model_file(custom, info.paths)
    assert path == info.paths.lending_db.parent / "dataset_model.joblib" and "retrained" in source
    custom["paths"]["local_model"] = str(tmp_path / "none.joblib")
    other = create_dataset(custom, "Field U", "test")
    assert model_file(custom, other.paths) == (None, "There is no saved model yet. Rebuild the demo with: "
                                                     "python -m src.build_all")


# --- On the page ---------------------------------------------------------------------------------------------

def _snapshot(*folders: Path) -> dict:
    found = {}
    for folder in folders:
        for path in Path(folder).rglob("*"):
            if path.is_file():
                found[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _page(world, monkeypatch):
    _, config_path = world
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    monkeypatch.delenv("FAIRLEND_PRESENT", raising=False)
    return AppTest.from_file(str(ROOT / "pages" / "2_Lenders.py"), default_timeout=120).run()


def _submit(at: AppTest, text: str) -> AppTest:
    at.text_area(key="try_text").input(text)
    next(b for b in at.button if b.label == "Label it").click()
    return at.run()


def test_the_page_shows_the_class_and_stores_nothing(world, monkeypatch):
    cfg, _ = world
    folders = [Path(cfg["paths"]["lending_db"]).parent, PROJECT_ROOT / "data"]
    at = _page(world, monkeypatch)
    assert "Try a message" in [s.value for s in at.subheader]
    before = _snapshot(*folders)
    at = _submit(at, TYPED)
    assert not at.exception, [e.value for e in at.exception]
    label = next(m.value for m in at.markdown if m.value.startswith("The model would label this message"))
    assert any(f"**{name}**" in label for name in MESSAGE_CLASSES)
    table = next(d.value for d in at.dataframe if list(d.value.columns) == ["Class", "Probability %"])
    assert list(table["Class"]) == list(MESSAGE_CLASSES)
    assert table["Probability %"].sum() == pytest.approx(100, abs=0.5)
    assert any(NOTE in c.value for c in at.caption)
    assert at.text_area(key="try_text").value == ""  # the box is cleared after labelling
    assert at.session_state["try_text"] == "" and "try_result" not in at.session_state  # nothing kept in memory
    after = _snapshot(*folders)
    assert after == before  # no file was created or changed, logs included
    for path in after:
        assert b"Zq7" not in Path(path).read_bytes()


def test_an_empty_submit_says_type_a_message(world, monkeypatch):
    at = _submit(_page(world, monkeypatch), "  ")
    assert not at.exception
    assert any("Type a message first." in i.value for i in at.info)
    assert not any(m.value.startswith("The model would label") for m in at.markdown)


def test_the_box_is_hidden_in_presentation_mode(world, monkeypatch):
    _, config_path = world
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    monkeypatch.setenv("FAIRLEND_PRESENT", "1")
    at = AppTest.from_file(str(ROOT / "pages" / "2_Lenders.py"), default_timeout=120).run()
    assert not at.exception
    assert "Try a message" not in [s.value for s in at.subheader]


def test_no_saved_model_gives_a_plain_message(world, monkeypatch, tmp_path):
    import copy
    from worlds import write_config
    cfg, _ = world
    custom = copy.deepcopy(cfg)
    custom["paths"]["local_model"] = str(tmp_path / "missing.joblib")
    monkeypatch.setenv(CONFIG_VARIABLE, str(write_config(custom, tmp_path / "c.yaml")))
    monkeypatch.delenv("FAIRLEND_PRESENT", raising=False)
    at = AppTest.from_file(str(ROOT / "pages" / "2_Lenders.py"), default_timeout=120).run()
    assert not at.exception
    assert any("There is no saved model yet" in i.value for i in at.info)


def test_the_module_stores_logs_and_sends_nothing():
    source = (ROOT / "src" / "try_message.py").read_text(encoding="utf-8")
    names = ("ground_truth", "gt_messages", "gt_borrowers", "gt_lenders", "requests", "urllib", "genai",
             "socket", "dotenv", ".env")
    assert forbidden_mentions(source, names) == []
    for word in ("print(", "logging", "open(", "write_text", "write_bytes", "to_csv", "insert", "upsert"):
        assert word not in source, word
