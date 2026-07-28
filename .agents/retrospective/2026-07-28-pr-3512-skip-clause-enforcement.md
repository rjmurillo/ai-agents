# Retrospective: PR #3512 SKIP clause enforcement

## Session Info
- **Date**: 2026-07-28
- **Task Type**: Bug fix (validation enforcement)
- **Outcome**: Complete. Fixed fail-closed contract violation and added route form coverage.

## Learnings Captured

### What went well
- Validator correctly detects all 6 historical violations and passes on the fixed tree
- Three new tests (missing dir, use-instead form, semicolon-use form) pass immediately
- Pre-PR validation passes with 0 failures across 36 checks

### What to improve
- The `retrospective-policy` hook blocked the first push attempt because no retrospective
  evidence existed for the session. Future pr-autofix runs should create the retrospective
  artifact before the push, not after discovering the hook failure.

### Key decision
- `load_skills()` returning `[]` for a missing directory was a fail-open bug per the PR's
  own stated contract. Raising `FileNotFoundError` makes `main()` exit 2, matching the
  documented fail-closed guarantee. Existing test for empty-but-present dir still passes.
