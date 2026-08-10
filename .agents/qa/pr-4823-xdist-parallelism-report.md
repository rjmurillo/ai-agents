---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10035.json
qaCommit: 953338d6fe8cfcd86206fb6a467060bb66d5693b
---

# QA Report: pytest-xdist Parallelism at Every Logical CPU

## Scope

Issue #4823. Run the bulk pre-push pytest partition and the CI main pytest step
on `-n auto --dist loadfile`. `-n auto` is xdist's own one-worker-per-logical-CPU
setting, so the worker count follows the machine instead of a constant. An
`AI_AGENTS_PYTEST_WORKERS` override accepts `auto` or a positive integer and
rejects anything else with exit 2. The prerequisite that makes collection order
deterministic landed on `main` as
`1bfc0b8829cbc34a5a315d3722fdb646150cc37c` (PR #4834).

Commits under test:

| Commit | Change |
|---|---|
| `5306e1d2e` | `pytest-xdist>=3.8.0` in both dev dependency tables, lock regenerated |
| `7d8aaa893` | Parallel flags on the bulk pre-push partition only |
| `4599e70f8` | Parallel flags on the CI `Run pytest` step only |
| `aaa1efa90` | Bulk pre-push partition scaled to every logical CPU |
| `ea508b072` | CI `Run pytest` step scaled to every runner CPU |
| `953338d6f` | Mutation marker assertions scoped to their own run |

An earlier revision of this branch used a fixed four workers. The design changed
to `-n auto` on instruction; the four-worker numbers are kept below only where
they are the honest comparison point, and are labelled as such.

Measurements in the `auto` sections ran at
`953338d6fe8cfcd86206fb6a467060bb66d5693b` on 48 logical CPUs and 125 GB RAM,
CPython 3.14.6, pytest 9.0.3, pytest-cov 7.1.0, pytest-xdist 3.8.0. On this host
`auto` resolves to 48 workers. That resolution is a property of the host, not of
the configuration, and a CI runner will resolve it to its own smaller count.

### How peak memory was measured

Every RSS figure comes from `/usr/bin/time -v`, which reports the largest single
process, not the sum across workers. It understates whole-run memory whenever
workers run concurrently. The figures are comparable to each other because they
were all taken the same way; they are not a total memory footprint.

## Gate 1: collection parity, serial versus parallel

Same SHA, `--collect-only -q`, non-integration partition.

| Mode | Collected | Deselected | pytest time | Wall |
|---|---|---|---|---|
| Serial | 25,394 of 25,444 | 50 | 25.69s | 29.5s |
| `-n 4 --dist loadfile` | 25,394 of 25,444 | 50 | 6.14s | 9.3s |

`diff` of the sorted flat node-ID lists (25,394 lines each) is empty. Result:
pass.

This gate was measured under the four-worker revision and is not re-measured for
`auto`. Collection parity is a property of collection order, which the
prerequisite fixed; the worker count changes how collected items are distributed,
not which items exist. The `auto` runs below corroborate it: every one reports
`25400 items` and none reports `Different tests were collected between`.

## Gate 2: the pre-push gate at every logical CPU

`uv run --frozen python scripts/validation/git_hook_policy.py pytest`, the real
gate, no coverage.

| Run | Workers | Gate wall | Bulk partition | Peak RSS | Outcome |
|---|---|---|---|---|---|
| `auto` 1 | 48 | 3:50.52 | 227.72s | 551,908 KB | 2 failed, 25,362 passed, 36 skipped |
| `auto` 2 | 48 | 3:57.40 | 232.15s | 547,032 KB | 25,364 passed, 36 skipped |

Run 1 exposed a real defect, which commit `953338d6f` fixes; run 2 is the same
gate after that fix. Both logs carry `created: 48/48 workers` and
`48 workers [25400 items]`.

Crash check: grepping run 2 for `crashed`, `Replacing crashed worker`, and
`INTERNALERROR` matches 10 lines, and every one is a test *name* containing the
word (for example
`tests/ci/test_taste_count_ratchet.py::test_a_crashed_linter_is_not_a_clean_tree`).
No worker crashed. Both runs also ran the serial safe-push partition: 38 passed,
9 deselected.

The four-worker revision measured 5:10.69, 5:23.45, and 5:41.55 on the same
host, so `auto` removes roughly 90 seconds of wall clock. Every run is under the
7-minute bound. Result: pass.

### The defect run 1 found

`tests/test_mutation_workspace_signals.py` failed two tests, both on the same
assertion:

    assert not list(marker_directory(REPO_ROOT).iterdir())

That directory is repo-global, and `tests/test_mutation_workspace.py` writes
markers into it as well. Under `--dist loadfile` the two modules land on
different workers and run at the same moment, so the emptiness assertion fails
on a file the failing test never created.

Reproduced deterministically with only those two modules at `-n 2 --dist
loadfile`: 2 failed and 24 passed, 3 of 3 runs; serial control 26 passed. After
`953338d6f`: 26 passed, 3 of 3 runs.

Both tests now assert the lifecycle of their own marker. They also assert the
marker exists while the run is live, before asserting it is gone, because a bare
absence assertion passes against any wrong path. Mutating the marker suffix to
`.NOPE` leaves the bare form green and fails both tests with the liveness
assertion present.

This was a latent defect, not a regression: the assertion was always wrong about
what it owned, and serial execution hid it by never overlapping the two modules.

## Gate 3: coverage equivalence, CI-shaped run

`scripts/ci/run_pytest_non_tmp.py --cov --cov-report=` with the five `--ignore`
paths the workflow passes, matching the CI step. All three runs below are at
`953338d6f`.

| Run | Workers | Result | pytest time | Wall | Peak RSS |
|---|---|---|---|---|---|
| Serial | 1 | 25,160 passed, 36 skipped | 765.23s | 12:52.25 | 889,756 KB |
| `auto` A | 48 | 2 failed, 25,158 passed, 36 skipped | 255.70s | 4:18.37 | 582,476 KB |
| `auto` B | 48 | 25,160 passed, 36 skipped | 234.16s | 3:56.95 | 581,812 KB |

Coverage comparison, serial versus run B:

| Metric | Serial | `auto` B |
|---|---|---|
| Files in report | 609 | 609 |
| Files only in one side | - | 0 |
| `num_statements` | 74,898 | 74,898 |
| `covered_lines` | 61,252 | 61,253 |
| `percent_covered` | 81.78055489 | 81.78189004 |
| Delta | - | +0.0013 pp |

The bound is 0.1 pp and the file set must match exactly. Both hold. Result:
pass.

Three files differ, by four lines total. `invoke_context_loader.py` lines 253
and 254 are covered only by the serial run and are the same stdin-drain arm
discussed below. `scripts/testing/mutation_workspace.py` lines 384 and 455 and
`scripts/validation/validate_argument_hint.py` line 158 are covered only by the
parallel run. The parallel run therefore covers one line more than serial on
net, so this is not a coverage loss.

pytest-cov merges worker data itself, so no explicit combine step exists or is
needed. `pytest_cov/engine.py` `DistMaster.finish()` reads verbatim:

```python
self.cov.stop()
self.cov.save()
self.cov = self.combining_cov
self.cov.load()
self.cov.combine()
self.cov.save()
```

`combining_cov` is constructed with
`data_file=os.path.abspath(self.cov.config.data_file)`, so the merge target is
the step's own `COVERAGE_FILE`. `scripts/ci/combine_pin_coverage.py` is
unchanged.

### The two failures in run A

Run A failed two tests that run B passed:

- `tests/eval/test_copilot_cli_acp.py::test_process_shutdown_obeys_the_session_deadline`
  hit `Failed: Timeout (>3.0s) from pytest-timeout`. The test carries
  `@pytest.mark.timeout(3)` at line 324.
- `tests/validation/test_portability_baseline_artifact.py::TestTheWriteItself::test_concurrent_writers_serialize_the_read_and_replace`
  failed `assert not first.is_alive()` after `first.join(timeout=2)` at line 379.

Both assert against a hard wall-clock deadline of a few seconds. Isolating the
cause: the two tests pass serially without coverage (2 passed in 0.68s) and
serially with coverage (2 passed in 0.70s), so coverage instrumentation alone
does not break them. They also passed both full pre-push gate runs, which use
`auto` without coverage. The failure needs 48 workers and coverage tracing
together, which is CPU oversubscription starving a thread past a two-second join.

Observed rate: 1 of 2 CI-shaped coverage runs at this SHA. These are latent
timing assumptions in files this change does not touch, and higher worker counts
raise the probability rather than creating the fragility. Widening the deadlines
would be a change to tests outside this plan and is not done here. On a CI runner
`auto` resolves to a much smaller worker count than 48, so the contention that
triggers this is largely an artifact of this 48-thread host.

### The serial-only pair in the stdin-drain arm

`invoke_context_loader.py` lines 253 and 254 have been serial-only in every
comparison taken on this branch, under four workers and under `auto`. The two
hook entry points each carry a private copy of the same five-line guard, which
reads stdin when it is not a terminal and swallows the resulting error when the
read fails. The two lines are the error handler and its body. See
`.claude/hooks/SessionStart/invoke_context_loader.py` lines 250 to 254 and
`.claude/hooks/PreCompact/invoke_compact_checkpoint.py` lines 180 to 184 for the
code; it is not reproduced here because this report is prose, not a second copy
of a duplicated block.

Measured, not inferred: each arm is covered by its owning test module in
isolation (`tests/test_context_loader.py` and `tests/test_compact_checkpoint.py`),
while the sibling module `tests/hooks/test_context_loader.py` patches
`sys.stdin` with `StringIO("")`, which returns without raising and leaves the arm
uncovered. Coverage of the arm therefore depends on the ambient `sys.stdin`
object when the owning module runs, and worker-local ordering differs from serial
ordering. The exact ordering interaction was not isolated further. This is a
pre-existing test-isolation weakness in files this change does not touch, worth
two lines out of 74,898 statements.

## Other gates

All re-run at `953338d6f` unless noted.

| Check | Result |
|---|---|
| `tests/validation/test_pytest_parallelism_policy.py` | 36 passed |
| `tests/workflows/test_pytest_xdist_parallelism.py` | 7 passed |
| `tests/test_pyproject_dev_deps_parity.py` | 11 passed |
| `tests/test_safe_push_pr_branch.py` | 38 passed, 9 deselected |
| `tests/test_mutation_workspace_signals.py` | 8 passed |
| `uv lock --check` | Clean |
| `ruff check` on the changed Python files | Clean |
| `scripts/validate_workflows.py .github/workflows/pytest.yml` | Passed |
| `scripts/ci/merge_tree_ratchet_check.py --base-ref origin/main` | Exit 0, all ratchets pass |
| doc-accuracy on `.agents/qa` | 0 findings cite this report, down from 2 |

Mutation checks confirm the new tests bind the contract rather than restate it.
Against the `auto` design: hard-coding a worker count in the CI step fails 2
tests, hard-coding the local default fails 8, and deleting the `auto` branch from
the override parser fails 5. Against the earlier four-worker design: changing
`PYTEST_DIST_MODE` to `loadscope` failed 1 and deleting the
`*_pytest_parallel_flags()` splat failed 6.

The doc-accuracy comparison is a delta, not a clean sheet: the repository-wide
run reports 3,089 findings both before and after, and the two that named this
report (`compile-2596` and `compile-2597`) are gone. The remaining 3,089 are a
pre-existing baseline across 138 files and are not this change's to clear.

## Open risk, carried forward

### The pr-autofix lease-renewal hang

Under the four-worker revision, one CI-shaped run failed
`tests/test_pr_autofix_late_live_state_gate.py::test_closed_after_review_skips_and_reports_recovery_head[.claude/commands/pr-autofix.md]`
with `Failed: Timeout (>120.0s) from pytest-timeout`, blocked in
`subprocess.run(..., capture_output=True)` inside `communicate()` and
`selector.select()`. The module runs its 24 tests in 6.84s in isolation with a
0.25s slowest call, so it is a hang and not slowness.

Mechanism, from reading `.claude/commands/pr-autofix.md` lines 78 to 160:
`start_lease_renewal` backgrounds a subshell that inherits the harness's stdout
and stderr pipes, and `stop_lease_renewal` runs `kill -- "-$PID"` (which fails
because the subshell is not a process-group leader without job control) before
`kill "$PID"`. A surviving grandchild keeps the pipe open, so `communicate()`
waits for an EOF that never arrives. `--cov` widens the window: pytest-cov
installs a `.pth` subprocess hook, so every `python3` grandchild starts coverage
tracing.

It did not recur in any of the four `auto` full-suite runs in this report. Total
observed rate across both designs at this SHA and its predecessor: 1 in 10
full-suite runs. This is a latent race in a file outside this change's plan.
Parallel execution raises its probability rather than creating it. It needs a
separate fix and is not addressed here.

### Wall-clock deadline tests under heavy oversubscription

Recorded in full under "The two failures in run A". Two tests with two- and
three-second deadlines failed in 1 of 2 coverage runs at 48 workers. They are
untouched by this change and pass serially with and without coverage.

Both open risks share one shape: parallelism does not introduce the fault, it
raises the odds of observing a fault that was already there. The mutation-marker
defect in Gate 2 had that same shape and was fixed here because it reproduced
deterministically and its fix was contained to one file.

## Not proven here

The sub-10-minute CI wall-clock target is unproven and remains pending. Every
measurement above is local. The CI number can only be read from a workflow run
after this branch is pushed, and no claim is made about it here.

`auto` resolving to 48 workers is a fact about this host. The worker count a CI
runner will choose was not measured and is not asserted.

## Push prerequisite, verified locally

The pre-push hook runs `scripts/ci/merge_tree_ratchet_check.py --base-ref
origin/main`. Earlier in this work it refused the branch: the merged tree had
conflicts against `1bfc0b8829cb`, so no ratchet was evaluated at all. The
add/add conflict was on `.agents/sessions/2026-08-10-session-10033.json` and
predated this branch.

Merge commit `3d82967895dfd2adf2f3479726b0cb7546346c97` resolved it and
preserved main's canonical session 10033. The xdist session was renumbered
to 10035 after main later landed its own 10034 for issue #4826. The
check now exits 0 and reports that the merged tree passes every registered
ratchet, with the cli exit contract ratchet at 27 against its budget of 27. The
push blocker recorded earlier in this report is cleared.

One inherited record remains outside this branch's scope: main's session 10033
names the pre-squash commit from PR #4834. That immutable main record was
preserved during conflict resolution rather than rewritten.

## Verdict

Pass. The file set in the coverage report is identical between modes, covered
lines differ by one out of 61,252 and percent-covered by +0.0013 points against
a 0.1-point bound, and the pre-push gate at `auto` is clean and well under the
7-minute bound.

Measured on this 48-thread host: the CI-shaped run drops from 765.23s serial to
234.16s at `auto`, a 3.3x improvement, and the pre-push gate drops from 5:10.69
at four workers to 3:57.40 at `auto`. Issue #4491 records the serial pre-push
partition at about 1,315s; that figure is quoted from the issue and was not
re-measured here.

Parallelism at this width surfaced one real defect, fixed in `953338d6f`, and
two latent timing fragilities that are recorded rather than papered over. The CI
wall-clock target stays pending until the branch is pushed.
