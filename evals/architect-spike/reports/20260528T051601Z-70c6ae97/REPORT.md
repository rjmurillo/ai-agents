# Eval Report: 20260528T051601Z-70c6ae97

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `372c90434fc8a745...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `be99fa1b1180c8f1...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 85.7% |
| Baseline recall | 85.7% |
| Signed delta (agent - baseline) | +0.00pp |
| 95% bootstrap CI | [+0.00pp, +0.00pp] |
| Recall with errors | 85.7% |
| Recall excluding errors | 85.7% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| A001 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| A002 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| A003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| A004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| A005 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| A006 | 1.00,0.50,0.50 | 0.00,0.50,0.50 |
| A007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| A008 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+0.00pp, +0.00pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 187,002
- Total tokens out: 5,792
- Estimated cost: $0.6479 USD (rate as of 2026-05-03)
- Wall-clock time: 207.6s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: A006
