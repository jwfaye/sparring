"""Tests of backend/grader.py with a fake Anthropic SDK and a fake `claude` CLI. Nothing real is called."""

import subprocess
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

QUESTION = {
    "id": "q1",
    "question": "What is overfitting?",
    "reference": "The model fits noise and generalises poorly.",
    "key_points": ["memorises noise", "train/test gap", "regularisation helps"],
    "common_mistakes": ["confusing it with underfitting"],
}

GRADE = {
    "score": 7,
    "covered": ["memorises noise"],
    "missing": ["train/test gap"],
    "wrong": [],
    "feedback": "Good start.",
    "improved_answer": "Overfitting is ...",
}


def fake_anthropic(response=None, error=None):
    """A stand-in for the `anthropic` package: typed errors and a client whose messages.create is scripted."""
    mod = types.ModuleType("anthropic")

    class APIStatusError(Exception):
        def __init__(self, message="", status_code=500):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    class AuthenticationError(APIStatusError):
        pass

    class RateLimitError(APIStatusError):
        pass

    class BadRequestError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        pass

    calls: list[dict[str, Any]] = []

    class Messages:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            if error is not None:
                raise error
            return response

    class Anthropic:
        def __init__(self):
            self.messages = Messages()

    for name, attr in (
        ("APIStatusError", APIStatusError),
        ("AuthenticationError", AuthenticationError),
        ("RateLimitError", RateLimitError),
        ("BadRequestError", BadRequestError),
        ("APIConnectionError", APIConnectionError),
        ("Anthropic", Anthropic),
        ("Messages", Messages),
        ("calls", calls),
    ):
        setattr(mod, name, attr)
    return mod


def api_response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        model="claude-test",
        usage=SimpleNamespace(input_tokens=11, output_tokens=5),
        content=[SimpleNamespace(type="text", text=text)],
    )


