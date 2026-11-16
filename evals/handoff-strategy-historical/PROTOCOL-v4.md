# Stalled-investigation strategy comparison: protocol v4

Issue #7350. Extends `PROTOCOL-v3.md`. Committed and pushed before the v4 launch.
Nothing here may change after the launch.

## What v3 left missing

The v3 batch (`runs/2026-11-15-v3/`, runner commit
`a427b61bda937e9fe831270438e8a65fdc00234d`) recorded 8 of 12 cells, all valid. The
other 4 cells failed with `claude exited 1`: both arms, repeats 1 and 2, on
`issue-6169-codex-login-stderr`. Each followed 8 completed cells. Each used the
whole retry ladder (60 s, 120 s, 240 s), which is why the batch ran about 28
minutes past its last recorded cell. The harness classified each as a transient
provider error with a reported cost, so spend stayed measured ($1.4452 total).
The hub answered 3 of 3 small probes normally 8 minutes after the batch ended.

Under the frozen rule, a missing cell makes the result INCONCLUSIVE. The 4 missing
cells hold the negative control's repeats 1 and 2 in both arms.

## Disclosure

I read the 8 completed cells before writing this file. Both arms passed all 3
stalled-task repeats with 0 repair turns, and both passed the negative control's
repeat 0. The decision to fill the missing cells does not depend on those results.
The rule would yield INCONCLUSIVE on a missing cell whatever the 8 showed, and the
cells to run are named by one reason only: a harness failure from a provider error.

## The change

Run the 4 missing cells, and only those, in a separate batch. The v3 cells are not
rerun and not replaced. A cell is scored once.

- New flag `--start-repeat N` runs repeat indices N and up. The ceiling holds:
  `start + repeats` may not exceed 3.
- New flag `--combine DIR [DIR ...]` reads each batch's `report.json`, refuses a
  cell present twice, and applies the frozen `decide` rule over all cells with 12
  expected. It writes `decision.json`.

The combined result is the result of the experiment. The fill batch's own
`report.json` carries a decision computed over its 4 cells alone, which is not the
experiment's decision.

## Two disclosures about the v3 batch and this one

- The facts block's observed output is the reproduction's own output, run once
  per cell. It carries the runner's timing line (for example `in 0.12s`), which
  varies by cell. So "the same bytes to both arms" holds for everything but that
  number. It is not a strategy signal, and the arms are interleaved so neither
  gets systematically faster or slower runs.
- The report now carries a non-graded leading `notes` key with the repository's
  `citation-freshness: ignore` marker, because the report quotes file and line
  citations from the issue text and from agent replies about the pre-fix commit.
  The v3 `report.json` was re-serialized with that key and no other change.

## Unchanged

Everything in `PROTOCOL.md`, `PROTOCOL-v2.md`, and `PROTOCOL-v3.md`: tasks, task
file hash, arms, role files, prompts, tools, model `claude-sonnet-5-5`, effort
`medium`, harness, hub auth with the same two forwarded variable names, 2 repair
rounds, 600 s per launch, the retry rule, the decision rule, and every abort
condition. Spend cap: v3 spent $1.4452 of the $20 cap, so this batch is capped at
`--max-cost-usd 15`, which keeps the total below $20.

## Run commands

```bash
. /path/to/operator/eval-env.sh   # sets ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY
uv run python scripts/eval/eval_handoff_strategy.py \
  --tasks scripts/eval/examples/handoff-strategy-tasks.json \
  --only-tasks issue-6169-codex-login-stderr --start-repeat 1 --repeats 2 \
  --model claude-sonnet-5-5 --effort medium --max-cells 4 --max-cost-usd 15 \
  --timeout 600 --real-home --pass-env ANTHROPIC_BASE_URL,ANTHROPIC_API_KEY \
  --workspace-root "$(mktemp -d)" \
  --output-dir evals/handoff-strategy-historical/runs/2026-11-15-v4-fill

uv run python scripts/eval/eval_handoff_strategy.py \
  --tasks scripts/eval/examples/handoff-strategy-tasks.json \
  --combine evals/handoff-strategy-historical/runs/2026-11-15-v3 \
            evals/handoff-strategy-historical/runs/2026-11-15-v4-fill \
  --output-dir evals/handoff-strategy-historical/runs/2026-11-15-combined
```

If the fill batch loses a cell to another provider failure, that cell stays
missing and the combined result is INCONCLUSIVE. No third batch runs.
