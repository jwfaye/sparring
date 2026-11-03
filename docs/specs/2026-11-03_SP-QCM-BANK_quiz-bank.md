---
id: SP-QCM-BANK
title: Quiz bank
version: 0.1
status: approved
author: agent
created: 2026-11-03
updated: 2026-11-03

owns:
  code: [bank/qcm/, tools/check_qcm.py]
  resources: []

depends_on: []
provides_to: []

constraints:
  choices_per_question: 4
  answer_min: 0
  answer_max: 3
---

# Quiz bank

## Intent
Hold the multiple-choice questions the Quiz tab serves (`bank/qcm/*.json`) and the checker that keeps them
trustworthy (`tools/check_qcm.py`). It exists so that every question shipped has a verified correct answer, a usable
explanation and no duplicate that would make a session repeat itself.

## Context
`server.py` loads the JSON files and `app/js/qcm.js` draws one question at a time, filtered by theme. Code questions
(`qcm_code.json`) are executed by the checker; theory questions (`qcm_ml_theory.json`) are reviewed by hand and
rewritten from the CC BY 4.0 source named in each item. `tools/add_qcm.py` appends validated drafts. The component is
code-only: `resources: []`.

## Goals
- G1: every question has the schema the checker enforces: `id`, `theme` (known), `question`, four distinct `choices`,
  `answer` (0-based index), `explanation`, `source`; code questions also carry `check`.
- G2: ids are unique across the bank and no two questions ask the same thing (normalized question text, plus the
  code for code questions, which share stems such as "What does this program print?").
- G3: theory questions are at interview level: a diagnostic or trade-off, not a definition lookup.

## Non-Goals
- NG1: serving or scoring the quiz in the browser (owned by `app/js/qcm.js`, frontier).
- NG2: the theory interview bank `bank/theory/` and its grader (SP-GRADER).
- NG3: generating new questions; this spec covers validation and curation of what is shipped.

## Assumptions
- A1: `bank/qcm/*.json` are JSON lists dumped with `ensure_ascii=False, indent=2` and a trailing newline.
- A2: the code checker runs in `.venv-check` with pandas and numpy pinned to the Pyodide versions.

## Interface
Inputs:
- `bank/qcm/*.json`: list of question objects with the G1 fields.

Outputs:
- `tools.check_qcm.main(argv)`: int, 0 when every file is valid; one `OK`/`KO` line per question and a summary line
  `<n> valid, <m> invalid`.

Errors:
- A `KO` line with reasons per question (missing field, unknown theme, bad choices, wrong announced answer,
  duplicate id); the exit code is 1.

## Behavior
### Nominal
1. Load each file, validate the schema of each question.
2. For a question with Python or SQL code, execute it and compare the result with the announced correct answer.
3. Report duplicates of `id` across files.

### Edge cases
- Two questions that differ only in wording but test the same fact -> keep one, fold any missing nuance into the
  survivor's `explanation`, remove the other without renumbering.
- A definitional question -> rewrite it as a diagnostic under the same `id` and `theme`.

### Failure scenarios
- Code raising an unexpected exception -> `KO` naming the exception.
- Another choice matching the computed result -> `KO` (ambiguous question).

## Architecture Impact
- New / changed coupling, cycles, or shared state: none; the bank is read by `server.py` (frontier).

## Diagram
N/A: trivial slice (load, validate, report).

## Acceptance Criteria
- [ ] AC1: the shipped quiz bank passes `tools.check_qcm` with zero invalid questions (`tests/test_banks.py`).
- [ ] AC2: quiz ids are unique and no two quiz questions share the same normalized question text and code
  (`tests/test_banks.py::test_quiz_questions_are_unique`).
- [ ] AC3: every `answer` is an integer index into four distinct non-empty choices, and every code question's
  announced answer matches what its code produces (`tests/test_banks.py::test_quiz_bank_is_valid`).

## Open Questions
