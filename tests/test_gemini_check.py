"""Phase 3B: the Gemini second opinion. EVERY network call is mocked: no test talks to Gemini.

A fake client stands in for the real one; a fake 'google.genai' package is used only to test how
the real client wrapper maps errors. The real SDK is never imported here.
"""

from __future__ import annotations

import copy
import io
import json
import re
import shutil
import sqlite3
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import gemini_check as gc
from src.config import MESSAGE_CLASSES
from src.dashboard_ui import CONFIG_VARIABLE
from src.datasets import DEMO, get_dataset_paths

from leak_check import forbidden_mentions
from worlds import build_classified_world, write_config

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = "AIza-TEST-ONLY-fake"  # starts like a key, deliberately too short to be one
NEW_FILES = ["src/gemini_check.py", "pages/4_About.py", "src/dashboard_data.py", "tests/test_gemini_check.py"]
LINE = re.compile(r"^(\d+)\. (\".*\")$", re.MULTILINE)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build_classified_world(tmp_path_factory.mktemp("gemini_world"), n_borrowers=400)


@pytest.fixture
def world(built, tmp_path, monkeypatch):
    """A private copy of the demo files and a config whose Gemini files live in tmp_path."""
    cfg = copy.deepcopy(built[0])
    for key in ("lending_db", "ground_truth_db", "predictions_db"):
        target = tmp_path / Path(cfg["paths"][key]).name
        shutil.copy(cfg["paths"][key], target)
        cfg["paths"][key] = str(target)
    cfg["paths"]["datasets_dir"] = str(tmp_path / "datasets")
    cfg["paths"]["active_dataset_file"] = str(tmp_path / "active.txt")
    g = cfg["classifier"]["gemini"]
    g.update(cache_file=str(tmp_path / "cache.json"), report_file=str(tmp_path / "report.csv"),
             summary_file=str(tmp_path / "summary.json"), batch_size=10, max_calls=40, delay_seconds=7,
             requests_per_minute=10, max_retries=3, backoff_base_seconds=5)
    monkeypatch.delenv(gc.KEY_VARIABLE, raising=False)
    monkeypatch.delenv("FAIRLEND_PRESENT", raising=False)
    config_path = write_config(cfg, tmp_path / "config.yaml")
    return cfg, config_path


