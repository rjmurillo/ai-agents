---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14710-bfb7b7c83-fix-issue-5013-push-pr-guard.json
qaCommit: defe0a525d33eede3a1bbcf04f4bd0bbe15f18b0
---

# Test Report: issue-5013 targeted checks

## Objective

Verify final SHA `defe0a525d33eede3a1bbcf04f4bd0bbe15f18b0` for issue #5013.

- **Feature**: Copilot excludes the push-pr identity guard while Claude keeps the canonical guard tree.
- **Scope**: `build/scripts/generate_hooks_expand.py`, `build/scripts/generate_hooks_events.py`, committed hook artifacts under `src/copilot-cli/hooks/`, and the focused push-pr guard suites.
- **Acceptance Criteria**: issue #5013 plus the `issue-5013-targeted-checks` brief. Windows 32x8 load evidence and a Windows Copilot CLI probe still remain issue-closure gates.

## Approach

1. **Behavior verified**: Copilot ships no push-pr owner or companion files, Claude keeps the owner plus nine companions, generated artifacts match the committed tree, and the focused generator and contract suites pass on the final SHA.
2. **Negative cases**: malformed `copilotExclude` metadata, NO-REGEN behavior, symlink-safe cleanup, orphan companion cleanup, real Copilot CLI loading, and unrelated full-suite flake attribution.
3. **Minimum proof**: one exact focused rerun with coverage, one clean `build_all.py --check`, one committed-artifact inspection, targeted contract suites, real Copilot CLI probes, and one full-suite verification pass with the unrelated race called out.

## Commands run

```text
1. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && COVERAGE_FILE=/tmp/review5013.coverage uv run python -m coverage run --branch --source=build/scripts -m pytest -q -ra tests/build_scripts/test_dispatch_expansion.py tests/build_scripts/test_generate_hooks.py tests/build_scripts/test_generate_dispatcher.py tests/build_scripts/test_copilot_dispatcher_artifact.py tests/build_scripts/test_hook_contract_knowledge.py tests/build_scripts/test_generate_hooks_runtime_contract.py tests/hooks/test_dispatch_groups_parity.py tests/hooks/test_adr_hook_claims.py tests/hooks/test_push_pr_guard_*.py
   exit 0

2. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && COVERAGE_FILE=/tmp/review5013.coverage uv run python -m coverage report -m --include='build/scripts/generate_hooks_expand.py,build/scripts/generate_hooks_events.py'
   exit 0

3. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run pytest -q -ra tests/build_scripts
   exit 0

4. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run pytest -q -ra tests/build_scripts/test_hook_contract_knowledge.py tests/hooks/test_adr_hook_claims.py
   exit 0

5. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && uv run python build/scripts/build_all.py --check
   exit 0

6. cd /home/richard/src/GitHub/rjmurillo/ai-agents-issue-5013 && python3 inline artifact inspection for committed Copilot and Claude hook inventories
   exit 0

7. RUN_CLI_E2E=1 uv run pytest tests/e2e/test_cli_hook_e2e.py tests/e2e/test_plugin_load_smoke.py -x -rs
   exit 0

8. RUN_INSTALLED_PLUGIN_HOOK_E2E=1 uv run pytest tests/e2e/test_installed_plugin_hook_e2e.py -x -rs
   exit 0
```

Additional final-SHA validation evidence:

- Claude-only rename suite: 455 passed, 1 skipped.
- Runtime contract suite: 171 passed.
- Full suite: 19692 passed, 36 skipped, 1 unrelated reproducible flaky race tracked as #5045.
- Pre-PR validation: 51/51 passed.

## Results

### Summary

| Check | Value | Status |
|------|-------|--------|
| Focused exact rerun | 1342 passed, 2 skipped in 133.11s | [PASS] |
| Coverage, changed modules | `generate_hooks_events.py` 92%, `generate_hooks_expand.py` 89% | [PASS] |
| `build_all.py --check` | exit 0 on a clean committed tree | [PASS] |
| Review-fix build scripts | 1689 passed, 1 skipped | [PASS] |
| Claude-only rename suite | 455 passed, 1 skipped | [PASS] |
| ADR contract and hook claims | 384 passed | [PASS] |
| Runtime contract | 171 passed | [PASS] |
| Local Copilot CLI e2e | 37 passed | [PASS] |
| Installed-plugin hook e2e | 8 passed, 1 platform skip | [PASS] |
| Pre-PR validation | 51/51 passed | [PASS] |
| Full suite | 19692 passed, 36 skipped, 1 unrelated reproducible race tracked as #5045 | [FLAKY] |

