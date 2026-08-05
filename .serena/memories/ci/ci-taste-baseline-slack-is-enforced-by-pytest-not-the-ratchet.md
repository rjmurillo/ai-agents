# Skill: The taste baseline slack ceiling is enforced by pytest, not by the ratchet (98%)

## Statement

`scripts/ci/count_ratchet.py` holds two separate ideas that read like one.

The **ratchet** answers "did this branch add violations?" The **baseline health
check** answers "does the committed scalar still describe the tree?" Only the
first runs in the ratchet's own code path. The second is a library function
whose entire caller set lives in tests.

Consequence: when the committed baseline drifts too far above the real count,
the failure surfaces as a **red pytest job**, not as a red taste-ratchet check.
Anyone who diagnoses it by reading ratchet output finds nothing wrong and
concludes the tree is fine.

## Cause

Verified 2026-08-05 by listing every reference in the repository:

```text
scripts/ci/count_ratchet.py:206   def baseline_health(...)      <- the only definition
tests/ci/test_count_ratchet_against_real_git.py:117             <- caller
tests/ci/test_count_ratchet_baseline_health.py:22..73           <- callers
```

Every caller is a test. There is no production call site.

The ratchet's real runtime path (`count_ratchet.py:447-478`) has exactly two
outcomes:

- `count > baseline` -> fail
- `count < baseline` -> pass

A count *below* the baseline is the drift case, and the ratchet passes it. That
is deliberate: a branch that removes violations must not be punished. The cost
is that the ratchet cannot notice accumulated drift, so a second mechanism has
to, and that mechanism is a test.

The single production enforcer is
`tests/ci/test_count_ratchet_against_real_git.py:94-118`,
`test_the_shipped_baseline_describes_the_tracked_tree`. Its docstring records
two real outages on 2026-08-03, at baselines 595 and 593.

## The arithmetic that trips it

`MAX_BASELINE_SLACK = 5` (`count_ratchet.py:186`). Its docstring says it was
calibrated against a largest-observed collision of two concurrent PRs.

For `n` PRs that each lower the true count by `d` while writing the same new
baseline, combined slack is `(n-1) * d`, and the check fails when that exceeds
5:

| Scenario | Slack | Result |
|---|---|---|
| 6 PRs remove a violation each, baseline untouched | 6 | fails |
| 6 PRs each write `B-1` | 5 | passes |
| 7 PRs each write `B-1` | 6 | fails |

A merge queue makes the collision count a scheduling parameter rather than an
accident, so a ceiling calibrated at two is the wrong size for a queue that
batches seven. Tracked as issue #4608.

## Recipe

When taste or count CI is red and the ratchet output looks clean, check the
baseline against the tree before reading anything else:

```bash
cat scripts/ci/taste_count_baseline.txt
git show origin/main:scripts/ci/taste_count_baseline.txt
uv run --frozen python3 -m pytest -q -p no:randomly \
  tests/ci/test_count_ratchet_against_real_git.py
```

A local baseline *above* main's means the branch is stale; merge main first.
A failure from that pytest file with a clean ratchet means drift, not a
regression your branch introduced.

## Generalization

A threshold constant is not a gate. `MAX_BASELINE_SLACK` looks like policy
sitting next to the enforcement code, and it is policy sitting next to code
that never reads it. Before trusting any constant to bound behavior, list its
callers and check that at least one runs in production. If every caller is a
test, the constant describes what the tests assert, not what the system does.
