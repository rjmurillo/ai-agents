# Pre-push wall clock is python-tests; everything else is noise

Measured on a real push of one documentation file, 2026-08-19, 4-CPU container,
branch `claude/pre-push-hook-duration-vru1ti`. Lefthook 2.1.10 per-job times as
the hook reported them:

```text
repair-packed-refs        0.16s
mutation-safety           0.15s
push-ref-staleness        0.84s
stdin piped group         1.80s
fast parallel stage      56.21s   (max member merge-tree-ratchet 22.17s)
security-scan             0.41s   (nothing scannable in the push)
expensive parallel group 620.03s
  python-tests           498.52s
  pre-pr-validation      110.12s
  the other ten jobs     under 3s each
```

Total about 679s, 11.3 minutes, to push one markdown file. The suite ran in
full: nothing in the pre-push graph scopes `python-tests` to the push range,
while CI's `pytest.yml` does apply a paths filter and skips the suite for
unrelated markdown.

## Where the time actually is

`python-tests` runs four partitions in a `for` loop
(`git_hook_policy.py` `run_pytest`), so they add rather than overlap. Isolated
on the same box:

```text
bulk       28327 tests  257.90s   54%
mutation      24 tests  166.64s   35%
safe-push     46 tests   36.89s    8%
pr-autofix    30 tests    8.84s    2%
                        -------
                         475s
```

The mutation partition is 35 percent of the job for 24 tests because each test
runs `git worktree add` on the whole repo plus a nested pytest, serialized by
the global lock in `scripts/testing/mutation_workspace_git.py`
(`_serialized_worktree_state`), so `-n 4` does not help it. CI runs mutation,
safe-push, and pr-autofix as separate parallel matrix legs at
`timeout-minutes: 10`, so dropping them locally loses no gate.

## Contention factors, measured rather than assumed

In-hook divided by isolated, same box, same day:

```text
python-tests        498.52 / 475.00  = 1.05
pre-pr-validation   110.12 / 103.25  = 1.07
fast parallel stage  56.21 /  21.05  = 2.67
```

The expensive jobs barely stretch. The fast stage nearly triples, because
fifteen short jobs contend for four cores at once. Do not carry a standalone
number for a fast-stage job into a timeout decision (`ci-scripts.md` MUST-16).

## The same work runs twice in one hook

The fast stage runs all eight count ratchets as parallel lefthook jobs. Then
`pre-pr-validation` runs the identical eight again, serially through
`uv run`, as its `Count Ratchets` gate (`checks_ratchet.py` `RATCHETS`):
38.37s of its 103.25s. `Unreachable Code Detection` (5.83s),
`Path Normalization` (1.72s), and `Planning Artifacts` duplicate fast-stage
jobs the same way. The hook is `piped: true`, so `pre-pr-validation` cannot
start unless the fast-stage copies already passed; the second run cannot
discover anything.

## Measured non-levers, so nobody re-derives them

```text
mypy                     1.07s cold, 0.16s warm (scoped to files differing from origin/main)
advisory jobs            at most 1.04s each on a checkout with no worktrees
semgrep                  6.68s for 7 files, 310 rules
pre_pr.py --quick        saves 1.89s of 103.25s, the four quick gates are cheap now
```

`--skip-tests`, `SKIP_TESTS`, and `--verbose` were parsed by `pre_pr.py` and
never read. All three are removed, along with the `_Gate.skip_flag` field no
gate ever set. Passing any of them now fails with argparse exit code 2.

## Reproduce

```bash
AI_AGENTS_PYTEST_WORKER_CAP=4 uv run --frozen python scripts/validation/git_hook_policy.py pytest
SKIP_AUTOFIX=1 uv run --frozen python scripts/validation/pre_pr.py   # per-gate times print at the end
```

Refs issue #4710 (hook latency), issue #5066 (fast-fail staging).
