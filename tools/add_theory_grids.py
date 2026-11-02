#!/usr/bin/env python3
"""Merge a draft of grading grids into the theory interview bank.

Usage: python -m tools.add_theory_grids DRAFT.py [--dry-run]
DRAFT.py defines GRIDS = {question_id: {reference, key_points, common_mistakes, uncertain?, note?}}.
Only valid grids (see tools/check_theory.py) are written; the id must exist in the bank.
"""
import glob
import importlib.util
import json
import os
import sys
from typing import Any

from tools import check_theory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "bank", "theory")

FIELDS = ("reference", "key_points", "common_mistakes", "uncertain", "note")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    spec = importlib.util.spec_from_file_location("draft", sys.argv[1])
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load draft module {sys.argv[1]}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    grids: dict[str, dict[str, Any]] = dict(mod.GRIDS)
    dry = "--dry-run" in sys.argv

    accepted, rejected = 0, 0
    written: dict[str, bool] = {}
    for f in sorted(glob.glob(os.path.join(BANK, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            items = json.load(fh)
        changed = False
        for q in items:
            g = grids.pop(q["id"], None)
            if g is None:
                continue
            cand = {k: v for k, v in q.items() if k not in FIELDS}
            cand.update({k: g[k] for k in FIELDS if k in g})
            errors = check_theory.check_grid(cand)
            if errors:
                rejected += 1
                print(f"KO  {q['id']}: " + "; ".join(errors))
                continue
            accepted += 1
            for k in FIELDS:
                q.pop(k, None)
            q.update({k: g[k] for k in FIELDS if k in g})
            changed = True
        if changed and not dry:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(items, fh, ensure_ascii=False, indent=2)
            written[os.path.relpath(f, ROOT)] = True
    for qid in grids:
        rejected += 1
        print(f"KO  {qid}: unknown id in the bank")
    print(f"\n{accepted} grid(s) accepted, {rejected} rejected" + (" (dry-run)" if dry else f" -> {', '.join(written) or 'nothing written'}"))
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
