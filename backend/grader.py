"""Grading of a free-text interview answer.

Two backends:
- "api":         Anthropic API through the official `anthropic` SDK. The SDK reads the key from the environment
                 (ANTHROPIC_API_KEY); it never appears in the code nor in the page.
- "claude-code": Claude Code in non-interactive mode (`claude -p`), on the user's subscription, without an API key.
                 The CLI must be installed and logged in (`claude`, then /login). No tool is exposed to the model.

Settings live in config.json, section "grader": backend = auto (default: api when a key is present, otherwise
claude-code when the CLI is logged in, otherwise offline) | api | claude-code | offline; model, effort, claude_bin,
timeout_seconds.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any

from backend.config import section as _cfg_section

Status = dict[str, Any]
Grade = dict[str, Any]
Question = dict[str, Any]

_CFG = _cfg_section("grader")
BACKEND = str(_CFG["backend"]).strip().lower()
MODEL = str(_CFG["model"])
EFFORT = str(_CFG["effort"])
CLAUDE_BIN = str(_CFG["claude_bin"])
CLAUDE_TIMEOUT = int(_CFG["timeout_seconds"])

SYSTEM = """You are a technical interviewer for data science / machine learning engineer positions: demanding but fair.
You receive an interview question, a reference answer, a grid of expected key points, the common mistakes, and the
candidate's free-text answer (typed quickly, in 2-3 minutes; spelling and style do not matter, only the substance).

Evaluate the candidate's answer against the grid:
- "score": integer out of 10. 10 = every key point, no error, well articulated. 7-9 = the essentials are there with
  minor gaps. 4-6 = partial understanding or important points missing. 0-3 = off topic, empty or serious errors.
  An empty answer or "I don't know" scores 0.
- "covered": the key points of the grid that are actually covered (briefly rephrased).
- "missing": the expected key points that are absent.
- "wrong": the candidate's false or imprecise statements, each with a short correction. Empty list if nothing is wrong.
- "feedback": 2 to 4 sentences addressed directly to the candidate: what was good and the priority to improve.
- "improved_answer": an improved version of the candidate's answer, as they could say it out loud in 1 to 2 minutes:
  keep their structure and correct ideas, fix the errors, add the missing points. 120 to 220 words.
Stay faithful to the grid: do not penalize a correct point outside the grid; do not count a point that is only
touched upon as covered.
Answer in English."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 10},
        "covered": {"type": "array", "items": {"type": "string"}},
        "missing": {"type": "array", "items": {"type": "string"}},
        "wrong": {"type": "array", "items": {"type": "string"}},
        "feedback": {"type": "string"},
        "improved_answer": {"type": "string"},
    },
    "required": ["score", "covered", "missing", "wrong", "feedback", "improved_answer"],
    "additionalProperties": False,
}


class GraderError(Exception):
    pass


def _api_status() -> Status:
    if importlib.util.find_spec("anthropic") is None:
        return {"available": False, "backend": "api", "model": MODEL,
                "reason": "Anthropic SDK missing (python -m pip install anthropic, or run the server with .venv/bin/python)."}
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return {"available": False, "backend": "api", "model": MODEL,
                "reason": "No API key in the environment (ANTHROPIC_API_KEY)."}
    return {"available": True, "backend": "api", "model": MODEL, "reason": ""}


def _claude_env() -> dict[str, str]:
    """Environment for the CLI, outside any parent Claude Code session (the CLI refuses to nest)."""
    return {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}


def _claude_code_status() -> Status:
    label = f"{MODEL} via Claude Code (subscription)"
    if not shutil.which(CLAUDE_BIN):
        return {"available": False, "backend": "claude-code", "model": label,
                "reason": f"Claude Code CLI not found ({CLAUDE_BIN}): install it or set its path in config.json (grader.claude_bin)."}
    try:
        proc = subprocess.run([CLAUDE_BIN, "auth", "status"], capture_output=True, text=True,
                              env=_claude_env(), timeout=30)
        info = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        info = {}
    if not info.get("loggedIn"):
        return {"available": False, "backend": "claude-code", "model": label,
                "reason": "Claude Code is not logged in: run `claude`, then /login, and restart the server."}
    return {"available": True, "backend": "claude-code", "model": label, "reason": ""}


_cache: dict[str, Any] = {"at": 0.0, "value": None}
_lock = threading.Lock()


def status(refresh: bool = False) -> Status:
    """Online grading availability: {available, backend, model, reason}.

    Cached (indefinitely when available, 60 s otherwise): `claude auth status` costs a subprocess.
    """
    with _lock:
        cached: Status | None = _cache["value"]
        if cached and not refresh and (cached["available"] or time.time() - _cache["at"] < 60):
            return cached
        st: Status
        if BACKEND == "api":
            st = _api_status()
        elif BACKEND == "claude-code":
            st = _claude_code_status()
        elif BACKEND == "offline":
            st = {"available": False, "backend": "offline", "model": MODEL, "reason": "config.json: backend = offline, deferred grading."}
        else:
            st = _api_status()
            if not st["available"]:
                cc = _claude_code_status()
                st = cc if cc["available"] else {**cc, "reason": st["reason"] + " " + cc["reason"]}
        if st["backend"] == "claude-code" and not st["available"]:
            st["reason"] += " Offline mode: answers are saved for deferred grading."
        _cache.update(at=time.time(), value=st)
        return st


