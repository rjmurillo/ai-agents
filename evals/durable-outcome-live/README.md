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

## Repeated run with hidden-regression tasks (n=3), Claude harness only

Issue #5768, second run, 2026-09-30. Code commit `f9ca29d9b`.

**Scope label: Claude only, not cross-harness.** Same model
(`claude-haiku-4-5-20251001`, observed in all 75 launches), same CLI (claude 2.1.285),
same two controls and control sizes as the pilot above, retry budget one, `--max-turns 25`.
Requested effort `low`. **Effort is unobservable**: the stream does not report it, and
`run-summary.json` records `effort_observed` as unobservable instead of a value.

### Corpus

Eight tasks: the six #5425 routing tasks plus two extension tasks from
`corpus/` (category `post_integration_regression`). Each extension task has a plausible
change that passes its local check and fails a check that exists only after integration.

| Task | Hidden regression | Integration check |
|---|---|---|
| HR-01 top-scores-order | `top_scores` sorts the caller's list in place | `chronology_and_best` must keep play order |
| HR-02 merge-settings-defaults | `merge_settings` edits its first argument | the next `load_settings` must see the shipped defaults |

The grader was tested with three fixtures per task: known-good passes both stages,
known-bad fails the local check, and the hidden-regression overlay passes the local
check and fails the integration check with marker `INTEGRATION_REGRESSION`
(`tests/eval/test_routing_integration.py`, `eval_routing_corpus.py --extension`).

### Runs

Three chunks, one per repetition, 8 tasks x 2 controls each (`rep0`, `rep1`, `rep2`).
Exactly 75 `claude` launches, 0 harness failures, 5.31 USD at the CLI list-price basis.
The pilot's 41 launches are not part of this count. `current.jsonl` and `reduced.jsonl`
join the three chunks with `cat`. `comparison.json`, `report-*.json`, and
`repetitions-*.json` come from `eval_durable_outcome.py` and `eval_durable_repetitions.py`.

### Result (24 runs per control)

| | current | reduced |
|---|---|---|
| Accepted durable | 15 | 14 |
| Accepted, not durable | 0 | 0 |
| Rejected | 9 | 10 |
| Cost per accepted durable task (USD) | 0.2044 | 0.1605 |
| Zero-success tasks | RB-01, RB-03, RB-06 | RB-01, RB-03, RB-06 |

`comparison.json` returns `MIXED`: reduced has one fewer durable accept (14 against 15)
and a lower cost per durable accept.

Variance across the three repetitions (sample standard deviation, n=3):

| | current | reduced |
|---|---|---|
| Durable accepts per repetition | 5, 5, 5 (stdev 0) | 5, 5, 4 (stdev 0.577) |
| Cost per durable accept per repetition (USD) | 0.2068, 0.2060, 0.2003 (stdev 0.0035) | 0.1648, 0.1375, 0.1840 (stdev 0.0234) |

The only task whose verdict changed across repetitions is RB-05 under `reduced`
(durable, durable, rejected). Every other task has the same verdict in all three
repetitions under both controls.

### What the data supports

- No run was `ACCEPTED_NOT_DURABLE`. Haiku produced a durable result on HR-01 and HR-02
  in all 12 runs (6 per control). The fixtures prove the grader would have flagged a
  hidden regression. The live runs did not produce one, so they say nothing about how
  often a model ships one.
- All three `reduced` repetitions (0.1375 to 0.1840 USD per durable accept) cost less than
  all three `current` repetitions (0.2003 to 0.2068). That is three paired observations on
  one model. It does not show the cost gap generalizes, and this run makes no significance claim.
- The durable-accept difference is one run (RB-05, one repetition). It is within what one
  flipped run produces.
- Eight tasks, one model, one harness. Nothing here speaks to Sonnet, Opus, Codex, or Copilot.

### Measured and unmeasured fields

| Field | Status |
|---|---|
| `rework_minutes` | Measured: wall minutes of correction rounds (round 1 and later). Agent rework only. Totals: 12.86 (current), 10.01 (reduced). The headline "correction minutes per accepted durable task" is now agent rework, not human time. |
| `human_correction_minutes` | 0, no human touched a run. |
| `review_findings` | 0 by construction. No reviewer ran. Not a measured absence. |
| `rollback_events` | 0 by construction. The driver has no rollback path, so an accepted change is never undone. Not a measured absence. |
| `unsupported_claims` | Regex proxy, now also counted when the integration check fails. |
| `unresolved_uncertainty` | Hedge-phrase regex proxy. Weakest evidence. |
| Effort | Unobservable. Not recorded as a value. |

