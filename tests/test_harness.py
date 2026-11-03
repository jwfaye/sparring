"""Tests of app/py/harness.py, the execution harness shared by the browser and the bank checkers."""

import json
import math

import numpy as np
import pandas as pd
import pytest


def run(harness, **payload):
    return json.loads(harness.run_json(json.dumps(payload)))


class TestPythonRunMode:
    def test_setup_and_code_share_a_namespace(self, harness):
        res = run(harness, mode="run", language="python", setup="x = 1", code="print(x + 1)")
        assert res == {"output": "2\n", "error": None}

    def test_run_call_is_evaluated_and_displayed(self, harness):
        res = run(harness, mode="run", language="python", setup="", code="def f():\n    return [1, 2]", run_call="f()")
        assert res["error"] is None
        assert ">>> f()\n[1, 2]" in res["output"]

    def test_user_error_keeps_only_user_frames(self, harness):
        res = run(harness, mode="run", language="python", setup="", code="y = 1\nz = 1 / 0")
        assert res["error"].startswith("Traceback (your code):")
        assert harness.USER_FILE in res["error"]
        assert "line 2" in res["error"]
        assert "ZeroDivisionError" in res["error"]
        assert "harness.py" not in res["error"]

    def test_run_call_error_points_to_the_call(self, harness):
        res = run(
            harness, mode="run", language="python", setup="", code="def f():\n    raise KeyError('k')", run_call="f()"
        )
        assert harness.CALL_FILE in res["error"]
        assert "KeyError" in res["error"]

    def test_setup_error_is_reported_as_such(self, harness):
        res = run(harness, mode="run", language="python", setup="raise ValueError('boom')", code="print(1)")
        assert res["error"].startswith("Error in the exercise setup (not in your code):")
        assert "boom" in res["error"]

    def test_stderr_is_captured_with_stdout(self, harness):
        res = run(harness, mode="run", language="python", setup="", code="import sys\nsys.stderr.write('warn')")
        assert res["output"] == "warn"


class TestPythonCheckMode:
    def test_every_test_runs_in_a_fresh_namespace(self, harness):
        tests = [
            {"name": "a", "code": "x = 5\nassert_eq(f(), 3)"},
            {"name": "b", "code": "assert 'x' not in dir()\nassert_eq(f(), 3)"},
        ]
        res = run(harness, mode="check", language="python", setup="", code="def f():\n    return 3", tests=tests)
        assert res["ok"] is True
        assert [t["ok"] for t in res["tests"]] == [True, True]

    def test_failed_assertion_message(self, harness):
        tests = [{"name": "value", "code": "assert_eq(f(), 4, 'wrong value')"}]
        res = run(harness, mode="check", language="python", setup="", code="def f():\n    return 3", tests=tests)
        assert res["ok"] is False
        message = res["tests"][0]["message"]
        assert message.startswith("wrong value")
        assert "Expected:\n4  [int]" in message
        assert "Got:\n3  [int]" in message

    def test_exception_in_user_code_is_reported_with_stdout(self, harness):
        tests = [{"name": "t", "code": "f()"}]
        res = run(
            harness,
            mode="check",
            language="python",
            setup="",
            code="def f():\n    print('before')\n    raise RuntimeError('x')",
            tests=tests,
        )
        test = res["tests"][0]
        assert test["ok"] is False
        assert test["message"].startswith("Exception raised:")
        assert "RuntimeError: x" in test["message"]
        assert test["stdout"] == "before\n"

    def test_no_tests_means_not_ok(self, harness):
        res = run(harness, mode="check", language="python", setup="", code="", tests=[])
        assert res == {"ok": False, "tests": []}

    def test_pandas_is_available_in_the_namespace(self, harness):
        tests = [{"name": "t", "code": "assert_eq(solve(df), pd.Series([1, 2], name='a'))"}]
        res = run(
            harness,
            mode="check",
            language="python",
            setup="df = pd.DataFrame({'a': [1, 2]})",
            code="def solve(df):\n    return df['a']",
            tests=tests,
        )
        assert res["ok"] is True


