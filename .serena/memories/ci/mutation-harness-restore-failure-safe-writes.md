# Mutation harness restore failures must write through a sibling file

## Question

How should a mutation harness restore a source file after running a mutant when
the restore write itself can fail?

## Finding

Writing restore bytes directly to the target can truncate the target before the
write fails. Issue #4497 reproduced this with a simulated write failure after
open-for-write, leaving the target empty while the harness reported only a
restore error.

## Decision

For `scripts/ci/mutation_harness_ciperms.py`, write both mutant and restore
bytes to a sibling scratch file, then replace the target. A failed scratch
write can corrupt only scratch. The tracked target keeps either the mutant or
the original bytes, never an empty partial restore.

The harness also purges the target directory `__pycache__` before each pytest
run and sets `PYTHONDONTWRITEBYTECODE=1` for the child process. The purge stops
CPython from reading stale bytecode after same-size mutations. The environment
flag stops a mutant run from seeding bytecode for the next run.

## Evidence

- Pre-fix measurement: forced restore write failure after truncation exited 2
  but left `sample.py` as `b""`.
- Fixed measurement: forced scratch write failure exited 2 and left
  `sample.py` as `b"changed\n"`, the already-applied mutant bytes.
- Regression tests:
  `tests/ci/test_mutation_harness_ciperms.py::TestRestoreFailureExitCode::test_truncate_then_fail_during_restore_does_not_empty_target`,
  `TestApplyMutation::test_pycache_is_purged_before_pytest_runs`, and
  `TestRunTests::test_run_tests_disables_bytecode_writes`.
