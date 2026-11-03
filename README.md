# Sparring

Your training partner for data science / ML engineer technical tests and interviews.

A local web app: Python/pandas and SQL exercises run in the browser (Pyodide), multiple-choice quizzes, and a
theory-interview mode where a model grades your free-text answers against a key-point grid.

## Run

As a command, from any directory (Python 3.12 or later, no other dependency):

```bash
pipx install git+https://github.com/jwfaye/sparring   # or: pip install git+https://github.com/jwfaye/sparring
sparring                                              # then open http://127.0.0.1:8765/
sparring 9000                                         # another port, also: --port 9000, --host 127.0.0.1
sparring --version                                    # version from the package metadata; --help lists the options
```

From a clone, exactly as before (`pip install .` from the clone gives the same `sparring` command):

```bash
python3 server.py            # then open http://127.0.0.1:8765/
python3 server.py 9000       # another port (otherwise: config.json)
```

Where things live: the installed command keeps your interview answers in `$XDG_DATA_HOME/sparring`
(`~/.local/share/sparring`; `~/Library/Application Support/sparring` on macOS, `%LOCALAPPDATA%\sparring` on Windows)
and reads its settings from `~/.config/sparring/config.json`; a clone run from its root keeps using `data/` and
`config.json` there. `SPARRING_DATA_DIR` overrides the data directory, `SPARRING_CONFIG` the settings file, and the
server logs both at startup. Details in Configuration.

No dependency is needed for the server itself. Optional extras, pinned in `pyproject.toml` and locked in `uv.lock`:

```bash
uv sync --all-extras                        # reproducible: every extra at the locked versions
python3 -m pip install -e ".[api]"          # Anthropic API grading backend (or: pip install -r requirements.txt)
python3 -m pip install -e ".[check]"        # pandas 2.2.3 / numpy 2.0.2, the versions shipped by Pyodide (for .venv-check)
python3 -m pip install -e ".[dev]"          # pytest, ruff, mypy
```

First load downloads Pyodide + pandas (about 15 MB) from a CDN, then the browser caches them. An internet connection
is needed on first load (and for CodeMirror and the fonts).

Light or dark theme follows the system setting; the "Dark / Light" button in the top bar forces one (remembered by
the browser).

To try the app without touching your progress: `http://127.0.0.1:8765/?profile=test` (separate storage).

## Configuration

Everything lives in one `config.json` (defaults in `backend/config.py`), the first found of:

1. the file named by `SPARRING_CONFIG`, when the variable is set;
2. `config.json` in the current directory (a clone run from its root);
3. `$XDG_CONFIG_HOME/sparring/config.json`, that is `~/.config/sparring/config.json` (the installed command; create
   it to change a default, a missing file means the defaults).

Because of step 2, start the installed command from a directory you trust: a `config.json` found there can set
`grader.claude_bin`, a program the grader runs, and the server warns at startup when that happens.

```json
{
  "server": { "host": "127.0.0.1", "port": 8765 },
  "grader": {
    "backend": "auto",
    "model": "claude-opus-5-5",
    "effort": "medium",
    "claude_bin": "claude",
    "timeout_seconds": 240
  }
}
```

- `server.host`: non-empty string (keep `127.0.0.1`: the server has no authentication)
- `server.port`: integer from 1 to 65535
- `grader.backend`: `auto` | `api` | `claude-code` | `offline` (case-insensitive)
- `grader.model`: grading model, non-empty string (`sonnet` to save subscription quota)
- `grader.effort`: `low` | `medium` | `high`
- `grader.claude_bin`: path to the Claude Code CLI, non-empty string
- `grader.timeout_seconds`: positive integer
- `SPARRING_CONFIG`: environment variable, path of the settings file, ahead of `./config.json` and the per-user file
  (the browser tests use it to start a server on a free port with the grader offline)
- `SPARRING_DATA_DIR`: environment variable, directory of your answers (`<dir>/theory[/<profile>]/answers.sqlite3`)
  instead of `data/` in a clone or `$XDG_DATA_HOME/sparring` (`~/.local/share/sparring`) for the installed command
- `SPARRING_LOG_LEVEL`: environment variable, server log level (default `INFO`)

Every value is validated at startup: an invalid value keeps its default and is logged as a warning, as are
unknown sections and keys, so a typo never prevents the server from starting.

