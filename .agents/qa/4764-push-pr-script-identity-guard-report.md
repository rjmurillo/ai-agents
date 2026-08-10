---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10021-b296588ab-fix-issue-4764-wildcard-python.json
qaCommit: 8cb44c28c81092b075fd4dc3d2c0daf93f5e931b
---
# Test Report: Issue #4764 Push-PR Script Identity Guard

**Date**: 2026-08-09
**Branch**: fix/push-pr-script-identity
**Validator**: QA Agent

## Summary

| Metric | Value |
|--------|-------|
| Identity Guard Suite | 672 passed, 0 failed, 0 skipped |
| Dispatch Parity Suite | 13 passed, 0 failed, 0 skipped |
| Plugin Path Suite | 7 passed, 0 failed, 0 skipped |
| Total Tests Verified | 692 |
| Test Execution Time | 81.91s |
| Surfaces Covered | Claude + Copilot (parametrized) |

## Required Behavior Verification

| Behavior | Status | Evidence |
|----------|--------|----------|
| Reject dynamic evaluator wrappers and aliases | [PASS] | Table-driven matrix covers interpreters, shells, loaders, command delegators, renamed binaries, and shebang wrappers |
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
| Fails closed on invalid input | [PASS] | Invalid payload, parser, wrapper, Git, and environment cases pass |
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
Delivered: All behaviors verified passing across 692 post-merge runtime tests
           with no failures or skips
Gap: None
Result: PASS
```

## Status

**QA COMPLETE**

All required behaviors verified at commit 98c2346577eedd1319f75032701ddb02179fbe0c. Guard rejects evaluator wrappers, command delegation, loader injection, Git execution channels, parser desynchronization, and noncanonical invocations while preserving benign commands and the canonical `python3 -I` form on both surfaces. Security review, independent GPT-5.6 Sol review, and five-axis code review returned approved with no Critical or High findings.

PR #4825 Copilot review 4894113215 later found two defects this round missed. See `.agents/qa/pr-4825-review-4894113215-report.md`.
