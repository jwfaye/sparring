#!/usr/bin/env python3
"""Validate the multiple-choice question bank.

For each question: schema (4 distinct choices, valid correct answer, explanation, known theme, source),
unique id, and for every question with Python/SQL code: the code is executed to confirm that the correct
answer is the announced one (and that no other choice matches the result).

"check" field of a question with code:
  {"type": "python_stdout"}                      -> the code's standard output == correct answer
  {"type": "python_expr", "expr": "x"}           -> repr(eval(expr)) after execution == correct answer
  {"type": "python_raises", "exception": "KeyError"} -> the code raises this exception, named in the correct answer
  {"type": "sql", "setup": "...", "expr": "rows"} -> str(eval(expr)) with rows = query result == correct answer
  {"type": "none", "reason": "..."}              -> cannot be executed (interpretation question); reason required

Usage: python -m tools.check_qcm [file_or_directory ...]   (default: bank/qcm)
"""

import contextlib
import glob
import io
import json
import os
import re
import sqlite3
import sys
import warnings
from collections.abc import Iterable, Iterator
from typing import Any

Question = dict[str, Any]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ["id", "theme", "question", "choices", "answer", "explanation", "source"]
THEMES = {
    "regression",
    "validation",
    "classification",
    "regularization",
    "trees-ensembles",
    "neural-networks",
    "nlp",
    "clustering",
    "dimensionality-reduction",
    "recommender-systems",
    "time-series",
    "python",
    "pandas",
    "sql",
    "git",
}
EXEC_LANGS = {"python", "sql"}


def norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def iter_files(targets: Iterable[str]) -> Iterator[str]:
    for t in targets:
        if os.path.isdir(t):
            yield from sorted(glob.glob(os.path.join(t, "*.json")))
        else:
            yield t


def load_items(path: str) -> list[Question]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or [data]
    raise ValueError("unexpected format")


def run_python(code: str) -> tuple[dict[str, Any], str, Exception | None]:
    """Execute the code in a fresh namespace; return (namespace, stdout, exception)."""
    ns: dict[str, Any] = {"__name__": "__main__"}
    buf, err = io.StringIO(), io.StringIO()
    exc: Exception | None = None
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            exec(compile(code, "<question>", "exec"), ns)
        except Exception as e:
            exc = e
    return ns, buf.getvalue(), exc


def compute_result(q: Question) -> tuple[str | None, str | None]:
    """Return (result_text, error). result_text is compared against the choices."""
    chk = q["check"]
    t = chk.get("type")
    code = q.get("code", "")
    if t == "python_stdout":
        _, out, exc = run_python(code)
        if exc is not None:
            return None, f"the code raises {type(exc).__name__}: {exc}"
        return out, None
    if t == "python_expr":
        ns, _, exc = run_python(code)
        if exc is not None:
            return None, f"the code raises {type(exc).__name__}: {exc}"
        try:
            return repr(eval(chk["expr"], ns)), None
        except Exception as e:
            return None, f"invalid expr: {type(e).__name__}: {e}"
    if t == "python_raises":
        _, _, exc = run_python(code)
        if exc is None:
            return None, "the code does not raise any exception"
        return type(exc).__name__, None
    if t == "sql":
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(chk.get("setup", ""))
            rows = [tuple(r) for r in con.execute(code.strip().rstrip(";")).fetchall()]
        except Exception as e:
            return None, f"SQL error: {type(e).__name__}: {e}"
        finally:
            con.close()
        try:
            return str(eval(chk.get("expr", "rows"), {"rows": rows})), None
        except Exception as e:
            return None, f"invalid expr: {type(e).__name__}: {e}"
    return None, f"unknown check type: {t!r}"


def check_question(q: Question) -> list[str]:
    errors: list[str] = []
    for f in REQUIRED:
        if f not in q:
            errors.append(f"missing field: {f}")
    if errors:
        return errors
    if q["theme"] not in THEMES:
        errors.append(f"unknown theme: {q['theme']!r}")
    ch = q["choices"]
    if not isinstance(ch, list) or len(ch) != 4 or not all(isinstance(c, str) and c.strip() for c in ch):
        errors.append("exactly 4 non-empty choices are required")
    elif len({norm(c).lower() for c in ch}) != 4:
        errors.append("duplicate choices")
    if not isinstance(q["answer"], int) or not 0 <= q["answer"] <= 3:
        errors.append("answer must be an integer between 0 and 3")
    if not str(q["explanation"]).strip():
        errors.append("empty explanation")
    code = q.get("code")
    if code is not None and "\n" not in code.strip() and len(code.strip()) > 60:
        errors.append("single-line code: format it over several lines")
    if errors:
        return errors

    lang = q.get("language", "python" if code else None)
    if code and lang in EXEC_LANGS:
        if "check" not in q:
            errors.append("question with Python/SQL code but no 'check' field (execution is mandatory)")
            return errors
        if q["check"].get("type") == "none":
            if not q["check"].get("reason"):
                errors.append("check 'none' without a reason")
            return errors
        result, err = compute_result(q)
        if err:
            errors.append("execution: " + err)
            return errors
        good = norm(q["choices"][q["answer"]])
        got = norm(result)
        if q["check"].get("type") == "python_raises":
            if got not in good:
                errors.append(f"the correct answer does not name the raised exception ({got}): {good!r}")
            return errors
        if got != good:
            errors.append(f"actual result {got!r} != announced correct answer {good!r}")
        for i, c in enumerate(q["choices"]):
            if i != q["answer"] and norm(c) == got:
                errors.append(f"choice {i} also matches the actual result: ambiguous question")
    return errors


def main(argv: list[str]) -> int:
    targets = argv or [os.path.join(ROOT, "bank", "qcm")]
    seen: dict[str, str] = {}
    n_ok, n_bad = 0, 0
    for path in iter_files(targets):
        rel = os.path.relpath(path, ROOT)
        try:
            items = load_items(path)
        except Exception as exc:
            print(f"KO  {rel}: invalid JSON ({exc})")
            n_bad += 1
            continue
        for q in items:
            qid = q.get("id", "?")
            errors = check_question(q)
            if qid in seen:
                errors.append(f"duplicate id (already in {seen[qid]})")
            seen[qid] = rel
            label = f"{qid:<18} [{q.get('theme', '?')}] {norm(q.get('question', ''))[:70]}"
            if errors:
                n_bad += 1
                print(f"KO  {label}")
                for e in errors:
                    print("   - " + e)
            else:
                n_ok += 1
                print(f"OK  {label}")
    print(f"\n{n_ok} valid, {n_bad} invalid")
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
