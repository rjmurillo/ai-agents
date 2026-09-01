---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-19-session-99921-b9d55af7c-retire-pretooluseposttooluseposttoolusefailure-hooks-windowsdefender-per-spawn.json
qaCommit: 62fe031767a35407e1f13026ecb2abc18de8a44f
---

# QA: ADR-097 zero tool-use hooks

**Branch**: `claude/tool-use-hooks-perf-ht7zhx`
**Date**: 2026-08-19
**Subject**: retirement of all five tool-call hooks, the generated Copilot
dispatcher, and `post_tool_call_memory.py`; the validator and CI-gate
dispositions that follow.

## Verdict

PASS. Full suite green; every new or changed gate carries a proven negative control.

## What was verified, and how

### Full suite

```text
uv run --frozen python -m pytest tests/hooks/ tests/build_scripts/ tests/ci/ \
    tests/validation/ tests/evals/ -q
8407 passed, 22 skipped in 295.74s
```

The full suite, run by the `python-tests` pre-push job over all of `tests/`,
then surfaced two more failures that selection had missed:
`test_hook_plugin_guards.py::test_copilot_pretooluse_has_no_unregistered_matcher_shims`
(read the deleted `_manifest.json` unconditionally) and
`test_dogfood_copilot_plugin_drift.py::test_check_flags_drift_on_the_real_shipped_tree`
(picked its mutation target with `rglob("*.py")[0]`, now empty). Both were fixed
by keeping the guard armed for the empty case rather than deleting it: an absent
manifest reads as an empty registered set, and the drift test mutates the first
file of any type after asserting the tree is non-empty. Final:

```text
27683 passed, 73 skipped
```

The lesson for the next reader: a subdirectory selection is not the suite. Two
guards over the shipped tree live in `tests/` root and were invisible to the
five-directory selection used during development.

CI then surfaced a third tier the local suite cannot reach at all:
`scripts/ci/vanilla_hook_guard.py` (Docker- and PowerShell-driven) and
`tests/integration/test_e2e_install.py::test_hook_command_paths_resolve_case_sensitively`
both assumed at least one `PreToolUse` hook is always registered. The guard
raised "no bash/powershell command for event PreToolUse" before reaching the
degrade-gracefully check it exists to run.

Both now treat zero registered hooks as "nothing to prove vanilla-safe", a
vacuous pass matching `validate_hook_anchoring.py`. Verified by driving the
guard directly on all four paths, not by reading the diff:

| Input | Expected | Observed |
|---|---|---|
| real zero-hook tree | exit 0 | exit 0, "VANILLA GUARD PASSED (vacuous)" |
| `hooks` is a list, not a mapping | exit 1 | exit 1, "malformed 'hooks' mapping" |
| manifest absent | exit 1 | exit 1, names the unreadable path |
| `linux-container` with no `--image` | exit 2 | exit 2, config error (ADR-035 precedence preserved) |

`tests/ci/test_vanilla_hook_guard.py` and `tests/integration/test_e2e_install.py`:
77 passed, 1 skipped.

So the coverage tiers that missed this change, in order of increasing distance
from the developer: a five-directory pytest selection, the full local suite, and
CI-only Docker/PowerShell gates. Only the third tier is genuinely unreachable
locally; the first two were a selection mistake.

Before disposition the same selection reported **45 failed**. Every failure was
traced to a subject ADR-097 deleted, and each was dispositioned individually
rather than by deleting whole files on sight: two files went entirely (their
whole subject was the committed dispatcher), fourteen individual cases were
removed from otherwise-live files, and three invariants were preserved by moving
them to a surviving subject.

### Gates that were red and are now green

| Gate | Before | After |
|---|---|---|
| `scripts/validation/validate_hook_anchoring.py` | exit 2, "no hook events in src/copilot-cli/hooks/hooks.json" | exit 0, "0 hook entries anchored correctly across all plugins" |
| `scripts/ci/test_installed_plugin_hooks.py` | exit 1 by design on an empty manifest | exit 0, "zero registered hook events and zero shipped dispatchers" |
| `scripts/ci/taste_count_ratchet.py` | STALE BASELINE 583 vs 576 | OK, baseline lowered to 576 with `--update` |
| `scripts/ci/cli_exit_contract_ratchet.py` | count above baseline after a covering test was deleted | OK, count == baseline 18 |

