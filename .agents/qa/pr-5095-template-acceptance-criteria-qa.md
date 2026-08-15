---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15150-pr-template-acceptance-criteria.json
qaCommit: d1d780af92b39ddb2d030d229b7a5bf76260734a
---

# QA Report: PR Template Acceptance Criteria Section

**Date**: 2026-08-15
**Session**: 15150
**Branch**: `claude/pr-process-improvements-bp43s2`
**Scope**: `.github/PULL_REQUEST_TEMPLATE.md`, `scripts/validation/git_hook_policy.py`
(`sync_observations` only), tests for both, plus one added sqlite error-path
test. Earlier commits on this branch also fixed root-container test guards and
bootstrap packages; `origin/main` has since shipped equivalent fixes through
sibling PRs, so those hunks no longer appear in this PR's effective diff.

## Change under test

1. `.github/PULL_REQUEST_TEMPLATE.md` gains an `## Acceptance criteria`
   section so the template matches the contract in `push-pr.md` step 4 and the
   parser in `scripts/external_signals/acceptance_criteria.py` (Refs #5068).
   The placeholder is visible prose, not an HTML comment, so the rendered body
   shows authors what to replace.
2. `sync_observations` in `scripts/validation/git_hook_policy.py` bails after
   the first Forgetful-MCP-unreachable failure instead of paying a failed
   handshake per file.
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
4. **Observation-sync bail**: 4 targeted tests in
   `tests/test_lefthook_integration.py` (all-success processes every file,
   McpError bails with a loud remaining-count warning, non-MCP failure
   continues, legacy single-file case unchanged). Measured trigger: each
   import spawn pays a 10s handshake timeout when Forgetful is absent; a
   new-branch push matched 43 observation files and exceeded the 5m job cap
   twice (302.93s, 304.23s in recorded push logs). PR #5092 (in flight)
   carries a fuller wall-clock-budget implementation of the same advisory;
   whichever lands second resolves toward the budget version.
5. **get_count non-numeric case**: passes with sqlite3 installed alongside
   main's directory-path error case.
6. **Markdownlint and dash policy**: pre-commit jobs green on every commit.

## Not covered

- The acceptance-criteria parser itself is unchanged; no parser tests were
  modified beyond the additive template regression test.
- The `sync_observations` bail keys on the `McpError` marker, not a time
  budget; a non-MCP hang is out of scope here and owned by the budget
  implementation in PR #5092.
- The unchecked placeholder in a raw, unfilled template body parses as one
  unchecked criterion, so the non-blocking spec-coverage signal reports FAIL
  until the author fills the section. Intended prompt-to-fill behavior per
  `push-pr.md`.

## Verdict

PASS. Template and validator agree on the acceptance-criteria contract, the
contract is pinned by a regression test, and the advisory bail is covered by
positive, negative, and edge tests.
