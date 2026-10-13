# pytest-testmon pre-push measurements (issue #6239)

Cited by ADR-104. Machine: the owner's 48-thread workstation, Python 3.14.7, pytest-testmon 2.2.0, `COVERAGE_CORE=ctrace`, `TMPDIR=/tmp`. All runs used the lefthook worker cap of 4 unless noted. These are single runs. None is a repeat, so none carries a variance estimate.

## Cold run through lefthook (no `.testmondata`)

Command: `uv run --frozen lefthook run pre-push --job python-tests --no-tty`

Raw output of the timing wrapper, saved at the time:

```
cold lefthook exit=0 wall=575.178044727
```

Lefthook prints nothing for a passing job, so there is no pytest output for this run. One run.

## Warm run through lefthook (database present, nothing changed)

Same command. Wall time 7.78 s, exit 0. The figure was printed to the terminal and no log file was kept. One run.

## Warm runs of the hook command (cap of 4, nothing changed)

Command: `AI_AGENTS_PYTEST_WORKER_CAP=4 uv run --frozen python scripts/validation/git_hook_policy.py pytest`

Two consecutive runs after a clean cold run, 7.28 s and 7.26 s, both exit 0. Header and summary lines from the saved logs (`w1.log`, identical to `w2.log` apart from timings):

```
testmon: changed files: 0, unchanged files: 2526, environment: default
============================ no tests ran in 1.65s =============================
testmon: changed files: 0, unchanged files: 2526, environment: default
============================ no tests ran in 1.36s =============================
testmon: changed files: 0, unchanged files: 2526, environment: default
============================ 63 deselected in 0.45s ============================
testmon: changed files: tests/test_safe_push_pr_branch.py, unchanged files: 2525, environment: default
============================ 18 deselected in 0.40s ============================
```

## Cross-path run (database copied to a second checkout)

A warm 30 MB `.testmondata` was copied into a second checkout of the same commit with its own virtualenv (a different path). The same hook command ran there, exit 0, 7 s wall. Saved log lines (`port.log`):

```
testmon: changed files: 0, unchanged files: 2526, environment: default
============================ no tests ran in 1.81s =============================
testmon: changed files: 0, unchanged files: 2526, environment: default
============================ no tests ran in 1.43s =============================
testmon: changed files: 0, unchanged files: 2526, environment: default
============================ 63 deselected in 0.58s ============================
testmon: changed files: tests/test_safe_push_pr_branch.py, unchanged files: 2525, environment: default
============================ 18 deselected in 0.42s ============================
```

Zero tests selected in all four partitions. `tests/validation/test_testmon_database_portable.py` repeats the check on a small project and adds a control: a one-file edit selects exactly the tests that import it.

## Runs without the lefthook cap (`-n auto`, 48 workers)

Reported from the terminal during development, no logs kept:

- cold, 5 min 46 s wall, 2 tests timed out at 120 s under load (since fixed);
- first repeat, 3 min 22 s wall, 174 tests selected, because the first run had stopped at its first failing partition and never recorded the other three;
- repeat after a complete run, 7 s, 0 selected.

## CI runner estimate (not measured)

Run 38015601869 of `pytest.yml` on main: the six matrix legs took 383, 369, 302, 210, 73 and 53 s, 1390 s in total on 4-vCPU runners without testmon. testmon with ctrace adds about 1.4x in the 2026-10-09 trial, so the seed job is estimated at 30 minutes. It is an inference until the first main push runs it.

## Replay trial, 2026-10-08 (bulk slice, 13,735 tests, 48-core host)

Recorded in the session evidence for issue #6239 (test-selection sourcing analysis, file D). One run each on a loaded shared host.

- Coverage core: on one injected fault in `scripts/github_core/api.py`, the default `sysmon` core selected 9 tests and `COVERAGE_CORE=ctrace` selected 56. Both caught the one failing test.
- ctrace cost: database build 64.0 s against 45.5 s with the default core (1.41x), database 10.8 MB against 7.5 MB. This is the source of the 1.4x factor used in the CI estimate above.
- Per-commit selection and wall time, testmon with the default core, replaying recent main commits in order:

| Commit | Tests selected | Wall |
|---|---|---|
| d76ddf952 | 2 | 5.1 s |
| 128a5507f | 877 | 35.6 s |
| 5ff89f523 | 586 | 20.5 s |
| 18f6acff4 | 1 | 4.9 s |
| 2ef97a246 | 221 | 23.9 s |
| f9327e0fa | 3 | 12.5 s |

These rows are the "4 to 36 s" range ADR-104 cites. Two other replayed commits changed `uv.lock` and reran every test.


## Bounding the pytest step (issue #6200), 2026-10-13

Same machine as above, shared with other sessions: load average 4.36, 7.01, 8.52 at the first run's start (48 threads, Python 3.14.7, pytest-testmon 2.2.0, `COVERAGE_CORE=ctrace`), a linked worktree at `origin/main` 55d1a8a4c plus the change. Worker cap `scaled` with a CPU reserve of 3, as lefthook sets it. All single runs, none repeated, so none carries a variance estimate. Logs were kept in a session scratch directory and are not committed; the lines below are copied from them. The load average came from `uptime` before the first run; the later runs were not checked.

Cold run, no `.testmondata`, seed fetch disabled, partitions in sequence, hook command run directly:

```
tests (bulk)                      = 2 failed, 49492 passed, 101 skipped, 11 subtests passed in 339.52s (0:05:39) =
(passed across the four partitions: 49492 + 100 + 54 + 20 = 49666)
tests/mutation                    100 passed in 96.57s (0:01:36)
tests/test_safe_push_pr_branch.py 54 passed, 9 deselected in 15.06s
tests/test_pr_autofix_...gate.py  20 passed in 2.33s
Elapsed (wall clock) time (h:mm:ss or m:ss): 7:42.09
```

The two failures were `test_semgrep_compat_rules_fire_on_the_target_without_exclusion` and `test_semgrep_family_prefix_exclusion_suppresses_nothing`. Each prints `semgrep-core exited with code 1` under 16 workers and passes alone in 5.52s. They are not part of the budget question.

Throughput: 49,492 tests in 339.52s is 146 tests per second. A seeded run selected 808 tests and took 49.9s, 16 tests per second. The rates differ 9x, so no test count maps to a time.

Cold collection, the deferred path, `gh` removed from `PATH`:

```
pytest: no testmon seed (gh is not installed); this push collects the suite instead of running it.
pytest: no testmon database and no seed, so the selection is the whole suite.
  Not run locally: all 49,808 tests. A cold run does not fit the 180s budget.
wall=20.48
```

No `.testmondata` was created.

Seeded runs after `mv .testmondata` aside (seed fetched from main's artifact, 73 changed files):

```
first run   exit 1, 22.5s wall: xdist "Different tests were collected between gw7 and gw1" (issue #6477)
second run  808 passed in 48.64s, partition 49.9s, wall=50.05
third run   63 deselected / 20 deselected, wall=4.36
later run   1153 passed in 72.11s, partition 74.5s, wall=79.60 (the change under test was in the tree)
```

In-hook, `LEFTHOOK_EXCLUDE=push-ref-policy lefthook run pre-push --no-tty` with `LEFTHOOK_OUTPUT=summary,success,failure`. `push-ref-policy` is excluded because its security-marker check blocks a branch with no `/review` marker:

```
warm database          done in 192.73s  python-tests 4.16s    pre-pr-validation 166.50s  count-ratchets 25.30s
fresh worktree, seeded done in 196.13s  python-tests 31.11s   pre-pr-validation 169.51s  count-ratchets 25.71s
```

Lefthook's `group` lines sum their members. The wall clock is the serial stages (about 26s, with `count-ratchets` the longest) plus the longest job of the expensive group, which is `pre-pr-validation`, not pytest.

Failing hooks print under `output: false` (`lefthook.yml:6`). In the same session `hook2.log` held the dash-prohibition failure with file and line, and `push1.log` held the security-marker failure. Passing runs (`hook3.log`) printed nothing, including the testmon banner.
