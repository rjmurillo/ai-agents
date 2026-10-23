# Routing benchmark Codex partial run, attempt 2026-10-20 (issues #5424 and #5426)

Harness: native `codex-cli 0.163.0`. The matrix is pinned to 0.163.0 (PR #6811). Predictions: `../PREDICTIONS.md` (`predictions-v1` with Amendments 1 and 2, merged in PR #6812 before any run). Owner decision D9 on 2026-10-23: publish the partial Codex results and make no more Codex runs.

**Result: INSUFFICIENT_EVIDENCE for H1, H2, H3, H4 and for the strategy decision.** The attempt stopped on an external failure. A probe `codex exec` right after the stop printed `ERROR: Your workspace is out of credits. Add credits to continue.` Nothing was substituted for a row that did not run.

Launch: three processes, one per arm pair (A and E, B and F, C and D), capped by `--max-invocations` (AE 102, BF 147, CD 151; total 400), with `--real-home` and `--repetitions 3`. The ChatGPT subscription login was used. `OPENAI_API_KEY`, `CODEX_API_KEY`, and `OPENAI_BASE_URL` were unset. The attempt was stopped by hand. It restarted from scratch, so it is a separate run. It is not pooled with the other attempts or with `../results-2026-10-03/`.

Files: `arms-AE.jsonl`, `arms-BF.jsonl`, `arms-CD.jsonl` (one JSON line per row) and `verdicts.json` (scorer output, stored on one line to stay under the repository file-size lint; the content is unchanged). The runner logs were empty and are not kept.

## What ran

All 34 rows are repetition 1. No row reached repetition 2 or 3. Row statuses: ACCEPTED 5, HARNESS_FAILED 29. Scenarios and arms with no row never started.

| Scenario | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| RB-01 | ACCEPTED | ACCEPTED | ACCEPTED | HARNESS_FAILED | ACCEPTED | ACCEPTED |
| RB-02 | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED |
| RB-03 | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED |
| RB-04 | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED |
| RB-05 | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED | HARNESS_FAILED |
| RB-06 | HARNESS_FAILED | HARNESS_FAILED | no row | no row | HARNESS_FAILED | HARNESS_FAILED |

A harness failure is not a task failure. It is excluded from every rate, as the predictions require. Per the predictions, a cell with more than 20 percent harness failures is `INSUFFICIENT_EVIDENCE`.

Completed work: 20 successful invocations, 641,495 uncached input tokens plus 74,444 output tokens, 1,680 seconds of wall time on those invocations. Of 49 recorded invocations, 29 failed with `exit code 1`. The backend confirmed the requested model and effort on 23 invocations (`HONORED`). The rest returned nothing and read `UNVERIFIED`.

## Scorer verdicts

Command: `uv run python scripts/eval/eval_routing_verdicts.py --results <the three jsonl files> --output verdicts.json`. Decision: `INSUFFICIENT_EVIDENCE`. Rows scored: 34.

| Hypothesis | Status | Reason from the scorer |
|---|---|---|
| H1 | INSUFFICIENT_EVIDENCE | arm C in ordinary_bounded has 2 of 3 harness failures (>20%) |
| H2 | INSUFFICIENT_EVIDENCE | fallback class: arm D in fallback_reasoning has 2 of 2 harness failures (>20%) |
| H3 | INSUFFICIENT_EVIDENCE | arm A in pooled_all_six has 5 of 6 harness failures (>20%) |
| H4 | INSUFFICIENT_EVIDENCE | arm E in fallback_reasoning has 2 of 2 harness failures (>20%) |

## Confounds

- Codex ran on the operator's real `CODEX_HOME` (`--real-home`). Each row records `ambient_home`.
- Cost is unpriced. `cost_usd` is null. Tokens are the economics measure.
- The credit stop began mid-run, so the point where it began is not a property of any arm.
