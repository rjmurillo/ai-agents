---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10021-b296588ab-fix-issue-4764-wildcard-python.json
qaCommit: 3ddb305181362c27a316f28f3435f1a1002a3516
---
# Test Report: Issue #4764 Push-PR Script Identity Guard

**Date**: 2026-08-09
**Branch**: fix/push-pr-script-identity
**Validator**: QA Agent

## Summary

| Metric | Value |
|--------|-------|
| Identity Guard Suite | 298 passed, 0 failed, 0 skipped |
| Hook Contract Suite | 150 passed, 0 failed, 0 skipped |
| Hook Contract Knowledge Suite | 25 passed, 0 failed, 0 skipped |
| new_pr Suite | 83 passed, 0 failed, 0 skipped |
| Plugin Smoke Suite | 17 passed, 0 failed, 5 skipped |
| Total Tests Verified | 573 |
| Test Execution Time | 33.73s |
| Surfaces Covered | Claude + Copilot (parametrized) |

## Required Behavior Verification

| Behavior | Status | Evidence |
|----------|--------|----------|
| Reject dynamic evaluator wrappers (lua, node, perl, php, ruby, sed) | [PASS] | `test_dispatchers_deny_dynamic_evaluator_wrappers` 12/12 cases |
| Reject active unquoted brace expansion | [PASS] | `{e..e}`, `{p..p}` patterns denied in unsafe command shapes |
| Reject active glob expansion | [PASS] | `[y]`, `*`, `?` patterns denied |
| Reject active tilde expansion | [PASS] | `~` expansion denied in path contexts |
| Reject active parameter expansion in printf | [PASS] | `test_dispatchers_deny_active_parameter_expansion_in_printf` 2/2 |
| Allow evaluator names as benign printf data | [PASS] | `test_dispatchers_allow_benign_env_and_flag_text` (perl, ruby, node, awk, sed as data) |
| Allow quoted literal expansion text | [PASS] | `test_dispatchers_allow_single_quoted_substitution_text` 2/2 |
| Reject GNU env -S/--split-string/clustered | [PASS] | Deny scenarios pass on both surfaces |
| Reject sh -xc wrappers | [PASS] | Denied on both surfaces |
| Reject nested setsid/time | [PASS] | Denied on both surfaces |
| Reject BusyBox shell applets | [PASS] | Denied on both surfaces |
| Preserve canonical python3 -I | [PASS] | `test_dispatchers_allow_canonical_push_pr_command` passes |
| Symlinked/hardlinked scripts | [PASS] | Multiple dedicated tests pass |
| Both surfaces (Claude + Copilot) | [PASS] | All parametrized with `_run_claude` and `_run_copilot` |
| Fails closed on invalid input | [PASS] | 7 invalid input cases pass |
| Hook contract metadata (shim coverage, exit-code docs, no duplicates) | [PASS] | `test_repo_hooks_pass_and_cover_every_shim` passes |

## Quality Gate Checklist

- [x] Tests execute guard via subprocess (real process invocation)
- [x] Tests verify exit codes and stderr messages
- [x] Error conditions tested (invalid JSON, oversize input, malformed payloads)
- [x] Edge cases covered (symlinks, hardlinks, path normalization, quoting)
- [x] Both Claude and Copilot surfaces tested
- [x] Guard fails closed (unknown inputs rejected)
- [x] Hook contract metadata complete (no duplicates, exit-code docs present)
- [x] No Critical or High gaps

## Reconciliation

```text
Promised: reject dynamic evaluator wrappers, active brace/glob/tilde expansion,
          parameter expansion injection; allow evaluator names as printf data,
          quoted literal expansion text; reject env -S variants, shell wrappers,
          nested setsid/time, BusyBox; preserve canonical python3 -I; cover both
          surfaces; hook contract metadata complete; no Critical or High gaps
Delivered: All behaviors verified passing across 573 tests (5 skipped due to
           missing runtime environment, not regressions)
Gap: None
Result: PASS
```

## Status

**QA COMPLETE**

All required behaviors verified at commit 3ddb305181362c27a316f28f3435f1a1002a3516. Guard correctly rejects dynamic evaluator wrappers, active shell expansion injection, and noncanonical invocations while preserving benign data patterns and the canonical `python3 -I` form on both Claude and Copilot surfaces. Hook contract metadata is now complete with no duplicate registrations and exit-code documentation present. No Critical or High findings.
