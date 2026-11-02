"""Tests of backend/store.py on a temporary data directory."""
import json
import os
import re

from backend import store


def test_add_answer_persists_a_record(store_dir):
    rec = store.add_answer("q1", "my answer", duration=42, mode="offline")
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", rec["id"])
    assert rec["qid"] == "q1" and rec["answer"] == "my answer" and rec["duration"] == 42
    assert rec["mode"] == "offline" and rec["grade"] is None
    with open(store_dir / "answers.json", encoding="utf-8") as fh:
        assert json.load(fh) == [rec]
    assert not (store_dir / "answers.json.tmp").exists()


def test_list_and_pending(store_dir):
    first = store.add_answer("q1", "a")
    store.add_answer("q2", "b")
    store.set_grade(first["id"], {"score": 7})
    answers = store.list_answers()
    assert [a["qid"] for a in answers] == ["q1", "q2"]
    assert [a["qid"] for a in store.pending()] == ["q2"]


def test_set_grade_stamps_the_record(store_dir):
    rec = store.add_answer("q1", "a")
    graded = store.set_grade(rec["id"], {"score": 9, "feedback": "good"})
    assert graded is not None
    assert graded["grade"] == {"score": 9, "feedback": "good"}
    assert isinstance(graded["graded_at"], int)
    assert store.list_answers()[0]["grade"]["score"] == 9
    assert store.set_grade("missing", {"score": 1}) is None


def test_delete_answer(store_dir):
    rec = store.add_answer("q1", "a")
    assert store.delete_answer(rec["id"]) is True
    assert store.delete_answer(rec["id"]) is False
    assert store.list_answers() == []


def test_profiles_are_isolated(store_dir):
    store.add_answer("q1", "main")
    store.add_answer("q2", "test", profile="test")
    assert [a["answer"] for a in store.list_answers()] == ["main"]
    assert [a["answer"] for a in store.list_answers(profile="test")] == ["test"]
    assert (store_dir / "test" / "answers.json").exists()


def test_profile_names_cannot_escape_the_data_directory(store_dir):
    path = store._path("../../etc")
    assert os.path.dirname(path) == os.path.join(str(store_dir), "etc")
    assert store._path("") == os.path.join(str(store_dir), "answers.json")
    assert store._path("a b/c") == os.path.join(str(store_dir), "abc", "answers.json")


def test_missing_file_means_no_answers(store_dir):
    assert store.list_answers() == []
    assert store.pending(profile="nobody") == []
