# Eval Report: 20260528T055503Z-62c6a9c2

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `e23b22f981d83268...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `17d53cd24ac42565...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 75.0% |
| Baseline recall | 75.0% |
| Signed delta (agent - baseline) | +0.00pp |
| 95% bootstrap CI | [-25.00pp, +25.00pp] |
| Recall with errors | 75.0% |
| Recall excluding errors | 75.0% |
| Error count | 0 |
| Flakiness | false |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| S001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| S002 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| S003 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| S004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| S005 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| S006 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| S007 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| S008 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |

## Confidence Interval

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-25.00pp, +25.00pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 49,668
- Total tokens out: 7,447
- Estimated cost: $0.2607 USD (rate as of 2026-05-03)
- Wall-clock time: 232.9s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

No non-zero pass-rate variance detected.
