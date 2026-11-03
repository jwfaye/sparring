#!/usr/bin/env python3
"""Validate a draft of multiple-choice questions and add only the passing ones to the bank.

Usage: python -m tools.add_qcm DRAFT [--out bank/qcm/NAME.json] [--dry-run]
DRAFT: a .json file (list) or a .py module defining QUESTIONS (list of dicts).
"""

import argparse
import importlib.util
import json
import os
import sys
from typing import Any

from tools import check_qcm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "bank", "qcm")


def load_draft(path: str) -> list[dict[str, Any]]:
    if path.endswith(".py"):
        spec = importlib.util.spec_from_file_location("draft", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load draft module {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return list(mod.QUESTIONS)
    return check_qcm.load_items(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    drafts = load_draft(args.draft)
    out_path = args.out or os.path.join(BANK, os.path.splitext(os.path.basename(args.draft))[0] + ".json")
    bank: list[dict[str, Any]] = []
    for f in check_qcm.iter_files([BANK]) if os.path.isdir(BANK) else []:
        bank.extend(check_qcm.load_items(f))
    current = check_qcm.load_items(out_path) if os.path.exists(out_path) else []
    current_ids = {q["id"] for q in current}
    known_ids = {q["id"] for q in bank}
    known_q = {check_qcm.norm(q["question"]).lower() for q in bank if q["id"] not in current_ids}

    accepted: list[tuple[dict[str, Any], list[str]]] = []
    rejected: list[tuple[dict[str, Any], list[str]]] = []
    seen: set[str] = set()
    for q in drafts:
        errors = check_qcm.check_question(q)
        qid = q.get("id", "?")
        if qid in seen:
            errors.append("duplicate id within the draft")
        seen.add(qid)
        if qid in known_ids and qid not in current_ids:
            errors.append("id already present in another bank file")
        if check_qcm.norm(q.get("question", "")).lower() in known_q:
            errors.append("question already present in the bank")
        (rejected if errors else accepted).append((q, errors))

    for q, _ in accepted:
        print(f"OK  {q['id']:<18} [{q['theme']}] {check_qcm.norm(q['question'])[:70]}")
    for q, errors in rejected:
        print(f"KO  {q.get('id', '?'):<18} {check_qcm.norm(q.get('question', ''))[:70]}")
        for e in errors:
            print("   - " + e)
    print(f"\n{len(accepted)} accepted, {len(rejected)} rejected")

    if accepted and not args.dry_run:
        merged = {q["id"]: q for q in current}
        for q, _ in accepted:
            merged[q["id"]] = q
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(list(merged.values()), fh, ensure_ascii=False, indent=2)
        print(
            f"-> {len(accepted)} question(s) written to {os.path.relpath(out_path, ROOT)} ({len(merged)} total in this file)"
        )
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
