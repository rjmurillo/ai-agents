# SPEC-6211: Balance xdist loadfile workers by splitting the slowest test files

Issue: #6211. Owner decision (2026-10-07, D2): keep `--dist loadfile`, split slow files, do not change the distribution mode.

## Step 0 First Principles

### Q1 Demand Reality

Richard Murillo asked for this on 2026-10-07 after the pre-push speed analysis. Issue #6211 records it. The pre-push `python-tests` job and ADR-104's 300s pre-push target are the systems that need it.

### Q2 Status Quo

A developer pushes and waits. At 16 workers, 15 workers finish early and sit idle while one worker runs a 43s file to the end.

### Q3 Desperate Specificity

The pre-push `python-tests` job. A push that runs longer than five minutes expires the model prompt cache for the agent session that started it.

### Q4 Narrowest Wedge

Split two test files into five smaller files without changing any test. About 2 hours.

### Q5 Observation

Measured on 2026-10-08 on an idle 48-core workstation, 832-file subset, 16 workers, 120.9s wall:

- Every worker spends 36.5s collecting before any test runs.
- The median worker finishes at 80.6s. The last finishes at 116.1s. The tail is 35.5s.
- The two slowest files take 43.1s and 41.1s when run alone.

### Q6 Future-fit

At ten times the tests, uneven files matter more, because the worker count grows too. Splitting by hand does not stop regrowth: `tests/test_validation_pre_pr.py` was split once before (#4352) and grew back. Ongoing detection belongs to the #6194 duration trend job, not to this change.

## Prior Art / Constraints

- #4352 split `tests/test_validation_pre_pr.py` into `tests/validation_pre_pr/`. Its session record notes that copied `noqa` comments trip the pre-push security suppression policy.
- `PYTEST_DIST_MODE = "loadfile"` in `scripts/validation/git_hook_policy.py:655` is deliberate. Module fixtures, module state, and file-local temp directories must keep behaving as they do serially.
- `test_validator_argv_is_accepted_by_the_real_checker` is slow by design. Its docstring says it is the only test that runs the real checkers. It stays, unchanged.
- `tests/validation/` is a package and already holds shared helper modules imported as `tests.validation.<name>`.

## Problem statement

Under `--dist loadfile`, one worker runs each whole file. Two files take over 40s each, so one worker finishes long after the others. That idle tail is 35.5s of a 120.9s run.

## User stories

- As a developer pushing a branch, I want the pytest step to finish when the work is done, not when the one slowest file finishes, so my push stays under five minutes.

## Ontology

- **Test file**: a `test_*.py` module. Under `loadfile` it is the unit of scheduling.
- **Scheduling unit time**: the wall time of one test file run alone.
- **Tail**: time between the median worker finishing and the last worker finishing.
- **Dominant test**: one test whose time is most of its file's time. Splitting a file cannot make a unit shorter than its dominant test.

## Data model

No data model. Test IDs change module path only.

## Integrations

- pytest-xdist `--dist loadfile` (unchanged).
- `scripts/test_selection` import graph: new files must import the same production modules, so selection still picks them.
- #6194 duration trend job: reads JUnit per module. New module names start a new baseline.

## Failure modes

- A moved test silently stops running. Mitigation: the total collected test count and the set of test names (ignoring module path) match before and after.
- A parametrized case is dropped when a parameter list is split across files. Mitigation: a guard test asserts the split lists cover every expected validator exactly once.
- A helper copied instead of shared drifts. Mitigation: helpers move to one module that both files import.
- Copied `noqa` comments trip the security suppression policy (#4352). Mitigation: no `noqa` comments are copied.

## Security

No security surface. Test-only refactor. No production code, secrets, or input handling changes.

## Observability

What proves it works: the traced 16-worker run of the same 832-file subset, before and after, reporting collection time, median worker finish, last worker finish, and tail.

## Acceptance criteria

1. The test suite shall collect the same number of tests, with the same test names ignoring module path, before and after the change.
2. When `tests/test_validation_pre_pr.py` is run alone, it shall take under 5s.
3. When any file created by this change is run alone, it shall take under 30s.
4. Where a test is the dominant test of its file, the new file shall contain only that test's cases, and the spec shall name it.
5. If the real-checker parameter list is split across files, then a guard test shall fail when any validator in `_EXPECTED` is missing from the split lists or appears in both.
6. When the 832-file subset runs at 16 workers with tracing, the tail shall be smaller than the 35.5s baseline, and the before and after numbers shall be recorded on #6211.
7. The change shall not edit any production file under `scripts/`.
8. The moved tests shall pass alone and under `-n 16 --dist loadfile`.

## Out of scope

- Changing `--dist` mode (owner decision D2).
- Making the dominant tests faster. The real-checker tests scan the whole tree on purpose. See #5382.
- Per-worker collection cost (36.5s per worker). Recorded on #6211 as a separate finding.
- The mutation partition (9 files, 134s at 16 workers). See #5381.
- Ordering slow files first. It is a scheduling change, not a split, so the owner decides it separately.

## Deferred

- An automatic file-time ratchet. Owner: #6194 trend job.

## Open questions

None.

## CVA summary

- Common: every split file keeps the loadfile isolation contract and imports shared helpers from one module.
- Varies: why a file is slow. Time spread across tests can be split. A dominant test or a shared module fixture cannot.
- Relationship: file time is at least its dominant test time, so the floor after splitting is about 26s.

## Buy-vs-build decision

N/A (test refactor). The buy-vs-build pass on 2026-10-07 covered test selection, not this change.

## Complexity classification

Tier 2. Clear domain. Method: measure, split, measure again.
