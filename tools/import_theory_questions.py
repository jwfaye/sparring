#!/usr/bin/env python3
"""Import the theory interview questions (without answers) from the two markdown sources.

- tools/sources/field_guide_01-theory.md  (alexeygrigorev/ai-engineering-field-guide, interview/questions/01-theory.md)
- tools/sources/ds_interviews_theory.md   (alexeygrigorev/data-science-interviews, theory.md, CC BY 4.0)

Writes bank/theory/questions_field_guide.json and bank/theory/questions_ds_interviews.json:
[{id, section, question, difficulty?, source}]. The grading grids (reference answer, key points, common
mistakes, translation) are added afterwards by tools/add_theory_grids.py and preserved on re-import.

Usage: python -m tools.import_theory_questions
"""
import json
import os
import re
import unicodedata
from typing import Any

Question = dict[str, Any]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "tools", "sources")
OUT = os.path.join(ROOT, "bank", "theory")
GRID_FIELDS = ("reference", "key_points", "common_mistakes", "uncertain", "note")


def slug(s: str, n: int = 3) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if w not in {"the", "a", "an", "of", "and", "in", "for", "to", "is", "do", "we", "how", "what", "it"}]
    return "-".join(words[:n]) or "q"


def parse_field_guide(text: str) -> list[Question]:
    items: list[Question] = []
    section: str | None = None
    skip_sections = {"Format", "Interview Questions", "Specialized Topics", "How to Prepare", "Sources", "ML Fundamentals"}
    for line in text.splitlines():
        m = re.match(r"^##+\s+(.*)", line)
        if m:
            section = m.group(1).strip()
            continue
        m = re.match(r"^- (.*)", line)
        if m and section and section not in skip_sections:
            q = re.sub(r"\s*\[\^[^\]]*\]?", "", m.group(1)).strip()
            q = re.sub(r"\s+", " ", q)
            items.append({"section": section, "question": q})
    return items


def parse_ds(text: str) -> list[Question]:
    items: list[Question] = []
    section: str | None = None
    emoji = {"👶": "easy", "⭐": "medium", "🚀": "expert"}
    for line in text.splitlines():
        m = re.match(r"^## (.*)", line)
        if m:
            section = m.group(1).strip()
            continue
        m = re.match(r"^\*\*(.+?)\*\*\s*$", line.strip())
        if m and section and section != "Table of contents":
            raw = m.group(1)
            diff = None
            for e, d in emoji.items():
                if e in raw:
                    diff = d
            q = re.sub(r"[👶⭐🚀️‍]+", "", raw).strip()
            q = re.sub(r"\s+", " ", q)
            q = re.sub(r"\s+I$", "", q)
            items.append({"section": section, "question": q, "difficulty": diff})
    return items


def merge(path: str, items: list[Question], prefix: str, source: str) -> list[Question]:
    old: dict[str, Question] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            old = {q["id"]: q for q in json.load(fh)}
    out: list[Question] = []
    seen: dict[str, int] = {}
    for it in items:
        base = f"{prefix}-{slug(it['section'], 2)}"
        n = seen.get(base, 0) + 1
        seen[base] = n
        qid = f"{base}-{n:02d}"
        q: Question = {"id": qid, "section": it["section"], "question": it["question"], "source": source}
        if it.get("difficulty"):
            q["difficulty"] = it["difficulty"]
        for f in GRID_FIELDS:
            if qid in old and f in old[qid]:
                q[f] = old[qid][f]
        out.append(q)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(SRC, "field_guide_01-theory.md"), encoding="utf-8") as fh:
        fg = merge(os.path.join(OUT, "questions_field_guide.json"), parse_field_guide(fh.read()), "fg",
                   "alexeygrigorev/ai-engineering-field-guide — interview/questions/01-theory.md")
    with open(os.path.join(SRC, "ds_interviews_theory.md"), encoding="utf-8") as fh:
        ds = merge(os.path.join(OUT, "questions_ds_interviews.json"), parse_ds(fh.read()), "ds",
                   "alexeygrigorev/data-science-interviews — theory.md (CC BY 4.0)")
    for name, items in (("field guide", fg), ("data-science-interviews", ds)):
        secs: dict[str, int] = {}
        for q in items:
            secs[q["section"]] = secs.get(q["section"], 0) + 1
        print(f"{name}: {len(items)} questions, {len(secs)} sections, {sum(1 for q in items if 'reference' in q)} with a grid")
        for s, n in secs.items():
            print(f"   {n:3d}  {s}")


if __name__ == "__main__":
    main()