@pytest.fixture
def api_available(grader_module, monkeypatch):
    monkeypatch.setattr(grader_module, "BACKEND", "api")
    monkeypatch.setattr(grader_module.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return grader_module


@pytest.fixture
def claude_cli(grader_module, monkeypatch):
    """Fake `claude` binary: records every subprocess call and answers from a script."""
    state: dict[str, Any] = {"logged_in": True, "calls": [], "result": None, "raise": None}

    def run(cmd: list[str], **kwargs: Any) -> Any:
        state["calls"].append((cmd, kwargs))
        if state["raise"] is not None:
            raise state["raise"]
        if cmd[1:3] == ["auth", "status"]:
            return SimpleNamespace(
                stdout='{"loggedIn": %s}' % ("true" if state["logged_in"] else "false"), stderr="", returncode=0
            )
        return state["result"]

    monkeypatch.setattr(grader_module, "BACKEND", "claude-code")
    monkeypatch.setattr(grader_module.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(grader_module.subprocess, "run", run)
    return state


class TestStatus:
    def test_api_without_sdk(self, grader_module, monkeypatch):
        monkeypatch.setattr(grader_module, "BACKEND", "api")
        monkeypatch.setattr(grader_module.importlib.util, "find_spec", lambda name: None)
        st = grader_module.status()
        assert st["available"] is False and st["backend"] == "api"
        assert "SDK" in st["reason"]

    def test_api_without_key(self, grader_module, monkeypatch):
        monkeypatch.setattr(grader_module, "BACKEND", "api")
        monkeypatch.setattr(grader_module.importlib.util, "find_spec", lambda name: object())
        st = grader_module.status()
        assert st["available"] is False
        assert "ANTHROPIC_API_KEY" in st["reason"]

    def test_api_available(self, api_available):
        st = api_available.status()
        assert st == {"available": True, "backend": "api", "model": api_available.MODEL, "reason": ""}

    def test_claude_code_missing_binary(self, grader_module, monkeypatch):
        monkeypatch.setattr(grader_module, "BACKEND", "claude-code")
        monkeypatch.setattr(grader_module.shutil, "which", lambda name: None)
        st = grader_module.status()
        assert st["available"] is False
        assert "not found" in st["reason"] and "Offline mode" in st["reason"]

    def test_claude_code_logged_in(self, grader_module, claude_cli):
        st = grader_module.status()
        assert st["available"] is True and st["backend"] == "claude-code"
        assert "Claude Code" in st["model"]
        cmd, kwargs = claude_cli["calls"][0]
        assert cmd[1:] == ["auth", "status"]
        assert "CLAUDECODE" not in kwargs["env"]

    def test_claude_code_auth_status_failure_reads_as_not_logged_in(self, grader_module, claude_cli):
        claude_cli["raise"] = OSError("cannot execute")
        s = grader_module.status()
        assert s["available"] is False and "not logged in" in s["reason"]
        claude_cli["raise"] = subprocess.TimeoutExpired(cmd="claude", timeout=30)
        s = grader_module.status(refresh=True)
        assert s["available"] is False and "not logged in" in s["reason"]

    def test_claude_code_not_logged_in(self, grader_module, claude_cli):
        claude_cli["logged_in"] = False
        st = grader_module.status()
        assert st["available"] is False
        assert "/login" in st["reason"]

    def test_offline_backend(self, grader_module, monkeypatch):
        monkeypatch.setattr(grader_module, "BACKEND", "offline")
        st = grader_module.status()
        assert st["available"] is False and st["backend"] == "offline"

    def test_auto_prefers_api_then_claude_code(self, grader_module, claude_cli, monkeypatch):
        monkeypatch.setattr(grader_module, "BACKEND", "auto")
        monkeypatch.setattr(grader_module.importlib.util, "find_spec", lambda name: None)
        assert grader_module.status()["backend"] == "claude-code"
        monkeypatch.setattr(grader_module, "_cache", {"at": 0.0, "value": None})
        monkeypatch.setattr(grader_module.importlib.util, "find_spec", lambda name: object())
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        assert grader_module.status()["backend"] == "api"

    def test_auto_reports_both_reasons_when_nothing_works(self, grader_module, claude_cli, monkeypatch):
        monkeypatch.setattr(grader_module, "BACKEND", "auto")
        monkeypatch.setattr(grader_module.importlib.util, "find_spec", lambda name: None)
        claude_cli["logged_in"] = False
        reason = grader_module.status()["reason"]
        assert "SDK" in reason and "/login" in reason

    def test_available_status_is_cached(self, grader_module, claude_cli):
        grader_module.status()
        grader_module.status()
        assert len(claude_cli["calls"]) == 1
        grader_module.status(refresh=True)
        assert len(claude_cli["calls"]) == 2


class TestPrompt:
    def test_build_prompt_contains_every_section(self, grader_module):
        prompt = grader_module.build_prompt(QUESTION, "  it memorises noise ")
        assert "## Question\nWhat is overfitting?" in prompt
        assert "## Reference answer\nThe model fits noise" in prompt
        assert "- memorises noise\n- train/test gap\n- regularisation helps" in prompt
        assert "- confusing it with underfitting" in prompt
        assert prompt.endswith("## Candidate's answer\nit memorises noise")

    def test_empty_answer_is_marked(self, grader_module):
        assert grader_module.build_prompt(QUESTION, "   ").endswith("(empty)")

    def test_finish_normalises_the_payload(self, grader_module):
        data = grader_module._finish(
            {"score": 15, "covered": [1, "a"], "feedback": None}, "m", {"input": 1, "output": 2}
        )
        assert data["score"] == 10
        assert data["covered"] == ["1", "a"] and data["missing"] == [] and data["wrong"] == []
        assert data["feedback"] == "" and data["improved_answer"] == ""
        assert data["model"] == "m" and data["usage"] == {"input": 1, "output": 2}
        assert grader_module._finish({"score": -3}, "m", {})["score"] == 0

    def test_finish_rejects_unreadable_scores(self, grader_module):
        with pytest.raises(grader_module.GraderError):
            grader_module._finish({"score": "ten"}, "m", {})


class TestGradeGuards:
    def test_question_without_grid(self, api_available):
        with pytest.raises(api_available.GraderError, match="no grading grid"):
            api_available.grade({"id": "q", "question": "?"}, "answer")

    def test_unavailable_backend(self, grader_module, monkeypatch):
        monkeypatch.setattr(grader_module, "BACKEND", "offline")
        with pytest.raises(grader_module.GraderError, match="offline"):
            grader_module.grade(QUESTION, "answer")


class TestApiBackend:
    def test_successful_grading(self, api_available, monkeypatch):
        import json

        mod = fake_anthropic(response=api_response(json.dumps(GRADE)))
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        data = api_available.grade(QUESTION, "it memorises noise")
        assert data["score"] == 7 and data["model"] == "claude-test"
        assert data["usage"] == {"input": 11, "output": 5}
        call = mod.calls[0]
        assert call["model"] == api_available.MODEL
        assert call["system"] == api_available.SYSTEM
        assert call["output_config"]["format"]["schema"] == api_available.SCHEMA
        assert call["output_config"]["effort"] == api_available.EFFORT
        assert call["messages"][0]["content"].endswith("it memorises noise")

    @pytest.mark.parametrize("stop_reason, expected", [("refusal", "declined"), ("max_tokens", "truncated")])
    def test_stop_reasons(self, api_available, monkeypatch, stop_reason, expected):
        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic(response=api_response("{}", stop_reason)))
        with pytest.raises(api_available.GraderError, match=expected):
            api_available.grade(QUESTION, "answer")

    def test_invalid_json(self, api_available, monkeypatch):
        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic(response=api_response("not json")))
        with pytest.raises(api_available.GraderError, match="invalid JSON"):
            api_available.grade(QUESTION, "answer")

    @pytest.mark.parametrize(
        "error_name, args, expected",
        [
            ("AuthenticationError", ("bad key", 401), "API key rejected: bad key"),
            ("RateLimitError", ("slow down", 429), "Rate limit"),
            ("BadRequestError", ("bad request", 400), "Request rejected by the API: bad request"),
            ("APIStatusError", ("boom", 503), "API error 503: boom"),
            ("APIConnectionError", ("down",), "Cannot reach the API"),
        ],
    )
    def test_typed_errors_become_grader_errors(self, api_available, monkeypatch, error_name, args, expected):
        mod = fake_anthropic()
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        error = getattr(mod, error_name)(*args)
        monkeypatch.setattr(mod.Messages, "create", lambda self, **kwargs: (_ for _ in ()).throw(error))
        with pytest.raises(api_available.GraderError, match=expected):
            api_available.grade(QUESTION, "answer")


