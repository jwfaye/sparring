#!/usr/bin/env python3
"""Export the interview answers awaiting grading (offline mode) together with their grid, for manual grading.

Usage: python -m tools.theory_pending [--profile NAME] [--json FILE]
Without --json: human-readable output. With --json: writes [{answer_id, question, reference, key_points, common_mistakes, answer}]
to be graded and then imported with tools/import_grades.py.
"""

import argparse
import json
from typing import Any

from backend import store
from tools import check_theory


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    questions = {q["id"]: q for q in check_theory.load_all()}
    out: list[dict[str, Any]] = []
    for a in store.pending(args.profile):
        q = questions.get(a["qid"], {})
        out.append(
            {
                "answer_id": a["id"],
                "at": a["at"],
                "qid": a["qid"],
                "question": q.get("question"),
                "reference": q.get("reference"),
                "key_points": q.get("key_points"),
                "common_mistakes": q.get("common_mistakes"),
                "answer": a["answer"],
            }
        )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print(f"{len(out)} pending answer(s) -> {args.json}")
        return
    print(f"{len(out)} answer(s) awaiting grading\n")
    for o in out:
        print(
            f"=== {o['answer_id']}  [{o['qid']}]\nQ: {o['question']}\n--- Candidate answer:\n{o['answer']}\n--- Key points:"
        )
        for p in o["key_points"] or []:
            print(f"  - {p}")
        print()


if __name__ == "__main__":
    main()
