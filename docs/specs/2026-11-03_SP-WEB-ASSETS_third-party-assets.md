---
id: SP-WEB-ASSETS
title: Third-party assets
version: 0.1
status: approved
author: agent
created: 2026-11-03
updated: 2026-11-03

owns:
  code: [app/index.html, tests/test_assets.py]
  resources: []

depends_on: []
provides_to: []

constraints:
  sri_algorithm: sha384
---

# Third-party assets

## Intent
Make sure the third-party code the page loads from a CDN is the code that was reviewed. Each CodeMirror asset
fetched from cdnjs carries a Subresource Integrity hash, so a compromised or tampered CDN response is refused by the
browser instead of running in the tab.

## Context
`app/index.html` loads CodeMirror 5.65.16 (one stylesheet and eight scripts) from cdnjs.cloudflare.com, Pyodide
0.27.7 from cdn.jsdelivr.net, and the Inter / JetBrains Mono fonts from fonts.googleapis.com. `server.py` serves the
page with a Content-Security-Policy restricted to those origins; SRI is independent of the CSP and needs no change
there. `app/index.html` is shared with the rest of the app: this spec owns only its external asset tags (the
`<link rel="stylesheet">` and `<script src>` elements pointing at a third-party origin), not its markup or the
scripts under `app/js/`. The component is code-only: `resources: []`.

## Goals
- G1: every cdnjs tag carries `integrity="sha384-..."` and `crossorigin="anonymous"`, with the hash of the exact
  file published for version 5.65.16.
- G2: the page still loads with no console error and the editor works.
- G3: the trade-off for the assets that cannot be integrity-checked (Pyodide, Google Fonts) is written down in
  `SECURITY.md`.

## Non-Goals
- NG1: SRI on Pyodide. `pyodide.js` could carry a hash, but it then fetches `pyodide.asm.js`, the wasm binary and
  the packages itself at runtime, and those cannot be verified by the page; a hash on the loader alone would give a
  false sense of security. Pyodide stays pinned to a version without an integrity attribute.
- NG2: SRI on the Google Fonts stylesheet, which is generated per user agent and has no stable hash.
- NG3: vendoring the assets under `app/` (listed as a possible future change in `SECURITY.md`).
- NG4: the Content-Security-Policy, COOP and COEP headers of `server.py`.

## Assumptions
- A1: the hashes are those of the files published on cdnjs for CodeMirror 5.65.16; cdnjs never rewrites a
  published version, so they stay valid until the version is bumped.
- A2: the cdnjs API (`https://api.cdnjs.com/libraries/codemirror/5.65.16?fields=sri`) publishes sha512 digests only;
  the sha384 digests are computed from the downloaded files and cross-checked against the API's sha512.

## Interface
Inputs:
- `app/index.html`: the page, read as text by the test.

Outputs:
- `tests/test_assets.py`: fails when a cdnjs `<script src>` or `<link rel="stylesheet" href>` lacks a non-empty
  `integrity` attribute starting with `sha384-` or lacks `crossorigin="anonymous"`.

Errors:
- A browser console error `Failed to find a valid digest in the 'integrity' attribute` means the hash no longer
  matches the file: recompute it from the published file, or bump the version and recompute every hash.

## Behavior
### Nominal
1. The browser fetches each cdnjs asset in CORS mode (`crossorigin="anonymous"`), hashes the response with SHA-384
   and compares it with the `integrity` attribute before executing or applying it.
2. The test parses `app/index.html` with `html.parser`, collects the external stylesheet and script tags, and
   asserts the attributes on every cdnjs tag.

### Edge cases
- Upgrading CodeMirror -> every hash must be recomputed with the new version; the test does not detect a stale
  hash (only the browser does), so the upgrade must be checked in a real browser.
- A non-cdnjs third-party tag (Pyodide, Google Fonts) -> no integrity attribute required; the test ignores it.

### Failure scenarios
- A tampered or truncated CDN response -> the browser refuses the asset, logs the error and the editor does not
  load; the page does not fall back to an unverified copy.
- A cdnjs tag added without SRI -> `tests/test_assets.py` fails.

## Architecture Impact
- New / changed coupling, cycles, or shared state: none; `server.py` (frontier) serves the page unchanged.

## Diagram
N/A: trivial slice (fetch, hash, compare).

## Acceptance Criteria
- [ ] AC1: every cdnjs `<script src>` and `<link rel="stylesheet" href>` in `app/index.html` carries a non-empty
  `integrity` attribute starting with `sha384-` and `crossorigin="anonymous"`
  (`tests/test_assets.py::test_cdnjs_assets_carry_subresource_integrity`).
- [ ] AC2: every `integrity` value is a well-formed sha384 digest: 64 base64 characters
  (`tests/test_assets.py::test_integrity_values_are_sha384_digests`).
- [ ] AC3: the page loads in a browser with no integrity or CORS console error and the editor works (checked by
  hand before merging, see the pull request).

## Open Questions
