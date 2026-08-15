---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15150-pr-template-acceptance-criteria.json
qaCommit: 8b1247ce1d6261fef6d9664bc913b3c60883591a
---

# QA Report: PR Template Acceptance Criteria Section

**Date**: 2026-08-15
**Session**: 15150
**Branch**: `claude/pr-process-improvements-bp43s2`
**qaCommit**: 2fa1d3ba05e47bdafea824e5fc9de79e189ce77c
**Scope**: `.github/PULL_REQUEST_TEMPLATE.md` (docs-only change)

## Change under test

Added an `## Acceptance criteria` section to the PR template so the template
matches the contract in `push-pr.md` step 4 and the parser in
`scripts/external_signals/acceptance_criteria.py` (consumed by the Validate
Spec Coverage job). Refs #5068.

## Validation performed

1. **Parser check (positive)**: Built a PR body from the updated template with
   the placeholder replaced by one checked criterion, then ran
   `acceptance_criteria.extract_acceptance_section` and `parse_criteria`
   against it. Result: section found, exactly 1 criterion parsed, checked
   state read correctly.
2. **Section boundary check (edge)**: Confirmed the parser stops at the next
   heading (`## Type of Change`), so the Type of Change checkboxes are not
   miscounted as acceptance criteria. Parsed count stayed at 1 with the full
   template body as input.
3. **Markdownlint**: `markdown-autofix` and `markdown-check` pre-commit jobs
   passed on the changed file (lefthook run in commit 2fa1d3b).
4. **Dash policy**: `staged-dash-policy` passed; the new section contains no
   em or en dashes.

## Additional scope: root-container push blockers (commit d82916e)

5. **Bundle suite regression**: after adding the root skip-guard to
   `orphan-ref-validator/tests/test_scan.py` (canonical and mirror kept
   byte-identical, verified by diff), `tests/test_skill_bundle_suites_run.py`
   passes: 8 passed.
6. **Previously failing environment tests**: with `sqlite3` and
   `openssh-client` installed, `tests/forgetful/`,
   `tests/test_import_forgetful_memories.py`, and
   `tests/validation/test_git_hook_policy_causal_restore.py` pass (41 passed,
   then full causal-restore suite green).
7. **bootstrap-vm.sh**: package-list edit only; script re-runs idempotently
   (apt-get install with already-installed packages is a no-op).
8. **Observation-sync bail-fast (commit 8b1247c)**: 4 targeted tests pass in
   `tests/test_lefthook_integration.py` (all-success processes every file,
   McpError bails with loud remaining-count warning, non-MCP failure
   continues, legacy single-file case unchanged). Measured trigger: each
   import spawn pays a 10s handshake timeout when Forgetful is absent; a
   new-branch push matched 43 observation files and exceeded the 5m job cap
   twice (302.93s, 304.23s in recorded push logs).

## Not covered

- No behavior change to any script; the parser itself is untouched, so no new
  script tests are required.
- The unchecked placeholder in a raw, unfilled template body parses as one
  unchecked criterion, which makes the (non-blocking) spec-coverage signal
  report FAIL until the author fills the section. That is the intended
  prompt-to-fill behavior documented in `push-pr.md`.

## Verdict

PASS. Template and validator now agree on the acceptance-criteria contract.
