# Routing benchmark live run, repetition 1 (issues #5424 and #5426)

2026-10-03. Harness: native `codex-cli 0.160.0`, `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.6-terra`. Predictions: `../PREDICTIONS.md` (`predictions-v1`, merged before this run in PR #6154). Matrix: `scripts/eval/examples/harness-capability-matrix.json`, every Codex cell VERIFIED at 0.160.0, Copilot dropped. Plan: 36 Codex rows (6 scenarios x 6 arms), all `ELIGIBLE_UNMATCHED`.

**Result: INSUFFICIENT_EVIDENCE for H1, H2, H3, H4 and for the strategy decision.** The run stopped on an external failure. After 21 completed invocations, every later invocation exited 1 with `Your workspace is out of credits. Add credits to continue.` (32 failed invocations, read from the CLI's own output on a later probe). Nothing was substituted for a row that did not run.

Launch: three processes in parallel, one per arm pair (A and E, B and F, C and D), each capped by `--max-invocations` (34, 49, 50), `--real-home`, repetition 1 only. Files: `arms-AE.jsonl`, `arms-BF.jsonl`, `arms-CD.jsonl`, one JSON line per row.

## What ran

| Scenario | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| RB-01 (ordinary) | TASK_FAILED | TASK_FAILED | TASK_FAILED | HARNESS_FAILED | HARNESS_FAILED | ACCEPTED |
| RB-02 to RB-06 | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED |

A harness failure is not a task failure. It is excluded from every rate, as the predictions require. Per the predictions, a cell with more than 20 percent harness failures is `INSUFFICIENT_EVIDENCE`: every cell here exceeds it.

Completed work: 21 invocations, 1,043,295 uncached input tokens plus 82,948 output tokens, 2,532 seconds of wall time. Every invocation that returned backend frames (23, including 2 that failed after the frames arrived) was `HONORED`: the backend named the requested model and effort. The other 30 returned nothing and read `UNVERIFIED`.

## Why each hypothesis is INSUFFICIENT_EVIDENCE

The evidence floor is 8 runs per arm in a class. One repetition of RB-01 gives 1 ordinary run per arm and 0 fallback runs.

| Hypothesis | Comparison | Runs per arm available | Verdict |
|---|---|---|---|
| H1 Luna default worker | C against A, ordinary | 1 each, both TASK_FAILED | INSUFFICIENT_EVIDENCE |
| H2 Terra fallback | D against A and C, fallback | 0 | INSUFFICIENT_EVIDENCE |
| H3 Sol-only fan-out | A against B, pooled | 1 each, both TASK_FAILED | INSUFFICIENT_EVIDENCE |
| H4 single-agent deep reasoning | E against A, fallback | 0 | INSUFFICIENT_EVIDENCE |

## Observations that are not verdicts

- On RB-01 the three fan-out arms (A, B, C) each failed deterministic grading after 2 correction rounds with the same scope violation: a change to `tests/check_visible_slugify.py`, which the scenario does not allow. Arm F, plan then a fresh single agent, was accepted. Arms D and E did not complete. The role prompt says only "Complete this requirement in the working tree", so it does not name the legal change surface. One scenario cannot separate an arm effect from a prompt effect.
- A smoke run before the batch (arm E, RB-01, `gpt-5.6-sol` high) was accepted in 1 invocation with backend-confirmed model and effort. It is not part of these files.

## Confounds

- Codex ran on the operator's real `CODEX_HOME` (`--real-home`). `~/.codex/AGENTS.md` and skills load in every invocation. Each row records `ambient_home`.
- Cost is unpriced: Codex reports no cost and the repository has no published rate for the GPT-5.6 ids. `cost_usd` is null. Tokens are the economics measure.
- The credit failure began mid-run on a shared account, so the point where it began is not a property of any arm.

## To finish

Add Codex credits, then run `uv run python scripts/eval/eval_routing_benchmark.py --live --real-home --max-invocations N --repetitions 3 --output <file>`. One full repetition needs about 130 invocations when fan-out rows spend their correction rounds (6 rows of 5 to 6 invocations each for A, B, and C on RB-01).
