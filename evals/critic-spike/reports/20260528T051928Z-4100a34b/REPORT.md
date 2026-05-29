# Eval Report: 20260528T051928Z-4100a34b

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `eaa8434900eeea8e...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `18ea11a54d52086b...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 83.3% |
| Baseline recall | 91.7% |
| Signed delta (agent - baseline) | -8.33pp |
| 95% bootstrap CI | [-25.00pp, +0.00pp] |
| Recall with errors | 83.3% |
| Recall excluding errors | 83.3% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| C001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| C002 | 1.00,0.50,1.00 | 0.00,0.50,0.50 |
| C003 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| C004 | 1.00,0.50,1.00 | 1.00,1.00,1.00 |
| C005 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| C006 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| C007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| C008 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-25.00pp, +0.00pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 92,574
- Total tokens out: 5,911
- Estimated cost: $0.3664 USD (rate as of 2026-05-03)
- Wall-clock time: 201.1s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: C002, C004