### Negative controls, because a gate that cannot fail is not a gate

Each new or changed gate was driven against input it must reject, and the
rejection was observed rather than assumed:

| Control | Expected | Observed |
|---|---|---|
| `validate_hook_anchoring`: manifest with no `hooks` key | exit 2 | exit 2, "malformed or missing" |
| `validate_hook_anchoring`: `hooks` value is a list, not a mapping | exit 2 | exit 2, "malformed or missing" |
| `validate_hook_anchoring`: unmutated generated seed | pass | 1 entry, 0 violations (control for the six drift cases) |
| `test_installed_plugin_hooks`: dispatcher on disk, zero events registered | exit 1 | exit 1, orphan named |
| `test_installed_plugin_hooks`: unparseable `hooks.json` | exit 1 | exit 1 |
| `test_installed_plugin_hooks`: event registered, no dispatcher | non-zero | exit 1, "FAIL: no dispatcher" |
| re-accretion ratchet: add a `PreToolUse` entry + plugin-surface group | fail | 2 failed, 12 passed |
| re-accretion ratchet: restore | pass | 14 passed |

The re-accretion mutation was run with `__pycache__` cleared between mutate and
restore, per `.claude/rules/testing.md` SHOULD 8.

### Invariants preserved rather than deleted

- **#4672, "a registered event with no dispatcher must fail"**: moved from
  `tests/hooks/test_partial_upgrade_degrades.py` (which drove the deleted
  shipped tree) to `tests/ci/test_installed_plugin_zero_hook_state.py`, driven
  as a real subprocess against a synthetic registering tree. This is the control
  proving the guard's non-empty path did not quietly become a no-op.
- **#5013, wrong-deny blast radius**: the regression pin was deleted with its
  subject. `tests/hooks/test_zero_tool_use_hooks.py` replaces the invariant it
  protected by pinning the zero-registration state across all four per-call
  events and all three manifests.
- **Vacuity guarding**: the deleted `test_the_customer_value_check_examines_a_nonempty_surface`
  guarded against a zero-file corpus passing silently. The new ratchet carries
  its own equivalent (`test_the_ratchet_examines_the_files_it_claims_to`) plus a
  negative control keeping session-scoped hooks legal.

### Regeneration

`uv run --frozen python build/scripts/build_all.py` is idempotent on the empty
case: re-running after a clean run produces no further diff. It reports "Found 0
Claude event(s)" and prunes the Copilot dispatcher rather than leaving a stale
copy.

## Serena MCP was unavailable; the documented fallback was used

`sessionStart.serenaActivated`, `sessionStart.serenaInstructions`, and
`sessionEnd.serenaMemoryUpdated` attest to `mcp__serena__*` calls. No Serena MCP
tool was registered in this session, confirmed twice via `ToolSearch` (a
`select:` lookup for `mcp__serena__activate_project` and a keyword search), both
returning zero serena-prefixed tools.

