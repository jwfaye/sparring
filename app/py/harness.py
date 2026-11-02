"""Execution harness shared by the browser (Pyodide) and the local tools (CPython).

Entry point: run_json(payload_json) -> json
payload = {
  "mode": "run" | "check",
  "language": "python" | "sql",
  "setup": str,            data preparation code (python) or SQL script (DDL + INSERT)
  "code": str,             the user's code
  "tests": [...],          check mode: python -> [{"name", "code"}], sql -> [{"name", "expected", "ordered"?, "columns"?, "setup"?}]
  "run_call": str | None   python, run mode: expression displayed after execution (e.g. "solve(df)")
}
Run mode response:   {"output": str, "error": str | None}
Check mode response: {"ok": bool, "tests": [{"name", "ok", "message", "stdout"}]}

Message strings returned to the browser are displayed as-is in the UI.
"""
import contextlib
import io
import json
import linecache
import math
import sqlite3
import traceback
from types import ModuleType
from typing import Any

Json = dict[str, Any]

USER_FILE = "<ton code>"
TEST_FILE = "<test>"
SETUP_FILE = "<setup>"
CALL_FILE = "<appel>"
MAX_REPR = 3000
MAX_ROWS = 60


def _pd() -> ModuleType | None:
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


def _np() -> ModuleType | None:
    try:
        import numpy as np
        return np
    except ImportError:
        return None


# ---------------------------------------------------------------- display
def display(v: Any) -> str:
    """Readable representation of a value (without the type suffix)."""
    pd = _pd()
    if pd is not None and isinstance(v, (pd.DataFrame, pd.Series)):
        with pd.option_context("display.max_rows", 60, "display.max_columns", 30, "display.width", 140):
            return str(v)
    s = repr(v)
    return s if len(s) <= MAX_REPR else s[:MAX_REPR] + " …"


def fmt(v: Any) -> str:
    """Readable representation plus metadata useful for diagnosis."""
    pd = _pd()
    if pd is not None and isinstance(v, pd.DataFrame):
        dtypes = {c: str(t) for c, t in v.dtypes.items()}
        return display(v) + f"\n[DataFrame shape={v.shape}, index={type(v.index).__name__}, dtypes={dtypes}]"
    if pd is not None and isinstance(v, pd.Series):
        return display(v) + f"\n[Series name={v.name!r}, dtype={v.dtype}, len={len(v)}, index={type(v.index).__name__}]"
    return display(v) + f"  [{type(v).__name__}]"


class CheckError(AssertionError):
    """Failed test assertion (message already formatted)."""


def _fail(expected: Any, got: Any, hint: str = "") -> None:
    msg = (hint.strip() + "\n\n") if hint else ""
    raise CheckError(msg + "Expected:\n" + fmt(expected) + "\n\nGot:\n" + fmt(got))


def _first_lines(s: object, n: int = 6) -> str:
    lines = [line for line in str(s).splitlines() if line.strip()]
    return "\n".join(lines[:n])


# ---------------------------------------------------------------- comparison
def _is_nan(x: Any) -> bool:
    if x is None:
        return True
    pd = _pd()
    if pd is not None:
        try:
            r = pd.isna(x)
            if isinstance(r, bool) or type(r).__name__ == "bool_":
                return bool(r)
            return False
        except Exception:
            return False
    return isinstance(x, float) and math.isnan(x)


def _scalar(x: Any) -> Any:
    """numpy scalar -> python scalar."""
    if hasattr(x, "item") and getattr(x, "shape", None) == ():
        try:
            return x.item()
        except Exception:
            return x
    return x


def _eq(got: Any, exp: Any, tol: float) -> bool:
    """Tolerant recursive equality (floats, NaN, lists, dicts, arrays)."""
    np = _np()
    if _is_nan(got) and _is_nan(exp):
        return True
    got, exp = _scalar(got), _scalar(exp)
    if isinstance(exp, bool) or isinstance(got, bool):
        return type(got) is type(exp) and got == exp
    if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
        return math.isclose(got, exp, rel_tol=tol, abs_tol=tol)
    if isinstance(exp, (list, tuple)):
        if not isinstance(got, (list, tuple)) or len(got) != len(exp):
            return False
        return all(_eq(g, e, tol) for g, e in zip(got, exp))
    if isinstance(exp, dict):
        if not isinstance(got, dict) or set(got) != set(exp):
            return False
        return all(_eq(got[k], exp[k], tol) for k in exp)
    if isinstance(exp, (set, frozenset)):
        return isinstance(got, (set, frozenset)) and got == exp
    if np is not None and isinstance(exp, np.ndarray):
        try:
            g = np.asarray(got)
            if g.shape != exp.shape:
                return False
            if np.issubdtype(exp.dtype, np.number) and np.issubdtype(g.dtype, np.number):
                return bool(np.allclose(g, exp, rtol=tol, atol=tol, equal_nan=True))
            return bool(np.array_equal(g, exp))
        except Exception:
            return False
    try:
        return bool(got == exp)
    except Exception:
        return False


