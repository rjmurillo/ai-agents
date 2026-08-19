---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15150-pr-template-acceptance-criteria.json
qaCommit: d64d0f4981a70dbccf78a823e36e233e2bed7ebf
---

# QA Report: PR Template Acceptance Criteria Section

**Date**: 2026-08-15
**Session**: 15150
**Branch**: `claude/pr-process-improvements-bp43s2`
**Scope**: `.github/PULL_REQUEST_TEMPLATE.md`, its parser regression test in
`tests/external_signals/test_acceptance_criteria.py`, and one added sqlite
error-path case in `tests/test_claude_mem_scripts.py`. Earlier commits on this
branch also fixed root-container test guards, bootstrap packages, and an
observation-sync advisory bail; sibling PRs on main (including #5087's
wall-clock-budget version of the same advisory) shipped equivalent or fuller
fixes first, and the merges of origin/main adopted main's versions, so none of
those hunks remain in this PR's effective diff.

## Change under test

1. `.github/PULL_REQUEST_TEMPLATE.md` gains an `## Acceptance criteria`
   section so the template matches the contract in `push-pr.md` step 4 and the
   parser in `scripts/external_signals/acceptance_criteria.py` (Refs #5068).
   The placeholder is visible prose, not an HTML comment, so the rendered body
   shows authors what to replace.
2. `tests/external_signals/test_acceptance_criteria.py` gains a regression
   test that parses the shipped template through the real parser.
3. `tests/test_claude_mem_scripts.py` gains a non-numeric-output error case
   for `get_count` (the nonexistent-path case was corrected on main by a
   sibling PR; this PR keeps only the additive case).

## Validation performed

1. **Parser check (positive)**: built a PR body from the updated template with
   the placeholder replaced by one checked criterion; `extract_acceptance_
   section` finds the section and `parse_criteria` returns exactly 1 criterion
   with the checked state read correctly.
2. **Section boundary (edge)**: parser stops at the next heading
   (`## Type of Change`); Type of Change checkboxes are not miscounted.
3. **Template regression test (new)**:
   `tests/external_signals/test_acceptance_criteria.py::test_pr_template_acceptance_section_parses`
   pins the template-to-parser contract: section present, at least one
   criterion parsed, placeholder not an HTML comment. File suite: 17 passed.
4. **get_count non-numeric case**: passes with sqlite3 installed alongside
   main's directory-path error case.
5. **Markdownlint and dash policy**: pre-commit jobs green on every commit.

## Not covered

- The acceptance-criteria parser itself is unchanged; no parser tests were
  modified beyond the additive template regression test.
- The observation-sync advisory is no longer part of this diff: main's
  wall-clock-budget implementation (landed via PR #5087, with PR #5092
  carrying the sibling-allocation companion) owns that behavior now.
- The unchecked placeholder in a raw, unfilled template body parses as one
  unchecked criterion, so the non-blocking spec-coverage signal reports FAIL
  until the author fills the section. Intended prompt-to-fill behavior per
  `push-pr.md`.

## Verdict

PASS. Template and validator agree on the acceptance-criteria contract, and
the contract is pinned by a regression test that runs the shipped template
through the real parser.
