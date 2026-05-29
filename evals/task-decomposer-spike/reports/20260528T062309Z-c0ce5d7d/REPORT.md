# Eval Report: 20260528T062309Z-c0ce5d7d

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `2276a273b278205f...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `ce963c1cf02142cf...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 91.7% |
| Baseline recall | 75.0% |
| Signed delta (agent - baseline) | +16.67pp |
| 95% bootstrap CI | [+0.00pp, +33.33pp] |
| Recall with errors | 91.7% |
| Recall excluding errors | 91.7% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| T001 | 1.00,0.50,1.00 | 1.00,1.00,1.00 |
| T002 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| T003 | 0.00,0.00,0.50 | 0.50,0.50,0.50 |
| T004 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| T005 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| T006 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| T007 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| T008 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+0.00pp, +33.33pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 64,146
- Total tokens out: 5,793
- Estimated cost: $0.2793 USD (rate as of 2026-05-03)
- Wall-clock time: 201.9s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: T001, T003