Apart from those three variables, the only thing that stays in the environment is the API key, never in a file of
the repository:
`export ANTHROPIC_API_KEY=sk-ant-...` (with `.venv/bin/python -m pip install -e ".[api]"`, then
`.venv/bin/python server.py`). Without a key and without Claude Code, exercises and quizzes are fully functional and
the interview mode falls back to offline grading.

## Layout

```
server.py                  static server + /api/* (merges bank/*/*.json); the `sparring` command is its main()
pyproject.toml             package metadata: the sparring command, app/ and bank/ shipped as sparring_data
config.json                settings (server, grader)
app/                       web page: index.html, css/, js/common.js, js/app.js, js/py-client.js, js/py-worker.js, js/qcm.js, js/theory.js, py/harness.py
backend/                   config.py, paths.py (shipped files and data directory), store.py (interview answers), grader.py (Claude Code or Anthropic API)
bank/exercises/*.json      exercise bank (one file = one list of exercises)
bank/qcm/*.json            quiz bank
bank/theory/*.json         interview questions + grading grids
sparring_data/             empty package: the wheel maps app/ and bank/ under it, a clone never reads it
data/theory/               your answers and grades, answers.sqlite3 per profile, in a clone (local, never committed); installed: ~/.local/share/sparring/theory/
tools/                     scripts, run from the root of a clone: python -m tools.<name>
.venv-check/               venv with pandas 2.2.3 / numpy 2.0.2 = the versions shipped by Pyodide 0.27.7
```

Tools:

