"""Setup screen first, then a training screen without configuration controls (SP-SETUP)."""

import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.e2e

MODES = ("exercises", "qcm", "theory")
CONTROLS = "select, input, .chip, [role='tablist']"


def test_page_opens_on_the_setup_screen_and_remembers_the_last_setup(page, app_url):
    page.goto(app_url)
    expect(page.locator("#view-setup")).to_be_visible()
    for mode in MODES:
        expect(page.locator(f"#view-{mode}")).to_be_hidden()
    expect(page.locator("#setup-exercises")).to_be_visible()
    page.select_option("#f-difficulty", "easy")
    page.click('.tab[data-mode="qcm"]')
    expect(page.locator("#setup-qcm")).to_be_visible()
    page.uncheck("#qcm-prioritize")
    page.select_option("#qcm-n", "20")
    page.check("#exam-enabled")
    page.fill("#exam-minutes", "30")
    page.locator("#exam-minutes").dispatch_event("change")
    page.click("#btn-start")
    expect(page.locator("#view-qcm")).to_be_visible()
    page.goto(app_url)
    expect(page.locator("#view-setup")).to_be_visible()
    expect(page.locator("#setup-qcm")).to_be_visible()
    expect(page.locator('.tab[data-mode="qcm"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator("#qcm-prioritize")).not_to_be_checked()
    expect(page.locator("#qcm-n")).to_have_value("20")
    expect(page.locator("#f-difficulty")).to_have_value("easy")
    expect(page.locator("#exam-minutes")).to_have_value("30")
    page.evaluate("localStorage.clear()")


@pytest.mark.parametrize("mode", MODES)
def test_training_screens_show_no_configuration_controls(ready_page, start, mode):
    page = ready_page
    start(page, mode)
    expect(page.locator("#view-setup")).to_be_hidden()
    expect(page.locator("#mode-label")).not_to_be_empty()
    for scope in ("header", f"#view-{mode}"):
        visible = page.locator(f"{scope} :is({CONTROLS})").evaluate_all(
            "els => els.filter(el => el.getClientRects().length > 0).map(el => el.id || el.className)"
        )
        assert visible == [], f"{scope} shows {visible}"
    expect(page.locator("#exam-clock")).to_be_hidden()
    expect(page.locator("#btn-setup")).to_be_visible()
    page.click("#btn-setup")
    expect(page.locator("#view-setup")).to_be_visible()
    expect(page.locator(f"#view-{mode}")).to_be_hidden()


def test_exam_countdown_shows_the_clock_only_when_set(ready_page, setup_screen, start):
    page = ready_page
    setup_screen(page)
    page.uncheck("#exam-enabled")
    start(page, "exercises")
    expect(page.locator("#exam-clock")).to_be_hidden()
    setup_screen(page)
    page.check("#exam-enabled")
    page.fill("#exam-minutes", "10")
    page.locator("#exam-minutes").dispatch_event("change")
    start(page, "exercises")
    clock = page.locator("#exam-clock")
    expect(clock).to_be_visible()
    expect(clock).to_have_text(re.compile(r"^(10:00|9:[0-5]\d)$"))
    setup_screen(page)
    expect(page.locator("#exam-running")).to_contain_text("Exam in progress")
    expect(page.locator("#exam-enabled")).to_be_hidden()
    page.click("#exam-toggle")
    expect(clock).to_be_hidden()
    expect(page.locator("#exam-enabled")).to_be_visible()
    page.uncheck("#exam-enabled")


def test_history_and_summary_open_from_the_setup_screen(ready_page, setup_screen):
    page = ready_page
    setup_screen(page)
    page.click("#btn-recap")
    expect(page.locator("#view-recap")).to_be_visible()
    expect(page.locator("#recap-summary .card").first).to_be_visible()
    setup_screen(page)
    page.click("#btn-qcm-history")
    expect(page.locator("#qcm-home")).to_be_visible()
    expect(page.locator("#qcm-quiz")).to_be_hidden()
    setup_screen(page)
    page.click("#btn-th-history")
    expect(page.locator("#th-home")).to_be_visible()
    expect(page.locator("#th-question")).to_be_hidden()
    setup_screen(page)


def test_start_with_an_empty_selection_keeps_the_setup_screen(ready_page, setup_screen):
    page = ready_page
    setup_screen(page)
    page.click('.tab[data-mode="qcm"]')
    expect(page.locator("#qcm-themes input").first).to_be_checked()
    page.click("#qcm-all")
    expect(page.locator("#qcm-themes input:checked")).to_have_count(0)
    page.check("#exam-enabled")
    page.click("#btn-start")
    expect(page.locator("#view-setup")).to_be_visible()
    expect(page.locator("#qcm-msg")).to_have_text("No question for this selection.")
    expect(page.locator("#exam-clock")).to_be_hidden()
    expect(page.locator("#exam-running")).to_be_hidden()
    page.uncheck("#exam-enabled")
    page.click("#qcm-all")
    expect(page.locator("#qcm-themes input:not(:checked)")).to_have_count(0)