class FakeClient:
    """Answers like a model would: one JSON entry per numbered text, labelled by a rule."""

    def __init__(self, rule=None, replies=None):
        self.prompts: list[str] = []
        self.rule = rule or (lambda text: "threat" if "police" in text.lower() else "normal")
        self.replies = list(replies or [])  # scripted replies or exceptions, used first

    def classify(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        items = [{"id": int(n), "label": self.rule(json.loads(t))} for n, t in LINE.findall(prompt)]
        return json.dumps(items)

    @property
    def calls(self) -> int:
        return len(self.prompts)

    def sent_texts(self) -> list[str]:
        return [json.loads(t) for prompt in self.prompts for _, t in LINE.findall(prompt)]


def run(config_path, client, *args, sleep=None):
    out = io.StringIO()
    waits: list[float] = []
    with redirect_stdout(out):
        code = gc.main(["--config", str(config_path), *args], client=client,
                       sleep=sleep or (lambda seconds: waits.append(seconds)))
    return code, out.getvalue(), waits


def selected(cfg) -> pd.DataFrame:
    return gc.select_test_messages(cfg, get_dataset_paths(cfg, DEMO))


# --- What may be sent ----------------------------------------------------------------------------------------------

def test_only_the_demo_test_split_is_selected(world):
    cfg, _ = world
    frame = selected(cfg)
    conn = sqlite3.connect(cfg["paths"]["ground_truth_db"])
    splits = dict(conn.execute("SELECT message_id, split FROM gt_messages"))
    conn.close()
    assert len(frame) == 40 and {splits[m] for m in frame["message_id"]} == {"test"}
    brands = ["Sunbird Credit", "Redstone Loans", "Lakeview Loans", "Ridgeway Credit"]
    assert not any(b.lower() in t.lower() for t in frame["text"] for b in brands)  # lender names masked


def test_a_real_dataset_is_refused_and_nothing_is_sent(world):
    cfg, config_path = world
    from src.import_data import import_upload, read_csvs
    from tiny_data import csv_bytes, tiny_rows
    assert import_upload(read_csvs(csv_bytes(tiny_rows())), cfg, mode="new", permission_confirmed=True,
                         redact=True, dataset_name="Field A").ok
    client = FakeClient()
    code, out, _ = run(config_path, client, "--dataset", "field-a")
    assert code == 1 and client.calls == 0
    assert "Refused: 'field-a' is not the demo" in out


def test_a_demo_not_marked_synthetic_is_refused(world):
    cfg, config_path = world
    conn = sqlite3.connect(cfg["paths"]["lending_db"])
    conn.execute("UPDATE meta SET value = 'false' WHERE key = 'synthetic'")
    conn.commit()
    conn.close()
    client = FakeClient()
    code, out, _ = run(config_path, client)
    assert code == 1 and client.calls == 0 and "synthetic = 'true'" in out


def test_messages_outside_the_test_split_are_refused(world, monkeypatch):
    cfg, config_path = world
    original = pd.read_sql_query

    def leaky(sql, conn, params=None, **kwargs):  # pretend the label query also returned dev rows
        frame = original(sql, conn, params=params, **kwargs)
        if "gt_messages" in sql:
            everything = original("SELECT message_id, true_class, template_id, split FROM gt_messages", conn)
            frame = pd.concat([frame, everything[everything["split"] != "test"].head(3)])
        return frame

    monkeypatch.setattr(gc.pd, "read_sql_query", leaky)
    client = FakeClient()
    code, out, _ = run(config_path, client)
    assert code == 1 and client.calls == 0 and "outside the test split" in out


def test_a_missing_key_is_refused_without_echoing_anything(world, monkeypatch):
    _, config_path = world
    out = io.StringIO()
    with redirect_stdout(out):
        code = gc.main(["--config", str(config_path)])  # no client given: the real path, which needs the key
    assert code == 1
    assert "GEMINI_API_KEY is not set in this PowerShell session, so nothing was sent" in out.getvalue()
    assert 'Read-Host "Paste key (will not be saved)"' in out.getvalue()


def test_a_set_key_is_never_printed_even_when_the_client_cannot_start(world, monkeypatch):
    _, config_path = world
    monkeypatch.setenv(gc.KEY_VARIABLE, FAKE_KEY)
    fake_google = types.ModuleType("google")
    fake_genai = types.ModuleType("google.genai")

    class Client:
        def __init__(self, api_key):
            raise ValueError(f"bad key {api_key}")  # an SDK error that contains the key

    fake_genai.Client = Client
    fake_genai.types = types.SimpleNamespace()
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_genai.types)
    out = io.StringIO()
    with redirect_stdout(out):
        code = gc.main(["--config", str(config_path)])
    assert code == 1 and "Could not start the Gemini client (ValueError)" in out.getvalue()
    assert FAKE_KEY not in out.getvalue() and "AIza" not in out.getvalue()


# --- Sending: dedupe, cache, resume, limits -------------------------------------------------------------------------

def test_distinct_texts_only_are_sent_and_mapped_back(world):
    cfg, config_path = world
    frame = selected(cfg)
    conn = sqlite3.connect(cfg["paths"]["lending_db"])  # make two test messages identical to a third
    ids = frame["message_id"].tolist()
    original = conn.execute("SELECT text FROM messages WHERE message_id = ?", (ids[0],)).fetchone()[0]
    conn.executemany("UPDATE messages SET text = ? WHERE message_id = ?", [(original, ids[1]), (original, ids[2])])
    conn.commit()
    conn.close()
    frame = selected(cfg)
    client = FakeClient()
    code, _, _ = run(config_path, client)
    assert code == 0
    sent = client.sent_texts()
    assert len(sent) == len(set(sent)) == frame["text"].nunique() == 38
    report = pd.read_csv(cfg["classifier"]["gemini"]["report_file"], comment="#")
    assert report["messages"].sum() == 40 and report["gemini_no_answer"].sum() == 0


