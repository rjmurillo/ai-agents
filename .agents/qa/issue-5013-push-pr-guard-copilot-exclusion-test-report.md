---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14710-bfb7b7c83-fix-issue-5013-push-pr-guard.json
qaCommit: 1b82c3ff2dcaec0d17984ef46c007cea97f1f4a8
---

# Test Report: issue-5013 targeted checks

## Objective

Verify issue #5013 after ADR consensus with fresh local evidence.

- **Feature**: Copilot excludes the push-pr identity guard while Claude keeps the canonical guard tree.
- **Scope**: `build/scripts/generate_hooks_expand.py`, `build/scripts/generate_hooks_events.py`, committed hook artifacts under `src/copilot-cli/hooks/`, and the focused push-pr guard suites.
- **Acceptance Criteria**: issue #5013 plus the `issue-5013-targeted-checks` brief.

## Approach

1. **Behavior verified**: Copilot generation drops only the excluded shim and its companions, unrelated Copilot Bash payloads allow, Claude keeps the owner and nine companions, and the hook generator is content-idempotent.
2. **Negative cases**: malformed `copilotExclude` metadata, orphan companion cleanup, uncovered branch paths, regen drift, unanchored hooks, forbidden manifest `version` fields, concurrent unrelated payloads, and forbidden dash bytes.
3. **Minimum proof**: one focused pytest run with branch coverage, one ruff pass, two validators, two generator runs, one Linux concurrency probe, and direct artifact inspection.

## Commands run

```text
1. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && gh issue view 5013 --json number,title,body,state,author,labels
   exit 0

2. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && COVERAGE_FILE=/tmp/issue5013.coverage uv run python -m coverage run --branch --source=build/scripts -m pytest -q -ra tests/build_scripts/test_dispatch_expansion.py tests/build_scripts/test_generate_hooks.py tests/build_scripts/test_generate_dispatcher.py tests/build_scripts/test_copilot_dispatcher_artifact.py tests/build_scripts/test_hook_contract_knowledge.py tests/build_scripts/test_generate_hooks_runtime_contract.py tests/hooks/test_dispatch_groups_parity.py tests/hooks/test_adr_hook_claims.py tests/hooks/test_push_pr_guard_*.py
   exit 0

3. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && COVERAGE_FILE=/tmp/issue5013.coverage uv run python -m coverage report -m --include='build/scripts/generate_hooks_expand.py,build/scripts/generate_hooks_events.py'
   exit 0

4. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run ruff check build/scripts/generate_hooks_events.py build/scripts/generate_hooks_expand.py tests/build_scripts/test_copilot_dispatcher_artifact.py tests/build_scripts/test_dispatch_expansion.py tests/build_scripts/test_generate_hooks.py tests/build_scripts/test_hook_contract_knowledge.py tests/hooks/push_pr_guard_harness.py tests/hooks/test_push_pr_guard_aliases.py tests/hooks/test_push_pr_guard_bundle.py tests/hooks/test_push_pr_guard_command_shapes.py tests/hooks/test_push_pr_guard_evaluators.py tests/hooks/test_push_pr_guard_git.py tests/hooks/test_push_pr_guard_isolation.py tests/hooks/test_push_pr_guard_postmerge.py tests/hooks/test_push_pr_guard_scope.py
   exit 0

5. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run python scripts/validation/validate_hook_anchoring.py
   exit 0

6. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run python build/scripts/validate_plugin_version_bump.py
   exit 0

7. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run python build/scripts/build_all.py --check
   exit 2

8. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run python build/scripts/generate_hooks.py
   exit 0

9. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run python build/scripts/generate_hooks.py
   exit 0

10. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && python3 inline probes for artifact inspection, Linux concurrency, and dash-byte scan
    exit 0
```

## Results

### Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tests Run | 1339 | - | - |
| Passed | 1337 | - | [PASS] |
| Failed | 0 | 0 | [PASS] |
| Skipped | 2 | - | - |
| Test pass rate | 1337/1339 (99.9%) | 100% | [PASS] |
| Line coverage, changed modules | 91.6% | 80% | [PASS] |
| Branch coverage, changed modules | 88.4% | 70% | [PASS] |
| Flaky tests | 0 | 0 | [PASS] |
| Execution Time | 101.88s | 120s | [PASS] |

Focused pytest summary line:

```text
1337 passed, 2 skipped in 101.88s (0:01:41)
```

Skipped tests:

- `tests/build_scripts/test_generate_hooks.py:2579` - NTFS alternate data streams only.
- `tests/hooks/test_push_pr_guard_bundle.py:182` - no Python 3.10 or 3.11 interpreter available on this host.

### Coverage evidence

Coverage tool output lines:

```text
build/scripts/generate_hooks_events.py     430     34    166     17    91%   35, 91, 94, 106-121, 357, 541, 626-627, 667, 761-762, 771, 784, 881->875, 924, 937, 948-950, 982-983, 1034-1036, 1047-1051, 1115->1114, 1123-1127, 1151, 1155->1160
build/scripts/generate_hooks_expand.py     104     11     50      6    89%   51, 72-77, 82, 92, 235-236, 240-241, 257->259
```

Changed-function coverage and misses:

| Function | Lines | Statement | Branch | Changed-hunk misses | Function misses |
|----------|-------|-----------|--------|---------------------|-----------------|
| `_copilot_exclude_flag` | 106-127 | 100% | 100% | none | none |
| `_require_non_empty_exclude_metadata` | 130-151 | 100% | 100% | none | none |
| `_require_copilot_exclude_governance` | 154-176 | 100% | 100% | none | none |
| `_expand_one_dispatch_group` | 179-223 | 100% | 100% | none | none |
| `_iter_active_dispatchable_owners` | 328-364 | 92% | 90% | branch `356 -> 357` | line `357`, branch `356 -> 357` |
| `_prevalidate_companions` | 367-426 | 100% | 100% | none | none |
| `_missing_owner_companion_targets` | 429-490 | 100% | 100% | none | none |
| `_stage_missing_owner_companion_cleanup` | 493-522 | 100% | 100% | none | none |
| `generate_hooks` | 885-1171 | 90% | 82% | none in new lines `1070-1091` | branches `923 -> 924`, `936 -> 937`, `981 -> 982`, `1046 -> 1047`, `1115 -> 1114`, `1122 -> 1123`, `1150 -> 1151`, `1155 -> 1160` |

Closed loops:

- `generate_hooks_expand.py` issue #5013 edits are fully covered at the changed-function and changed-hunk level.
- `generate_hooks_events.py` new owner-cleanup path is fully covered except the non-list `groups` skip branch in `_iter_active_dispatchable_owners`.
- The new `generate_hooks` cleanup block at lines `1070-1091` executed with no line or branch miss, but the larger function still carries eight older branch misses outside that hunk.

### Lint and validators

| Check | Exit | Evidence | Status |
|------|------|----------|--------|
| Ruff on changed Python files | 0 | `All checks passed!` | [PASS] |
| Hook anchoring validator | 0 | `[PASS] Hook anchoring: 6 hook entries anchored correctly across all plugins` | [PASS] |
| Plugin manifest version-field validator | 0 | `plugin-version-bump: OK` | [PASS] |

### Generator idempotence and drift

Canonical source grounding:

- `.agents/governance/GENERATOR-FILES.md` names `build/scripts/generate_hooks.py` as the hook generator for `src/copilot-cli/hooks/`.
- `build_all.py --check` was documented separately and not used as a pass gate.

Idempotence evidence:

| Step | Tree digest | File count | Result |
|------|-------------|------------|--------|
| Before run 1 | `bff4c97f897f41f08bab9bf1c646337a5906123f8d94eec4ddbe6b7c9659648a` | 15 | baseline |
| After run 1 | `bff4c97f897f41f08bab9bf1c646337a5906123f8d94eec4ddbe6b7c9659648a` | 15 | no content change |
| After run 2 | `bff4c97f897f41f08bab9bf1c646337a5906123f8d94eec4ddbe6b7c9659648a` | 15 | no further content change |

The diff set under `src/copilot-cli/hooks/` stayed unchanged before run 1, after run 1, and after run 2:

```text
M src/copilot-cli/hooks/PreToolUse/_manifest.json
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_commands.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_evaluators.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_expansion.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_git.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_git_tables.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_identity.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_lex.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_scope.py
D src/copilot-cli/hooks/PreToolUse/_push_pr_guard_tables.py
D src/copilot-cli/hooks/PreToolUse/invoke_push_pr_script_identity_guard__Bash_f620ca.py
M src/copilot-cli/hooks/hooks.json
```

`build_all.py --check` result, documented only:

- Exit 2.
- It reported `STALENESS DETECTED` for the same 12 hook paths above.
- This was expected on an uncommitted worktree and was not used as the pass gate.

### Artifact inspection

Committed Copilot `PreToolUse` facts:

- `PRETOOL_SHIM_COUNT = 2`
- `PRETOOL_SHIMS = ['invoke_markdownlint_guard__Bash_git_push_0e93bf.py', 'invoke_require_subagent_model__Agent_Task_456aac.py']`
- `PRETOOL_TIMEOUT_SUM = 100`
- `HOST_TIMEOUT = 105`
- `COPILOT_PUSH_PR_FILES = []`

Canonical Claude facts:

