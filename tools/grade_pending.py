#!/usr/bin/env python3
"""Grade every pending answer through the configured grader backend (API key or Claude Code).

Usage: .venv/bin/python -m tools.grade_pending [--profile NAME]
"""

import argparse
import sys

from backend import grader, store
from tools import check_theory


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()
    st = grader.status()
    if not st["available"]:
        print("Grading unavailable: " + st["reason"])
        return 1
    questions = {q["id"]: q for q in check_theory.load_all()}
    pend = store.pending(args.profile)
    print(f"{len(pend)} answer(s) to grade with {st['model']}")
    for a in pend:
        q = questions.get(a["qid"])
        if q is None:
            print(f"KO  {a['id']}: unknown question {a['qid']}")
            continue
        try:
            g = grader.grade(q, a["answer"])
            store.set_grade(a["id"], g, args.profile)
            print(f"OK  {a['id']} [{a['qid']}] -> {g['score']}/10")
        except grader.GraderError as exc:
            print(f"KO  {a['id']}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
