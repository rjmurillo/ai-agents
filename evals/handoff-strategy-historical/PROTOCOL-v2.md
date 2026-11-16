# Stalled-investigation strategy comparison: protocol v2

Issue #7350. Supersedes `PROTOCOL.md` (v1) for the run. Committed and pushed
before any v2 launch. Nothing here may change after the first v2 launch.

## Why v1 produced no result

The v1 batch ran at runner commit `e1c9dfe0ab26ef1fea6175b41294adf664db4298`
and is archived in `runs/2026-11-15-v1-rate-limited/report.json`. It recorded 0
cells and $0.00 of spend. The first launch (task `issue-7328-mypy-symlink-run-mypy`,
arm `continue_analyst`, repeat 0) exited 1. I reproduced that launch with a
wrapper that kept the CLI's output. The stream held a `rate_limit_error` from
the provider, `total_cost_usd` 0, and zero tokens. A bare launch minutes later
succeeded, so the limit was intermittent. Other agents share the same account.

The harness read that exit as an unmeasured cost. The spend guard fails closed on
an unmeasured cost, so the other 11 cells were skipped. No cell reached a
reproduction, a held-out check, or a decision. No outcome was seen before this
file was written. Nothing in the task set, arms, caps, or decision rule changes
in response to a result.

A second defect surfaced while reading that code. When a launch failed partway
through a cell, the spend of the cell's earlier launches was dropped from the
guard. That error would have under-counted spend against the $20 cap.

## The changes

1. **Transient errors are retried, not scored.** A launch whose stream names
   `rate_limit_error` or `overloaded_error` and reports a cost is transient. The
   runner waits 60 s, 120 s, then 240 s and relaunches the same prompt, up to 3
   times per launch, identically in both arms. A retry is not a repair turn and
   does not use the correction budget. Each cell records `transient_retries`.
   Wait time is not counted as wall time. Failed attempts count their reported
   cost and elapsed time.
2. **A transient failure that exhausts its retries is a measured $0 failure.**
   The stream reported its cost, so the guard does not fail closed. The cell is
   recorded as a harness failure, not retried again, and the decision rule's
   "missing or invalid cells" clause makes the result INCONCLUSIVE.
3. **A failed cell carries its whole spend.** Earlier launches in the cell are
   added to the guard.

An error with no named provider limit, or one that reports no cost, behaves as in
v1: no retry, and the guard fails closed.

## Unchanged from v1

Task file (SHA-256 `bad0f411a3a6681037942b45c760fab949dffa3a3ee50d2a35cfde0cce8ab315`),
base and fix commits, reproductions, held-out checks and deselected nodes,
`known_good` and `known_bad`, arms, role files and their hashes, instructions,
prompt templates, tools, model `claude-sonnet-5-5`, effort `medium`, harness,
`--real-home`, 3 repetitions per arm per task, 2 repair rounds, 600 s per launch,
`--max-cells 12`, `--max-cost-usd 20`, per-run fields, abort conditions, limits,
and the decision rule. v1 stands for all of them.

The v1 hard ceilings still hold: 2 tasks, 3 repetitions, one model, one effort,
one harness. The total launch ceiling is unchanged in model-launch terms: at most
72 completed launches. Transient retries add failed attempts that reported $0.

## Run command

```bash
uv run python scripts/eval/eval_handoff_strategy.py \
  --tasks scripts/eval/examples/handoff-strategy-tasks.json \
  --repeats 3 --model claude-sonnet-5-5 --effort medium --max-cells 12 \
  --max-cost-usd 20 --timeout 600 --real-home \
  --workspace-root "$(mktemp -d)" \
  --output-dir evals/handoff-strategy-historical/runs/2026-11-15-v2
```
