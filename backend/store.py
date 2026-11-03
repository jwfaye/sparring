"""Local storage of interview answers and their grades (SP-STORE): one SQLite database per profile.

The records of a profile live in `<data dir>/theory[/<profile>]/answers.sqlite3`, table `answers`, opened through
the standard `sqlite3` module with one short-lived connection per call (WAL journal, 5 s busy timeout), so the
server threads and the `tools/` scripts can share the file. An `answers.json` left by an earlier version is imported
on the first access of the profile, then renamed to `answers.json.migrated`; nothing is deleted.

The data directory comes from backend/paths.py: SPARRING_DATA_DIR when set, else data/ at the root of a clone, else
the per-user data directory ($XDG_DATA_HOME/sparring or ~/.local/share/sparring) of an installed `sparring`.
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from typing import Any

from backend import paths

Answer = dict[str, Any]

DATA_DIR = paths.data_dir()
DATA = os.path.join(DATA_DIR, "theory")
DB_NAME = "answers.sqlite3"
LEGACY_NAME = "answers.json"
MIGRATED_SUFFIX = ".migrated"
BUSY_TIMEOUT_S = 5.0
COLUMNS = ("id", "qid", "at", "duration", "answer", "mode", "grade", "graded_at")
SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    id TEXT PRIMARY KEY,
    qid TEXT NOT NULL,
    at INTEGER NOT NULL,
    duration NUMERIC,
    answer TEXT NOT NULL,
    mode TEXT NOT NULL,
    grade TEXT,
    graded_at INTEGER
);
CREATE INDEX IF NOT EXISTS answers_qid ON answers (qid);
"""
_INSERT = (
    "INSERT {} INTO answers (id, qid, at, duration, answer, mode, grade, graded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_SELECT = "SELECT id, qid, at, duration, answer, mode, grade, graded_at FROM answers"
_lock = threading.Lock()
log = logging.getLogger("sparring")


def _dir(profile: str | None) -> str:
    profile = re.sub(r"[^a-zA-Z0-9_-]", "", profile or "")
    return os.path.join(DATA, profile) if profile else DATA


def _path(profile: str | None) -> str:
    return os.path.join(_dir(profile), DB_NAME)


def _row(rec: Answer) -> tuple[Any, ...]:
    """The column values of a record, `grade` serialized as JSON text."""
    grade = rec.get("grade")
    return (
        rec["id"],
        rec["qid"],
        rec["at"],
        rec.get("duration"),
        rec["answer"],
        rec.get("mode", "offline"),
        json.dumps(grade, ensure_ascii=False) if grade is not None else None,
        rec.get("graded_at"),
    )


def _record(row: tuple[Any, ...]) -> Answer:
    rec: Answer = dict(zip(COLUMNS, row))
    rec["grade"] = json.loads(rec["grade"]) if rec["grade"] is not None else None
    return rec


def _migrated_name(legacy: str) -> str:
    """`answers.json.migrated`, or a numbered name when an earlier migration already left one."""
    target = legacy + MIGRATED_SUFFIX
    n = 1
    while os.path.exists(target):
        n += 1
        target = f"{legacy}{MIGRATED_SUFFIX}.{n}"
    return target


def _import_legacy(conn: sqlite3.Connection, legacy: str, db: str) -> None:
    """Insert every record of the legacy JSON file in one transaction, skipping known ids, then rename the file."""
    with open(legacy, encoding="utf-8") as fh:
        items: list[Answer] = json.load(fh)
    if not isinstance(items, list):
        raise TypeError(f"{legacy}: expected a JSON list of answer records, got {type(items).__name__}")
    with conn:
        conn.executemany(_INSERT.format("OR IGNORE"), [_row(rec) for rec in items])
    target = _migrated_name(legacy)
    os.replace(legacy, target)
    log.info("Imported %d interview answer(s) from %s into %s; the file is now %s", len(items), legacy, db, target)


def _open(profile: str | None) -> sqlite3.Connection:
    """Connect to the profile database, creating the directory and the schema and importing a legacy file first."""
    with _lock:
        directory = _dir(profile)
        os.makedirs(directory, exist_ok=True)
        db = os.path.join(directory, DB_NAME)
        conn = sqlite3.connect(db, timeout=BUSY_TIMEOUT_S)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(SCHEMA)
            legacy = os.path.join(directory, LEGACY_NAME)
            if os.path.exists(legacy):
                _import_legacy(conn, legacy, db)
        except BaseException:
            conn.close()
            raise
        return conn


def list_answers(profile: str | None = None) -> list[Answer]:
    conn = _open(profile)
    try:
        return [_record(row) for row in conn.execute(_SELECT + " ORDER BY at, rowid")]
    finally:
        conn.close()


def pending(profile: str | None = None) -> list[Answer]:
    return [a for a in list_answers(profile) if not a.get("grade")]


def add_answer(
    qid: str, answer: str, duration: float | None = None, profile: str | None = None, mode: str = "offline"
) -> Answer:
    rec: Answer = {
        "id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
        "qid": qid,
        "at": int(time.time() * 1000),
        "duration": duration,
        "answer": answer,
        "mode": mode,
        "grade": None,
        "graded_at": None,
    }
    conn = _open(profile)
    try:
        with conn:
            conn.execute(_INSERT.format(""), _row(rec))
    finally:
        conn.close()
    return rec


def set_grade(answer_id: str, grade: dict[str, Any], profile: str | None = None) -> Answer | None:
    conn = _open(profile)
    try:
        with conn:
            cur = conn.execute(
                "UPDATE answers SET grade = ?, graded_at = ? WHERE id = ?",
                (json.dumps(grade, ensure_ascii=False), int(time.time() * 1000), answer_id),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(_SELECT + " WHERE id = ?", (answer_id,)).fetchone()
        return _record(row)
    finally:
        conn.close()


def delete_answer(answer_id: str, profile: str | None = None) -> bool:
    conn = _open(profile)
    try:
        with conn:
            cur = conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))
        return cur.rowcount > 0
    finally:
        conn.close()
