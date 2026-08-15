---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5079.json
qaCommit: ce88c21b80debe3e5d61d2d87ebb651a0fbef18a
---

# QA report: generated-artifact staleness gate (PR #5088, issue #5079)

## What was verified

That `scripts/validation/pre_pr.py` now fails when generated output is stale against its sources, and passes when it is not.

## Negative control

Required by `.claude/rules/generated-artifacts.md` MUST 2. A checker that has never been seen to fail is not evidence.

Appended one marker line to the generator source `.claude/commands/pr-autofix.md` without regenerating, then ran the gate. Re-run on the round-5 head (`9d2acdc87` plus the test split) after the round-4 message change, because the load-bearing evidence must quote the message the shipped code actually emits:

```text
STALENESS DETECTED - uncommitted regen drift:
  src/copilot-cli/skills/pr-autofix/SKILL.md
[FAIL] build_all.py --check failed (exit 2). Examined 2 of 2 checks.
Read the check's output above for the cause. If it reports staleness or drift, regenerate and commit:
  uv run python scripts/sync_plugin_lib.py
  uv run python build/scripts/build_all.py
Otherwise fix the error the check itself reported; regenerating is not the remedy for a configuration or source failure.
rc=1
```

The dash in `STALENESS DETECTED` is transcribed as a hyphen; the source prints an em dash there (flagged in Notes for Reviewers on the PR). The named file is the one PR #5059 shipped hand-edited, so the control reproduces the reported defect rather than an arbitrary failure.

## Positive control

Reverted the marker with `git checkout -- .claude/commands/pr-autofix.md`, re-ran on the round-5 head:

```text
generated staleness: 0 stale in 2 generator check(s) examined (0.8s of 420s budget)
rc=0
```

The examined count is printed on the clean path, so a caller can tell zero drift across two checks from zero checks run (`.claude/rules/ci-scripts.md` MUST 12).

## Ordering control

`.claude/rules/generated-artifacts.md` requires `sync_plugin_lib.py` before `build_all.py`. Two tests pin it against stubs:

- `test_a_failing_sync_leaves_build_all_unrun` asserts a marker file the `build_all` stub would have written is absent. Exit code alone would pass either way.
- `test_the_control_run_does_reach_build_all` asserts the same marker is present on the clean path, so the assertion above cannot pass against a gate that never invokes `build_all` at all.

## Unit suite

Round-5 head (the gate tests split across two modules; see Round 5):

```text
$ uv run pytest tests/validation/test_check_generated_staleness.py tests/validation/test_check_generated_staleness_termination.py tests/validation/test_pre_pr_sequence_registry.py -q
34 passed in 5.86s
```

25 gate tests (16 core + 9 termination) plus 9 registry tests.

## Full corpus

Required by `.claude/rules/ci-scripts.md` MUST 13. The gate's own command against the whole tree on this branch:

```text
$ uv run python scripts/validation/check_generated_staleness.py
generated staleness: 0 stale in 2 generator check(s) examined (0.8s of 420s budget)
rc=0
```

The gate ships with zero outstanding violations, so it cannot block the next contributor's push. The elapsed-of-budget figure was added in round 5 so budget consumption is visible before it trips.

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

## Round 2: review-finding remediation (2026-08-15)

Three copilot-pull-request-reviewer findings, each verified then fixed:

- The external 600s kill on `build_all.py --check` could skip its
  snapshot-restoring `finally` (SIGKILL) and leave partial generated writes in
  the caller's worktree. The `build_all` row now carries no external kill; the
  sync row keeps its cap (dry run, no partial state).
  `test_build_all_carries_no_external_kill` and
  `test_the_dry_run_row_does_carry_a_cap` pin the asymmetry both ways.
- Exit codes now follow ADR-035 via a `_Status` IntEnum: drift 1, absent
  script or bad root 2 (config), killed child 3 (external). Asserted on
  `main(argv)`: `test_an_absent_script_is_a_config_error_not_drift`,
  `test_a_killed_child_is_an_external_error`. The timeout branch preserves
  partial child output (`test_a_killed_child_keeps_the_output_it_already_flushed`).
- The registry-contract docstring now cites
  `scripts/validation/pre_pr_sequence.py:147` and quotes the adapter signature
  byte for byte, with the divergence section canonical-source-mirror requires.

Re-verified after merging origin/main: 25 tests pass; ruff and mypy clean;
`check_generated_staleness.py` against the full corpus prints
`0 stale in 2 generator check(s) examined`, rc=0; taste (583), ruff (27),
type-ignore (44), and cli-exit-contract (27) ratchets unchanged.

