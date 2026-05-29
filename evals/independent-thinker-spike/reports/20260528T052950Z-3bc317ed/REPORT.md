# Eval Report: 20260528T052950Z-3bc317ed

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `949c3d472607cf0c...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `28e65952fbbb529d...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 75.0% |
| Baseline recall | 58.3% |
| Signed delta (agent - baseline) | +16.67pp |
| 95% bootstrap CI | [+0.00pp, +33.33pp] |
| Recall with errors | 75.0% |
| Recall excluding errors | 75.0% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| I001 | 1.00,1.00,1.00 | 1.00,0.50,0.50 |
| I002 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| I003 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| I004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| I005 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| I006 | 1.00,1.00,1.00 | 1.00,0.50,1.00 |
| I007 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| I008 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+0.00pp, +33.33pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 39,012
- Total tokens out: 11,705
- Estimated cost: $0.2926 USD (rate as of 2026-05-03)
- Wall-clock time: 336.1s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: I001, I006
