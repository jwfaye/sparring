#!/usr/bin/env python3
"""Validate the theory interview bank (bank/theory/*.json) and list questions without a grading grid.

A complete grid = reference (concise reference answer), key_points (3 to 6), common_mistakes (>= 1).
Every question carries a difficulty (easy | medium | expert). `uncertain: true` + `note` flags a question judged too
uncertain for a reliable grid (shown in the app).
Usage: python -m tools.check_theory [--missing]
"""

import glob
import json
import os
import sys
from typing import Any

Question = dict[str, Any]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "bank", "theory")
DIFFICULTIES = ("easy", "medium", "expert")


def check_grid(q: Question) -> list[str]:
    errors: list[str] = []
    if q.get("difficulty") not in DIFFICULTIES:
        errors.append("difficulty must be one of " + ", ".join(DIFFICULTIES))
    ref = q.get("reference", "")
    if not ref.strip():
        errors.append("missing reference")
    elif len(ref) > 1800:
        errors.append(f"reference too long ({len(ref)} characters, max 1800)")
    kp = q.get("key_points")
    if not isinstance(kp, list) or not 3 <= len(kp) <= 6 or not all(isinstance(p, str) and p.strip() for p in kp):
        errors.append("key_points must contain 3 to 6 strings")
    cm = q.get("common_mistakes")
    if not isinstance(cm, list) or not cm or not all(isinstance(p, str) and p.strip() for p in cm):
        errors.append("common_mistakes must contain at least 1 string")
    if q.get("uncertain") and not q.get("note"):
        errors.append("uncertain without an explanatory note")
    return errors


def load_all() -> list[Question]:
    items: list[Question] = []
    for f in sorted(glob.glob(os.path.join(BANK, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            for q in json.load(fh):
                q["_file"] = os.path.relpath(f, ROOT)
                items.append(q)
    return items


def main(argv: list[str]) -> int:
    items = load_all()
    seen: set[str] = set()
    missing: list[Question] = []
    n_ok, n_bad = 0, 0
    for q in items:
        if q["id"] in seen:
            print(f"KO  {q['id']}: duplicate id")
            n_bad += 1
        seen.add(q["id"])
        if "reference" not in q and "key_points" not in q:
            missing.append(q)
            continue
        errors = check_grid(q)
        if errors:
            n_bad += 1
            print(f"KO  {q['id']:<34} {q['question'][:60]}")
            for e in errors:
                print("   - " + e)
        else:
            n_ok += 1
    print(f"\n{len(items)} questions: {n_ok} valid grid(s), {n_bad} invalid, {len(missing)} without a grid")
    if "--missing" in argv:
        for q in missing:
            print(f"   {q['id']:<34} [{q['section']}] {q['question']}")
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
