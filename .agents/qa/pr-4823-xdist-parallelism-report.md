---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10034.json
qaCommit: 3d82967895dfd2adf2f3479726b0cb7546346c97
---

# QA Report: Four-Worker pytest-xdist Parallelism

## Scope

Issue #4823. Run the bulk pre-push pytest partition and the CI main pytest step
on four xdist workers with `--dist loadfile`. The prerequisite that makes
collection order deterministic landed on `main` as
`1bfc0b8829cbc34a5a315d3722fdb646150cc37c` (PR #4834).

Commits under test:

| Commit | Change |
|---|---|
| `5306e1d2e` | `pytest-xdist>=3.8.0` in both dev dependency tables, lock regenerated |
| `7d8aaa893` | Four-worker flags on the bulk pre-push partition only |
| `4599e70f8` | Four-worker flags on the CI `Run pytest` step only |

All measurements below ran at `4599e70f8e28846f5f327a56baccf6c18b726d57` on
48 cores and 125 GB RAM, CPython 3.14.6, pytest 9.0.3, pytest-cov 7.1.0,
pytest-xdist 3.8.0.

## Gate 1: collection parity, serial versus parallel

Same SHA, `--collect-only -q`, non-integration partition.

| Mode | Collected | Deselected | pytest time | Wall |
|---|---|---|---|---|
| Serial | 25,394 of 25,444 | 50 | 25.69s | 29.5s |
| `-n 4 --dist loadfile` | 25,394 of 25,444 | 50 | 6.14s | 9.3s |

`diff` of the sorted flat node-ID lists (25,394 lines each) is empty. Result:
pass.

## Gate 2: three four-worker repeats of the pre-push gate

`uv run --frozen python scripts/validation/git_hook_policy.py pytest`, the real
gate, no coverage.

| Run | Gate wall | Bulk partition | Peak RSS | Outcome |
|---|---|---|---|---|
| 1 | 310.69s (5:10.69) | 303.53s | 593,388 KB | 25,358 passed, 36 skipped |
| 2 | 323.45s (5:23.45) | 315.41s | 573,460 KB | 25,358 passed, 36 skipped |
| 3 | 341.55s (5:41.55) | 335.71s | 614,396 KB | 25,358 passed, 36 skipped |

Each run also ran the serial safe-push partition: 38 passed, 9 deselected. Each
log carries `created: 4/4 workers` and `4 workers [25394 items]`. A grep for
`node down:`, `Replacing crashed worker`, `INTERNALERROR`, `worker .* crashed`,
and `Different tests were collected between` matched nothing in all three. Every
run is under the 7-minute bound. Result: pass.

Test-count movement is accounted for: the baseline on the prerequisite branch was
25,321 passed and this branch adds 37 tests to that partition (30 in
`tests/validation/test_pytest_parallelism_policy.py` and 7 in
`tests/workflows/test_pytest_xdist_parallelism.py`), giving 25,358. The 38th new
test lands in the serial safe-push partition, which the bulk command excludes
with `--ignore tests/test_safe_push_pr_branch.py`.

## Gate 3: coverage equivalence, CI-shaped run

`scripts/ci/run_pytest_non_tmp.py --cov --cov-report=` with the five `--ignore`
paths the workflow passes, matching the CI step.

| Run | Result | pytest time | Wall | Peak RSS |
|---|---|---|---|---|
| Serial | 25,154 passed, 36 skipped | 739.21s | 12:25.80 | 891,736 KB |
| Parallel A | 1 failed, 25,153 passed, 36 skipped | 321.22s | 5:23.32 | 600,244 KB |
| Parallel B | 25,154 passed, 36 skipped | 300.23s | 5:02.27 | 616,696 KB |
| Parallel C | 25,154 passed, 36 skipped | 310.61s | 5:12.69 | 620,612 KB |

Coverage comparison, serial versus each clean parallel run:

| Metric | Serial | Parallel B | Parallel C |
|---|---|---|---|
| Files in report | 609 | 609 | 609 |
| Files only in one side | - | 0 | 0 |
| `num_statements` | 74,895 | 74,895 | 74,895 |
| `covered_lines` | 61,249 | 61,247 | 61,247 |
| `percent_covered` | 81.779825 | 81.777155 | 81.777155 |
| Delta | - | -0.0027 pp | -0.0027 pp |

The bound is 0.1 pp. Result: pass.

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

### The two-line coverage delta

Exactly one file differs in each comparison, always by the same two lines, and
the file identity is not stable across parallel runs:

| Comparison | File | Lines covered only by the serial run |
|---|---|---|
| Serial vs parallel B | `.claude/hooks/SessionStart/invoke_context_loader.py` | 253, 254 |
| Serial vs parallel C | `.claude/hooks/PreCompact/invoke_compact_checkpoint.py` | 183, 184 |

Both line pairs are the same duplicated `_drain_stdin` arm:

```python
if not sys.stdin.isatty():
    try:
        sys.stdin.read()
    except OSError:
        pass
```

Measured, not inferred: each arm is covered by exactly one owning test module in
isolation (`tests/test_context_loader.py` and `tests/test_compact_checkpoint.py`
both cover their arm when run alone), while the sibling module
`tests/hooks/test_context_loader.py` patches `sys.stdin` with `StringIO("")`,
which returns without raising and leaves the arm uncovered. Coverage of the arm
therefore depends on the ambient `sys.stdin` object at the moment the owning
module runs, and per-worker ordering differs from serial ordering. The exact
ordering interaction was not isolated further. This is a pre-existing
test-isolation weakness in files this change does not touch; the effect is two
lines out of 74,895 statements.

## Other gates

| Check | Result |
|---|---|
| `tests/validation/test_pytest_parallelism_policy.py` | 30 passed |
| `tests/workflows/test_pytest_xdist_parallelism.py` | 7 passed |
| `tests/test_pyproject_dev_deps_parity.py` | 11 passed |
| `tests/test_safe_push_pr_branch.py` | passed, including the new serial-partition guard |
| `uv lock --check` | Clean |
| `ruff check` on the five changed Python files | Clean |
| `scripts/validate_workflows.py .github/workflows/pytest.yml` | Passed |

Mutation checks confirm the new tests bind the contract rather than restate it:
changing `PYTEST_DIST_MODE` to `loadscope` fails 1 test, deleting the
`*_pytest_parallel_flags()` splat fails 6, putting `-n auto` in the CI step fails
2, and adding `-n 2` to a coverage-pin step fails 2.

## Open risk, carried forward

Parallel run A above failed one test:
`tests/test_pr_autofix_late_live_state_gate.py::test_closed_after_review_skips_and_reports_recovery_head[.claude/commands/pr-autofix.md]`
raised `Failed: Timeout (>120.0s) from pytest-timeout` while blocked in
`subprocess.run(..., capture_output=True)` inside `communicate()` and
`selector.select()`. The same module runs its 24 tests in 6.84s in isolation with
a 0.25s slowest call, so this is a hang and not slowness.

Observed rate: 1 failure in 3 CI-shaped parallel runs, 0 failures in 3 pre-push
gate runs, so 1 in 6 four-worker full-suite runs at this SHA. It did not
reproduce on either retry.

Mechanism, from reading `.claude/commands/pr-autofix.md` lines 78 to 160:
`start_lease_renewal` backgrounds a subshell that inherits the harness's stdout
and stderr pipes, and `stop_lease_renewal` runs `kill -- "-$PID"` (which fails
because the subshell is not a process-group leader without job control) before
`kill "$PID"`. A surviving grandchild keeps the pipe open, so `communicate()`
waits for an EOF that never arrives. `--cov` widens the window: pytest-cov
installs a `.pth` subprocess hook, so every `python3` grandchild starts coverage
tracing. That is consistent with the failure appearing only in the
coverage-shaped runs.

This is a latent race in a file outside this change's plan. Parallel execution
raises its probability rather than creating it. It needs a separate fix and is
not addressed here.

## Not proven here

The sub-10-minute CI wall-clock target is unproven. Every measurement above is
local. The CI number can only be read from a workflow run after this branch is
pushed.

## Push prerequisite, verified locally

`merge-tree-ratchet` runs in the `pre-push` hook and currently refuses this
branch:

```text
merge-tree-ratchet: merge has conflicts against 1bfc0b8829cb. Ratchets were not
evaluated; resolve the conflicts and rerun the ratchet.
```

The add/add conflict on `.agents/sessions/2026-08-10-session-10033.json`
predated this work. Merge commit
`3d82967895dfd2adf2f3479726b0cb7546346c97` preserved main's canonical session
10033. The xdist session remains 10034. After the merge, all 48 targeted
dependency, local-policy, and workflow contract tests passed.

One inherited record remains outside this branch's scope: main's session 10033
names the pre-squash commit from PR #4834. The immutable main record was
preserved during conflict resolution.

## Verdict

Pass. Collection is identical between modes, three consecutive four-worker gate
runs are clean and under the 7-minute bound, and coverage differs by 0.0027
percentage points against a 0.1-point bound. The CI-shaped run drops from 739.21s
serial to 300-311s parallel, a 2.4x improvement, measured here. Issue #4491
records the serial pre-push partition at about 1,315s; that figure is quoted from
the issue and was not re-measured in this session.
