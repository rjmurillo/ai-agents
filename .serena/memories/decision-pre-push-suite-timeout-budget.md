# Decision: split pre-push suites share one timeout budget

## Question

`run_pytest` in `scripts/validation/git_hook_policy.py` was changed (PR #3568,
issue #3562) to run the pre-push suite as TWO pytest processes instead of one,
so that `tests/test_safe_push_pr_branch.py` could be selected with a different
marker expression (`not safe_push_transport`) than the rest of the suite
(`not integration`). Should each process get its own timeout?

## Conventional answer

Pass the module-level ceiling to each subprocess. That is what the first
implementation did: every command received `TEST_SUITE_TIMEOUT_SECONDS`
(1740s) as its own `timeout_seconds`.

## First-principles position

`TEST_SUITE_TIMEOUT_SECONDS` is named for the SUITE, not for a process. Its
purpose is to bound how long `git push` can block. Splitting the suite across
N processes and handing each the full ceiling silently multiplies that bound
by N. Lefthook has its own outer deadline, so the hook can be killed from
outside at a time that depends on how the suite happens to be partitioned.
The failure then looks nondeterministic and gets blamed on flakiness.

The invariant that matters is: total wall clock spent in pytest during
pre-push <= TEST_SUITE_TIMEOUT_SECONDS, regardless of how many commands the
partition produces.

## Evidence

- `scripts/validation/git_hook_policy.py`, constant at line 99,
  `_pytest_commands` and `run_pytest` near line 2962.
- Flagged by Copilot review thread `PRRT_kwDOQoWRls6UPk2_` on PR #3568.
- Reproduced by `test_run_pytest_shares_one_timeout_budget_across_commands`
  in `tests/test_safe_push_pr_branch.py`, which records the
  `timeout_seconds` handed to each command and asserts it decreases by the
  elapsed time. Under revert it fails because both values equal the constant.

## Decision

`run_pytest` computes `deadline = time.monotonic() + TEST_SUITE_TIMEOUT_SECONDS`
once, then passes `deadline - time.monotonic()` to each command and returns
exit 1 with an explanatory message if the budget is spent before a command
starts. Adding a third partition cannot extend the push block.

Related: the same PR wraps `OSError` and `SyntaxError` from the object id
validator import so every load failure raises `RuntimeError` naming the
module path, with the original exception preserved as `__cause__`. Before
that, a missing file produced a bare `FileNotFoundError` while a missing
symbol produced a `RuntimeError`, so workflow logs told two different stories
for the same class of failure.

## Worker count refinement

Issue #4823 correctly uses `-n auto` for isolated CI jobs. The local pre-push
suite is not isolated. Lefthook runs `python-tests` beside other CPU-heavy jobs
in one parallel group.

On 2026-08-12, three normal pushes on a 48-thread host produced 9, then 33
subprocess timeout failures. The same nodes passed immediately when isolated.
The local hook now sets `AI_AGENTS_PYTEST_WORKER_CAP=4`. The effective count is
the smaller of that cap and the visible CPU count. CI and direct calls keep the
`auto` default, and an explicit `AI_AGENTS_PYTEST_WORKERS` override still wins.
`run_pytest` consumes both control variables before starting child pytest
processes, so policy tests observe an ordinary environment.

This is not a reduction in coverage. Every partition still runs. The cap
reduces local scheduler contention while preserving the suite-wide timeout
budget above.