class TestAssertEq:
    def test_scalars_are_compared_with_tolerance(self, harness):
        harness.assert_eq(1.0000001, 1.0)
        harness.assert_eq(np.float64(2.5), 2.5)
        with pytest.raises(harness.CheckError):
            harness.assert_eq(1.1, 1.0)

    def test_nan_and_none_are_equal(self, harness):
        harness.assert_eq(float("nan"), math.nan)
        harness.assert_eq(None, float("nan"))
        harness.assert_eq(np.nan, None)

    def test_booleans_are_not_integers(self, harness):
        with pytest.raises(harness.CheckError):
            harness.assert_eq(True, 1)
        harness.assert_eq(True, True)

    def test_containers_are_compared_recursively(self, harness):
        harness.assert_eq([1, (2.0, {"a": 3.0000001})], [1, (2, {"a": 3})])
        harness.assert_eq({1, 2}, {2, 1})
        with pytest.raises(harness.CheckError):
            harness.assert_eq([1, 2], [1, 2, 3])
        with pytest.raises(harness.CheckError):
            harness.assert_eq({"a": 1}, {"b": 1})

    def test_numpy_arrays(self, harness):
        harness.assert_eq(np.array([1.0, np.nan]), np.array([1.0, np.nan]))
        harness.assert_eq([1, 2], np.array([1, 2]))
        with pytest.raises(harness.CheckError):
            harness.assert_eq(np.array([1, 2]), np.array([1, 2, 3]))

    def test_dataframe_equal_regardless_of_dtype(self, harness):
        got = pd.DataFrame({"a": [1, 2], "b": [1.0, 2.0]})
        expected = pd.DataFrame({"a": [1.0, 2.0], "b": [1, 2]})
        harness.assert_eq(got, expected)

    def test_dataframe_column_mismatch_message(self, harness):
        got = pd.DataFrame({"b": [1], "a": [2]})
        expected = pd.DataFrame({"a": [2], "b": [1]})
        with pytest.raises(harness.CheckError) as info:
            harness.assert_eq(got, expected)
        assert "Different columns." in str(info.value)
        assert "Expected: ['a', 'b']" in str(info.value)

    def test_dataframe_ignore_order_and_index(self, harness):
        expected = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        shuffled = expected.iloc[[1, 0]]
        with pytest.raises(harness.CheckError):
            harness.assert_eq(shuffled, expected)
        harness.assert_eq(shuffled, expected, ignore_order=True)
        reindexed = expected.set_axis([10, 20])
        with pytest.raises(harness.CheckError):
            harness.assert_eq(reindexed, expected)
        harness.assert_eq(reindexed, expected, ignore_index=True)

    def test_dataframe_value_mismatch_includes_pandas_diagnosis(self, harness):
        got = pd.DataFrame({"a": [1, 2]})
        expected = pd.DataFrame({"a": [1, 3]})
        with pytest.raises(harness.CheckError) as info:
            harness.assert_eq(got, expected, "values differ")
        text = str(info.value)
        assert text.startswith("values differ")
        assert "DataFrame shape=(2, 1)" in text

    def test_series_rules(self, harness):
        expected = pd.Series([1, 2], index=["a", "b"], name="n")
        harness.assert_eq(pd.Series([1.0, 2.0], index=["a", "b"]), expected)
        harness.assert_eq(pd.Series([2, 1], index=["b", "a"]), expected, ignore_order=True)
        harness.assert_eq(pd.Series([1, 2], index=[5, 6]), expected, ignore_index=True)
        with pytest.raises(harness.CheckError):
            harness.assert_eq(pd.Series([2, 1], index=["a", "b"]), expected)

    def test_type_mismatches_have_explicit_messages(self, harness):
        with pytest.raises(harness.CheckError, match="A DataFrame is expected, not list"):
            harness.assert_eq([1], pd.DataFrame({"a": [1]}))
        with pytest.raises(harness.CheckError, match="A Series is expected, not int"):
            harness.assert_eq(1, pd.Series([1]))
        with pytest.raises(harness.CheckError, match="Unexpected type: DataFrame"):
            harness.assert_eq(pd.DataFrame({"a": [1]}), [1])


