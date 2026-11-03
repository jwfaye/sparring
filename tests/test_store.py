"""Tests of backend/store.py on a temporary data directory, of the legacy JSON import and of SPARRING_DATA_DIR."""
import importlib
import json
import logging
import os
import re
import sqlite3
import threading

import pytest

from backend import paths, store

LEGACY = [
    {"id": "20261101-100000-aaaaaa", "qid": "q1", "at": 1761991200000, "duration": 30, "answer": "old graded",
     "mode": "offline", "grade": {"score": 8, "feedback": "fine"}, "graded_at": 1761991300000},
    {"id": "20261101-110000-bbbbbb", "qid": "q2", "at": 1761994800000, "duration": None, "answer": "old pending",
     "mode": "offline", "grade": None},
]


def rows(path):
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT id, qid, grade FROM answers ORDER BY at").fetchall()


def write_legacy(directory, items=LEGACY):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "answers.json").write_text(json.dumps(items), encoding="utf-8")


def test_add_answer_persists_a_record(store_dir):
    rec = store.add_answer("q1", "my answer", duration=42, mode="offline")
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", rec["id"])
    assert rec["qid"] == "q1" and rec["answer"] == "my answer" and rec["duration"] == 42
    assert rec["mode"] == "offline" and rec["grade"] is None and rec["graded_at"] is None
    assert store.list_answers() == [rec]
    assert (store_dir / "answers.sqlite3").exists()
    assert not (store_dir / "answers.json").exists()


def test_list_and_pending(store_dir):
    first = store.add_answer("q1", "a")
    store.add_answer("q2", "b")
    store.set_grade(first["id"], {"score": 7})
    answers = store.list_answers()
    assert [a["qid"] for a in answers] == ["q1", "q2"]
    assert [a["qid"] for a in store.pending()] == ["q2"]


def test_set_grade_stamps_the_record(store_dir):
    rec = store.add_answer("q1", "a")
    graded = store.set_grade(rec["id"], {"score": 9, "feedback": "good", "covered": ["é"]})
    assert graded is not None
    assert graded["grade"] == {"score": 9, "feedback": "good", "covered": ["é"]}
    assert isinstance(graded["graded_at"], int)
    assert store.list_answers()[0]["grade"]["score"] == 9
    assert rows(store_dir / "answers.sqlite3")[0][2] == '{"score": 9, "feedback": "good", "covered": ["é"]}'
    assert store.set_grade("missing", {"score": 1}) is None


def test_delete_answer(store_dir):
    rec = store.add_answer("q1", "a")
    assert store.delete_answer(rec["id"]) is True
    assert store.delete_answer(rec["id"]) is False
    assert store.list_answers() == []


def test_answers_are_ordered_by_time(store_dir):
    late = store.add_answer("q1", "late")
    early = store.add_answer("q2", "early")
    with sqlite3.connect(store_dir / "answers.sqlite3") as conn:
        conn.execute("UPDATE answers SET at = at - 60000 WHERE id = ?", (early["id"],))
    assert [a["id"] for a in store.list_answers()] == [early["id"], late["id"]]


def test_equal_timestamps_keep_insertion_order(store_dir):
    first = store.add_answer("q1", "first")
    store.add_answer("q1", "second")
    with sqlite3.connect(store_dir / "answers.sqlite3") as conn:
        conn.execute("UPDATE answers SET at = ?", (first["at"],))
    assert [a["answer"] for a in store.list_answers()] == ["first", "second"]


def test_profiles_are_isolated(store_dir):
    store.add_answer("q1", "main")
    store.add_answer("q2", "test", profile="test")
    assert [a["answer"] for a in store.list_answers()] == ["main"]
    assert [a["answer"] for a in store.list_answers(profile="test")] == ["test"]
    assert (store_dir / "test" / "answers.sqlite3").exists()


def test_database_schema_and_journal_mode(store_dir):
    store.add_answer("q1", "a")
    with sqlite3.connect(store_dir / "answers.sqlite3") as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        columns = [row[1] for row in conn.execute("PRAGMA table_info(answers)")]
        indexed = [row[1] for row in conn.execute("PRAGMA index_list(answers)")]
    assert columns == list(store.COLUMNS)
    assert "answers_qid" in indexed


def test_profile_names_cannot_escape_the_data_directory(store_dir):
    path = store._path("../../etc")
    assert os.path.dirname(path) == os.path.join(str(store_dir), "etc")
    assert store._path("") == os.path.join(str(store_dir), "answers.sqlite3")
    assert store._path("a b/c") == os.path.join(str(store_dir), "abc", "answers.sqlite3")
    store.add_answer("q1", "a", profile="a b/c")
    assert (store_dir / "abc" / "answers.sqlite3").exists()


