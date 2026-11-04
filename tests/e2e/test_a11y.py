"""Accessibility: axe-core finds no serious or critical violation on any screen, in both themes (SP-A11Y).

axe is injected from `node_modules/axe-core/axe.min.js` (`npm ci` installs it), in a browser context created with
`bypass_csp=True` because the page's Content-Security-Policy only allows scripts from its own origin and the pinned
CDNs; the other modules keep the normal context. Moderate and minor findings do not fail the suite: they are
reported as a pytest warning so they stay visible in the run summary.
"""

import os
import re
import warnings

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.e2e

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AXE = os.path.join(ROOT, "node_modules", "axe-core", "axe.min.js")
MODES = ("exercises", "qcm", "theory")
SCREENS = (
    "setup-exercises",
    "setup-qcm",
    "setup-theory",
    "exercises",
    "qcm",
    "theory",
    "recap",
    "qcm-history",
    "theory-history",
)
THEMES = ("light", "dark")
BLOCKING = ("serious", "critical")


@pytest.fixture(scope="module")
def axe_page(browser, base_url, app_url, pyodide_timeout):
    """One page with axe injected, Pyodide loaded and the banks rendered, in a context that bypasses the CSP."""
    if not os.path.exists(AXE):
        pytest.skip("axe-core is not installed: run npm ci")
    context = browser.new_context(base_url=base_url, bypass_csp=True)
    page = context.new_page()
    page.goto(app_url)
    expect(page.locator("#py-status")).to_have_text("Python ready", timeout=pyodide_timeout)
    expect(page.locator("#view-setup")).to_be_visible()
    expect(page.locator("#qcm-themes label.chip").first).to_be_attached()
    expect(page.locator("#th-sections input").first).to_be_attached()
    page.add_script_tag(path=AXE)
    yield page
    page.evaluate("localStorage.removeItem('tt.theme')")
    context.close()


def show(page, screen, setup_screen, start):
    """Bring the page to one of SCREENS through the setup screen."""
    if screen.startswith("setup-"):
        setup_screen(page)
        page.click(f'.tab[data-mode="{screen.removeprefix("setup-")}"]')
        expect(page.locator(f"#{screen}")).to_be_visible()
    elif screen in MODES:
        start(page, screen)
    elif screen == "recap":
        setup_screen(page)
        page.click("#btn-recap")
        expect(page.locator("#view-recap")).to_be_visible()
    else:
        mode = screen.removesuffix("-history")
        setup_screen(page)
        page.click("#btn-qcm-history" if mode == "qcm" else "#btn-th-history")
        expect(page.locator("#qcm-home" if mode == "qcm" else "#th-home")).to_be_visible()


def run_axe(page, screen, theme, setup_screen, start):
    page.evaluate("t => { document.documentElement.dataset.theme = t; }", theme)
    show(page, screen, setup_screen, start)
    result = page.evaluate("axe.run(document, { resultTypes: ['violations'] })")
    return [
        f"{v['impact']} {v['id']}: {', '.join(node['target'][0] for node in v['nodes'])}" for v in result["violations"]
    ]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("screen", SCREENS)
def test_no_serious_or_critical_violation(axe_page, screen, theme, setup_screen, start):
    findings = run_axe(axe_page, screen, theme, setup_screen, start)
    blocking = [line for line in findings if line.startswith(BLOCKING)]
    assert blocking == [], "\n".join(findings)
    if findings:
        warnings.warn(f"axe ({screen}, {theme}), not blocking: " + "; ".join(findings), stacklevel=1)


def test_tabs_follow_the_aria_tab_pattern(axe_page, setup_screen):
    page = axe_page
    setup_screen(page)
    tabs = page.locator('[role="tablist"] [role="tab"]')
    expect(tabs).to_have_count(len(MODES))
    for mode in MODES:
        tab = page.locator(f'[role="tab"][data-mode="{mode}"]')
        expect(tab).to_have_attribute("aria-controls", f"setup-{mode}")
        expect(page.locator(f"#setup-{mode}")).to_have_attribute("role", "tabpanel")
        expect(page.locator(f"#setup-{mode}")).to_have_attribute("aria-labelledby", f"tab-{mode}")
    page.click('.tab[data-mode="exercises"]')
    expect(page.locator('.tab[data-mode="exercises"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator('.tab[data-mode="qcm"]')).to_have_attribute("aria-selected", "false")
    expect(page.locator('.tab[data-mode="qcm"]')).to_have_attribute("tabindex", "-1")
    page.focus('.tab[data-mode="exercises"]')
    page.keyboard.press("ArrowRight")
    expect(page.locator('.tab[data-mode="qcm"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator("#setup-qcm")).to_be_visible()
    expect(page.locator("#setup-exercises")).to_be_hidden()
    assert page.evaluate("document.activeElement.dataset.mode") == "qcm"
    page.keyboard.press("End")
    expect(page.locator("#setup-theory")).to_be_visible()
    page.keyboard.press("ArrowRight")
    expect(page.locator("#setup-exercises")).to_be_visible()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("#setup-theory")).to_be_visible()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("#setup-qcm")).to_be_visible()
    page.keyboard.press("Home")
    expect(page.locator("#setup-exercises")).to_be_visible()
    assert page.evaluate("document.activeElement.dataset.mode") == "exercises"


def test_theme_toggle_label_reflects_the_state(axe_page):
    page = axe_page
    page.evaluate("document.documentElement.dataset.theme = 'light'")
    page.click("#theme-toggle")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#theme-toggle")).to_have_attribute("aria-label", "Switch to light theme")
    page.click("#theme-toggle")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(page.locator("#theme-toggle")).to_have_attribute("aria-label", "Switch to dark theme")


def test_escape_then_tab_leaves_the_code_editor(axe_page, start):
    page = axe_page
    start(page, "exercises")
    page.click(".CodeMirror")
    assert page.evaluate("document.activeElement.closest('.CodeMirror') !== null")
    page.keyboard.press("Escape")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.closest('.CodeMirror')") is None
    assert page.evaluate("document.activeElement.id") == "splitter"


def test_splitter_arrow_keys_resize_the_output_pane_within_bounds(axe_page, start):
    page = axe_page
    start(page, "exercises")
    page.focus("#splitter")
    height = "document.querySelector('#output-pane').getBoundingClientRect().height"
    page.keyboard.press("ArrowUp")
    expect(page.locator("#output-pane")).not_to_have_class(re.compile(r"\bcollapsed\b"))
    before = page.evaluate(height)
    page.keyboard.press("ArrowUp")
    after = page.evaluate(height)
    assert after == pytest.approx(before + 20, abs=1)
    expect(page.locator("#splitter")).to_have_attribute("aria-valuenow", str(round(after)))
    page.keyboard.press("ArrowDown")
    assert page.evaluate(height) == pytest.approx(before, abs=1)
    for _ in range(30):
        page.keyboard.press("ArrowDown")
    assert page.evaluate(height) == pytest.approx(60, abs=1)
    expect(page.locator("#splitter")).to_have_attribute("aria-valuenow", "60")
