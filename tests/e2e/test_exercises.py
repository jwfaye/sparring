"""Exercises mode: the bank's own solutions pass their tests in the browser (Pyodide for Python, sqlite3 for SQL)."""

import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def exercises(ready_page):
    """The bank as the page sees it, fetched through the page's own request context."""
    data = ready_page.request.get("/api/exercises").json()
    return {ex["id"]: ex for ex in data["items"]}


def start_with_language(page, setup_screen, start, language):
    """Pick the language filter on the setup screen, start the exercises and open the first one of the list."""
    setup_screen(page)
    page.select_option("#f-language", language)
    start(page, "exercises")
    page.click('#ex-list li[data-i="0"]')


def check_current_exercise(page, exercises):
    ex = exercises[page.evaluate("window.tt.current.id")]
    page.evaluate("code => window.tt.editor.setValue(code)", ex["solution"])
    page.click("#btn-check")
    verdict = page.locator("#results .verdict")
    expect(verdict).to_have_class(re.compile(r"\bok\b"))
    n = len(ex["tests"])
    expect(verdict).to_have_text(f"OK · {n}/{n} test(s) passed")
    expect(page.locator("#results details.result.ok")).to_have_count(n)
    expect(page.locator("#results details.result.fail")).to_have_count(0)
    return ex


def test_python_solution_passes_every_test(ready_page, exercises, setup_screen, start):
    page = ready_page
    start_with_language(page, setup_screen, start, "python")
    ex = check_current_exercise(page, exercises)
    assert ex["language"] == "python"
    expect(page.locator("#ex-list li.active .st-ok")).to_have_count(1)


def test_sql_solution_passes_every_test(ready_page, exercises, setup_screen, start):
    if not any(ex["language"] == "sql" for ex in exercises.values()):
        pytest.skip("no SQL exercise in the bank")
    page = ready_page
    start_with_language(page, setup_screen, start, "sql")
    ex = check_current_exercise(page, exercises)
    assert ex["language"] == "sql"


def test_stop_interrupts_an_infinite_loop_and_python_keeps_working(ready_page, pyodide_timeout, setup_screen, start):
    page = ready_page
    assert page.evaluate("self.crossOriginIsolated") is True
    start_with_language(page, setup_screen, start, "python")
    page.evaluate("code => window.tt.editor.setValue(code)", "while True:\n    pass\n")
    page.click("#btn-run")
    expect(page.locator("#btn-stop")).to_be_enabled()
    expect(page.locator("#output")).to_have_text("Running…")
    page.click("#btn-stop")
    expect(page.locator("#output")).to_contain_text("Execution interrupted")
    expect(page.locator("#btn-stop")).to_be_disabled()
    expect(page.locator("#py-status")).to_have_text("Python ready", timeout=pyodide_timeout)
    page.evaluate("code => window.tt.editor.setValue(code)", "print('after stop')\n")
    page.click("#btn-run")
    expect(page.locator("#output")).to_contain_text("after stop")