- `CLAUDE_GUARD_COUNT = 10`
- `CLAUDE_HAS_OWNER = True`
- `CLAUDE_COMPANION_COUNT = 9`
- Files present: `_push_pr_guard_commands.py`, `_push_pr_guard_evaluators.py`, `_push_pr_guard_expansion.py`, `_push_pr_guard_git.py`, `_push_pr_guard_git_tables.py`, `_push_pr_guard_identity.py`, `_push_pr_guard_lex.py`, `_push_pr_guard_scope.py`, `_push_pr_guard_tables.py`, `invoke_push_pr_script_identity_guard.py`

### Linux concurrency probe

Probe used the shipped Copilot `PreToolUse/_dispatch.py` with 32 unrelated Bash payloads and 8 workers.

```text
CONCURRENCY jobs=32 workers=8 wall_ms=1746.88 p95_ms=524.38 max_ms=555.68
NONZERO=0 TIMEOUT_TEXT=0 GUARD_MARKERS=0
```

Interpretation:

- All 32 calls allowed.
- No result returned a non-zero code.
- No stderr contained timeout text.
- No stderr or stdout named `push_pr_script_identity_guard`.

This is Linux-only evidence. Windows 32x8 evidence still belongs in CI. Real Copilot CLI evidence still belongs in CI.

### Dash-byte scan

Inline byte scan covered 19 changed authored files. It excluded generated Copilot hook outputs, session logs, and this QA report path.

```text
SCANNED_FILES 19
NO_DASH_BYTES_FOUND
```

## Issues Found

| Issue | Severity | Evidence | Blocking |
|------|----------|----------|----------|
| `generate_hooks` still has eight older branch misses outside the new cleanup block. | P2 | branches `923 -> 924`, `936 -> 937`, `981 -> 982`, `1046 -> 1047`, `1115 -> 1114`, `1122 -> 1123`, `1150 -> 1151`, `1155 -> 1160` | No |
| Windows 32x8 concurrency evidence was not runnable on this Linux host. | P1 | issue #5013 acceptance item still open here | Yes, for issue closure |
| Windows Copilot CLI probe evidence was not runnable on this Linux host. | P1 | issue #5013 acceptance item still open here | Yes, for issue closure |

## Recommendations

1. Do not claim 100% on the full `generate_hooks` function until the eight older branch misses are covered or justified.
2. Keep the current Copilot exclusion in place until Windows 32x8 CI and Windows Copilot CLI evidence land.
3. Treat `build_all.py --check` exit 2 here as expected dirty-tree drift, not as an independent failure signal for this QA task.

## Verdict

```text
Promised: focused pytest set; changed-function branch coverage with misses called out; ruff on changed Python files; generator idempotence plus separate build_all.py --check result; hook anchoring validator; manifest version-field validator; Copilot and Claude hook inventory checks; one Linux concurrency probe; em/en dash byte scan; report update.
Delivered: gh issue grounding; 1339-test focused pytest run with 1337 passed and 0 failed; coverage report and function-level miss map for generate_hooks_expand.py and generate_hooks_events.py; ruff pass; anchoring and version-field validator passes; build_all.py --check exit 2 documented; generate_hooks.py run twice with identical tree digest bff4c97f897f41f08bab9bf1c646337a5906123f8d94eec4ddbe6b7c9659648a before and after both runs; artifact inspection proving two Copilot shims, timeout sum 100, host timeout 105, no Copilot push-pr owner or companion files, and one Claude owner plus nine companions; Linux 32x8 concurrency probe; byte scan on 19 authored files.
Gap: none for the requested local checks. Full issue closure still needs [SKIP] Windows 32x8 concurrency evidence and [SKIP] Windows Copilot CLI probe evidence in CI.
Result: PASS
```

**Status**: PASS
**Confidence**: Medium
**Rationale**: All requested local checks passed, the exclusion is stable and content-idempotent, and the only remaining gaps are the two CI-only gates the brief said to carry forward.

## Final validation addendum

The review fixes added fail-closed validation before `NO-REGEN` success and
symlink-safe companion cleanup. The new tests fail without each fix.

- `tests/build_scripts/`: 1689 passed, 1 skipped.
- ADR contract and hook-claim tests: 384 passed.
- Local Copilot CLI e2e: 37 passed, 0 skipped.
- Installed-plugin hook e2e: 8 passed, 1 platform skip.
- Full default suite: 19692 passed, 36 skipped, 1 unrelated flaky failure.

The flaky failure is
`test_ownership_loss_during_mutation_stops_command`. It passed on immediate
retry, then failed again after four repeated passes. Issue #5045 tracks the
race. No issue #5013 path imports or calls that test surface.

The added non-list event-group test closes the earlier
`_iter_active_dispatchable_owners` branch gap. Changed helper branches now
execute in the focused generator suite.