def test_cached_texts_are_never_sent_again(world):
    cfg, config_path = world
    first = FakeClient()
    assert run(config_path, first)[0] == 0
    assert first.calls == 4  # 40 texts in batches of 10
    second = FakeClient()
    code, out, _ = run(config_path, second)
    assert code == 0 and second.calls == 0
    assert "texts sent 0, from cache 40" in out
    cache = json.loads(Path(cfg["classifier"]["gemini"]["cache_file"]).read_text(encoding="utf-8"))
    assert len(cache["answers"]) == 40
    assert not any(t in json.dumps(cache) for t in selected(cfg)["text"])  # labels only, no text


def test_the_cache_key_includes_model_and_prompt_version(world):
    assert gc.cache_key("a", "v1", "m") != gc.cache_key("a", "v2", "m") != gc.cache_key("a", "v1", "n")
    assert gc.cache_key("a", "v1", "m") == gc.cache_key("a", "v1", "m")


def test_a_capped_run_resumes_where_it_stopped(world, tmp_path):
    cfg, _ = world
    capped = copy.deepcopy(cfg)
    capped["classifier"]["gemini"]["max_calls"] = 2
    path = write_config(capped, tmp_path / "capped.yaml")
    first = FakeClient()
    code, out, _ = run(path, first)
    assert code == 2 and first.calls == 2
    assert "stopped at the cap of 2 calls" in out
    summary = json.loads(Path(cfg["classifier"]["gemini"]["summary_file"]).read_text(encoding="utf-8"))
    assert summary["complete"] is False and summary["gemini_answered"] == 20
    second = FakeClient()
    code, _, _ = run(path, second)
    assert code == 0 and second.calls == 2
    assert set(first.sent_texts()).isdisjoint(second.sent_texts())  # nothing sent twice


def test_the_call_cap_counts_retries(world, tmp_path):
    cfg, _ = world
    capped = copy.deepcopy(cfg)
    capped["classifier"]["gemini"]["max_calls"] = 3
    path = write_config(capped, tmp_path / "capped.yaml")
    client = FakeClient(replies=[gc.TransientError(429)] * 10)
    code, out, _ = run(path, client)
    assert code == 2 and client.calls == 3
    assert "cap of 3 calls" in out


def test_backoff_on_429_and_5xx(world):
    _, config_path = world
    client = FakeClient(replies=[gc.TransientError(429), gc.TransientError(503)])
    code, _, waits = run(config_path, client)
    assert code == 0 and client.calls == 6  # 2 failures, then the 4 batches
    assert waits[:3] == [5, 7, 10]  # backoff 5 s, then the normal pause before the retry, then backoff 10 s
    assert all(w >= 6 for w in waits if w not in (5, 10))  # the pause is max(7, 60/10)


def test_giving_up_after_max_retries(world):
    _, config_path = world
    client = FakeClient(replies=[gc.TransientError(500)] * 10)
    code, out, _ = run(config_path, client)
    assert code == 2 and client.calls == 4  # 1 try + 3 retries
    assert "gave up after 3 retries" in out


def test_invalid_replies_are_no_answer_never_guessed_and_asked_again(world):
    cfg, config_path = world
    bad = ["this is not json", json.dumps([{"id": 1, "label": "rude"}, {"id": 2}]), json.dumps({"x": 1})]
    client = FakeClient(replies=bad)
    code, out, _ = run(config_path, client)
    assert code == 0
    summary = json.loads(Path(cfg["classifier"]["gemini"]["summary_file"]).read_text(encoding="utf-8"))
    assert summary["gemini_answered"] == 10  # only the 4th batch was valid
    assert summary["confusion_gemini"]["normal"]["no answer"] + summary["confusion_gemini"]["threat"][
        "no answer"] + summary["confusion_gemini"]["firm_pressure"]["no answer"] + summary["confusion_gemini"][
        "shaming_third_party"]["no answer"] == 30
    assert "invalid answers 30" in out
    again = FakeClient()
    run(config_path, again)
    assert len(again.sent_texts()) == 30  # the unanswered ones are asked again, the answered ones are not


