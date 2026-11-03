# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-03

### Added
- Local training app: Python/pandas and SQL exercises executed in the browser with Pyodide, multiple-choice quizzes
  whose code questions are checked by execution, and a theory-interview mode graded by Claude through the Anthropic
  API or a Claude Code subscription (faf5bbd).
- Validated `config.json` settings, bank checkers under `tools/`, a pytest suite and a GitHub Actions CI, and a
  hardened local server that refuses non-local hosts, foreign origins and non-JSON POSTs (faf5bbd).
- repoach review configuration, the spec template and the first spec, SP-GRADER (#1).
- Stop button and a 20 s run timeout for exercises: Python runs in a Web Worker and the page stays responsive during
  a run (#5).
- ESLint configuration for `app/js` and Playwright browser tests of the main flows, each with its own CI job (#6).
- `SPARRING_CONFIG` environment variable naming the settings file to read instead of `config.json` (#7).
- Pre-commit configuration mirroring the CI checks, and weekly Dependabot updates for pip, npm and the GitHub
  Actions, minor and patch bumps grouped (#9).

### Changed
- License changed from MIT to AGPL-3.0-or-later; the copyright notice is displayed in the page footer and the server
  log (#2).
- Quiz question `qcm-th-011` rewritten as a diagnostic of a training versus cross-validated accuracy gap (#3).
- The browser test suite is opt-in: a plain `pytest -q` excludes it and `-m e2e` runs it (#7).
- CI runs the Python checks on 3.12 and 3.13, every action pinned to a commit SHA, with a concurrency group and a
  timeout on every job (#9).

### Fixed
- Two duplicate quiz questions removed (`qcm-th-033`, `qcm-th-034`), their nuances folded into the explanations of
  the questions they duplicated (#3).
- Revealing a hint threw a `ReferenceError` (#6).

### Security
- Subresource Integrity (sha384) and `crossorigin="anonymous"` on the nine CodeMirror assets loaded from cdnjs (#4).
- `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` on every response: the
  page is cross-origin isolated (#5).
- The CI workflow runs with a read-only token (#6).

[Unreleased]: https://github.com/jwfaye/sparring/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jwfaye/sparring/releases/tag/v0.1.0
