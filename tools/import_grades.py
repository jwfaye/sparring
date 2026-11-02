#!/usr/bin/env python3
"""Import grades produced offline: a JSON file {answer_id: {score, covered, missing, wrong, feedback, improved_answer}}.

Usage: python -m tools.import_grades GRADES.json [--profile NAME]
"""
import argparse
import json

from backend import store

REQUIRED = ("score", "covered", "missing", "wrong", "feedback", "improved_answer")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()
    with open(args.file, encoding="utf-8") as fh:
        grades = json.load(fh)
    n = 0
    for answer_id, g in grades.items():
        missing = [k for k in REQUIRED if k not in g]
        if missing:
            print(f"KO  {answer_id}: missing fields {missing}")
            continue
        g = dict(g)
        g["score"] = max(0, min(10, int(g["score"])))
        g.setdefault("model", "manual grading (Claude, offline)")
        if store.set_grade(answer_id, g, args.profile):
            n += 1
            print(f"OK  {answer_id}: {g['score']}/10")
        else:
            print(f"KO  {answer_id}: answer not found")
    print(f"\n{n} grade(s) imported")


if __name__ == "__main__":
    main()