@pytest.mark.parametrize("raw, expected", [
    ('[{"id": 1, "label": "threat"}, {"id": 2, "label": "normal"}]', {1: "threat", 2: "normal"}),
    ('[{"id": 1, "label": " threat "}]', {1: "threat"}),
    ('[{"id": 3, "label": "threat"}]', {}),            # an id that was not asked
    ('[{"id": "1", "label": "threat"}]', {}),          # id must be a number
    ('[{"id": 1, "label": "Threat"}]', {}),            # unknown class (case matters)
    ('[{"id": 1, "label": "threat"}, {"id": 1, "label": "normal"}]', {}),  # contradictory
    ('{"labels": [{"id": 2, "label": "firm_pressure"}]}', {2: "firm_pressure"}),
    ("", {}), ("null", {}), ("[1, 2]", {}),
])
def test_parse_reply(raw, expected):
    assert gc.parse_reply(raw, [1, 2]) == expected


# --- The report ------------------------------------------------------------------------------------------------------

def test_report_and_summary_by_hand():
    frame = pd.DataFrame({
        "message_id": ["a", "b", "c", "d"], "text": ["t1", "t2", "t3", "t3"],
        "true_class": ["threat", "threat", "normal", "normal"], "template_id": ["T1", "T1", "N1", "N1"],
        "local_label": ["threat", "threat", "normal", "threat"]})
    report, summary = gc.build_report(frame, {"t1": "threat", "t2": "threat", "t3": "shaming_third_party"})
    assert summary["local_vs_truth"] == pytest.approx(0.75) and summary["gemini_vs_truth"] == pytest.approx(0.5)
    assert summary["local_vs_gemini"] == pytest.approx(0.5)
    assert summary["confusion_gemini"]["normal"]["shaming_third_party"] == 2
    assert [d["template_id"] for d in summary["disagreeing_phrasings"]] == ["N1"]
    assert report.set_index("template_id").loc["T1", "local_right_share"] == pytest.approx(1.0)
    assert "t1" not in json.dumps(summary)  # the summary never holds text


def test_the_printed_summary_says_it_is_a_second_opinion(world):
    cfg, config_path = world
    code, out, _ = run(config_path, FakeClient())
    assert code == 0 and out.startswith(gc.SECOND_OPINION)
    for text in selected(cfg)["text"]:
        assert text not in out  # message text appears only in the report file
    first_line = Path(cfg["classifier"]["gemini"]["report_file"]).read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("# SYNTHETIC demo test split only.")


# --- The real client wrapper, with a fake SDK ------------------------------------------------------------------------

def _fake_sdk(monkeypatch, behaviour):
    fake_google, fake_genai = types.ModuleType("google"), types.ModuleType("google.genai")
    errors = types.ModuleType("google.genai.errors")

    class APIError(Exception):
        def __init__(self, code, message):
            super().__init__(message)
            self.code = code

    errors.APIError = APIError
    sdk_types = types.ModuleType("google.genai.types")
    sdk_types.GenerateContentConfig = lambda **kwargs: kwargs

    class Models:
        def generate_content(self, model, contents, config):
            return behaviour(APIError, model, contents, config)

    class Client:
        def __init__(self, api_key):
            self.models = Models()

    fake_genai.Client, fake_genai.types, fake_genai.errors, fake_google.genai = Client, sdk_types, errors, fake_genai
    for name, module in (("google", fake_google), ("google.genai", fake_genai), ("google.genai.errors", errors),
                         ("google.genai.types", sdk_types)):
        monkeypatch.setitem(sys.modules, name, module)


@pytest.mark.parametrize("code, expected", [(429, gc.TransientError), (503, gc.TransientError),
                                            (400, gc.PermanentError), (403, gc.PermanentError)])
