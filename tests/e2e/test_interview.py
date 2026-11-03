"""Interview mode: answer a question in offline mode and find it on the history page."""

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.e2e

ANSWER = (
    "Overfitting: the model fits the noise of the training set, so the training error keeps dropping while the "
    "validation error rises. Regularize, get more data or simplify the model."
)


def history(page, profile):
    return page.request.get(f"/api/theory/history?profile={profile}").json()["items"]


def test_offline_answer_is_saved_in_the_history(page, app_url, profile, start):
    page.goto(app_url)
    before = len(history(page, profile))
    page.click('.tab[data-mode="theory"]')
    expect(page.locator("#th-status")).to_contain_text("Offline mode")
    expect(page.locator("#th-sections input").first).to_be_attached()
    start(page, "theory")
    expect(page.locator("#th-question")).to_be_visible()
    question = page.locator("#th-q-fr").inner_text()
    assert question
    page.fill("#th-answer", ANSWER)
    expect(page.locator("#th-submit")).to_have_text("Save (deferred grading)")
    page.click("#th-submit")
    expect(page.locator("#th-result")).to_contain_text("Answer saved (offline mode)")
    expect(page.locator("#th-after")).to_be_visible()
    page.click("#th-back")
    expect(page.locator("#view-setup")).to_be_visible()
    page.click("#btn-th-history")
    expect(page.locator("#th-home")).to_be_visible()
    items = page.locator("#th-history li[data-id]")
    expect(items).to_have_count(before + 1)
    expect(items.first).to_contain_text(question)
    expect(items.first.locator(".score-pill")).to_have_text("pending")
    items.first.click()
    expect(page.locator("#th-question")).to_be_visible()
    expect(page.locator("#th-answer")).to_have_value(ANSWER)
    page.click("#th-back")
    expect(page.locator("#th-home")).to_be_visible()
    saved = history(page, profile)
    assert len(saved) == before + 1
    assert saved[-1]["answer"] == ANSWER
    assert saved[-1]["mode"] == "offline"
    assert saved[-1]["grade"] is None
