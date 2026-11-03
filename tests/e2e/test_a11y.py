"""Accessibility: axe-core finds no serious or critical violation on any tab, in both themes (SP-A11Y).

axe is injected from `node_modules/axe-core/axe.min.js` (`npm ci` installs it), in a browser context created with
`bypass_csp=True` because the page's Content-Security-Policy only allows scripts from its own origin and the pinned
CDNs; the other modules keep the normal context. Moderate and minor findings do not fail the suite: they are
reported as a pytest warning so they stay visible in the run summary.
"""
import os
import warnings

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.e2e

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AXE = os.path.join(ROOT, "node_modules", "axe-core", "axe.min.js")
TABS = ("exercises", "qcm", "theory", "recap")
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
    expect(page.locator("#ex-list li[data-i]").first).to_be_visible()
    expect(page.locator("#qcm-themes label.chip").first).to_be_attached()
    expect(page.locator("#th-sections input").first).to_be_attached()
    page.add_script_tag(path=AXE)
    yield page
    page.evaluate("localStorage.removeItem('tt.theme')")
    context.close()


def run_axe(page, tab, theme):
    page.evaluate("t => { document.documentElement.dataset.theme = t; }", theme)
    page.click(f'.tab[data-view="{tab}"]')
    expect(page.locator(f"#view-{tab}")).to_be_visible()
    result = page.evaluate("axe.run(document, { resultTypes: ['violations'] })")
    return [
        f"{v['impact']} {v['id']}: {', '.join(node['target'][0] for node in v['nodes'])}"
        for v in result["violations"]
    ]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("tab", TABS)
def test_no_serious_or_critical_violation(axe_page, tab, theme):
    findings = run_axe(axe_page, tab, theme)
    blocking = [line for line in findings if line.startswith(BLOCKING)]
    assert blocking == [], "\n".join(findings)
    if findings:
        warnings.warn(f"axe ({tab}, {theme}), not blocking: " + "; ".join(findings), stacklevel=1)


def test_tabs_follow_the_aria_tab_pattern(axe_page):
    page = axe_page
    tabs = page.locator('[role="tablist"] [role="tab"]')
    expect(tabs).to_have_count(len(TABS))
    for view in TABS:
        tab = page.locator(f'[role="tab"][data-view="{view}"]')
        expect(tab).to_have_attribute("aria-controls", f"view-{view}")
        expect(page.locator(f"#view-{view}")).to_have_attribute("role", "tabpanel")
        expect(page.locator(f"#view-{view}")).to_have_attribute("aria-labelledby", f"tab-{view}")
    page.click('.tab[data-view="exercises"]')
    expect(page.locator('.tab[data-view="exercises"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator('.tab[data-view="qcm"]')).to_have_attribute("aria-selected", "false")
    expect(page.locator('.tab[data-view="qcm"]')).to_have_attribute("tabindex", "-1")
    page.focus('.tab[data-view="exercises"]')
    page.keyboard.press("ArrowRight")
    expect(page.locator('.tab[data-view="qcm"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator("#view-qcm")).to_be_visible()
    expect(page.locator("#view-exercises")).to_be_hidden()
    assert page.evaluate("document.activeElement.dataset.view") == "qcm"
    page.keyboard.press("End")
    expect(page.locator("#view-recap")).to_be_visible()
    page.keyboard.press("ArrowRight")
    expect(page.locator("#view-exercises")).to_be_visible()


def test_theme_toggle_label_reflects_the_state(axe_page):
    page = axe_page
    page.evaluate("document.documentElement.dataset.theme = 'light'")
    page.click("#theme-toggle")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#theme-toggle")).to_have_attribute("aria-label", "Switch to light theme")
    page.click("#theme-toggle")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(page.locator("#theme-toggle")).to_have_attribute("aria-label", "Switch to dark theme")


def test_escape_then_tab_leaves_the_code_editor(axe_page):
    page = axe_page
    page.click('.tab[data-view="exercises"]')
    page.click(".CodeMirror")
    assert page.evaluate("document.activeElement.closest('.CodeMirror') !== null")
    page.keyboard.press("Escape")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.closest('.CodeMirror')") is None
    assert page.evaluate("document.activeElement.id") == "splitter"
