---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-07-session-10004-scope-gate-stacked-base.json
qaCommit: 369e60a955797d9059ecb2928c1989973d744a55
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
| `uv run pytest tests/test_scope_pr_base.py tests/test_scope_pr_base_credibility.py tests/test_scope_pr_base_real_git.py tests/test_detect_scope_explosion.py -q` | 174 passed |
| `uv run ruff check scripts/detect_scope_explosion.py scripts/scope_pr_base.py tests/test_scope_pr_base_credibility.py tests/test_detect_scope_explosion.py` | passed |

## Verdict

PASS. Session 10004 now has current QA evidence bound to the branch head that
still contains its scope-gate changes.
