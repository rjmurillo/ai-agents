# PR 4545 Review Remediation Notes

## Scope

- Merged current `origin/main` into the live PR head without rebasing.
- Recovered five unpublished behavior and test commits.
- Skipped the unpublished Ruff baseline change to retain current main's value.
- Applied the six requested review corrections.
- Pinned one resolved base OID for merge construction and baseline reads.
- Isolated synthetic Git commands from user configuration without hook bypasses.
- Changed merge conflicts from success to the distinct fail-closed exit `100`.
- Made remote refresh ordered and fail closed before pinning one aggregate base OID.
- Replaced `git archive` with temporary-index materialization unaffected by
  `export-ignore`.
- Added CLI exit-contract ownership to the aggregate registry and Lefthook.
- Distinguished new, missing, malformed, and externally unreadable baselines.
- Reported cleanup failures without replacing an active primary failure.
- Left `.github/workflows/pr-validation.yml` unchanged as directed.

## Security Flagging

**Status**: Security-relevant changes detected

**Triggered By**: Root Lefthook configuration and subprocess environment isolation

**PIV Required**: Yes

**Justification**: The recovered `lefthook.yml` change adds the memory-index
baseline to merge-tree gate scheduling. Root Lefthook files require security
review before merge under `.claude/rules/security.md`. The DevOps remediation
also changes Git subprocess environment and configuration isolation.

## Validation

- Targeted ratchet tests: 106 passed.
- Merge-tree implementation coverage: 86%.
- Scoped Ruff and mypy: passed.
- Synthetic-path and failure-remediation mutations: killed.
- Moving-ref, platform-path, hostile-config, and conflict controls: passed.
- Full relevant ratchet suite: 337 passed.
- Targeted controls repeated twice: 45 passed per run.
- Merge-tree module coverage: 91%.
- Cleanup, stale-refresh, and shell-trigger mutations: killed.
- CWE-78 scan: 4 files scanned, 0 findings.
- Real merge-tree ratchet against `origin/main`: passed.
- Canonical pre-PR validation: 50 checks, 46 passed, 4 skipped, 0 failed.