class TestSql:
    SETUP = "CREATE TABLE t(a INT, b TEXT); INSERT INTO t VALUES (1, 'x'), (2, 'y');"

    def test_run_mode_formats_a_table(self, harness):
        res = run(harness, mode="run", language="sql", setup=self.SETUP, code="SELECT a, b FROM t ORDER BY a;")
        assert res["error"] is None
        lines = res["output"].splitlines()
        assert lines[0].split() == ["a", "b"]
        assert lines[2].split() == ["1", "x"]
        assert lines[-1] == "(2 row(s))"

    def test_run_mode_reports_sql_errors(self, harness):
        res = run(harness, mode="run", language="sql", setup=self.SETUP, code="SELECT nope FROM t")
        assert res["output"] == ""
        assert res["error"].startswith("OperationalError:")

    def test_empty_query(self, harness):
        res = run(harness, mode="run", language="sql", setup=self.SETUP, code="  ;  ")
        assert res["error"] == "ValueError: Empty query."

    def test_check_ordered_and_unordered(self, harness):
        tests = [
            {"name": "ordered", "expected": [[1, "x"], [2, "y"]]},
            {"name": "unordered", "expected": [[2, "y"], [1, "x"]], "ordered": False},
        ]
        res = run(
            harness, mode="check", language="sql", setup=self.SETUP, code="SELECT a, b FROM t ORDER BY a", tests=tests
        )
        assert res["ok"] is True

    def test_check_detects_row_differences(self, harness):
        tests = [
            {"name": "swapped", "expected": [[2, "y"], [1, "x"]]},
            {"name": "count", "expected": [[1, "x"]]},
            {"name": "columns", "expected": [[1, "x"], [2, "y"]], "columns": ["A", "c"]},
        ]
        res = run(
            harness, mode="check", language="sql", setup=self.SETUP, code="SELECT a, b FROM t ORDER BY a", tests=tests
        )
        messages = {t["name"]: t["message"] for t in res["tests"]}
        assert res["ok"] is False
        assert messages["swapped"].startswith("Different rows.")
        assert messages["count"].startswith("Row count: expected 1, got 2.")
        assert messages["columns"].startswith("Expected columns: ['A', 'c']")
        assert "Expected:" in messages["swapped"] and "Got:" in messages["swapped"]

    def test_check_uses_the_test_setup_when_given(self, harness):
        tests = [{"name": "other data", "setup": "CREATE TABLE t(a INT); INSERT INTO t VALUES (9);", "expected": [[9]]}]
        res = run(harness, mode="check", language="sql", setup=self.SETUP, code="SELECT a FROM t", tests=tests)
        assert res["ok"] is True

    def test_check_reports_sql_errors(self, harness):
        res = run(
            harness,
            mode="check",
            language="sql",
            setup=self.SETUP,
            code="SELECT zz FROM t",
            tests=[{"name": "t", "expected": []}],
        )
        assert res["tests"][0]["message"].startswith("SQL error: OperationalError:")

    def test_null_and_float_cells(self, harness):
        cells = [line.strip() for line in harness.format_table(["a"], [[None], [0.1 + 0.2]]).splitlines()[2:4]]
        assert cells == ["NULL", "0.3"]

    def test_format_table_edge_cases(self, harness):
        assert harness.format_table([], []) == "(no columns / no rows)"
        many = harness.format_table(["n"], [[i] for i in range(harness.MAX_ROWS + 5)])
        assert f"({harness.MAX_ROWS + 5} row(s))" in many
        assert "5 more row(s)" in many


class TestEntryPoint:
    def test_default_mode_is_python_run(self, harness):
        assert run(harness, code="print('hi')") == {"output": "hi\n", "error": None}

    def test_internal_errors_never_raise(self, harness):
        res = json.loads(harness.run_json("not json"))
        assert res["ok"] is False
        assert res["error"].startswith("Harness internal error:")

    def test_display_truncates_long_values(self, harness):
        text = harness.display("x" * (harness.MAX_REPR + 10))
        assert len(text) <= harness.MAX_REPR + 2
        assert text.endswith("…")
