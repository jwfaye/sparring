---
id: SP-CI
title: Continuous integration and repository hygiene
version: 0.5
status: approved
author: agent
created: 2026-11-03
updated: 2026-11-03

owns:
  code: [.github/workflows/ci.yml, .github/dependabot.yml, .pre-commit-config.yaml, tests/test_ci_config.py]
  resources: []

depends_on: []
provides_to: []

constraints:
  python_versions: ["3.12", "3.13"]
  unit_timeout_minutes: 15
  e2e_timeout_minutes: 30
  coverage_fail_under_percent: 65
---

# Continuous integration and repository hygiene

## Intent
Run the project's checks on every pull request and every push to `main`, on both supported Python versions, with
every third-party action pinned to a commit, measure the test coverage of the Python code against a floor, and give
contributors the same checks before each commit. It exists so that a regression, a drifting dependency, a tampered
action tag or a silent loss of test coverage is caught before it reaches `main`.

## Context
The checks themselves belong to other components: `ruff check .`, `python -m mypy .` and `python -m pytest -q`
(the Python code and its bank checkers), `npm run lint` (SP-WEB-QA) and `python -m pytest -q -m e2e tests/e2e`
(SP-WEB-QA). This component only orchestrates them: the GitHub Actions workflow `CI`
(`.github/workflows/ci.yml`), the Dependabot configuration (`.github/dependabot.yml`) and the pre-commit
configuration (`.pre-commit-config.yaml`), plus `tests/test_ci_config.py`, which reads the three files and checks
the properties below. Coverage is measured by `pytest-cov` (`dev` extra), configured in the `[tool.coverage.*]`
tables of `pyproject.toml` (the file belongs to SP-PACKAGING; this component owns the content of those tables and
the `pytest-cov` entry of the `dev` extra). `repoach.toml` waits on the check named `test`
(`auto_merge.required_checks`) and re-arms on the workflow named `CI` (`rearm_workflows`); branch protection on
`main` requires the checks `test`, `js` and `e2e`. Code-only: `resources: []`.

## Goals
- G1: the Python steps run on Python 3.12 and 3.13 with `fail-fast: false`, so one failing leg never hides the
  other's result.
- G2: exactly one check named `test` summarizes the matrix, so `repoach.toml` and branch protection keep a single
  stable name.
- G3: every `uses:` of the workflow and every hook repository of the pre-commit configuration is pinned to a full
  commit SHA, with the version tag in a trailing comment, so a moved tag cannot change what runs.
- G4: a superseded pull request run is cancelled, and no job runs without a time limit.
- G5: Dependabot proposes weekly updates for pip, npm and the actions, with minor and patch bumps grouped, never
  touches the pandas and numpy pins of the `check` extra, and moves the packages that must change together
  (`eslint` with `@eslint/js`, the GitHub Actions) in one pull request whatever the bump.
- G6: `pre-commit install` gives a contributor the linter, the type checker, ESLint and the file checks before each
  commit, with the project's own interpreter and `node_modules`.
- G7: the `unit (3.12)` leg measures branch coverage of `backend/`, `server.py` and `tools/` (without
  `tools/sources/`), fails under the `fail_under` floor of `pyproject.toml` and publishes `coverage.xml` as a run
  artifact; the floor is the measured total rounded down to the whole percent minus two points, so it never fails
  on noise and cannot drift down silently. A plain `pytest -q` does not measure (no `--cov` in `addopts`), so the
  local run and the `e2e` job stay as fast as before.

## Non-Goals
- NG1: changing what the checks test; the commands are those of the Development section of the README.
- NG2: formatting the tree with `ruff format`: the tree is not formatted yet, so the pre-commit configuration runs
  the linter only.
- NG3: running the browser suite on more than one Python version or more than one browser.
- NG4: publishing anything; releases are a separate component.
- NG5: coverage of the JavaScript and the browser suite, and a per-file floor; one total floor only.

## Assumptions
- A1: `ubuntu-latest` provides the pinned action versions' runtime and a Chromium-capable environment.
- A2: the `check` extra pins pandas and numpy to the Pyodide 0.27.7 versions (`pandas==2.2.3`, `numpy==2.0.2`),
  the ones the exercises run on in the browser (SP-PY-RUNTIME), and `.venv-check` mirrors them; numpy
  2.0.2 publishes no wheel for Python 3.13, so the 3.13 leg installs `pandas==2.2.3` with `numpy~=2.1.0`, the
  closest release that does.
