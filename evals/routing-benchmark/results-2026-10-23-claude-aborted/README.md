# Routing benchmark Claude run, aborted by a grader defect, 2026-10-23 (issues #5424 and #5426)

Harness: native `claude` CLI `2.1.309 (Claude Code)`. Predictions: `../PREDICTIONS.md` (`predictions-v1` with Amendments 1 to 4). The run started on 2026-10-23 at 10:03 (operator clock), before Amendment 5, with the old grader. It completed all 72 planned rows. The owner decided (D13) to fix the grader and repeat the run, so this run is reported and not used.

**Not pooled and no floor credit.** This run is reported apart from `../results-2026-10-23-claude-v2/` and never pooled with it. It does not count toward any evidence floor. The scorer output below is what the old grader produced and is kept as a record.

Result as scored: `INSUFFICIENT_EVIDENCE` for H1, H2, H3, H4 and for the strategy decision. Rows: ACCEPTED 56, TASK_FAILED 16, HARNESS_FAILED 0, NOT_RUN 0.

Launch: `--harnesses claude`, arms A, B, E, and F, 3 repetitions, two processes: A with E (cap 164 invocations) and B with F (cap 236). The subscription login was used. `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and the Bedrock and Vertex variables were unset and stripped by the runner. The run used 214 invocations, 6,528 seconds of wall time summed over invocations, 1,071,494 input tokens (net of cache reads) and 564,538 output tokens.

Files: `arms-AE.jsonl`, `arms-BF.jsonl` (one JSON line per row) and `verdicts.json` (scorer output, stored on one line with `json.dumps` because the pretty-printed form is 554 lines and exceeds the repository file-size lint; the content is unchanged). The runner logs `arms-AE.log` and `arms-BF.log` were empty (0 bytes) and are not kept.

## The grader defect

The #5425 grader ignored only `__pycache__` and `.pyc` files when it listed changed paths. A worker that ran pytest in its workdir left a `.pytest_cache` folder behind, and the grader counted each file in it as a scope violation. Running the scenario's checks is not an edit to the tree, so the defect is in the grader and not in any arm. Amendment 5 (PR #6888) makes the grader also ignore `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, and `.hypothesis`.

Evidence in this run: 6 of 72 rows failed with `.pytest_cache` as the only scope violation: RB-06 arm A repetition 1, RB-01 arm A repetition 2, RB-06 arm A repetition 2, RB-01 arm A repetition 3, RB-05 arm A repetition 3, and RB-01 arm B repetition 3. Five are arm A rows (5 of arm A's 6 failures) and one is arm B. The check output was not stored, so these rows cannot be graded again. That is why the whole run was repeated and not patched.

## What ran

Rows per scenario, arm, and repetition (A is ACCEPTED, T is TASK_FAILED, H is HARNESS_FAILED). Arms C and D were rejected before the run (see Effort evidence) and have no rows.

| Scenario | Arm A | Arm B | Arm E | Arm F |
|---|---|---|---|---|
| RB-01 | r1:A r2:T r3:T | r1:A r2:A r3:T | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-02 | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-03 | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-04 | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-05 | r1:A r2:A r3:T | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-06 | r1:T r2:T r3:T | r1:T r2:T r3:T | r1:T r2:T r3:T | r1:T r2:T r3:T |

## Per-arm results (old grader)

Counts as of 2026-10-23. The old grader depresses arm A most, so these tables are not a comparison of arms.

| Arm | Class | Runs | Accepted | Rate | Residual defects per run | Mean seconds per accepted | Mean uncached tokens per accepted |
|---|---|---|---|---|---|---|---|
| A | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 99.2 | 27,288 |
| A | ordinary_bounded | 12 | 6 | 50.0% | 1.75 | 197.4 | 44,365 |
| B | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 125.8 | 33,914 |
| B | ordinary_bounded | 12 | 8 | 66.7% | 0.58 | 189.5 | 55,058 |
| E | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 33.6 | 7,441 |
| E | ordinary_bounded | 12 | 9 | 75.0% | 0.25 | 61.6 | 11,614 |
| F | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 86.1 | 22,343 |
| F | ordinary_bounded | 12 | 9 | 75.0% | 0.25 | 134.2 | 30,992 |

Pooled across the six scenarios:

| Arm | Class | Runs | Accepted | Rate | Residual defects per run | Mean seconds per accepted | Mean uncached tokens per accepted |
|---|---|---|---|---|---|---|---|
| A | all six pooled | 18 | 12 | 66.7% | 1.17 | 148.3 | 35,827 |
| B | all six pooled | 18 | 14 | 77.8% | 0.39 | 162.2 | 45,997 |
| E | all six pooled | 18 | 15 | 83.3% | 0.17 | 50.4 | 9,945 |
| F | all six pooled | 18 | 15 | 83.3% | 0.17 | 114.9 | 27,532 |

## Scorer verdicts (old grader)

Command: `uv run python scripts/eval/eval_routing_verdicts.py --results arms-AE.jsonl arms-BF.jsonl --output verdicts.json`. Decision: `INSUFFICIENT_EVIDENCE`. Rows scored: 72.

| Hypothesis | Status | Reason from the scorer |
|---|---|---|
| H1 | INSUFFICIENT_EVIDENCE | arm C in ordinary_bounded has no runs |
| H2 | INSUFFICIENT_EVIDENCE | fallback class: arm D in fallback_reasoning has no runs |
| H3 | INSUFFICIENT_EVIDENCE | neither SUPPORTED nor FALSIFIED rule holds |
| H4 | INSUFFICIENT_EVIDENCE | fallback evidence rule not met |

H1 and H2 need arms C and D, which have no runs. The H3 and H4 reasons are the scorer's. They are not a finding about the arms, because the grader defect changed arm A's counts.

## Effort evidence

Effort evidence for every row and for the verdict block is `behavioral` (Amendment 4). The Claude stream names no reasoning effort. Each of the 214 invocations records `model_verdict` HONORED (the requested model was observed) and `effort_verdict` UNVERIFIED (the requested effort was never observed). An arm that "uses high effort" means it requested high.

Behavioral measurement on 2026-10-23, `claude` 2.1.309, thinking tokens at each level, from Amendment 4 item 6:

| Model | low | medium | high | Result |
|---|---|---|---|---|
| claude-opus-5-5 | 100 | 106 | 134 | verified |
| claude-sonnet-5-5 | 105 | 103 | 105 | not verified |
| claude-haiku-5-5 | 285 | 233 | 337 | not verified |

Opus 5.5 strictly increases, so arms A, B, E, and F were planned. Sonnet 5.5 and Haiku 5.5 do not, so arms C and D were rejected and not substituted. They have no rows.

## Observations that are not verdicts

The scorer does not read these.

- Five of arm A's six failures are `.pytest_cache`-only rows, so arm A's 12 of 18 here is depressed by the grader defect. The repeated run under the fixed grader shows arm A at 15 of 18.
- RB-06 failed in all 12 rows. Two of them (arm A repetitions 1 and 2) failed only on `.pytest_cache`. The other 10 failed on a follow-up check with no itemized scope violation or missing file.
