# Live durable-outcome pilot, Claude harness only

Issue #5768. Produced by `scripts/eval/eval_durable_live.py` on 2026-09-30.

**Scope label: Claude only, not cross-harness.** One model (`claude-haiku-4-5-20251001`,
taken from the API response in the stream), one CLI (claude 2.1.285), one repetition per
task and control. Requested effort was `low`. The stream names no effort, so effort is
not verified. Base commit `e2c8d95fb88353992553a8cc69f1b1fe0dcdb610`.

## What was compared

Six tasks from the #5425 routing corpus, under two instruction controls. The control text
reached claude through `--append-system-prompt-file`. `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`
kept every other CLAUDE.md out.

| Control | Files | Bytes |
|---|---|---|
| `current` | CLAUDE.md, AGENTS.md, .claude/CLAUDE.md, builder-ethos.md, universal.md, voice.md | 40,774 |
| `reduced` | AGENTS.md | 2,076 |

Both used model haiku, `--max-turns 25`, and a retry budget of one correction round.
`RunConfig.context_bytes` is 0 in both files because `eval_durable_outcome.py --baseline`
refuses configs that differ in any field except `control`. The control sizes above and in
`run-summary.json` carry the difference.

## Result

| Task | current | reduced |
|---|---|---|
| RB-01 bounded implementation | REJECTED | REJECTED |
| RB-02 multi-file invariants | ACCEPTED_DURABLE (1 correction) | ACCEPTED_DURABLE (1 correction) |
| RB-03 investigate before edit | REJECTED | REJECTED |
| RB-04 scope expansion | ACCEPTED_DURABLE | ACCEPTED_DURABLE |
| RB-05 plausible but wrong | ACCEPTED_DURABLE | ACCEPTED_DURABLE |
| RB-06 architecture resolved | REJECTED | REJECTED |

| Headline | current | reduced |
|---|---|---|
| Accepted durable tasks | 3 of 6 | 3 of 6 |
| Cost per accepted durable task (USD, CLI list-price basis) | 0.2773 | 0.2143 |
| Correction minutes per accepted durable task | 0 | 0 |
| Residual risk | 2 | 2 |

`comparison.json` (reduced against current) reports `BETTER`: equal accepted durable tasks,
lower cost per accepted durable task, and no task that fell from a durable accept to zero.

Read that result as a pilot, not a finding:

- One repetition per cell. The same three tasks passed and the same three failed under both
  controls, so the 22 percent cost gap is the only difference, and one run per cell cannot
  separate it from sampling noise.
- The corpus has no "regression appears only after integration" case. The follow-up
  validation re-grades the agent's diff on a fresh `initial/` state, and it never disagreed
  with the final grade. No run was `ACCEPTED_NOT_DURABLE`.
- `review_findings`, `rollback_events`, and `rework_minutes` are 0 by construction. No
  reviewer ran, the driver has no rollback path, and no human touched a run.
  `unsupported_claims` and `unresolved_uncertainty` are regex proxies. See the
  `_durable_live.py` docstring.
- Haiku only. Nothing here speaks to Sonnet, Opus, Codex, or Copilot.

## Runs and files

| Directory | What it is |
|---|---|
| `claude-haiku-2026-09-30-run1` | First run, `--max-turns 12`, 19 launches. Six cells hit the turn limit and the script wrongly counted them as harness failures, so the comparison was refused. Kept as raw evidence: half the runs needed more than 12 turns. No record from this run is used in the result. |
| `claude-haiku-2026-09-30` | Second run, `--max-turns 25`, 20 launches. 11 of 12 cells produced a record. `reduced` RB-03 round 1 exited 1 at the turn limit and was wrongly counted as a harness failure, so `run-summary.json` says the comparison was refused. The script was fixed to grade a turn-limit exit. |
| `claude-haiku-2026-09-30-rerun-reduced-rb03` | Re-run of that one cell with the fixed script, 2 launches. |

`claude-haiku-2026-09-30/reduced-complete.jsonl` is `reduced.jsonl` (five records) followed
by the re-run's one record, joined with `cat`. `report-current.json`,
`report-reduced-complete.json`, and `comparison.json` in that directory come from
`eval_durable_outcome.py` over `current.jsonl` and `reduced-complete.jsonl`.
`invocations.jsonl` in each directory holds one summary per launch: observed model, turns,
tokens, cost, tool calls, tool errors, and permission denials. Full streams are not kept.

The run-2 cost total is 1.572 USD over 20 launches, the re-run 0.188 USD over 2, and run 1
1.240 USD over 19.
