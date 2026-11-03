---
id: SP-A11Y
title: Accessibility of the web page
version: 0.1
status: approved
author: agent
created: 2026-11-03
updated: 2026-11-03

owns:
  code: [tests/e2e/test_a11y.py]
  resources: []

depends_on: [SP-WEB-QA]
provides_to: []

constraints:
  contrast_normal_text: 4.5
  contrast_large_text_and_ui: 3.0
  blocking_axe_impacts: [serious, critical]
---

# Accessibility of the web page

## Intent
Make the page operable with the keyboard alone and understandable with a screen reader, with text and controls
readable in both themes, and keep it that way with an automated audit. It exists because a training tool that only
works with a mouse and good eyesight excludes part of the candidates it is meant to help.

## Context
`app/index.html` had no `aria-` or `role` attribute: the tab bar was four plain buttons, the clickable exercise
list items were not focusable, the form controls had titles but no labels, the status pill and the result areas
changed silently, and the CodeMirror input had no accessible name. This component owns `tests/e2e/test_a11y.py`
and, in the shared files below, only the accessibility attributes and the focus styles:

- `app/index.html` (shared: SP-WEB-ASSETS owns its third-party asset tags, which keep their `integrity`
  attributes): landmarks, the tab pattern, labels, live regions, `tabindex` on scrollable code blocks.
- `app/css/style.css` (shared, frontier for the rest): the `:focus-visible` rules, the `.visually-hidden` utility,
  the tokens adjusted for contrast, the rules that style the new elements (`.tablist`, `.ex-item`,
  `.output-toggle`, `.views`).
- `app/js/common.js` (shared, frontier for the rest): `selectTab` (aria-selected and roving tabindex), the arrow-key
  handler of the tab list, the theme toggle's `aria-label`, the `tabindex` of the code blocks that `renderMd` emits.

The tab wiring of `app/js/app.js` calls `TT.selectTab`; `app.js`, `qcm.js` and `theory.js` (frontier) also carry
the attributes their rendered markup needs (exercise list buttons, `aria-expanded` on the disclosures,
`aria-valuenow` on the splitter, hidden header text in the tables, editor label and Escape binding). The runtime
section of `app.js` (SP-PY-RUNTIME) is untouched. The test uses the fixtures of SP-WEB-QA (`browser`, `base_url`,
`app_url`, `pyodide_timeout`) and the `axe-core` devDependency of `package.json` (owned by SP-WEB-QA, one line
added). Code-only: `resources: []`.

## Goals
- G1: landmarks (`header`, `nav`, one `main`, `footer`), one `h1` and a consistent heading hierarchy, every form
  control with a visible label or an `aria-label`, every button with text or an `aria-label` that contains its
  visible text.
- G2: the tab bar follows the WAI-ARIA tabs pattern: `role="tablist"`, `role="tab"` with `aria-selected`,
  `aria-controls` and a roving `tabindex`, panels with `role="tabpanel"` and `aria-labelledby`; Left, Right, Home
  and End move between tabs and select them; click and Tab/Enter keep working.
- G3: every interactive element is reachable with Tab and operable with Enter or Space (exercise list, output
  collapse, splitter with arrow keys), with a visible focus ring in both themes; no keyboard trap: Escape then Tab
  leaves the code editor.
- G4: the regions that change on their own announce it (`role="status"` on the Python status and the messages,
  `aria-live="polite"` on the run output, the check results, the quiz feedback and the interview result,
  `role="alert"` on the exam banner); the clocks are `role="timer"`, which is deliberately not live, so a screen
  reader is not interrupted every second.
- G5: text and UI colors reach WCAG AA in both themes (4.5:1 for normal text, 3:1 for large text and UI
  components), with the smallest token change that gets there.
- G6: `tests/e2e/test_a11y.py` runs axe-core on the four tabs in both themes and fails on any `serious` or
  `critical` violation; `moderate` and `minor` findings are reported as a warning.

## Non-Goals
- NG1: keyboard operation inside the CodeMirror editor beyond the Escape binding (Tab indents, as expected in a
  code editor).
- NG2: a screen-reader rendering of the syntax highlighting or of the progress bars (the numbers next to them carry
  the information).
- NG3: restyling the page: the focus ring, the three token changes and the dark-theme Check button are the only
  visible differences.
- NG4: `prefers-reduced-motion`: the stylesheet has no transition or animation and the scrolls are instant, so
  there is nothing to reduce.

## Assumptions
- A1: `npm ci` has run, so `node_modules/axe-core/axe.min.js` exists; the test skips with a message otherwise.
- A2: the page's Content-Security-Policy (`script-src 'self'` plus the pinned CDNs) blocks an injected script, so
  the test's context is created with `bypass_csp=True`; the other e2e modules keep the normal context.