## Not verified

- Behavior on a machine where `sync_plugin_lib.py --check` reports drift. No such state was reachable on this branch, so the short-circuit was exercised against stubs rather than against real sync drift.

## Round 3: reliability-verdict remediation (2026-08-15)

The reliability review returned CRITICAL_FAIL on the round-2 head: removing
build_all's external kill closed the SIGKILL corruption path but opened an
unbounded stall path for callers not under the lefthook job cap. Both rows
now carry a 600s deadline enforced by graceful termination: SIGINT first
(KeyboardInterrupt, so build_all's snapshot-restoring finally runs), kill
only after a 30s grace window, EXTERNAL (exit 3) either way.
`test_expiry_lets_the_child_finally_run` proves the child's finally runs on
expiry with a marker file; `test_every_row_carries_a_deadline` replaces the
old asymmetry pins. 25 tests pass; ruff/mypy clean; corpus gate rc=0;
ratchets unchanged.

Copilot round 3 also flagged that the standalone `build-all-check` lefthook
job now raced the gate's own `build_all --check` in the same parallel
pre-push group (two unlocked snapshot/restore cycles over the same owned
prefixes). The standalone job is removed; `tests/test_lefthook_integration.py`
pins its absence with the rationale (847 tests pass).

## Round 4: budget containment and message honesty (2026-08-15)

Copilot round 4: (a) two 600s row budgets exceeded the 15m lefthook cap on
pre-pr-validation, whose expiry kills the tree without the SIGINT path; the
gate now shares one 420s aggregate budget (worst case + grace = 450s, half
the cap), pinned by a test that parses the live lefthook.yml, and an
exhausted budget reports EXTERNAL without spawning the next child. (b) The
failure message no longer asserts staleness for every nonzero child exit;
it directs the reader to the child's echoed output and gives both remedies,
because the child exit contracts are ambiguous (build_all: 2 = config or
staleness; sync: 1 = missing, unreadable, or drifted). 27 tests pass;
ruff/mypy clean; corpus gate rc=0; ratchets unchanged.

## Round 5: outer-cap clamp and evidence refresh (2026-08-15)

Copilot round 5 and the spec completeness judge, fixed in `9d2acdc87` and
`ce88c21b8`:

- The static half-cap split starts the gate's clock when the sequence reaches
  it, after earlier validations have spent part of the same 900s lefthook
  timer, so it alone could not guarantee the SIGINT deadline fires before the
  outer SIGKILL. The `pre-pr-validation` job now declares its cap via
  `PRE_PR_OUTER_CAP_SECONDS` and the gate clamps its deadline to the process's
  remaining share minus the grace, refusing to spawn a child when the share is
  spent (`test_a_spent_outer_share_reports_external_without_running_the_child`,
  with an unspent-cap control and a malformed-value warn-and-fall-back test).
  The declaration is pinned equal to the job's actual timeout by the live
  lefthook.yml parse. The clamp is opt-in by environment because pytest
  imports the module long before calling it.
- The two untested termination branches the completeness judge named are now
  driven: a child that ignores SIGINT is killed after the grace with the
  partial-writes warning
  (`test_a_child_that_ignores_the_interrupt_is_killed_with_a_warning`), and
  the non-POSIX `terminate()` fallback is pinned with a fake on every
  platform (`test_a_non_posix_host_terminates_instead_of_signaling`).
  `_echo_tail` truncation and blank-output behavior are also pinned.
- Evidence refresh: the negative control above was re-run on this head so it
  quotes the round-4 message the shipped code actually emits, and the unit
  suite section now shows the current count (34). Reconciliation for round
  2's citations: `test_build_all_carries_no_external_kill` and
  `test_the_dry_run_row_does_carry_a_cap` were superseded when rounds 3-4
  replaced per-row caps with the aggregate budget; their current equivalents
  are `test_the_gate_budget_is_positive_and_shared` and
  `test_budget_plus_grace_fits_inside_the_lefthook_cap`. Round 3's
  `test_every_row_carries_a_deadline` was likewise absorbed by the aggregate
  budget tests in round 4.
- The gate tests split across two modules
  (`test_check_generated_staleness.py`,
  `test_check_generated_staleness_termination.py`) with shared stubs in
  `staleness_gate_helpers.py`, because round-5 coverage pushed the single
  module past the 500-line test file-size ceiling; the taste ratchet is back
  at baseline 583.

34 tests pass; ruff and mypy clean; corpus gate rc=0 with the elapsed figure;
taste (583), ruff (27), and type-ignore (44) ratchets unchanged.

VERDICT: PASS
