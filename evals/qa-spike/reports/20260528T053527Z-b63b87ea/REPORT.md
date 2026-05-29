# Eval Report: 20260528T053527Z-b63b87ea

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `3aad35c74ecde56a...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `832513474e478a27...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 83.3% |
| Baseline recall | 83.3% |
| Signed delta (agent - baseline) | +0.00pp |
| 95% bootstrap CI | [-41.67pp, +33.33pp] |
| Recall with errors | 83.3% |
| Recall excluding errors | 83.3% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| Q001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| Q002 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| Q003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| Q004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| Q005 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| Q006 | 0.00,0.00,0.00 | 1.00,1.00,1.00 |
| Q007 | 0.00,0.00,0.00 | 0.50,0.50,0.00 |
| Q008 | 0.50,0.00,0.00 | 0.00,0.00,0.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance. Flaky fixtures are excluded from all headline metrics below: agent recall, baseline recall, delta, and bootstrap CI are all computed on the stable fixture subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-41.67pp, +33.33pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 167,634
- Total tokens out: 5,673
- Estimated cost: $0.5880 USD (rate as of 2026-05-03)
- Wall-clock time: 205.4s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: Q007, Q008
