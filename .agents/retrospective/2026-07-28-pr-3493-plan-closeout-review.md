# Retrospective: PR #3493 Plan Closeout Advisory Review

## Session

- **PR**: #3493 (chore/3426-reclassify-stale-plans)
- **Issue**: #3426
- **Date**: 2026-07-28

## Learnings Captured

1. **Semgrep subprocess taint analysis**: Even list-based subprocess calls trigger Semgrep when environment-sourced data flows into arguments. Defense-in-depth via input validation (regex format check) resolves the finding without adding nosemgrep suppressions.

2. **Plan reference regex scope**: Issue reference patterns need to cover both `/issues/N` and `/pull/N` GitHub URLs. PR-tracked plans are common and invisible without the wider pattern.

3. **Advisory scripts should not block**: The plan closeout advisory correctly returns success after printing warnings, maintaining the advisory-only contract from issue #3426.