def test_missing_database_means_no_answers(store_dir):
    assert store.list_answers() == []
    assert store.pending(profile="nobody") == []


def test_legacy_json_is_imported_then_renamed(store_dir, caplog):
    write_legacy(store_dir / "p")
    with caplog.at_level(logging.INFO, logger="sparring"):
        answers = store.list_answers(profile="p")
    assert [a["id"] for a in answers] == [LEGACY[0]["id"], LEGACY[1]["id"]]
    assert answers[0]["grade"] == {"score": 8, "feedback": "fine"} and answers[0]["graded_at"] == 1761991300000
    assert answers[1]["grade"] is None and answers[1]["graded_at"] is None and answers[1]["duration"] is None
    assert answers[0]["duration"] == 30 and answers[0]["mode"] == "offline"
    assert [a["id"] for a in store.pending(profile="p")] == [LEGACY[1]["id"]]
    assert not (store_dir / "p" / "answers.json").exists()
    migrated = store_dir / "p" / "answers.json.migrated"
    assert json.loads(migrated.read_text(encoding="utf-8")) == LEGACY
    assert (store_dir / "p" / "answers.sqlite3").exists()
    lines = [r.getMessage() for r in caplog.records if r.name == "sparring"]
    assert len(lines) == 1 and lines[0].startswith("Imported 2 interview answer(s) from ")


def test_migration_is_idempotent(store_dir):
    write_legacy(store_dir)
    store.list_answers()
    new = store.add_answer("q3", "new")
    write_legacy(store_dir, LEGACY + [{"id": "20261101-120000-cccccc", "qid": "q4", "at": 1761998400000,
                                       "answer": "restored"}])
    answers = store.list_answers()
    assert [a["id"] for a in answers] == [LEGACY[0]["id"], LEGACY[1]["id"], "20261101-120000-cccccc", new["id"]]
    assert answers[2]["mode"] == "offline" and answers[2]["duration"] is None and answers[2]["grade"] is None
    assert len(answers) == 4


def test_migration_keeps_an_earlier_migrated_file(store_dir):
    write_legacy(store_dir)
    store.list_answers()
    write_legacy(store_dir, [])
    store.list_answers()
    assert json.loads((store_dir / "answers.json.migrated").read_text(encoding="utf-8")) == LEGACY
    assert json.loads((store_dir / "answers.json.migrated.2").read_text(encoding="utf-8")) == []
    assert not (store_dir / "answers.json").exists()


def test_malformed_legacy_file_is_left_in_place(store_dir):
    store_dir.mkdir(parents=True)
    (store_dir / "answers.json").write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        store.list_answers()
    assert (store_dir / "answers.json").exists()
    assert not (store_dir / "answers.json.migrated").exists()


def test_legacy_record_without_id_rolls_back_and_keeps_the_file(store_dir):
    write_legacy(store_dir, LEGACY + [{"qid": "q9", "at": 1, "answer": "no id"}])
    with pytest.raises(KeyError):
        store.list_answers()
    assert (store_dir / "answers.json").exists()
    assert not (store_dir / "answers.json.migrated").exists()
    assert rows(store_dir / "answers.sqlite3") == []


def test_concurrent_adds_from_threads(store_dir):
    write_legacy(store_dir)
    errors: list[BaseException] = []

    def work(n: int) -> None:
        try:
            for i in range(20):
                store.add_answer(f"q{n}", f"answer {i}")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    answers = store.list_answers()
    assert len(answers) == 2 + 8 * 20
    assert len({a["id"] for a in answers}) == len(answers)
    assert len(list(store_dir.glob("answers.json.migrated*"))) == 1


@pytest.fixture
def data_dir_override(tmp_path, monkeypatch):
    """backend.store reloaded with SPARRING_DATA_DIR pointing at a temporary directory, then restored."""
    target = tmp_path / "elsewhere"
    monkeypatch.setenv(paths.DATA_ENV_VAR, str(target))
    importlib.reload(store)
    yield target
    monkeypatch.delenv(paths.DATA_ENV_VAR)
    importlib.reload(store)


def test_data_dir_override_moves_the_answers(data_dir_override):
    assert store.DATA_DIR == str(data_dir_override)
    assert store.DATA == os.path.join(str(data_dir_override), "theory")
    rec = store.add_answer("q1", "elsewhere", profile="p")
    assert rows(data_dir_override / "theory" / "p" / "answers.sqlite3") == [(rec["id"], "q1", None)]


def test_default_data_dir_is_under_the_clone(monkeypatch):
    monkeypatch.delenv(paths.DATA_ENV_VAR, raising=False)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert paths.is_clone()
    assert paths.data_dir() == os.path.join(root, "data")