- A3: the pre-commit tool is installed by the `dev` extra; contributors run it from `.venv-check`.

## Interface
Inputs:
- `push` to `main` and `pull_request` events: trigger the workflow `CI`.
- `.github/dependabot.yml`: read by GitHub on its weekly schedule.
- `.pre-commit-config.yaml`: read by `pre-commit install` and `pre-commit run --all-files`.

Outputs:
- Checks on a pull request: `unit (3.12)`, `unit (3.13)`, `test`, `js`, `e2e`; `test` is the one required by
  `repoach.toml` and branch protection.
- A run artifact `coverage-xml` holding `coverage.xml` from the `unit (3.12)` leg, and the `term-missing` report in
  that leg's log.
- Dependabot pull requests with the commit prefix `build(deps)`.
- A git pre-commit hook that runs the configured checks on the staged files.

Errors:
- A failing, cancelled or skipped matrix leg fails `test` (`if: always()` on the aggregate job with a result check).
- A job exceeding its `timeout-minutes` (15 for a matrix leg, 5 for `test`, 10 for `js`, 30 for `e2e`) is
  cancelled and reported as failed.
- A total coverage below `fail_under` fails the `unit (3.12)` leg (pytest exits non-zero after the report), hence
  `test`.

## Behavior
### Nominal
1. A push or pull request starts `CI`; the concurrency group `CI-<ref>` cancels the run in progress for the same
   pull request ref and lets runs on `main` finish.
2. `unit` installs the project with pip on each Python version, then runs `ruff check .`, `python -m mypy .` and
   `python -m pytest -q ${{ matrix.pytest-options }}`: `--cov --cov-report=term-missing --cov-report=xml` on 3.12,
   nothing on 3.13. The 3.12 leg then uploads `coverage.xml` with `actions/upload-artifact` (`if:
   matrix.python-version == '3.12'`, `if-no-files-found: error`).
3. `test` depends on `unit`, runs even when a leg failed (`if: always()`), and exits 0 only when
   `needs.unit.result == 'success'`.
4. `js` runs `npm ci` and `npm run lint` on Node 22; `e2e` installs the `check`, `dev` and `e2e` extras, Chromium
   and, with `npm ci` on Node 22, the `axe-core` package that `tests/e2e/test_a11y.py` (SP-A11Y) injects, then runs
   the browser suite on Python 3.12.
5. Locally, `pre-commit install` registers the hook; each commit runs end-of-file-fixer, trailing-whitespace,
   check-json, check-yaml, check-toml, `ruff check`, `.venv-check/bin/python -m mypy .` (when a Python file is
   staged) and `npm run lint` (when a file under `app/js`, `eslint.config.js` or a package file is staged).

### Edge cases
- Only one leg fails -> the other leg still finishes (`fail-fast: false`) and `test` fails.
- The total drops below the floor -> only `unit (3.12)` fails, with the `Missing` column naming the uncovered
  lines; the 3.13 leg is unaffected.
- The total rises -> nothing changes until a pull request raises `fail_under` (measured total rounded down minus
  two).
- A pull request receives a second push while CI runs -> the first run is cancelled.
- A Dependabot update of an action -> the SHA and its trailing version comment are both updated by Dependabot.
- A new pandas or numpy release -> no Dependabot pull request: the `pip` entry ignores every version of both
  (`ignore` with `dependency-name` only), because the pins follow Pyodide, not PyPI.
- A new ESLint major -> `eslint` and `@eslint/js` arrive in the single `javascript` group pull request
  (`patterns: ["eslint*", "@eslint/*"]`, `update-types: [minor, patch, major]`); the other npm packages keep
  their minor-and-patch group, which excludes those patterns.
- A new major of one action -> every action update arrives in the single `actions` group pull request
  (`patterns: ["*"]`, `update-types: [minor, patch, major]`).

### Failure scenarios
- A pinned action SHA is unreachable -> the job fails at checkout, which is the intended behavior for a moved or
  deleted tag.
- A `pip` cache miss or a slow CDN during `e2e` -> the job runs longer but is bounded by its timeout.

## Architecture Impact
- Adds dependency: none (the workflow invokes commands, it imports no module).
- New / changed coupling, cycles, or shared state: the check name `test` is shared with `repoach.toml`
  (`auto_merge.required_checks`) and with the branch protection of `main`; renaming it requires changing both. The
  `[tool.coverage.*]` tables and the `pytest-cov` pin live in `pyproject.toml`, a file owned by SP-PACKAGING; this
  component owns their content, nothing else in that file.

