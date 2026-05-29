# Eval Report: 20260528T040743Z-643d1793

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `f802eb0f1b2155a3...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `d93a851efbd06790...`

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
| F001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F002 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| F003 | 0.50,0.50,0.50 | 0.50,1.00,1.00 |
| F004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F005 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F006 | 0.50,0.00,0.50 | 0.50,0.50,0.50 |
| F007 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F008 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-25.00pp, +0.00pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 53,928
- Total tokens out: 12,903
- Estimated cost: $0.3553 USD (rate as of 2026-05-03)
- Wall-clock time: 361.6s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F003, F006
