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