Focused pytest summary line:

```text
1342 passed, 2 skipped in 133.11s (0:02:13)
```

Skipped tests:

- `tests/build_scripts/test_generate_hooks.py:2704` - NTFS alternate data streams only.
- `tests/hooks/test_push_pr_guard_bundle.py:182` - no Python 3.10 or 3.11 interpreter available on this host.

### Coverage evidence

Coverage tool output lines. These are the full remaining misses on the final SHA:

```text
build/scripts/generate_hooks_events.py     464     33    174     16    92%   36, 92, 95, 107-122, 444-445, 484->491, 660, 745-746, 786, 880-881, 890, 903, 1000->994, 1043, 1056, 1067-1069, 1101-1102, 1162-1164, 1175-1179, 1246->1245, 1282, 1286->1291
build/scripts/generate_hooks_expand.py     104     11     50      6    89%   51, 72-77, 82, 92, 235-236, 240-241, 257->259
```

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

### Flaky test note

The only known unstable result in the final full-suite run is unrelated to issue #5013:

| Test | Scope | Tracking | Status |
|------|-------|----------|--------|
| `test_ownership_loss_during_mutation_stops_command` | Reproducible race outside the push-pr exclusion path | #5045 | [FLAKY] |

## Issues Found

| Issue | Severity | Evidence | Blocking |
|------|----------|----------|----------|
| Windows 32x8 load and latency evidence is still missing from this report. | P1 | ADR-085 issue-closure gates still require the Windows 32x8 run and its p95 and max latency budget. | Yes, for issue closure |
| Windows Copilot CLI probe evidence is still missing from this report. | P1 | ADR-085 issue-closure gates still require a real Windows Copilot CLI probe. | Yes, for issue closure |
| One unrelated reproducible race remains in the full suite. | P2 | `test_ownership_loss_during_mutation_stops_command` is tracked separately as #5045 and is outside issue #5013 code paths. | No |

## Recommendations

1. Keep the Copilot exclusion in place until the Windows 32x8 and Windows Copilot CLI gates land.
2. Use the fresh coverage lines above when citing remaining misses. Do not reuse the stale pre-final coverage map.
3. Keep #5045 separate from issue #5013 triage and closure.

## Verdict

```text
Promised: refresh the issue #5013 QA report for final SHA defe0a525d33eede3a1bbcf04f4bd0bbe15f18b0 with the exact focused rerun, fresh coverage, clean build_all result, final suite summaries, committed-artifact facts, and the remaining Windows closure gates carried forward.
Delivered: exact focused rerun with 1342 passed and 2 skipped in 133.11s; fresh coverage lines for generate_hooks_events.py at 92% and generate_hooks_expand.py at 89% with all remaining misses named; build_all.py --check exit 0 on a clean committed tree; tests/build_scripts at 1689 passed and 1 skipped; ADR contract and hook claims at 384 passed; Claude-only rename suite at 455 passed and 1 skipped; runtime contract at 171 passed; local Copilot CLI e2e at 37 passed; installed-plugin hook e2e at 8 passed and 1 platform skip; full suite at 19692 passed, 36 skipped, and 1 unrelated reproducible race tracked as #5045; pre-PR validation at 51/51 passed; committed artifact inspection confirming two Copilot shims, timeout sum 100, host timeout 105, no Copilot push-pr files, and one Claude owner plus nine companions.
Gap: none for this report refresh. Full issue closure still needs [SKIP] Windows 32x8 load evidence and [SKIP] a Windows Copilot CLI probe.
Result: PASS
```

**Status**: PASS
**Confidence**: Medium
**Rationale**: Final-SHA local, contract, e2e, and pre-PR evidence now agree; the only remaining gates are the two Windows closure checks carried forward from issue #5013.
