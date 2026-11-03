#!/usr/bin/env python3
"""Validate a draft of exercises and add only the passing ones to the bank.

Usage: python -m tools.add_exercises DRAFT [--out bank/exercises/NAME.json] [--dry-run]

DRAFT: a .json file (list of exercises) or a .py module defining EXERCISES (list of dicts).
Criteria (see tools/check_bank.py): schema, known theme, id and title not already in the bank,
>= 2 tests, the solution passes, the starter code fails, no hint in the statement.
Output: accepted/rejected report with reasons; exit code 1 if at least one draft is rejected.
"""

import argparse
import importlib.util
import json
import os
import sys
from typing import Any

from tools import check_bank

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "bank", "exercises")


def load_draft(path: str) -> list[dict[str, Any]]:
    if path.endswith(".py"):
        spec = importlib.util.spec_from_file_location("draft", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load draft module {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return list(mod.EXERCISES)
    return check_bank.load_items(path)


def existing_bank() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for f in check_bank.iter_files([BANK]):
        items.extend(check_bank.load_items(f))
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--out", default=None, help="target bank file (default: bank/exercises/<draft name>.json)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    drafts = load_draft(args.draft)
    bank = existing_bank()
    out_path = args.out or os.path.join(BANK, os.path.splitext(os.path.basename(args.draft))[0] + ".json")
    known_ids = {e["id"] for e in bank}
    known_titles = {e["title"].strip().lower() for e in bank}
    current = check_bank.load_items(out_path) if os.path.exists(out_path) else []
    current_ids = {e["id"] for e in current}

    accepted: list[tuple[dict[str, Any], list[str]]] = []
    rejected: list[tuple[dict[str, Any], list[str]]] = []
    seen_ids: set[str] = set()
    for ex in drafts:
        errors = check_bank.check_exercise(ex)
        exid = ex.get("id", "?")
        if exid in seen_ids:
            errors.append("duplicate id within the draft")
        seen_ids.add(exid)
        if exid in known_ids and exid not in current_ids:
            errors.append("id already present in another bank file")
        if ex.get("title", "").strip().lower() in known_titles and exid not in current_ids:
            errors.append("title already present in the bank")
        (rejected if errors else accepted).append((ex, errors))

    for ex, _ in accepted:
        print(f"OK  {ex['id']:<26} [{ex['language']}/{ex['difficulty']}/{ex['theme']}] {ex['title']}")
    for ex, errors in rejected:
        print(f"KO  {ex.get('id', '?'):<26} {ex.get('title', '')}")
        for e in errors:
            print("   - " + e)
    print(f"\n{len(accepted)} accepted, {len(rejected)} rejected")

    if accepted and not args.dry_run:
        merged = {e["id"]: e for e in current}
        for ex, _ in accepted:
            merged[ex["id"]] = ex
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(list(merged.values()), fh, ensure_ascii=False, indent=2)
        print(
            f"-> {len(accepted)} exercise(s) written to {os.path.relpath(out_path, ROOT)} ({len(merged)} total in this file)"
        )
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