def _sorted_frame(df: Any) -> Any:
    try:
        return df.sort_values(list(df.columns), kind="mergesort").reset_index(drop=True)
    except Exception:
        key = df.astype(str).agg("\x1f".join, axis=1)
        return df.iloc[key.argsort(kind="mergesort").to_numpy()].reset_index(drop=True)


def assert_eq(got: Any, expected: Any, msg: str = "", *, ignore_order: bool = False, ignore_index: bool = False,
              tol: float = 1e-6) -> None:
    """Compare `got` with `expected`.

    - DataFrame: same columns (order included), same values; dtypes are not checked strictly.
      ignore_order=True: row order (and the index) is ignored.
      ignore_index=True: the index is ignored (positional comparison).
    - Series: same rules (ignore_order sorts by index).
    - scalars / lists / dicts / arrays: tolerant equality (floats, NaN).
    """
    pd = _pd()
    if pd is not None and isinstance(expected, pd.DataFrame):
        if not isinstance(got, pd.DataFrame):
            _fail(expected, got, msg or f"A DataFrame is expected, not {type(got).__name__}.")
        g, e = got, expected
        if list(g.columns) != list(e.columns):
            _fail(expected, got, (msg + "\n" if msg else "")
                  + f"Different columns.\nExpected: {list(e.columns)}\nGot:      {list(g.columns)}")
        if ignore_order:
            g, e = _sorted_frame(g), _sorted_frame(e)
            ignore_index = True
        if ignore_index:
            g, e = g.reset_index(drop=True), e.reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(
                g, e, check_dtype=False, check_index_type=False, check_column_type=False,
                check_names=False, check_exact=False, rtol=tol, atol=tol,
                check_categorical=False, check_freq=False)
        except AssertionError as ex:
            _fail(expected, got, (msg + "\n" if msg else "") + _first_lines(ex))
        return
    if pd is not None and isinstance(expected, pd.Series):
        if not isinstance(got, pd.Series):
            _fail(expected, got, msg or f"A Series is expected, not {type(got).__name__}.")
        g, e = got, expected
        if ignore_order:
            g, e = g.sort_index(kind="mergesort"), e.sort_index(kind="mergesort")
        if ignore_index:
            g, e = g.reset_index(drop=True), e.reset_index(drop=True)
        try:
            pd.testing.assert_series_equal(
                g, e, check_dtype=False, check_index_type=False, check_names=False,
                check_exact=False, rtol=tol, atol=tol, check_categorical=False, check_freq=False)
        except AssertionError as ex:
            _fail(expected, got, (msg + "\n" if msg else "") + _first_lines(ex))
        return
    if pd is not None and isinstance(got, (pd.DataFrame, pd.Series)):
        _fail(expected, got, msg or f"Unexpected type: {type(got).__name__} (expected: {type(expected).__name__}).")
    if not _eq(got, expected, tol):
        _fail(expected, got, msg)


# ---------------------------------------------------------------- python execution
def _fresh_ns() -> dict[str, Any]:
    ns: dict[str, Any] = {"__name__": "__main__", "assert_eq": assert_eq}
    pd, np = _pd(), _np()
    if pd is not None:
        ns["pd"] = pd
    if np is not None:
        ns["np"] = np
    return ns


def _exec(src: str, ns: dict[str, Any], filename: str) -> None:
    linecache.cache[filename] = (len(src), None, src.splitlines(True), filename)
    exec(compile(src, filename, "exec"), ns)


def _format_tb(exc: BaseException, keep: tuple[str, ...] = (USER_FILE, TEST_FILE, SETUP_FILE, CALL_FILE)) -> str:
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename in keep]
    parts = []
    if frames:
        parts.append("Traceback (your code):\n")
        parts.extend(traceback.format_list(frames))
    parts.extend(traceback.format_exception_only(type(exc), exc))
    return "".join(parts).rstrip()