## Diagram
```mermaid
flowchart TD
    A[push or pull_request] --> B["unit (3.12)"]
    A --> C["unit (3.13)"]
    A --> D[js]
    A --> E[e2e]
    B --> F[test: needs unit, if always, result == success]
    C --> F
```

## Acceptance Criteria
This component is configuration read by GitHub and by pre-commit, not code the suite imports: the selectors below
parse the three files and check their shape; what they cannot see is named as observable on GitHub or in a shell.

- [ ] AC1: a pull request shows the checks `unit (3.12)`, `unit (3.13)`, `test`, `js` and `e2e` from the workflow
  `CI`, and `test` is green only when both `unit` legs are green (`gh pr checks <N>`); the shape is checked by
  `tests/test_ci_config.py::TestWorkflow::test_unit_matrix_runs_both_python_versions_without_fail_fast` and
  `tests/test_ci_config.py::TestWorkflow::test_the_required_check_test_aggregates_the_matrix`.
- [ ] AC2: every `uses:` line of `.github/workflows/ci.yml` is of the form `owner/repo@<40-hex-sha> # vX.Y.Z`
  (`tests/test_ci_config.py::TestWorkflow::test_every_action_is_pinned_to_a_commit_with_its_version_in_a_comment`)
  and no checkout persists its token
  (`tests/test_ci_config.py::TestWorkflow::test_checkout_never_persists_credentials`).
- [ ] AC3: the workflow is named `CI`, has a `concurrency` block and every job a `timeout-minutes` key
  (`tests/test_ci_config.py::TestWorkflow::test_workflow_is_named_ci_with_a_concurrency_group_and_a_timeout_on_every_job`).
- [ ] AC4: `.github/dependabot.yml` lists the ecosystems `pip`, `npm` and `github-actions` with a weekly schedule, a
  group covering minor and patch bumps each and the commit prefix `build(deps)`
  (`tests/test_ci_config.py::TestDependabot::test_three_ecosystems_weekly_with_grouped_minor_and_patch_updates`);
  GitHub's Dependabot tab shows the three.
- [ ] AC7: the `pip` entry groups minor and patch bumps and ignores every version of `pandas` and `numpy`
  (`tests/test_ci_config.py::TestDependabot::test_pip_groups_minor_and_patch_and_ignores_every_version_of_the_pyodide_pins`);
  the `npm` entry has a `javascript` group with the patterns `eslint*` and `@eslint/*` for minor, patch and major,
  and a minor-and-patch group excluding them
  (`tests/test_ci_config.py::TestDependabot::test_npm_moves_eslint_and_its_config_together_including_majors`);
  the `github-actions` entry has one `actions` group for minor, patch and major
  (`tests/test_ci_config.py::TestDependabot::test_actions_arrive_in_one_group_including_majors`).
- [ ] AC5: the pre-commit configuration pins its hook repositories to commits and declares the file checks,
  `ruff-check`, mypy and eslint
  (`tests/test_ci_config.py::TestPreCommit::test_hook_repositories_are_pinned_to_commits_and_the_hooks_mirror_ci`);
  `pre-commit run --all-files` from `.venv-check` passes on the tree after this change.
- [ ] AC8: the `unit` matrix gives the 3.12 leg the options `--cov --cov-report=term-missing --cov-report=xml` and
  the 3.13 leg none, the pytest step consumes them, and an `actions/upload-artifact` step guarded by
  `matrix.python-version == '3.12'` uploads `coverage.xml`
  (`tests/test_ci_config.py::TestWorkflow::test_only_the_3_12_leg_measures_coverage_and_uploads_the_report`);
  `pyproject.toml` measures `backend`, `server` and `tools` with branches, omits `tools/sources/*`, sets an integer
  `fail_under`, keeps `--cov` out of `addopts` and lists `pytest-cov` in the `dev` extra
  (`tests/test_ci_config.py::TestCoverage::test_the_floor_is_configured_and_plain_pytest_does_not_measure`);
  `python -m pytest -q --cov --cov-report=term-missing` from `.venv-check` passes the floor on the tree after this
  change.
- [ ] AC6: `gh api repos/jwfaye/sparring/branches/main/protection` reports `required_status_checks.strict == true`
  with the contexts `test`, `js` and `e2e`, `enforce_admins.enabled == false`, `required_linear_history.enabled ==
  true`, `allow_force_pushes.enabled == false`, `allow_deletions.enabled == false`, and no required reviews.

## Open Questions
