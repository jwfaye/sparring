"""Tests of server.py: bank merging and the HTTP API on a live server bound to an ephemeral port."""

import http.server
import json
import threading
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

import server

THEORY_QUESTION = {
    "id": "ds-test-01",
    "section": "Validation",
    "source": "test",
    "question": "What is overfitting?",
    "reference": "Fits noise.",
    "key_points": ["noise", "gap", "regularisation"],
    "common_mistakes": ["underfitting"],
}
GRADE = {
    "score": 8,
    "covered": ["noise"],
    "missing": [],
    "wrong": [],
    "feedback": "ok",
    "improved_answer": "...",
    "model": "fake",
    "usage": {"input": 1, "output": 1},
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def bank_dir(tmp_path, monkeypatch):
    bank = tmp_path / "bank"
    write_json(bank / "exercises" / "a.json", [{"id": "ex-1", "title": "One"}, {"id": "ex-2", "title": "Two"}])
    write_json(bank / "exercises" / "b.json", {"items": [{"id": "ex-3", "title": "Three"}]})
    write_json(bank / "qcm" / "q.json", {"exercises": [{"id": "qcm-1"}]})
    write_json(bank / "theory" / "t.json", [THEORY_QUESTION, {"id": "ds-test-02", "question": "No grid yet"}])
    monkeypatch.setattr(server, "BANK_DIR", str(bank))
    return bank


class TestLoadBank:
    def test_merges_every_file_and_tags_the_origin(self, bank_dir):
        res = server.load_bank("exercises")
        assert [i["id"] for i in res["items"]] == ["ex-1", "ex-2", "ex-3"]
        assert res["files"] == [i for i in res["files"] if i.endswith((".json",))]
        assert len(res["files"]) == 2
        assert res["items"][0]["_file"].endswith("a.json")
        assert res["errors"] == []

    def test_accepts_items_exercises_and_single_object_layouts(self, bank_dir):
        assert [i["id"] for i in server.load_bank("qcm")["items"]] == ["qcm-1"]
        write_json(bank_dir / "theory" / "single.json", {"id": "solo", "question": "?"})
        assert "solo" in [i["id"] for i in server.load_bank("theory")["items"]]

    def test_reports_broken_files_without_failing(self, bank_dir):
        (bank_dir / "exercises" / "broken.json").write_text("{not json", encoding="utf-8")
        write_json(bank_dir / "exercises" / "number.json", 42)
        res = server.load_bank("exercises")
        assert [i["id"] for i in res["items"]] == ["ex-1", "ex-2", "ex-3"]
        assert len(res["errors"]) == 2
        assert any("broken.json" in e for e in res["errors"])
        assert any("number.json" in e and "unexpected format" in e for e in res["errors"])

    def test_unknown_kind_is_empty(self, bank_dir):
        assert server.load_bank("nothing") == {"items": [], "files": [], "errors": []}

    def test_theory_question_lookup(self, bank_dir):
        found = server.theory_question("ds-test-01")
        assert found is not None
        assert found["question"] == "What is overfitting?"
        assert server.theory_question("missing") is None


@pytest.fixture
def live(bank_dir, store_dir, grader_module, monkeypatch):
    """A running server on an ephemeral port, with the grader forced offline unless a test overrides it."""
    monkeypatch.setattr(grader_module, "BACKEND", "offline")
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, headers={"Content-Type": "application/json"} if data else {}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8")), resp.headers
        except urllib.error.HTTPError as err:
            payload = err.read().decode("utf-8")
            return err.code, (json.loads(payload) if payload else None), err.headers

    yield SimpleNamespace(call=call, base=base)
    httpd.shutdown()
    httpd.server_close()


class TestHttpApi:
    def test_health_and_cache_headers(self, live):
        status, body, headers = live.call("/api/health")
        assert status == 200 and body == {"ok": True}
        assert headers["Cache-Control"] == "no-store"
        assert headers["Content-Type"].startswith("application/json")

    def test_banks_are_served(self, live):
        assert [i["id"] for i in live.call("/api/exercises")[1]["items"]] == ["ex-1", "ex-2", "ex-3"]
        assert [i["id"] for i in live.call("/api/qcm")[1]["items"]] == ["qcm-1"]
        assert [i["id"] for i in live.call("/api/theory/questions")[1]["items"]] == ["ds-test-01", "ds-test-02"]

    def test_static_page_is_served(self, live):
        with urllib.request.urlopen(live.base + "/", timeout=5) as resp:
            page = resp.read().decode("utf-8")
        assert "<title>" in page

    def test_status_reflects_the_grader(self, live):
        status, body, _ = live.call("/api/theory/status")
        assert status == 200 and body["available"] is False and body["backend"] == "offline"

    def test_offline_answer_flow(self, live):
        status, body, _ = live.call(
            "/api/theory/answer", {"qid": "ds-test-01", "answer": "noise", "duration": 30, "profile": "test"}
        )
        assert status == 200 and body["offline"] is True
        rec = body["record"]
        assert rec["qid"] == "ds-test-01" and rec["mode"] == "offline" and rec["grade"] is None
        _, history, _ = live.call("/api/theory/history?profile=test")
        assert [a["id"] for a in history["items"]] == [rec["id"]]
        assert live.call("/api/theory/history")[1]["items"] == []
        status, body, _ = live.call("/api/theory/grade", {"id": rec["id"], "profile": "test"})
        assert status == 503 and "offline" in body["error"]
        status, body, _ = live.call("/api/theory/delete", {"id": rec["id"], "profile": "test"})
        assert status == 200 and body == {"ok": True}
        assert live.call("/api/theory/history?profile=test")[1]["items"] == []

    def test_online_answer_flow(self, live, grader_module, monkeypatch):
        monkeypatch.setattr(
            grader_module,
            "status",
            lambda refresh=False: {"available": True, "backend": "fake", "model": "fake", "reason": ""},
        )
        monkeypatch.setattr(grader_module, "grade", lambda q, a: dict(GRADE, answer_seen=a))
        status, body, _ = live.call("/api/theory/answer", {"qid": "ds-test-01", "answer": "noise everywhere"})
        assert status == 200 and body["offline"] is False
        assert body["record"]["mode"] == "online"
        assert body["record"]["grade"]["score"] == 8
        assert body["record"]["grade"]["answer_seen"] == "noise everywhere"

    def test_online_answer_without_grid_stays_offline(self, live, grader_module, monkeypatch):
        monkeypatch.setattr(
            grader_module,
            "status",
            lambda refresh=False: {"available": True, "backend": "fake", "model": "fake", "reason": ""},
        )
        status, body, _ = live.call("/api/theory/answer", {"qid": "ds-test-02", "answer": "x"})
        assert status == 200 and body["offline"] is True

    def test_forced_offline_mode_skips_grading(self, live, grader_module, monkeypatch):
        monkeypatch.setattr(
            grader_module,
            "status",
            lambda refresh=False: {"available": True, "backend": "fake", "model": "fake", "reason": ""},
        )
        status, body, _ = live.call("/api/theory/answer", {"qid": "ds-test-01", "answer": "x", "mode": "offline"})
        assert status == 200 and body["offline"] is True

    def test_grader_failure_keeps_the_answer(self, live, grader_module, monkeypatch):
        monkeypatch.setattr(
            grader_module,
            "status",
            lambda refresh=False: {"available": True, "backend": "fake", "model": "fake", "reason": ""},
        )

        def failing(q, a):
            raise grader_module.GraderError("model down")

        monkeypatch.setattr(grader_module, "grade", failing)
        status, body, _ = live.call("/api/theory/answer", {"qid": "ds-test-01", "answer": "x"})
        assert status == 502 and body["error"] == "model down"
        assert body["record"]["grade"] is None
        assert len(live.call("/api/theory/history")[1]["items"]) == 1

    def test_regrade_pending_answer(self, live, grader_module, monkeypatch):
        rec = live.call("/api/theory/answer", {"qid": "ds-test-01", "answer": "x"})[1]["record"]
        monkeypatch.setattr(
            grader_module,
            "status",
            lambda refresh=False: {"available": True, "backend": "fake", "model": "fake", "reason": ""},
        )
        monkeypatch.setattr(grader_module, "grade", lambda q, a: dict(GRADE))
        status, body, _ = live.call("/api/theory/grade", {"id": rec["id"]})
        assert status == 200 and body["record"]["grade"]["score"] == 8

    def test_error_paths(self, live):
        assert live.call("/api/theory/answer", {"qid": "nope", "answer": "x"})[0] == 404
        assert live.call("/api/theory/grade", {"id": "nope"})[0] == 404
        assert live.call("/api/nothing", {})[0] == 404
        req = urllib.request.Request(
            live.base + "/api/theory/answer", data=b"not json", headers={"Content-Type": "application/json"}
        )
        with pytest.raises(urllib.error.HTTPError) as info:
            urllib.request.urlopen(req, timeout=5)
        assert info.value.code == 400


# Cross-origin isolation headers (SP-PY-RUNTIME): they unlock SharedArrayBuffer for the Pyodide interrupt buffer.
def test_coop_header_is_same_origin(live):
    _, _, headers = live.call("/api/health")
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"


def test_coep_header_is_require_corp(live):
    _, _, api_headers = live.call("/api/health")
    assert api_headers["Cross-Origin-Embedder-Policy"] == "require-corp"
    with urllib.request.urlopen(live.base + "/js/py-worker.js", timeout=5) as resp:
        assert resp.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
        assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert "Content-Security-Policy" in resp.headers
