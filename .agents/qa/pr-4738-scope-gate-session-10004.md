---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-07-session-10004-scope-gate-stacked-base.json
qaCommit: 7ff4931e628b2ae6070434e6fbf0d8fccb0236cf
---
# Test Report: PR #4738 stacked-base scope gate session 10004

## Scope

Refreshed QA evidence for the earlier PR #4738 branch session so the carried
session artifact matches the current branch head. The underlying branch work
still covers stacked-base rescoping, credibility checks, and the real-git
ancestry tests introduced on this PR.

## Validation

| Command | Result |
|---------|--------|
| `uv run --frozen pytest tests/test_scope_pr_base_real_git.py tests/test_scope_pr_base_credibility.py tests/test_detect_scope_explosion.py tests/ci/test_pr_validation_workflow.py -q` | 175 passed |
| `uv run --frozen pytest -m windows_path -q` | 1027 passed, 3 skipped, 24585 deselected |
| `uv run --frozen ruff check scripts/detect_scope_explosion.py scripts/scope_pr_base.py tests/test_scope_pr_base_credibility.py tests/test_detect_scope_explosion.py` | passed |

## Verdict

PASS. Session 10004 now has current QA evidence bound to the branch head that
still contains its scope-gate changes.
