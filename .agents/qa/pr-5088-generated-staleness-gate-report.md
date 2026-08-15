---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5079.json
qaCommit: b80917d8f179fe8de4c6ab33f4c9645d17812870
---

# QA report: generated-artifact staleness gate (PR #5088, issue #5079)

## What was verified

That `scripts/validation/pre_pr.py` now fails when generated output is stale against its sources, and passes when it is not.

## Negative control

Required by `.claude/rules/generated-artifacts.md` MUST 2. A checker that has never been seen to fail is not evidence.

Appended one marker line to the generator source `.claude/commands/pr-autofix.md` without regenerating, then ran the gate:

```text
STALENESS DETECTED - uncommitted regen drift:
  src/copilot-cli/skills/pr-autofix/SKILL.md
[FAIL] build_all.py --check reported staleness (exit 2). Examined 2 of 2 checks.
Fix: run the generators in order, then commit the result:
  uv run python scripts/sync_plugin_lib.py
  uv run python build/scripts/build_all.py
rc=1
```

The named file is the one PR #5059 shipped hand-edited, so the control reproduces the reported defect rather than an arbitrary failure.

## Positive control

Reverted the marker with `git checkout -- .claude/commands/pr-autofix.md`, re-ran:

```text
generated staleness: 0 stale in 2 generator check(s) examined
rc=0
```

The examined count is printed on the clean path, so a caller can tell zero drift across two checks from zero checks run (`.claude/rules/ci-scripts.md` MUST 12).

## Ordering control

`.claude/rules/generated-artifacts.md` requires `sync_plugin_lib.py` before `build_all.py`. Two tests pin it against stubs:

- `test_a_failing_sync_leaves_build_all_unrun` asserts a marker file the `build_all` stub would have written is absent. Exit code alone would pass either way.
- `test_the_control_run_does_reach_build_all` asserts the same marker is present on the clean path, so the assertion above cannot pass against a gate that never invokes `build_all` at all.

## Unit suite

```text
$ uv run pytest tests/validation/test_check_generated_staleness.py tests/validation/test_pre_pr_sequence_registry.py -q
tests/validation/test_check_generated_staleness.py ............          [ 57%]
tests/validation/test_pre_pr_sequence_registry.py .........              [100%]
21 passed in 3.61s
```

## Full corpus

Required by `.claude/rules/ci-scripts.md` MUST 13. The gate's own command against the whole tree on this branch:

```text
$ uv run python scripts/validation/check_generated_staleness.py
generated staleness: 0 stale in 2 generator check(s) examined
rc=0
```

The gate ships with zero outstanding violations, so it cannot block the next contributor's push.

## Full pre-PR run

```text
$ uv run python scripts/validation/pre_pr.py
Total Validations: 54
[PASS] Generated Artifact Staleness (1.29s)
Duration: 304.63s
```

One failure appeared in that run, `Count Ratchets`, reporting `type-ignore count ratchet: REGRESSION. 47 > baseline 44 (+3)`. The +3 was the first draft of this PR's test file. Fixed by replacing a manual attribute rebind with `monkeypatch.setattr` and typing the callback parameter as `Callable[[], bool]`. The baseline was not raised:

```text
$ uv run --frozen --extra dev python scripts/ci/type_ignore_count_ratchet.py
type-ignore count ratchet: OK (count == baseline 44).
```

## Other gates

```text
uv run ruff check <changed files>                            All checks passed
uv run mypy scripts/validation/check_generated_staleness.py  Success
scripts/ci/taste_count_ratchet.py                            OK (count == baseline 583)
scripts/ci/ruff_count_ratchet.py                             OK (count == baseline 27)
tests/ci/test_validation_scripts_are_reachable.py            163 passed, 2 skipped
```

## Runtime

| Measurement | Wall clock |
| --- | --- |
| `build_all.py --check` alone, standalone | 4.43s |
| Both checks, standalone, cold | 3.63s |
| The gate inside the `pre_pr.py` sequence | 1.29s |
| Full `pre_pr.py`, 54 validations | 304.63s |

Roughly 0.4 percent of the run. It stays in the default sequence with no changed-paths filter, which would be wrong regardless of cost: `build_all --check` scores the whole tree, and a path filter on a whole-tree check manufactures a green tick.

## Not verified

- Behavior on a machine where `sync_plugin_lib.py --check` reports drift. No such state was reachable on this branch, so the short-circuit was exercised against stubs rather than against real sync drift.
- The 600s per-check timeout was not exercised. It is sized against a 4.43s standalone measurement under `.claude/rules/ci-scripts.md` MUST 16, not against an observed slow run.

VERDICT: PASS