| Script | Role |
|---|---|
| `tools.check_bank` | validates the exercise bank with the same harness as the browser |
| `tools.add_exercises` | validates a draft and adds only the exercises that pass |
| `tools.check_qcm` | validates the quiz bank (executes the questions' code) |
| `tools.add_qcm` | validates a quiz draft and adds it to the bank |
| `tools.import_theory_questions` | imports interview questions from `tools/sources/` |
| `tools.add_theory_grids`, `tools.check_theory` | adds grading grids, validates them |
| `tools.theory_pending`, `tools.import_grades`, `tools.grade_pending` | deferred (offline) or batch grading |

## Exercises

Ask Claude in the conversation: "generate N <difficulty> exercises on the theme <theme>" (one or several themes).
Claude writes a draft module, then:

```bash
.venv-check/bin/python -m tools.add_exercises draft.py --dry-run   # report, writes nothing
.venv-check/bin/python -m tools.add_exercises draft.py             # adds the valid exercises to bank/exercises/<draft>.json
```

Only the exercises that pass every criterion are added; the others are listed with the rejection reason.
Themes: groupby, merge, pivot, dates, nan, cleaning, python, sql-joins, sql-groupby, sql-window, sql-cte, sql-subqueries.
Difficulties: easy, medium, hard.

An exercise is valid when: the schema is correct, the theme is known, id and title are new, there are at least 2 tests
(setup data + another dataset), the solution passes every test, the starter code does not, and the statement gives no
hint. Statement rule: it specifies the output format and an example, never the method nor the trap (those go in `hints`).

```bash
.venv-check/bin/python -m tools.check_bank             # whole bank
.venv-check/bin/python -m tools.check_bank file.json   # one file
```

Exercise format:

```json
{
  "id": "pd-groupby-001", "title": "...", "theme": "groupby",
  "difficulty": "easy | medium | hard", "language": "python | sql",
  "statement": "statement (mini-markdown: **bold**, `code`, lists, ``` blocks)",
  "setup": "python: code creating the data | sql: DDL + INSERT script",
  "starter": "starter code shown in the editor",
  "run_call": "python, optional: expression displayed after Run, e.g. solve(df)",
  "tests": "python: [{name, code}] with assert_eq(got, expected, msg?, ignore_order?, ignore_index?)\n       sql: [{name, expected: [[...]], ordered?: true, columns?: [...], setup?: '...'}]",
  "hints": ["optional hints, revealed one at a time with the Hint button"],
  "solution": "reference solution (hidden behind a confirmation)"
}
```

Shortcuts: `Ctrl+Enter` run, `Ctrl+Shift+Enter` check, `Ctrl+/` comment. Progress, code and exam timer live in the
browser's `localStorage` (Summary tab: Export / Reset).

Your code runs in a Web Worker (`app/js/py-worker.js`), so the page never freezes. The **Stop** button interrupts
the current run, and a run is interrupted automatically after 20 s (`RUN_TIMEOUT_MS` in `app/js/py-client.js`);
the output then shows `Execution interrupted after N s`. The interruption is immediate when the page is cross-origin
isolated (the default with `server.py`); otherwise, or when the code swallows the `KeyboardInterrupt`, Python is
reloaded in the worker (a few seconds) and the next run waits for "Python ready".

## Quiz

**Quiz** tab: one question at a time, shuffled choices, keys 1-4 to answer, Enter for the next one, explanation after
each answer, score and list of failed questions at the end, error history by theme, "Review my mistakes" button.

Bank: `bank/qcm/*.json`. Question format:

```json
{
  "id": "qcm-py-001", "theme": "python | pandas | sql | git | regression | validation | classification | regularization | trees-ensembles | neural-networks | nlp | clustering | dimensionality-reduction | recommender-systems | time-series",
  "question": "statement (mini-markdown)", "code": "optional, multi-line", "language": "python | sql | bash | text",
  "choices": ["4 choices"], "answer": 1, "explanation": "...", "source": "...",
  "check": {"type": "python_stdout | python_expr | python_raises | sql | none", "...": "see tools/check_qcm.py"}
}
```

Every question with Python/SQL code must carry a `check`: the checker **executes the code** and confirms that the
announced answer is the right one (and that no other choice matches the result).

To get more: "generate N quiz questions on the theme <theme>". Claude writes a draft, then:

```bash
.venv-check/bin/python -m tools.add_qcm draft.py --dry-run   # report
.venv-check/bin/python -m tools.add_qcm draft.py             # adds to bank/qcm/<draft>.json
.venv-check/bin/python -m tools.check_qcm                    # re-validates the whole bank
```

ML theory questions are adapted from alexeygrigorev/data-science-interviews (theory.md, CC BY 4.0).

## Theory interview

**Interview** tab: a question, a free-text answer, an optional timer (2 or 3 min), then:

- **online**: the backend (`backend/grader.py`) sends the question, the grid and your answer to the model (structured
  JSON output) and returns a score out of 10, covered / missing / wrong points, feedback and an improved version of
  your answer. Two backends, chosen by `grader.backend` in `config.json`:
  - `claude-code`: `claude -p` in non-interactive mode on your Claude Code subscription, no API key. No tool is
    exposed to the model, the system prompt is replaced (about 1,500 tokens per grading), nothing is written to your
    sessions. Each grading consumes subscription quota like one Claude Code exchange. About 10 s per grading;
  - `api`: official `anthropic` SDK, key read from `ANTHROPIC_API_KEY`.
  With `auto`, the API is used when a key is present, otherwise Claude Code when it is logged in, otherwise offline;
- **offline**: the answer is saved in `data/theory/answers.sqlite3` (never committed; a SQLite database, one per
  profile). Then ask Claude: "grade my pending interview answers": it runs `python -m tools.theory_pending`, grades
  with the same grid and imports the scores with `python -m tools.import_grades`; or run
  `python -m tools.grade_pending` once a key is available. Answers saved by an earlier version in `answers.json` are
  imported into the database the first time the profile is read, and the file is renamed `answers.json.migrated`.

Score history by section and weak points on the tab's home. Every saved answer can be reopened.

Bank: `bank/theory/*.json`, 231 questions imported without answers by `tools.import_theory_questions` from
`tools/sources/` (65 from the AI engineering field guide, 166 from data-science-interviews, source kept on each
question), each with a grid generated once: `reference` (concise reference answer), `key_points` (3 to 6),
`common_mistakes`, and `uncertain`/`note` when the grid is judged unsure. Validation: `python -m tools.check_theory`.
To add or fix grids: a draft `GRIDS = {id: {...}}`, then `python -m tools.add_theory_grids draft.py`.

The API key never appears in the code, the page or the repository: the SDK reads it from the environment.

## Development

```bash
.venv-check/bin/python -m pip install -e ".[check,dev]"   # once: pandas/numpy as in Pyodide, pytest, ruff, mypy, pre-commit
.venv-check/bin/pre-commit install                        # once: git hook running ruff, mypy, eslint and the file checks before each commit
ruff check .                                              # lint
.venv-check/bin/python -m mypy .                          # type check
.venv-check/bin/python -m pytest -q                       # unit tests + the three bank checkers (browser tests excluded)
.venv-check/bin/python -m pytest -q --cov --cov-report=term-missing   # same, with branch coverage of backend, server.py and tools; fails under 65%
npm ci && npm run lint                                    # ESLint on app/js (eslint.config.js)
.venv-check/bin/python -m pip install -e ".[e2e]" && .venv-check/bin/python -m playwright install chromium   # once: Playwright + Chromium
.venv-check/bin/python -m pytest -q -m e2e tests/e2e                                                           # browser tests (headless, opt-in)
```

Tests live in `tests/` and run from the project root with `python -m pytest`, which puts the root on `sys.path`.
They cover the execution harness, the answer store, the grader (with a fake SDK and a fake `claude` CLI, nothing
real is called), the HTTP API on a live server, the command line and the path resolution of an installed copy, and
a smoke test that the shipped banks pass their checkers. To check the package itself, build the wheel and look at
it: `python -m pip wheel . --no-deps -w /tmp/wheel && unzip -l /tmp/wheel/sparring-*.whl` (it must list
`sparring_data/app/` and `sparring_data/bank/`, nothing from `data/` or `tests/`).
`tests/e2e/` drives the page in headless Chromium (Playwright) against a `server.py` started on a free port with the
`e2e` profile: page boot, an exercise check, a quiz answer, an offline interview answer, the theme toggle. The suite
is opt-in (`-m e2e` overrides the `addopts` of `pyproject.toml`) and its modules skip when the `e2e` extra is not
installed. The same steps run in GitHub Actions on every push to `main`
and every pull request (`.github/workflows/ci.yml`): the Python steps on a matrix of Python 3.12 and 3.13 (jobs
`unit (3.12)` and `unit (3.13)`, summarized by the required check `test`; the 3.12 leg measures coverage, fails under
the `fail_under` floor of `pyproject.toml` and uploads `coverage.xml` as an artifact), the lint in `js`, the browser
tests in `e2e`. Dependabot (`.github/dependabot.yml`) opens weekly update pull requests for pip, npm and the actions.

## Code review with repoach

Pull requests are reviewed by [repoach](https://github.com/repoachhq/repoach), configured in `repoach.toml` to use
the local Claude Code login (`kind = "claude_code"`), so no key is needed:

```bash
pipx install git+https://github.com/repoachhq/repoach@main
repoach doctor                      # shows the configured provider route
repoach review pr <N> --dry-run     # review a PR, post nothing
repoach review gate <N>             # evidence-first merge gate, read-only
```

## Security

Sparring is a local, single-user tool. The server has no authentication and must stay on a loopback address
(`server.host` = `127.0.0.1`, the default): exposing it on a network exposes your saved answers and lets anyone spend
your API credits or Claude Code quota. The API refuses requests whose Host is not local, cross-origin requests and
non-JSON POSTs, the page is served with a Content-Security-Policy, and the CodeMirror assets loaded from cdnjs are
integrity-checked. The server also sends `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp`: this cross-origin isolation is what unlocks `SharedArrayBuffer`, which
the Stop button and the run timeout use to interrupt Python without reloading it (every pinned CDN answers with
`Cross-Origin-Resource-Policy: cross-origin`, so nothing is blocked). Exercise code runs in the browser (Pyodide, in a
Web Worker), never on the server; the bank checkers in `tools/` do execute bank and draft code on your machine, so run
them only on banks you trust. The API key lives in the environment only, and `data/` is never committed. Details,
network calls made by the page and how to report an issue: [SECURITY.md](SECURITY.md).

## Contributing

Conventions, the spec-first workflow and the review loop are in [CONTRIBUTING.md](CONTRIBUTING.md); every
user-visible change is listed in [CHANGELOG.md](CHANGELOG.md). To release: bump `project.version` in
`pyproject.toml` and move the `[Unreleased]` entries of the changelog to a dated `## [X.Y.Z] - YYYY-MM-DD` section;
tag the merged commit `vX.Y.Z` and push the tag; `.github/workflows/release.yml` checks that the tag matches the
version, builds the sdist and the wheel, and publishes the GitHub release with that changelog section as notes and
the dist files attached.

## License

Copyright (c) 2026 Joseph Faye.

Sparring is free software under the [GNU Affero General Public License v3.0 or later](LICENSE). You may use,
study, modify and redistribute it, provided that any distributed or network-hosted version is published under the
same license, keeps this copyright notice, and displays it in its user interface (AGPL sections 5 and 13).

Interview questions adapted from data-science-interviews (CC BY 4.0) and the AI engineering field guide, source kept
on each question.
