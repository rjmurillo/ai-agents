# Eval Report: 20260528T055856Z-7562dce2

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `6dd9b9498e7f934b...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `ad774e35b2d3af33...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 66.7% |
| Baseline recall | 75.0% |
| Signed delta (agent - baseline) | -8.33pp |
| 95% bootstrap CI | [-33.33pp, +16.67pp] |
| Recall with errors | 66.7% |
| Recall excluding errors | 66.7% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| M001 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| M002 | 0.00,0.50,0.50 | 0.50,0.50,0.50 |
| M003 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| M004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| M005 | 0.00,0.00,0.00 | 0.50,0.50,0.50 |
| M006 | 0.50,0.50,0.50 | 0.50,0.00,0.50 |
| M007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| M008 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-33.33pp, +16.67pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 110,028
- Total tokens out: 7,894
- Estimated cost: $0.4485 USD (rate as of 2026-05-03)
- Wall-clock time: 274.9s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: M002, M006
