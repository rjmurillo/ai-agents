# Eval Report: 20260528T035241Z-45e0c2f3

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `c82cb6c80b6d78d3...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `6dfd687ac99185cb...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 83.3% |
| Baseline recall | 41.7% |
| Signed delta (agent - baseline) | +41.67pp |
| 95% bootstrap CI | [+10.00pp, +72.73pp] |
| Recall with errors | 83.3% |
| Recall excluding errors | 83.3% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| F002 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F003 | 0.00,0.50,0.00 | 0.00,0.00,0.00 |
| F004 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F005 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F006 | 1.00,1.00,1.00 | 0.00,0.00,0.00 |
| F007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F008 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F009 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F010 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance. Flaky fixtures are excluded from all headline metrics below: agent recall, baseline recall, delta, and bootstrap CI are all computed on the stable fixture subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+10.00pp, +72.73pp]**. The interval **excludes** zero, so the observed delta is statistically distinguishable from no effect.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 282,576
- Total tokens out: 9,966
- Estimated cost: $0.9972 USD (rate as of 2026-05-03)
- Wall-clock time: 312.7s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F003
