# Routing benchmark Claude run, 2026-10-23 (issues #5424 and #5426)

Harness: native `claude` CLI `2.1.309 (Claude Code)`. Predictions: `../PREDICTIONS.md` (`predictions-v1` with Amendments 1 to 5). The run started on 2026-10-23 at 15:59 (operator clock) on commit 9d6df0fbc, which carries the grader fix of Amendment 5 (PR #6888). It repeats `../results-2026-10-23-claude-aborted/` in full under the fixed grader.

**Result: INSUFFICIENT_EVIDENCE for H1, H2, H3, H4 and for the strategy decision.** All 72 planned rows ran: ACCEPTED 60, TASK_FAILED 12, HARNESS_FAILED 0, NOT_RUN 0. The run stopped for no external reason.

Launch: `--harnesses claude`, arms A, B, E, and F, 3 repetitions, two processes: A with E (cap 164 invocations) and B with F (cap 236), 400 in total. The subscription login was used. `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and the Bedrock and Vertex variables were unset and stripped by the runner. The runs used 209 invocations, 5,820 seconds of wall time summed over invocations, 935,889 input tokens (net of cache reads) and 493,185 output tokens.

Files: `arms-AE.jsonl`, `arms-BF.jsonl` (one JSON line per row) and `verdicts.json` (scorer output, stored on one line with `json.dumps` because the pretty-printed form is 554 lines and exceeds the repository file-size lint; the content is unchanged). The runner logs `arms-AE.log` and `arms-BF.log` were empty (0 bytes) and are not kept.

## What ran

Rows per scenario, arm, and repetition (A is ACCEPTED, T is TASK_FAILED, H is HARNESS_FAILED). Arms C and D were rejected before the run (see Effort evidence) and have no rows.

| Scenario | Arm A | Arm B | Arm E | Arm F |
|---|---|---|---|---|
| RB-01 | r1:A r2:A r3:A | r1:A r2:A r3:T | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-02 | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-03 | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-04 | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-05 | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A | r1:A r2:A r3:A |
| RB-06 | r1:T r2:T r3:T | r1:T r2:T r3:T | r1:T r2:T r3:T | r1:T r2:A r3:T |

## Per-arm results

Counts as of 2026-10-23. Residual defects are scope violations plus missing expected files, with one added when validation fails without itemizing either (interpretation I1 in `verdicts.json`). They are lower bounds. Economics use accepted rows only.

| Arm | Class | Runs | Accepted | Rate | Residual defects per run | Mean seconds per accepted | Mean uncached tokens per accepted |
|---|---|---|---|---|---|---|---|
| A | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 86.6 | 23,548 |
| A | ordinary_bounded | 12 | 9 | 75.0% | 0.25 | 118.5 | 26,675 |
| B | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 104.6 | 31,170 |
| B | ordinary_bounded | 12 | 8 | 66.7% | 0.33 | 163.5 | 44,931 |
| E | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 25.7 | 5,829 |
| E | ordinary_bounded | 12 | 9 | 75.0% | 0.25 | 60.4 | 11,205 |
| F | fallback_reasoning | 6 | 6 | 100.0% | 0.00 | 86.2 | 20,201 |
| F | ordinary_bounded | 12 | 10 | 83.3% | 0.17 | 108.5 | 24,422 |

Pooled across the six scenarios (the H3 basis):

| Arm | Class | Runs | Accepted | Rate | Residual defects per run | Mean seconds per accepted | Mean uncached tokens per accepted |
|---|---|---|---|---|---|---|---|
| A | all six pooled | 18 | 15 | 83.3% | 0.17 | 105.7 | 25,424 |
| B | all six pooled | 18 | 14 | 77.8% | 0.22 | 138.2 | 39,033 |
| E | all six pooled | 18 | 15 | 83.3% | 0.17 | 46.5 | 9,055 |
| F | all six pooled | 18 | 16 | 88.9% | 0.11 | 100.1 | 22,839 |

## Scorer verdicts

Command: `uv run python scripts/eval/eval_routing_verdicts.py --results arms-AE.jsonl arms-BF.jsonl --output verdicts.json`. Decision: `INSUFFICIENT_EVIDENCE`. Rows scored: 72.

| Hypothesis | Status | Reason from the scorer |
|---|---|---|
| H1 | INSUFFICIENT_EVIDENCE | arm C in ordinary_bounded has no runs |
| H2 | INSUFFICIENT_EVIDENCE | fallback class: arm D in fallback_reasoning has no runs |
| H3 | INSUFFICIENT_EVIDENCE | neither SUPPORTED nor FALSIFIED rule holds |
| H4 | INSUFFICIENT_EVIDENCE | fallback evidence rule not met |

What each reason means for this run:

- H1 and H2 need arms C and D, which have no runs.
- H3 compares arm A with arm B over all six scenarios. A accepts 15 of 18 and B accepts 14 of 18, so A is within one run in six of B. A uses 34.9% fewer uncached tokens per accepted task (25,424 against 39,033). A uses 23.5% less wall-clock per accepted task (105.7 s against 138.2 s). The pre-registered bar is 25% on both, so the latency leg is short and "materially better" does not hold. The reverse rule (FALSIFIED) does not hold either.
- H4 compares arm E with arm A on `fallback_reasoning`. Both accept 6 of 6, so E has no quality advantage. A is not cheaper than E (A 86.6 s and 23,548 tokens, E 25.7 s and 5,829 tokens), so the FALSIFIED rule does not hold either.

## Effort evidence

Effort evidence for every row and for the verdict block is `behavioral` (Amendment 4). The Claude stream names no reasoning effort. Each of the 209 invocations records `model_verdict` HONORED (the requested model was observed) and `effort_verdict` UNVERIFIED (the requested effort was never observed). An arm that "uses high effort" means it requested high.

Behavioral measurement on 2026-10-23, `claude` 2.1.309, thinking tokens at each level, from Amendment 4 item 6:

| Model | low | medium | high | Result |
|---|---|---|---|---|
| claude-opus-5-5 | 100 | 106 | 134 | verified |
| claude-sonnet-5-5 | 105 | 103 | 105 | not verified |
| claude-haiku-5-5 | 285 | 233 | 337 | not verified |

Opus 5.5 strictly increases, so arms A, B, E, and F were planned. Sonnet 5.5 and Haiku 5.5 do not, so arms C and D were rejected and not substituted. They have no rows.

## Observations that are not verdicts

The scorer does not read these.

- On the two fallback scenarios (RB-02, RB-03), arm E matched arm A's acceptance (6 of 6 each) at 29.7% of A's wall-clock per accepted task (25.7 s against 86.6 s) and 24.8% of its uncached tokens (5,829 against 23,548). That is about a third of the time and a quarter of the tokens. It is one result on two scenarios and six runs per arm.
- RB-06 failed most often: 11 of its 12 rows failed (arms A, B, E, and F, three repetitions each), and the only pass was arm F repetition 2. Each failure ended with validation FAIL and no itemized scope violation or missing file, so a follow-up check failed. The rows do not record which check. Every RB-06 failure used both correction rounds.
- Outside RB-06, one row failed: RB-01 arm B repetition 3. It used both correction rounds and has the same shape.
- Arm F accepted the most rows (16 of 18). The gap to arms A and E (15 of 18) is one run.
- Arm B (Haiku and Sonnet workers with an Opus reviewer) accepted the fewest (14 of 18) and was the slowest and most token-heavy per accepted task.

## Confounds

- Claude ran on the operator's real login with instruction files, settings, hooks, MCP servers, skills, and session transcripts disabled by flags. The built-in system prompt and the login stay in effect. Each row records `ambient_home`.
- Effort is requested and never confirmed. All effort claims are `behavioral`.
- Economics is latency and tokens. The stream carries a `cost_usd` figure, but the subscription login is unpriced and no verdict reads it.
- Repetitions are three per cell. Wall-clock reflects the operator's machine and subscription load on that day.