AGENTS.md defines a fallback for exactly this case ("fallback:
`.serena/memories/<name>.md`"), and it was executed: `memory-index.md`,
`usage-mandatory.md`, `hooks/require-subagent-model-gate.md`, and
`decision-memory-hooks-registered-directly-not-grouped.md` were read directly,
and the last two were updated with supersession markers per
`.claude/rules/curating-memories.md`. The session log records the fallback rather
than claiming an MCP call, matching the pattern already on `main` in
`2026-08-19-session-99919-...json`.

`scripts/validate_session_json.py` now reports `[PASS] Session log is valid`.

## Scope not covered

- No real-CLI smoke ran for the empty Copilot plugin. The
  `installed-plugin-hook-guard.yml` matrix (three platforms, positive and
  degraded) covers it in CI and is the intended evidence; it was not run locally.
- The Windows and Defender per-spawn cost that motivates ADR-097 is
  owner-reported and remains unmeasured here, as ADR-097's Context section states.

## Addendum: two CI-only gates the local suite could not exercise

The "no real-CLI smoke ran" scope gap above was not hypothetical. The PR's
first CI run (head `2f14b88d`) surfaced two failures that no path run against
`tests/` locally, because both drive real Docker containers or a
PATH-scrubbed PowerShell that this sandbox cannot run:

| Check | Failure | Root cause |
|---|---|---|
| `Vanilla Linux (no Python)`, `Vanilla Windows (no interpreter resolvable)` (`Plugin Hook Guard Result`) | `VANILLA GUARD FAILED: no bash/powershell command for event PreToolUse` | `scripts/ci/vanilla_hook_guard.py` asserted at least one `PreToolUse` hook command always exists, before it ever reached the degrade-gracefully assertion it exists to run. |
| `pytest (bulk-nested)`, `Run Windows path-contract tests`, `Run Python Tests` | `AssertionError: expected at least one hook script command path` in `tests/integration/test_e2e_install.py::TestInstalledHooks::test_hook_command_paths_resolve_case_sensitively` | Same assumption: a case-sensitivity check over hook script paths asserted the collected list was non-empty. |

Both are `tests/integration/` and `tests/ci/` Docker- or CLI-driven paths, a
different selection than the `tests/hooks/ tests/build_scripts/ tests/ci/
tests/validation/ tests/evals/` run recorded above, and neither ran in the
`python-tests` pre-push job either (that job also skips these; confirmed by
running the exact two test files locally after the fix, both green, and by
`pre_pr.py --quick` passing clean afterward).

Fix (commit `ef125dc2176fb7c06a6987bbdc7ebd32c2c28856`, 3 files): zero
`PreToolUse` hooks registered is read as "nothing to prove vanilla-safe"
(vacuous pass), matching `validate_hook_anchoring.py`'s existing zero-is-valid
treatment. A missing or malformed manifest still fails closed. New negative
controls: `test_event_is_registered_raises_on_a_malformed_hooks_mapping`,
`test_main_fails_when_the_manifest_is_missing`. Re-verified locally:

```text
uv run --frozen python -m pytest tests/ci/test_vanilla_hook_guard.py \
    tests/integration/test_e2e_install.py -q
71 passed, 1 skipped
uv run --frozen python scripts/validation/validate_hook_anchoring.py
[PASS] Hook anchoring: 0 hook entries anchored correctly across all plugins
```

`pre_pr.py --quick` after this commit: 56 of 57 validations pass; the one
failure was this QA report's own staleness check (`.agents/qa/`, `.agents/sessions/`,
and `.agents/memory/episodes/` are QA-evidence-exempt paths, so rebinding
`qaCommit` above to this commit and appending this addendum clears it without
re-triggering staleness on itself).

## Addendum 2: nine post-review defects, verified and fixed before push

Copilot's automated PR review (`pullrequestreview-4977497778`, head
`aee51e154`) found nine defects, none touching this ADR's decision. Each was
verified against the live source before editing, per this repo's evidence
standard, not taken on the reviewer's word:

