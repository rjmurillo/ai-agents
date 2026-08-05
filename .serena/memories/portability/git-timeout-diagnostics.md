# Git timeout diagnostics in portability validators

## Decision

Use `git_timeout_problem(proc, action)` at every fail-closed Git call site that needs operator-facing diagnostics.

## Reason

`run_git` returns code 124 on timeout. Generic `returncode != 0` checks still fail closed, but they hide which Git probe timed out. This makes CI failures hard to diagnose.

The 30-second bound is a hang ceiling, not a latency target. On 2026-08-05,
20 runs of every bounded probe in this repository covered 169,611 Git objects.
The slowest command was object enumeration at 179.915 ms maximum and
155.260 ms median. The next-slowest maximum was 22.681 ms. The bound was
therefore more than 166 times the slowest observed result.

## Reproduce calibration

Run this from the repository root:

```python
import statistics
import subprocess
import time

commands = {
    "root": ["rev-parse", "--show-toplevel"],
    "head": ["rev-parse", "--verify", "--quiet", "HEAD"],
    "tree": ["ls-tree", "-r", "-z", "--full-tree", "HEAD"],
    "refs": ["show-ref", "--head"],
    "ref-list": ["for-each-ref", "--format=%(objectname)"],
    "objects": [
        "cat-file",
        "--batch-check=%(objecttype)",
        "--batch-all-objects",
    ],
    "history": [
        "log",
        "-1",
        "--format=%H",
        "HEAD",
        "--",
        "scripts/validation/portability_git.py",
    ],
    "attribute": [
        "check-attr",
        "diff",
        "--",
        "scripts/validation/portability_git.py",
    ],
    "blob": [
        "cat-file",
        "blob",
        "HEAD:scripts/validation/portability_git.py",
    ],
}

for name, args in commands.items():
    samples = []
    for _ in range(20):
        start = time.perf_counter()
        subprocess.run(
            ["git", "--no-replace-objects", *args],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        samples.append(time.perf_counter() - start)
    print(
        name,
        round(statistics.median(samples) * 1000, 3),
        round(max(samples) * 1000, 3),
    )
```

Recorded output in milliseconds, shown as median then maximum:

```text
object-count 169611
attribute 3.502 4.126
blob 3.113 3.819
head 1.789 1.929
history 3.795 4.884
objects 155.260 179.915
ref-list 3.241 4.916
refs 3.797 22.681
root 1.712 2.679
tree 9.553 20.721
```

The object count comes from:

```bash
git --no-replace-objects cat-file --batch-check='%(objectname)' \
  --batch-all-objects | wc -l
```

One fixed bound keeps local and CI behavior deterministic. An environment
override would let the same commit pass locally and fail in CI. Per-operation
budgets add policy without an observed need. Retries would multiply a local
resource stall and delay the same fail-closed result.

## Failure mode

A larger repository or degraded disk can make a legitimate Git probe exceed
30 seconds. The validator will refuse the change and name the timed-out
operation. Reproduce that operation in the affected repository before changing
`GIT_TIMEOUT_SECONDS`. Increase the shared ceiling only when the measured
legitimate runtime needs it.

## Pattern

1. Call `run_git`.
2. Call `git_timeout_problem` with the exact operation.
3. Print or return the operation-specific problem.
4. Keep the existing generic nonzero fallback for other Git failures.

## Evidence

The follow-up to PR #4568 applied this pattern to tree listing, ref listing, object enumeration, repository-root lookup, HEAD lookup, baseline attributes, shared Git-line reads, history lookup, and committed-object reads. The focused portability selection passed 204 tests. The full suite passed 23,320 tests with 33 skips. Ruff and targeted mypy passed. Final observability review found no Critical or High issue.

## Files

- `scripts/validation/portability_git.py`
- `scripts/validation/portability_baseline.py`
- `scripts/validation/portability_common.py`