def test_the_wrapper_maps_errors_and_never_echoes_their_text(world, monkeypatch, code, expected):
    cfg, _ = world

    def behaviour(api_error, model, contents, config):
        raise api_error(code, f"x-goog-api-key: {FAKE_KEY} rejected")

    _fake_sdk(monkeypatch, behaviour)
    client = gc.GeminiClient(FAKE_KEY, gc.Settings.from_config(cfg))
    with pytest.raises(expected) as caught:
        client.classify("prompt")
    assert FAKE_KEY not in str(caught.value) and "x-goog" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_the_wrapper_asks_for_json_at_temperature_zero(world, monkeypatch):
    cfg, _ = world
    seen = {}

    def behaviour(api_error, model, contents, config):
        seen.update(model=model, config=config)
        return types.SimpleNamespace(text='[{"id": 1, "label": "normal"}]')

    _fake_sdk(monkeypatch, behaviour)
    reply = gc.GeminiClient(FAKE_KEY, gc.Settings.from_config(cfg)).classify("p")
    assert reply == '[{"id": 1, "label": "normal"}]'
    assert seen["model"] == cfg["classifier"]["gemini"]["model"]
    assert seen["config"]["temperature"] == 0 and seen["config"]["response_mime_type"] == "application/json"
    assert seen["config"]["response_schema"]["items"]["properties"]["label"]["enum"] == list(MESSAGE_CLASSES)


# --- The About page (read only) ------------------------------------------------------------------------------------------

def test_the_about_page_shows_the_last_summary_but_not_in_presentation_mode(world, monkeypatch):
    cfg, config_path = world
    assert run(config_path, FakeClient())[0] == 0
    monkeypatch.setenv(CONFIG_VARIABLE, str(config_path))
    at = AppTest.from_file(str(ROOT / "pages" / "4_About.py"), default_timeout=120).run()
    assert not at.exception
    assert "Second opinion on the synthetic test set" in [s.value for s in at.subheader]
    monkeypatch.setenv("FAIRLEND_PRESENT", "1")
    at = AppTest.from_file(str(ROOT / "pages" / "4_About.py"), default_timeout=120).run()
    assert "Second opinion on the synthetic test set" not in [s.value for s in at.subheader]


# --- Static checks ----------------------------------------------------------------------------------------------------------

KEY_SHAPE = re.compile(r"AIza[0-9A-Za-z_\-]{35}")


@pytest.mark.parametrize("module", NEW_FILES)
def test_no_key_shaped_string_and_no_env_file_access(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    assert KEY_SHAPE.findall(source) == [], "a string shaped like a Google API key"
    if not module.startswith("tests/"):  # this test file names the patterns it looks for
        assert not re.search(r"""open\([^)]*\.env|['"]\.env['"]|dotenv""", source), "touches .env"


def test_the_key_shape_check_can_fail():
    assert KEY_SHAPE.search("key = 'AIza" + "B" * 35 + "'")
    assert not KEY_SHAPE.search(FAKE_KEY)  # the fake key used here is deliberately not key-shaped


def test_the_dashboard_still_never_names_labels_or_the_sdk():
    for module in ("pages/4_About.py", "src/dashboard_data.py"):
        names = ("ground_truth", "gt_messages", "gt_borrowers", "gt_lenders", "genai", "requests", "urllib")
        assert forbidden_mentions((ROOT / module).read_text(encoding="utf-8"), names) == []


def test_the_key_is_only_read_from_the_environment():
    source = (ROOT / "src" / "gemini_check.py").read_text(encoding="utf-8")
    assert "os.environ.get(KEY_VARIABLE" in source
    assert "print(key" not in source and "f\"{key" not in source and "{api_key}" not in source


def test_a_full_run_with_a_key_never_prints_or_stores_it(world, monkeypatch):
    """The real path (key from the environment, the wrapper, a fake SDK): the key appears nowhere."""
    cfg, config_path = world
    monkeypatch.setenv(gc.KEY_VARIABLE, FAKE_KEY)

    def behaviour(api_error, model, contents, config):
        items = [{"id": int(n), "label": "normal"} for n, _ in LINE.findall(contents)]
        return types.SimpleNamespace(text=json.dumps(items))

    _fake_sdk(monkeypatch, behaviour)
    out = io.StringIO()
    with redirect_stdout(out):
        code = gc.main(["--config", str(config_path)], sleep=lambda seconds: None)
    assert code == 0
    g = cfg["classifier"]["gemini"]
    written = out.getvalue() + "".join(Path(g[k]).read_text(encoding="utf-8")
                                       for k in ("cache_file", "report_file", "summary_file"))
    assert FAKE_KEY not in written and "AIza" not in written