class TestClaudeCodeBackend:
    def cli_result(self, payload, returncode=0, stdout=None, stderr=""):
        import json

        return SimpleNamespace(
            stdout=json.dumps(payload) if stdout is None else stdout, stderr=stderr, returncode=returncode
        )

    def test_successful_grading_uses_structured_output(self, grader_module, claude_cli):
        claude_cli["result"] = self.cli_result(
            {
                "is_error": False,
                "structured_output": GRADE,
                "usage": {
                    "input_tokens": 2,
                    "cache_creation_input_tokens": 1000,
                    "cache_read_input_tokens": 3,
                    "output_tokens": 50,
                },
                "modelUsage": {"claude-opus-5-5": {}},
            }
        )
        data = grader_module.grade(QUESTION, "it memorises noise")
        assert data["score"] == 7
        assert data["model"] == "claude-opus-5-5 (Claude Code)"
        assert data["usage"] == {"input": 1005, "output": 50}
        cmd, kwargs = claude_cli["calls"][-1]
        assert cmd[:2] == ["/usr/bin/claude", "-p"] or cmd[1] == "-p"
        assert "--no-session-persistence" in cmd
        assert cmd[cmd.index("--tools") + 1] == ""
        assert cmd[cmd.index("--setting-sources") + 1] == ""
        assert cmd[cmd.index("--system-prompt") + 1] == grader_module.SYSTEM
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert "--json-schema" in cmd
        assert kwargs["input"].endswith("it memorises noise")
        assert kwargs["timeout"] == grader_module.CLAUDE_TIMEOUT
        assert "CLAUDECODE" not in kwargs["env"]

    def test_falls_back_to_result_text(self, grader_module, claude_cli):
        import json

        claude_cli["result"] = self.cli_result(
            {"is_error": False, "result": json.dumps(GRADE), "usage": {}, "modelUsage": {}}
        )
        data = grader_module.grade(QUESTION, "answer")
        assert data["score"] == 7 and data["model"] == f"{grader_module.MODEL} (Claude Code)"

    def test_not_logged_in_refreshes_status(self, grader_module, claude_cli):
        claude_cli["result"] = self.cli_result({"is_error": True, "result": "Not logged in · Please run /login"})
        with pytest.raises(grader_module.GraderError, match="not logged in"):
            grader_module.grade(QUESTION, "answer")
        assert sum(1 for cmd, _ in claude_cli["calls"] if cmd[1:3] == ["auth", "status"]) == 2

    def test_other_cli_errors(self, grader_module, claude_cli):
        claude_cli["result"] = self.cli_result({"is_error": True, "result": "model overloaded"})
        with pytest.raises(grader_module.GraderError, match="Claude Code: model overloaded"):
            grader_module.grade(QUESTION, "answer")

    def test_nonzero_exit_without_json(self, grader_module, claude_cli):
        claude_cli["result"] = self.cli_result({}, returncode=1, stdout="", stderr="first line\nfatal: something broke")
        with pytest.raises(grader_module.GraderError, match="Claude Code failed: fatal: something broke"):
            grader_module.grade(QUESTION, "answer")

    def test_unreadable_output(self, grader_module, claude_cli):
        claude_cli["result"] = self.cli_result({"is_error": False, "result": "plain text"})
        with pytest.raises(grader_module.GraderError, match="invalid JSON"):
            grader_module.grade(QUESTION, "answer")

    def test_truncated_json_on_a_failed_exit(self, grader_module, claude_cli):
        claude_cli["result"] = self.cli_result({}, returncode=1, stdout='{"is_error": true, "result": "cut', stderr="")
        with pytest.raises(grader_module.GraderError, match="Claude Code failed: "):
            grader_module.grade(QUESTION, "answer")

    def test_timeout_and_missing_binary(self, grader_module, claude_cli):
        grader_module.status()
        claude_cli["raise"] = subprocess.TimeoutExpired(cmd="claude", timeout=1)
        with pytest.raises(grader_module.GraderError, match="did not answer"):
            grader_module.grade(QUESTION, "answer")
        claude_cli["raise"] = FileNotFoundError()
        with pytest.raises(grader_module.GraderError, match="not found"):
            grader_module.grade(QUESTION, "answer")
