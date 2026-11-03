"""The page boots cleanly and the theme toggle works."""

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.e2e


def test_page_loads_without_console_errors_or_failed_requests(ready_page):
    page = ready_page
    page.wait_for_load_state("networkidle")
    expect(page.locator("#ex-list li[data-i]").first).to_be_visible()
    expect(page.locator("#qcm-themes label.chip").first).to_be_attached()
    expect(page.locator("#th-status")).to_contain_text("Offline mode")
    assert page.log.console_errors == []
    assert page.log.failed_requests == []


def test_theme_toggle_flips_the_root_attribute(page, app_url):
    page.goto(app_url)
    before = page.evaluate("window.TT.currentTheme()")
    after = "light" if before == "dark" else "dark"
    page.click("#theme-toggle")
    expect(page.locator("html")).to_have_attribute("data-theme", after)
    expect(page.locator("#theme-toggle")).to_have_text("Light" if after == "dark" else "Dark")
    page.click("#theme-toggle")
    expect(page.locator("html")).to_have_attribute("data-theme", before)
