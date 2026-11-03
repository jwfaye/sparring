"""Quiz mode: start a session from the setup screen and answer with the keyboard."""

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