def run_python(setup: str, code: str, mode: str, tests: list[Json] | None = None,
               run_call: str | None = None) -> Json:
    if mode == "run":
        ns, buf = _fresh_ns(), io.StringIO()
        error: str | None = None
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                _exec(setup or "", ns, SETUP_FILE)
            except Exception as exc:
                return {"output": buf.getvalue(),
                        "error": "Error in the exercise setup (not in your code):\n" + _format_tb(exc)}
            try:
                _exec(code, ns, USER_FILE)
                if run_call:
                    linecache.cache[CALL_FILE] = (len(run_call), None, [run_call], CALL_FILE)
                    val = eval(compile(run_call, CALL_FILE, "eval"), ns)
                    print(f">>> {run_call}\n{display(val)}")
            except Exception as exc:
                error = _format_tb(exc)
        return {"output": buf.getvalue(), "error": error}

    results: list[Json] = []
    for t in tests or []:
        ns, buf = _fresh_ns(), io.StringIO()
        ok, message = False, ""
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                _exec(setup or "", ns, SETUP_FILE)
                _exec(code, ns, USER_FILE)
                _exec(t.get("code", ""), ns, TEST_FILE)
                ok = True
            except CheckError as exc:
                message = str(exc)
            except Exception as exc:
                message = "Exception raised:\n" + _format_tb(exc)
        results.append({"name": t.get("name", "test"), "ok": ok, "message": message,
                        "stdout": buf.getvalue()[-2000:]})
    return {"ok": bool(results) and all(r["ok"] for r in results), "tests": results}


# ---------------------------------------------------------------- sql execution
def _sql_exec(setup: str, query: str) -> tuple[list[str], list[list[Any]]]:
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(setup or "")
        q = (query or "").strip().rstrip(";").strip()
        if not q:
            raise ValueError("Empty query.")
        cur = con.execute(q)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchall()]
        return cols, rows
    finally:
        con.close()


def _cell(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v)


def format_table(cols: list[str], rows: list[list[Any]], max_rows: int = MAX_ROWS) -> str:
    n = max([len(cols)] + [len(r) for r in rows]) if (cols or rows) else 0
    if n == 0:
        return "(no columns / no rows)"
    cols = list(cols) + ["?"] * (n - len(cols))
    data = [[_cell(v) for v in r] + [""] * (n - len(r)) for r in rows[:max_rows]]
    widths = [max([len(cols[i])] + [len(r[i]) for r in data]) for i in range(n)]
    head = "  ".join(cols[i].ljust(widths[i]) for i in range(n))
    sep = "  ".join("-" * w for w in widths)
    body = "\n".join("  ".join(r[i].ljust(widths[i]) for i in range(n)) for r in data)
    extra = f"\n… ({len(rows) - max_rows} more row(s))" if len(rows) > max_rows else ""
    return f"{head}\n{sep}\n{body}{extra}\n({len(rows)} row(s))"


def _row_key(row: list[Any]) -> str:
    return json.dumps(row, default=str)


def run_sql(setup: str, query: str, mode: str, tests: list[Json] | None = None) -> Json:
    if mode == "run":
        try:
            cols, rows = _sql_exec(setup, query)
        except Exception as exc:
            return {"output": "", "error": f"{type(exc).__name__}: {exc}"}
        return {"output": format_table(cols, rows), "error": None}

    results: list[Json] = []
    for t in tests or []:
        ok, message = False, ""
        try:
            cols, rows = _sql_exec(t.get("setup", setup), query)
            exp_rows = [list(r) for r in t["expected"]]
            exp_cols = t.get("columns")
            ordered = t.get("ordered", True)
            problems = []
            if exp_cols and [c.lower() for c in cols] != [c.lower() for c in exp_cols]:
                problems.append(f"Expected columns: {exp_cols}\nGot columns:      {cols}")
            g, e = rows, exp_rows
            if not ordered:
                g, e = sorted(g, key=_row_key), sorted(e, key=_row_key)
            if len(g) != len(e):
                problems.append(f"Row count: expected {len(e)}, got {len(g)}.")
            elif not all(_eq(a, b, 1e-6) for a, b in zip(g, e)):
                problems.append("Different rows" + ("" if ordered else " (order ignored)") + ".")
            if problems:
                message = ("\n".join(problems) + "\n\nExpected:\n" + format_table(exp_cols or cols, exp_rows)
                           + "\n\nGot:\n" + format_table(cols, rows))
            else:
                ok = True
        except Exception as exc:
            message = f"SQL error: {type(exc).__name__}: {exc}"
        results.append({"name": t.get("name", "test"), "ok": ok, "message": message, "stdout": ""})
    return {"ok": bool(results) and all(r["ok"] for r in results), "tests": results}


# ---------------------------------------------------------------- entry point
def run(payload: Json) -> Json:
    mode = payload.get("mode", "run")
    if payload.get("language") == "sql":
        return run_sql(payload.get("setup", ""), payload.get("code", ""), mode, payload.get("tests") or [])
    return run_python(payload.get("setup", ""), payload.get("code", ""), mode,
                      payload.get("tests") or [], payload.get("run_call"))


def run_json(payload_json: str) -> str:
    try:
        res = run(json.loads(payload_json))
    except Exception as exc:
        res = {"output": "", "ok": False, "tests": [],
               "error": "Harness internal error:\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))}
    return json.dumps(res, default=str)