| # | Finding | Verified how | Fix |
|---|---|---|---|
| 1 | `scripts/ci/vanilla_hook_guard.py`: `event_is_registered` read `{"PreToolUse": {}}` as "not registered" instead of malformed | Read the function; `isinstance(entries, list)` on a dict is `False`, so the branch fell through to the not-registered return | Split absent/list/non-list into three cases; non-list now raises `GuardError` |
| 2 | `scripts/ci/test_installed_plugin_hooks.py`: `_manifest_is_readable` accepted the same malformed shape | Read `_registered_events`; its list comprehension silently drops a non-list entry, so the readable check never caught it | `_manifest_is_readable` now requires every present event value to be a list |
| 3 | `tests/hooks/test_zero_tool_use_hooks.py`: ratchet never scanned `.github/hooks/*.json` or the generated `src/copilot-cli/hooks/hooks.json` | Read the ratchet; confirmed it reads only `.claude/hooks/hooks.json`, `dispatch_groups.json`, and `.claude/settings.json` | Added both scans (Copilot native + PascalCase casing for `.github/hooks/`) plus a guard-the-guard test |
| 4 | `agent-harness-reference/SKILL.md`: "Lib bootstrap" row claimed a manifest walk-up to `.claude-plugin/plugin.json` | Read `invoke_context_loader.py`; the fallback is a fixed relative parent-walk, never a manifest search | Rewrote the row to the actual fallback |
| 5 | `agent-harness-reference/SKILL.md`: "Shipped registrations" section and two "Event policy" rows described pre-ADR-097 counts and an "Active" dispatcher | Re-counted `.claude/hooks/hooks.json`, `src/copilot-cli/hooks/hooks.json`, `.claude/settings.json` directly | Rewrote to the current zero state |
| 6 | `scripts/ci/vanilla_hook_guard.py:136` (`event_is_registered`), same bug class as #1 | Same code path as #1, distinct call site | Same fix as #1 |
| 7 | `ai-agents-architecture-contract/SKILL.md`: "Copilot dispatcher" row contradicted the "0 events, 0 registrations" row 8 lines above | Read both rows in the same table | Marked the dispatcher row retired |
| 8 | `ADR-071`: claimed the two SessionStart dispatch groups in `.claude/settings.json` "remain subject to" `validate_hook_anchoring.py`'s plugin-root invariant | Read `validate_hook_anchoring.py`; `_CLAUDE_REL` only reads `.claude/hooks/hooks.json`, never `.claude/settings.json` | Rewrote to name the real anchor (`$CLAUDE_PROJECT_DIR`) and the real scope |
| 9 | `hook-protocol.md`: claimed all three memory scripts are "not currently registered" | Read `invoke_memory_recall.py` and `invoke_memory_reflection.py`; both are thin wrappers registered in `.claude/settings.json` | Rewrote to name the two live pipelines and the one genuinely-retired script |

Findings 1, 2, and 6 are the same malformed-manifest defect shape in two
files; each fix ships with its own negative-control test rather than a shared
helper, since the two callers (`vanilla_hook_guard.py`, a CI-only Docker/
PowerShell driver; `test_installed_plugin_hooks.py`, an in-process certifier)
have no existing shared module to route through.

Targeted tests for the three edited Python files: 65 passed (0 failed).
Broader selection (`tests/hooks/ tests/build_scripts/ tests/ci/
tests/validation/`): 8069 passed, 22 skipped, 0 failed. `validate_hook_anchoring.py`
and `check_skill_md_portability.py` (after trimming a duplicate citation that
grew the vendor-portability marker count from 31 to 32 refs) both pass clean.

## Addendum 3: merge conflict against `origin/main`, resolved

`origin/main` advanced past this branch's fork point (PR #5170, "stop
injecting stale HANDOFF.md at session start"). `merge-tree-ratchet` in
`Count Ratchets` correctly refused to evaluate count deltas against an
unmerged tree rather than silently comparing against a stale base. One real
conflict, in `CONTRIBUTING.md`'s lifecycle-hooks table: this branch had
already dropped the `PostToolUse`/`invoke_observation_sync.py` row (ADR-097)
and main had reworded the `SessionStart` row to drop "HANDOFF.md +" (#5170).
Resolved by keeping this branch's ADR-097 state (no `observation_sync` row)
with main's reworded `SessionStart` text, combining both independent
changes rather than picking one side. `invoke_context_loader.py` and
`dispatch_groups.json` auto-merged clean; verified the merged
`dispatch_groups.json` parses as valid JSON and re-verified the
`agent-harness-reference/SKILL.md` "Lib bootstrap" row's line citation
against the merged file, which had shifted from lines 34-41 to 38-45 because
main's docstring edit added four lines above the cited fallback code.
`Count Ratchets` passed clean after the merge; re-ran `pre_pr.py --quick` to
confirm.
