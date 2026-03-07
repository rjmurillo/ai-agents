# Skill Sidecar Learnings: CI Infrastructure

**Last Updated**: 2026-03-04
**Sessions Analyzed**: 1

## Constraints (HIGH confidence)

- When a CI job fails on a PR, check if the failure exists on main before debugging PR code. Run the same workflow on main or check recent main runs. Pre-existing bugs waste time if misattributed to the PR. (PR #1361, 2026-03-04)

## Preferences (MED confidence)

- After major cleanup operations (file deletions, merges from main), update the PR description before pushing. The `pr_description.py` CI validator checks that files mentioned in the description match the actual diff. Stale descriptions cause `DESCRIPTION_RESULT: FAIL`. (PR #1361, 2026-03-04)
- Virtual environment tools (`uv run python`) should be first priority in Python detection functions like `set_python_cmd()`, before system `python3`/`python`/`py` fallbacks. System Python often lacks project dependencies (pytest, etc.) that live in the virtual environment. See `.githooks/pre-push:110`. (PR #1361, 2026-03-04)

## Notes for Review (LOW confidence)

- `$GITHUB_OUTPUT` requires heredoc delimiter syntax for multiline values. Writing `key=value` where value contains newlines causes each line after the first to be parsed as a separate output entry. Lines not matching `key=value` format trigger `##[error]Invalid format`. The `write_output()` helper in `scripts/ai_review_common.py` does not handle this. Filed as issue #1386. (PR #1361, 2026-03-04)
