---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10033.json
qaCommit: b555a6cbbe6edf0a2014461e94bbd4866ef5b952
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

## Round 2: PR #4825 Copilot review 4894113215

**Date**: 2026-08-10

The review found two defects the first round missed and one stale document
inventory. Each verdict was reverified against the tree before any prescribed
fix was applied.

### Finding 1: guard applied policy before relevance (CONFIRMED)

Measured by driving the committed guard script with the host payload shape,
22 commands unrelated to `new_pr.py` and 11 `new_pr.py` attempts.

| Measurement | Before | After |
|-------------|--------|-------|
| Unrelated commands denied | 15 of 22 | 0 of 22 |
| `new_pr.py` attempts denied | 11 of 11 | 11 of 11 |

Denied before the fix: `git status && git diff`, `bash -c`, `sh -c`, `node -e`,
`perl -e`, an unrelated `python3` script, `uv run pytest`, a pipeline,
`git fetch`, `make`, `npm`, `eval`, an `LD_PRELOAD` prefix, a glob, `python -c`.
Installing the plugin disabled normal Bash work outside `/push-pr`.

The second row is the negative control: a scope gate that let a `new_pr.py`
attempt through would show a nonzero allowed count there.

### Finding 2: unrun validators reported as a clean pass (CONFIRMED)

`new_pr.py` routed three repository-local detectors through a helper that
ignored all three arguments and always returned `False`. Output claimed
"scripts/ is changed or dirty" on a clean branch, recorded nothing, and
summarized as "All pre-creation validations passed!".

### Finding 3: local settings inventory overstated (CONFIRMED)

Four documents claimed eight registrations across six events. The documented
provenance command prints `.claude/settings.json 5 7`.

### Verification

| Suite | Result |
|-------|--------|
| `tests/hooks/` | pass |
| `tests/build_scripts/` | pass |
| `tests/test_plugin_path_resolution.py` | pass |
| `tests/test_new_pr.py` | pass |
| Combined | 3254 passed, 1 skipped |
| `ruff check` on changed Python | clean |
| `build/scripts/build_all.py --check` | exit 0 |

### Coverage added

- `test_dispatchers_allow_commands_outside_guard_scope` (22 commands, both surfaces)
- `test_dispatchers_deny_commands_inside_guard_scope` (13 preserved bypass vectors, both surfaces)
- `test_dispatchers_allow_dynamic_launcher_that_never_names_the_script` (pins the accepted residual)
- `test_trusted_digests_match_the_shipped_bundle` (digest drift gate, both surfaces)
- `TestRepositoryValidatorTrust` (clean branch, changed `scripts/`, summary text, no subprocess spawned)

### Accepted residual

A command that reconstructs the path at runtime without naming it is outside
the detection surface. The guard bounds the identity of named push-pr
invocations; it is not a Python or shell sandbox. An actor able to run
arbitrary code does not need `new_pr.py` to open a pull request. Recorded in
the guard module docstring, in `probe-evidence.md` section 7a, and pinned by a
test so it stays a decision rather than a discovery.

**Result**: PASS