- A3: `:has()` and `color-mix()` are supported by the browsers the app targets (every browser that runs Pyodide
  0.27 supports both).

## Interface
Inputs:
- `python -m pytest -q -m e2e tests/e2e/test_a11y.py`: the audit alone; it is part of the `e2e` suite and of the
  CI job `e2e`, which runs `npm ci` for it (SP-CI).

Outputs:
- `TT.selectTab(view)`: sets `.active`, `aria-selected` and `tabindex` on the tab buttons for `view`; called by
  `switchView` in `app.js`.
- Markup contract used by the test: `[role="tablist"] [role="tab"][data-view]` with `aria-controls="view-<view>"`,
  `#view-<view>[role="tabpanel"][aria-labelledby="tab-<view>"]`, `#theme-toggle[aria-label]`, `#splitter` after
  the editor in tab order.

Errors:
- A serious or critical axe violation fails the parametrized test for that tab and theme, with every finding of
  that run in the assertion message.

## Behavior
### Nominal
1. The test opens `/?profile=e2e` in a `bypass_csp` context, waits for `Python ready` and for the three banks to be
   rendered, injects axe once, then for each theme (`data-theme` set on the root) and each tab (clicked) runs
   `axe.run(document, {resultTypes: ['violations']})` and keeps the violations whose impact is serious or
   critical.
2. Arrow keys on a focused tab move focus to the neighbor (wrapping) and click it; `switchView` then calls
   `selectTab`, which updates `aria-selected` and the roving `tabindex`.
3. Escape in the editor blurs CodeMirror's input; the next Tab continues from the editor's position in the
   document, to the splitter.
4. `applyTheme` sets the toggle's text to the theme it switches to and its `aria-label` to
   `Switch to <theme> theme`.

### Edge cases
- `axe-core` missing -> the module skips with `run npm ci`.
- A code block wider than its box (statement, quiz, solution, failing test) -> it is focusable (`tabindex="0"`),
  so it can be scrolled with the keyboard and axe's `scrollable-region-focusable` passes whatever exercise the
  shuffled order shows first.
- The splitter -> `role="separator"` with `aria-valuenow` kept equal to the output height in pixels; Up and Down
  resize by 20 px, within the same bounds as the drag.

### Failure scenarios
- A new control without a name, a new icon-only button or a color change below AA -> the audit fails in CI with
  the rule id and the selector.

## Architecture Impact
- Adds dependency: SP-A11Y -> SP-WEB-QA (the test lives in `tests/e2e/` next to its fixtures and uses them; the
  `axe-core` devDependency sits in `package.json`).
- New / changed coupling, cycles, or shared state: `app.js` (frontier) calls `TT.selectTab`; the CI job `e2e`
  (SP-CI) gains an `npm ci` step. No cycle.

## Diagram
N/A: attributes and one test; no flow of its own.

## Acceptance Criteria
- [ ] AC1: axe-core reports no serious or critical violation on each of the four tabs in the light and the dark
  theme (`tests/e2e/test_a11y.py::test_no_serious_or_critical_violation`).
- [ ] AC2: the tab bar is a `tablist` of four `tab`s controlling `tabpanel`s, `aria-selected` and the roving
  `tabindex` follow the active tab, and Right, End and wrap-around Right select the next tabs from the keyboard
  (`tests/e2e/test_a11y.py::test_tabs_follow_the_aria_tab_pattern`).
- [ ] AC3: the theme toggle's `aria-label` names the theme it switches to, before and after a click
  (`tests/e2e/test_a11y.py::test_theme_toggle_label_reflects_the_state`).
- [ ] AC4: Escape then Tab leaves the code editor and lands on the splitter
  (`tests/e2e/test_a11y.py::test_escape_then_tab_leaves_the_code_editor`).
- [ ] AC5: every token pair used for text (`--muted`, `--accent`, `--ok`, `--fail`, `--warn` on `--bg`, `--bg2`,
  `--bg3` and their tinted backgrounds) reaches 4.5:1 in both themes, and the Check button's text reaches 4.5:1 on
  its green in the dark theme (computed from the tokens; covered by the `color-contrast` rule of AC1 for the
  elements rendered at audit time).
- [ ] AC6: manual keyboard walk in Chrome, both themes: Tab reaches the tabs, the exam controls, the theme toggle,
  the filters, the exercise list, the toolbar, the editor, the splitter, the output toggle; arrows move between
  tabs; the quiz is answered with 1-4 and Enter; the interview textarea and buttons are reachable; the focus ring is
  visible on every stop and nothing regressed visually (screenshots in the pull request).

## Open Questions
