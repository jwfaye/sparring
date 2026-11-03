"""Local storage of interview answers and their grades (<data dir>/theory[/<profile>]/answers.json).

The data directory comes from backend/paths.py: SPARRING_DATA_DIR when set, else data/ at the root of a clone, else
the per-user data directory ($XDG_DATA_HOME/sparring or ~/.local/share/sparring) of an installed `sparring`.
"""
import json
import os
import re
import threading
import time
import uuid
from typing import Any

from backend import paths

Answer = dict[str, Any]

DATA = os.path.join(paths.data_dir(), "theory")
_lock = threading.Lock()


def _dir(profile: str | None) -> str:
    profile = re.sub(r"[^a-zA-Z0-9_-]", "", profile or "")
    return os.path.join(DATA, profile) if profile else DATA


def _path(profile: str | None) -> str:
    return os.path.join(_dir(profile), "answers.json")


def _load(profile: str | None) -> list[Answer]:
    p = _path(profile)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        data: list[Answer] = json.load(fh)
    return data


def _save(profile: str | None, items: list[Answer]) -> None:
    os.makedirs(_dir(profile), exist_ok=True)
    tmp = _path(profile) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(profile))


def list_answers(profile: str | None = None) -> list[Answer]:
    with _lock:
        return _load(profile)


def pending(profile: str | None = None) -> list[Answer]:
    return [a for a in list_answers(profile) if not a.get("grade")]


def add_answer(qid: str, answer: str, duration: float | None = None, profile: str | None = None,
               mode: str = "offline") -> Answer:
    rec: Answer = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6], "qid": qid, "at": int(time.time() * 1000),
           "duration": duration, "answer": answer, "mode": mode, "grade": None}
    with _lock:
        items = _load(profile)
        items.append(rec)
        _save(profile, items)
    return rec


def set_grade(answer_id: str, grade: dict[str, Any], profile: str | None = None) -> Answer | None:
    with _lock:
        items = _load(profile)
        for a in items:
            if a["id"] == answer_id:
                a["grade"] = grade
                a["graded_at"] = int(time.time() * 1000)
                _save(profile, items)
                return a
    return None


def delete_answer(answer_id: str, profile: str | None = None) -> bool:
    with _lock:
        items = _load(profile)
        kept = [a for a in items if a["id"] != answer_id]
        _save(profile, kept)
        return len(kept) != len(items)
