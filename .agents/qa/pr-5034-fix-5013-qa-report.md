---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-01-fix-5013.json
qaCommit: d5b8f24af6e63b3f8c42357222b679dbf4c184de
---

# QA Report: PR #5034 - fix/push-pr-timeout-denial-5013

## Verdict

PASS - All acceptance criteria met.

## Test Results

- 28,648 tests pass, 37 skipped, 0 failures
- 30 new regression tests in test_push_pr_timeout_regression_5013.py
- 313 hook guard tests pass (scope, postmerge, bundle, timeout regression)

## Changes

1. **Fail-open on timeout**: hook_dispatch_timeout.py returns ALLOW_EXIT (0) on
   TimeoutExpired or OSError instead of BLOCK_EXIT (2)
2. **Narrowed matcher**: Bash(*new_pr*|*push_pr*|*push-pr*|*python*|*pypy*|*pr.py*|uv run *)
   replaces bare Bash so unrelated commands (ls, git, cat) never invoke the guard
3. **Copilot shim regenerated**: new narrow-matcher shim replaces old wide-matcher shim
4. **Remediation message corrected**: Claude side uses /install-plugin rjmurillo/ai-agents

## Acceptance Criteria Coverage

- [x] AC1: No denial of unrelated commands (narrowed matcher + allow-on-timeout)
- [x] AC2: Matcher narrowed from bare Bash to tool-glob pattern
- [x] AC3: Fail-open on timeout (exit 0 with stderr warning)
- [x] AC4: Canonical new_pr.py still denied (30 positive tests)
- [x] AC5: Lookalikes denied (extglob, POSIX quoting, pypy, range obfuscation)
- [x] AC6: Concurrency regression passes (40 commands, 8 workers)
- [x] AC7: Hook trees synced (build-all-check passes)
- [x] AC8: Copilot probe covered by existing guard scope tests
- [x] AC9: Hook necessity documented in PR description and issue thread
