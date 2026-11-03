---
id: SP-THEORY-BANK
title: Theory interview bank
version: 0.1
status: approved
author: agent
created: 2026-11-03
updated: 2026-11-03

owns:
  code: [bank/theory/, tools/check_theory.py, tools/add_theory_grids.py, tools/import_theory_questions.py]
  resources: []

depends_on: []
provides_to: []

constraints:
  key_points_min: 3
  key_points_max: 6
  common_mistakes_min: 1
  reference_max_chars: 1800
---

# Theory interview bank

## Intent
Hold the interview questions the Interview tab serves (`bank/theory/*.json`), each with the grading grid the grader
(SP-GRADER) scores answers against, and the tools that keep the bank consistent. It exists so that every shipped
question has a correct reference answer, key points a model can grade one by one, real common mistakes and a
difficulty the app can filter on.

## Context
`server.py` loads the JSON files and `app/js/theory.js` draws one question at a time; `backend/grader.py` sends
the question, `reference`, `key_points` and `common_mistakes` with the answer to the model. The questions were
imported without answers by `tools/import_theory_questions.py` from the two sources kept verbatim in
`tools/sources/`; the grids were generated once by a model with `tools/add_theory_grids.py`, then reviewed by hand on
2026-11-03 under the rules below. The component is code-only: `resources: []`.

## Goals
- G1: every question has the schema the checker enforces: `id`, `section`, `question`, `source`, `difficulty`
  (`easy`, `medium` or `expert`), `reference` (non-empty, at most 1800 characters), `key_points` (3 to 6 non-empty
  strings), `common_mistakes` (at least 1 non-empty string); `uncertain: true` requires a `note`.
- G2: ids are unique across the bank and never change; the grading grid of a question is edited under its id.
- G3: grids are reviewed against five rules: (a) the reference and the key points are factually correct; (b) each key
  point is one gradeable statement, not a bare topic word; (c) each common mistake is a real mistake, not a
  restatement of a key point; (d) no key point contradicts the reference; (e) American spelling.
- G4: the difficulty distribution of a file is consistent with the other file (medium as the majority, a minority of
  easy, a few expert), assigned by judgment of what the question demands.

## Non-Goals
- NG1: grading answers (SP-GRADER) or storing verdicts (`backend/store.py`).
- NG2: serving the questions in the browser (`app/js/theory.js`, frontier).
- NG3: generating new questions or translating the bank; this spec covers validation and curation of what is
  shipped.

## Assumptions
- A1: `bank/theory/*.json` are JSON lists dumped with `ensure_ascii=False, indent=2` and a trailing newline, keys in
  the order `id, section, question, source, difficulty, reference, key_points, common_mistakes` (then `uncertain`,
  `note` when present); a no-op round trip through `json` is byte-identical.
- A2: the source documents in `tools/sources/` are kept verbatim; the data-science-interviews source gives a
  difficulty per question, the field guide gives none.

## Interface
Inputs:
- `bank/theory/*.json`: list of question objects with the G1 fields.
- `DRAFT.py` for `tools.add_theory_grids`: a module defining `GRIDS = {id: {reference, key_points, common_mistakes,
  uncertain?, note?}}`.

Outputs:
- `tools.check_theory.main(argv)`: int, 0 when every question is valid; `KO` lines with reasons, then a summary line
  `<n> questions: <ok> valid grid(s), <bad> invalid, <m> without a grid`; `--missing` lists questions without a grid.
- `tools.check_theory.check_grid(q)`: the list of errors of one question (empty when valid); `DIFFICULTIES` names the
  accepted difficulty values.
- `tools.add_theory_grids`: merges the valid grids of a draft into the bank (`--dry-run` writes nothing).
- `tools.import_theory_questions`: rewrites the two files from the sources, keeping the grids and the difficulty
  already in the bank when the source gives none.

Errors:
- A `KO` line per invalid question (missing or invalid difficulty, missing or too long reference, wrong number of key
  points, empty common mistakes, uncertain without a note, duplicate id); exit code 1.

## Behavior
### Nominal
1. Load each file, check the schema of each question with `check_grid`, report duplicate ids.
2. A grid review edits the JSON with the `json` module (`ensure_ascii=False, indent=2`, trailing newline), keeps the
   key order and the id, and records what changed per question in the pull request.
3. A re-import rebuilds the question list from the sources and carries over the grid fields and the difficulty.

### Edge cases
- A key point that is a bare topic word (for example "Remedies") -> rewrite it as the statement the reference makes
  on that topic, under the same id.
- A common mistake that restates a key point -> replace it with a real mistake, or drop it if at least one remains.
- A grid judged unsalvageable -> rewrite the whole grid under the same id and say so in the pull request.
- A question whose grid cannot be made reliable -> `uncertain: true` with a `note`, shown in the app.

### Failure scenarios
- A file that is not a JSON list -> the checker raises; the bank test fails.
- A draft grid rejected by `check_grid` -> `KO <id>: <reasons>`, nothing written for that id.

## Architecture Impact
- New / changed coupling, cycles, or shared state: none; the bank is read by `server.py` and `backend/grader.py`
  (SP-GRADER reads the grid fields through the HTTP API, no import of this component).

## Diagram
N/A: trivial slice (load, validate, report).

## Acceptance Criteria
- [ ] AC1: the shipped theory bank passes `tools.check_theory` with zero invalid questions and zero questions without
  a grid (`tests/test_banks.py::test_theory_bank_is_valid`).
- [ ] AC2: every theory question has a `difficulty` in `easy`, `medium`, `expert`, and `key_points` holds 3 to 6
  non-empty strings (`tests/test_banks.py::test_theory_questions_have_difficulty_and_key_points`).
- [ ] AC3: theory ids are unique across the bank files
  (`tests/test_banks.py::test_bank_files_are_json_lists_with_unique_ids`).

## Open Questions
