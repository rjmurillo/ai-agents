---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-19-session-99921-b9d55af7c-retire-pretooluseposttooluseposttoolusefailure-hooks-windowsdefender-per-spawn.json
qaCommit: 5a2de5f4b0148d19004da39a229d83f395da0766
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