def build_prompt(question: Question, answer: str) -> str:
    grid = question.get("key_points") or []
    mistakes = question.get("common_mistakes") or []
    parts = [
        f"## Question\n{question['question']}",
        f"## Reference answer\n{question.get('reference', '')}",
        "## Expected key points\n" + "\n".join(f"- {p}" for p in grid),
        "## Common mistakes\n" + "\n".join(f"- {m}" for m in mistakes),
        f"## Candidate's answer\n{answer.strip() or '(empty)'}",
    ]
    return "\n\n".join(parts)


def _finish(data: dict[str, Any], model: str, usage: dict[str, int]) -> Grade:
    try:
        data["score"] = max(0, min(10, int(data.get("score", 0))))
    except (TypeError, ValueError) as e:
        raise GraderError("Unreadable score in the model's answer.") from e
    for key in ("covered", "missing", "wrong"):
        data[key] = [str(x) for x in (data.get(key) or [])]
    data["feedback"] = str(data.get("feedback") or "")
    data["improved_answer"] = str(data.get("improved_answer") or "")
    data["model"] = model
    data["usage"] = usage
    return data


def grade(question: Question, answer: str) -> Grade:
    """Grade an answer; returns {score, covered, missing, wrong, feedback, improved_answer, model, usage}."""
    if not question.get("key_points"):
        raise GraderError("This question has no grading grid yet.")
    st = status()
    if not st["available"]:
        raise GraderError(st["reason"])
    prompt = build_prompt(question, answer)
    if st["backend"] == "claude-code":
        return _grade_claude_code(prompt)
    return _grade_api(prompt)


def _grade_api(prompt: str) -> Grade:
    import anthropic

    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
    except anthropic.AuthenticationError as e:
        raise GraderError(f"API key rejected: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise GraderError("Rate limit reached, try again in a minute.") from e
    except anthropic.BadRequestError as e:
        raise GraderError(f"Request rejected by the API: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise GraderError(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise GraderError("Cannot reach the API (network?).") from e

    if resp.stop_reason == "refusal":
        raise GraderError("The model declined to grade this answer.")
    if resp.stop_reason == "max_tokens":
        raise GraderError("API response truncated (max_tokens).")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise GraderError("Unreadable API response (invalid JSON).") from e
    return _finish(data, resp.model, {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens})


def _grade_claude_code(prompt: str) -> Grade:
    """Grade through `claude -p`: no session persistence, no tool exposed, neither CLAUDE.md nor project settings,
    and the system prompt replaced by SYSTEM (much shorter than Claude Code's own)."""
    cmd = [
        CLAUDE_BIN, "-p",
        "--no-session-persistence",
        "--tools", "",
        "--setting-sources", "",
        "--system-prompt", SYSTEM,
        "--model", MODEL,
        "--effort", EFFORT,
        "--output-format", "json",
        "--json-schema", json.dumps(SCHEMA, ensure_ascii=False),
    ]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=_claude_env(),
                              cwd=tempfile.gettempdir(), timeout=CLAUDE_TIMEOUT)
    except FileNotFoundError as e:
        raise GraderError(f"Claude Code CLI not found ({CLAUDE_BIN}).") from e
    except subprocess.TimeoutExpired as e:
        raise GraderError(f"Claude Code did not answer within {CLAUDE_TIMEOUT} s.") from e

    out = proc.stdout.strip()
    res: dict[str, Any]
    try:
        res = json.loads(out[out.index("{"):]) if "{" in out else {}
    except ValueError:
        res = {}
    if proc.returncode != 0 and not res:
        err = (proc.stderr or out or "").strip().splitlines()
        raise GraderError("Claude Code failed: " + (err[-1] if err else f"exit code {proc.returncode}"))
    if res.get("is_error"):
        msg = str(res.get("result") or "unknown error")
        if "login" in msg.lower() or "logged" in msg.lower():
            status(refresh=True)
            msg = "Claude Code is not logged in: run `claude`, then /login."
        raise GraderError(f"Claude Code: {msg}")
    data = res.get("structured_output")
    if not isinstance(data, dict):
        try:
            data = json.loads(res.get("result") or "")
        except ValueError as e:
            raise GraderError("Unreadable Claude Code response (invalid JSON).") from e
    usage = res.get("usage") or {}
    used_model = next(iter(res.get("modelUsage") or {}), MODEL)
    return _finish(data, f"{used_model} (Claude Code)", {
        "input": int(usage.get("input_tokens", 0)) + int(usage.get("cache_creation_input_tokens", 0))
                 + int(usage.get("cache_read_input_tokens", 0)),
        "output": int(usage.get("output_tokens", 0)),
    })
