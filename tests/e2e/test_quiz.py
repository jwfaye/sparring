"""Quiz mode: start a session from the setup screen, answer with the keyboard, reach the result screen."""

import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.e2e


def test_answer_with_the_keyboard_shows_the_explanation(page, app_url, start):
    page.goto(app_url)
    expect(page.locator("#qcm-themes label.chip").first).to_be_attached()
    start(page, "qcm")
    expect(page.locator("#qcm-quiz")).to_be_visible()
    expect(page.locator("#qcm-progress")).to_have_text(re.compile(r"^Question 1 / \d+$"))
    choices = page.locator("#qcm-choices .choice")
    expect(choices).to_have_count(4)
    page.keyboard.press("1")
    feedback = page.locator("#qcm-feedback")
    expect(feedback).to_be_visible()
    expect(feedback.locator(".verdict-line")).to_have_text(re.compile(r"^(Correct|Wrong\. The right answer: .+)$"))
    expect(feedback.locator(".md")).not_to_be_empty()
    expect(page.locator("#qcm-choices .choice.correct")).to_have_count(1)
    expect(choices.first).to_be_disabled()
    expect(page.locator("#qcm-next")).to_be_visible()
    page.click("#qcm-quit")
    expect(page.locator("#view-setup")).to_be_visible()


def test_finishing_a_session_shows_the_result_and_back_returns_to_setup(page, app_url, start):
    page.goto(app_url)
    expect(page.locator("#qcm-themes label.chip").first).to_be_attached()
    page.click('.tab[data-mode="qcm"]')
    page.select_option("#qcm-n", "10")
    start(page, "qcm")
    for i in range(10):
        expect(page.locator("#qcm-progress")).to_have_text(f"Question {i + 1} / 10")
        page.keyboard.press("1")
        expect(page.locator("#qcm-feedback")).to_be_visible()
        expect(page.locator("#qcm-next")).to_have_text("Next" if i < 9 else "See the result")
        page.keyboard.press("Enter")
    expect(page.locator("#qcm-end")).to_be_visible()
    expect(page.locator("#qcm-score .big")).to_have_text(re.compile(r"^\d+ / 10$"))
    expect(page.locator("#qcm-end-themes tr")).not_to_have_count(0)
    page.click("#qcm-back")
    expect(page.locator("#view-setup")).to_be_visible()
    expect(page.locator("#view-qcm")).to_be_hidden()
    page.click("#btn-qcm-history")
    expect(page.locator("#qcm-sessions li").first).to_contain_text("/ 10")
