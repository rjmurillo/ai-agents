---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10021-b296588ab-fix-issue-4764-wildcard-python.json
qaCommit: 5f1f139c5a1b2a0acb1190963fdaae6b0d39ec74
---
# Test Report: Issue #4764 Push-PR Script Identity Guard

**Date**: 2026-08-09
**Branch**: fix/push-pr-script-identity
**Validator**: QA Agent

## Summary

| Metric | Value |
|--------|-------|
| Guard Test Suite | 270 passed, 0 failed, 0 skipped |
| Related Suites | 210 passed (dispatch, parity, new_pr) |
| Total Tests Verified | 480 |
| Test Execution Time | 35.2s |
| Surfaces Covered | Claude + Copilot (parametrized) |

## Required Behavior Verification

| Behavior | Status | Evidence |
|----------|--------|----------|
| Reject GNU env -S | [PASS] | `env -S 'python3 -I attacker/x'` denied, line 258 |
| Reject --split-string | [PASS] | `env --split-string='python3 -I attacker/x'` denied, line 259 |
| Reject abbreviated --split | [PASS] | `env --split='python3 -I attacker/x'`, `env --spl=...` denied, lines 262-263 |
| Reject clustered -S | [PASS] | `env -iS 'python3 -I attacker/x'` denied, line 261 |
| Reject unknown env options | [PASS] | Guard returns rc=2 with "unsupported env options" (manually verified; no dedicated test name) |
| Reject sh -xc wrappers | [PASS] | `sh -xc 'python3 attacker/x'` denied, line 285 |
| Reject nested setsid/time | [PASS] | `setsid python3 ...`, `time python3 ...` denied, lines 291, 402-405 |
| Reject BusyBox shell applets | [PASS] | `busybox sh -xc ...`, `setsid busybox ash -xc ...` denied, lines 292-293 |
| Preserve canonical python3 -I | [PASS] | `test_dispatchers_allow_canonical_push_pr_command` passes on both surfaces |
| Brace expansion | [PASS] | `{e..e}`, `{p..p}` patterns tested in deny scenarios, lines 399-404 |
| Globbing | [PASS] | `[y]`, `*`, `?` patterns tested, lines 402, _SHELL_EXPANSION_MARKERS |
| Variable expansion | [PASS] | `${BASH_VERSION:+pyt}hon3`, `$PY` tested, lines 401, 399 |
| Command substitution | [PASS] | `$(echo bypass)`, backtick forms denied, lines 394-395 |
| Alternate interpreters | [PASS] | `pypy3`, `python`, `py` tested in deny scenarios |
| Quoting | [PASS] | Single-quoted safe text allowed; incomplete quoting rejected |
| Normalization | [PASS] | `test_dispatchers_deny_normalized_alias_of_runtime_script` (path traversal) |
| Links (sym/hard) | [PASS] | Symlinked scripts, parent symlinks, hardlinks all tested |
| Benign commands | [PASS] | `test_dispatchers_allow_benign_env_and_flag_text`, `test_dispatchers_allow_unrelated_shell_expansion` |
| Both surfaces | [PASS] | Tests parametrized with `_run_claude` and `_run_copilot` runners |

## Quality Gate Checklist

- [x] Tests execute guard via subprocess (real process invocation, not mocks)
- [x] Tests verify exit codes and stderr messages
- [x] Error conditions tested (invalid JSON, oversize input, malformed payloads)
- [x] Edge cases covered (symlinks, hardlinks, path normalization, quoting)
- [x] Both Claude and Copilot surfaces tested
- [x] Guard fails closed (unknown inputs rejected)

## Findings

### Low Severity

| Finding | Detail |
|---------|--------|
| No explicit test for "unsupported env options" error path | The `_env_command_index` branch for unknown `-` flags (line 305) is exercised at runtime but no parametrized test case asserts this specific error message. The guard still fails closed. |

### No Critical or High Findings

## Reconciliation

```text
Promised: reject env -S/--split-string/--split/clustered -S/unknown env options,
          shell evaluators (sh -xc), nested setsid/time, BusyBox applets,
          preserve canonical python3 -I, cover brace/glob/variable/cmdsub/
          alt-interpreters/quoting/normalization/links/benign on both surfaces
Delivered: All behaviors verified passing across 270 guard tests + 210 related tests
Gap: One low-severity gap (no named test for unknown env option error message)
Result: PASS
```

## Status

**QA COMPLETE**

All required behaviors verified. Guard correctly rejects noncanonical invocations and preserves the exact legitimate `python3 -I` form on both Claude and Copilot surfaces. No Critical or High findings.
