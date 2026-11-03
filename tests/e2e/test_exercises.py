"""Exercise tab: the bank's own solutions pass their tests in the browser (Pyodide for Python, sqlite3 for SQL)."""
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


def test_python_solution_passes_every_test(ready_page, exercises):
    page = ready_page
    page.select_option("#f-language", "python")
    page.click('#ex-list li[data-i="0"]')
    ex = check_current_exercise(page, exercises)
    assert ex["language"] == "python"
    expect(page.locator("#ex-list li.active .st-ok")).to_have_count(1)


def test_sql_solution_passes_every_test(ready_page, exercises):
    if not any(ex["language"] == "sql" for ex in exercises.values()):
        pytest.skip("no SQL exercise in the bank")
    page = ready_page
    page.select_option("#f-language", "sql")
    page.click('#ex-list li[data-i="0"]')
    ex = check_current_exercise(page, exercises)
    assert ex["language"] == "sql"
