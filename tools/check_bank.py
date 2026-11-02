#!/usr/bin/env python3
"""Validate the exercise bank with the same harness the browser uses.

For each exercise:
  - schema (required fields, allowed values, unique id)
  - the solution passes every test
  - the starter code does NOT pass the tests (otherwise the exercise is trivial)

Usage: python -m tools.check_bank [file_or_directory ...]   (default: bank/exercises)
Exit code: 0 when everything is valid, 1 otherwise.
"""
import glob
import importlib.util
import json
import os
import re
import sys
from collections.abc import Iterable, Iterator
from typing import Any

Exercise = dict[str, Any]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("harness", os.path.join(ROOT, "app", "py", "harness.py"))
if _spec is None or _spec.loader is None:
    raise ImportError("app/py/harness.py not found")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

REQUIRED = ["id", "title", "theme", "difficulty", "language", "statement", "setup", "starter", "tests", "solution"]
DIFFICULTIES = {"easy", "medium", "hard"}
LANGUAGES = {"python", "sql"}
THEMES = {
    "groupby", "merge", "pivot", "dates", "nan", "cleaning", "python",
    "sql-joins", "sql-groupby", "sql-window", "sql-cte", "sql-subqueries",
}
LEAK_WORDS = re.compile(r"\b(hint|hints|tip|tips|trick|tricks|trap|traps|pitfall|pitfalls)\b", re.IGNORECASE)


def iter_files(targets: Iterable[str]) -> Iterator[str]:
    for t in targets:
        if os.path.isdir(t):
            yield from sorted(glob.glob(os.path.join(t, "*.json")))
        else:
            yield t


def load_items(path: str) -> list[Exercise]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or data.get("exercises") or [data]
    raise ValueError("unexpected format")


def run_tests(ex: Exercise, code: str) -> dict[str, Any]:
    payload = {"mode": "check", "language": ex["language"], "setup": ex["setup"],
               "code": code, "tests": ex["tests"]}
    result: dict[str, Any] = json.loads(harness.run_json(json.dumps(payload)))
    return result


def check_exercise(ex: Exercise) -> list[str]:
    errors: list[str] = []
    for f in REQUIRED:
        if f not in ex:
            errors.append(f"missing field: {f}")
    if errors:
        return errors
    if ex["difficulty"] not in DIFFICULTIES:
        errors.append(f"invalid difficulty: {ex['difficulty']!r}")
    if ex["language"] not in LANGUAGES:
        errors.append(f"invalid language: {ex['language']!r}")
    if ex["theme"] not in THEMES:
        errors.append(f"unknown theme: {ex['theme']!r} (expected one of: {', '.join(sorted(THEMES))})")
    if not isinstance(ex["tests"], list) or len(ex["tests"]) < 2:
        errors.append("at least 2 tests are required (setup data + another dataset)")
        return errors
    if LEAK_WORDS.search(ex["statement"]):
        errors.append("the statement contains an explicit hint/trap: move it to 'hints'")
    if "hints" in ex and (not isinstance(ex["hints"], list) or not all(isinstance(h, str) for h in ex["hints"])):
        errors.append("'hints' must be a list of strings")
    for i, t in enumerate(ex["tests"]):
        if ex["language"] == "python" and "code" not in t:
            errors.append(f"test {i}: missing 'code' field")
        if ex["language"] == "sql" and "expected" not in t:
            errors.append(f"test {i}: missing 'expected' field")
    if errors:
        return errors

    sol = run_tests(ex, ex["solution"])
    if sol.get("error"):
        errors.append("harness: " + sol["error"])
    for t in sol.get("tests", []):
        if not t["ok"]:
            errors.append(f"the solution fails test \"{t['name']}\":\n" + indent(t["message"]))

    starter = run_tests(ex, ex["starter"])
    if starter.get("ok"):
        errors.append("the tests pass with the unmodified starter code (trivial exercise or weak tests)")
    return errors


def indent(s: object, n: int = 6) -> str:
    pad = " " * n
    return "\n".join(pad + line for line in str(s).splitlines())


def main(argv: list[str]) -> int:
    targets = argv or [os.path.join(ROOT, "bank", "exercises")]
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
        for ex in items:
            exid = ex.get("id", "?")
            errors = check_exercise(ex)
            if exid in seen:
                errors.append(f"duplicate id (already in {seen[exid]})")
            seen[exid] = rel
            label = f"{exid:<28} [{ex.get('language','?')}/{ex.get('difficulty','?')}/{ex.get('theme','?')}] {ex.get('title','')}"
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