## Codex harness, repeated run (n=3), cross-harness half of #5768

Issue #5768, 2026-10-03. Driver commit `75c32c4f9`, run with `eval_durable_live.py --harness codex`.

**Scope label: Codex only, one model.** Model `gpt-5.6-luna`, taken from the backend response frames in all
69 launches. CLI `codex-cli 0.160.0` in all 69 launches (the CLI updated itself between earlier probes and this run).
Requested effort `low`, and the backend frames named `low` in every launch, so effort is verified here, unlike the Claude
runs. Same eight tasks, same two controls, same control text sources, retry budget one, three repetitions.
Claude-side results above are `claude-haiku-4-5-20251001`.

Launches: 69 (24, 22, 23 per repetition), 0 harness failures. Spend is in subscription credits and is not priced:
Codex reports no cost and the repo has no published rate for the GPT-5.6 ids, so `model_cost_usd` is `0.0` and means
unavailable. The cost-per-durable-accept lines in the reports and in `comparison.json` are therefore not comparable and
say nothing. Compare tokens instead.

### Result (24 runs per control)

| | current | reduced |
|---|---|---|
| Accepted durable | 16 | 12 |
| Accepted, not durable | 0 | 0 |
| Rejected | 8 | 12 |
| Durable accepts per repetition | 6, 4, 6 (stdev 1.15) | 2, 6, 4 (stdev 2.00) |
| Zero-success tasks | RB-06 | RB-01, RB-06 |
| Uncached input tokens, all launches | 918,079 | 746,515 |
| Cached input tokens | 6,334,208 | 5,677,312 |
| Output tokens | 47,792 | 54,198 |
| Launches (including corrections) | 33 | 36 |
| Wall seconds, all launches | 1,272 | 1,552 |

`comparison.json` returns `WORSE` for reduced against current on durable accepts. Per repetition the sign changes
(repetition 1 returned `BETTER`), and the stdev of reduced is 2.0 on a mean of 4. Three repetitions support no
significance claim.

### Against the Claude result

| | Claude haiku, current | Claude haiku, reduced | Codex luna, current | Codex luna, reduced |
|---|---|---|---|---|
| Accepted durable of 24 | 15 | 14 | 16 | 12 |
| Zero-success tasks | RB-01, RB-03, RB-06 | RB-01, RB-03, RB-06 | RB-06 | RB-01, RB-06 |

- RB-06 (architecture resolved) failed in every run on both harnesses and both controls.
- The direction of the control effect differs: Claude shows a one-run gap (15 against 14), Codex a four-run gap
  (16 against 12). Different models and harnesses, so this is two observations and not a harness effect.
- No run on either harness was `ACCEPTED_NOT_DURABLE`. Neither harness produced a live hidden regression.

### What limits this result

- **Ambient instructions.** Codex runs with the operator's own `CODEX_HOME`, so `~/.codex/AGENTS.md`
  (9,533 bytes) and skills load under both controls. The `reduced` control is the 2,076-byte AGENTS.md plus that
  constant, not AGENTS.md alone. An earlier draft isolated the home with a link to the login file. It was removed
  because the repository never links, copies, or reads a credential file. Two launches from that draft are in no result.
- `current` is 40,854 bytes here and was 40,774 for the Claude runs, because `main` moved.
- `review_findings`, `rollback_events`, `unsupported_claims`, `unresolved_uncertainty`: same by-construction and proxy
  limits as the Claude runs.
- `unapproved_external_actions` can under-count on Codex. A failed shell command counts as a tool error, as a failed
  Bash call does on Claude, and the driver subtracts tool errors from calls outside the allowed set, so a failing test run
  can offset one real non-shell call. Neither run produced a non-shell call, so the count was not affected here.
- A model-generated command can read files outside the workspace, because `-s workspace-write` limits writes and not
  reads. The same holds for the Claude driver's `Bash(python:*)`.

Files: `codex-luna-2026-10-03-n3/rep0` to `rep2` hold the per-repetition JSONL, `invocations.jsonl` (model, effort,
tokens per launch), and `run-summary.json`. `current.jsonl`, `reduced.jsonl`, `report-*.json`, `repetitions-*.json`,
and `comparison.json` come from `eval_durable_outcome.py` and `eval_durable_repetitions.py` over the joined files.
