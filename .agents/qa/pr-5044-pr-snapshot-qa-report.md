---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15200-fix-4898-pr-snapshot.json
qaCommit: f82b4fb5fbae5e6d2439d03842875b76930b33f2
---

# QA Report: PR #5044 - Immutable PR Snapshot

## Test Execution

```bash
uv run pytest tests/test_pr_snapshot.py -q
```

**Result**: 58 passed in 1.79s

## Coverage Summary

- 34 unit tests: validation, exit codes, identity, staleness, env sanitization, CLI
- 24 integration tests: real Git repos with renames, deletes, binary, Unicode,
  newline paths, shallow rejection, hook/submodule/filter suppression, caller
  verification, scanner invocation, fork rejection, full capture end-to-end

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| Capture owner, repo, PR number, head SHA, base SHA, base branch | PASS |
| Fetch exact objects into isolated temporary storage | PASS |
| Verify fetched object IDs and reject shallow/partial | PASS |
| NUL-delimited changed paths (renames, deletes, binary, Unicode, newline) | PASS |
| Run existing scanner against snapshot (--run-scanner) | PASS |
| Treat content as untrusted (no hooks, scripts, filters, submodules) | PASS |
| Recheck PR identity before publishing (head, base, repo, branch) | PASS |
| Fail closed for auth, quota, transport, fetch, verification | PASS |
| Prove caller checkout unchanged (--verify-caller) | PASS |

## Verdict

PASS
