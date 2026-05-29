# Eval Report: 20260528T045032Z-d5b2eeb5

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `f802eb0f1b2155a3...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `2dbf68ca1563b076...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 90.0% |
| Baseline recall | 86.7% |
| Signed delta (agent - baseline) | +3.33pp |
| 95% bootstrap CI | [-6.67pp, +13.33pp] |
| Recall with errors | 90.0% |
| Recall excluding errors | 90.0% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F002 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F003 | 1.00,1.00,0.50 | 1.00,1.00,1.00 |
| F004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F005 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F006 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F007 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F008 | 0.50,1.00,1.00 | 0.00,0.50,0.00 |
| F009 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| F010 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| F011 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F012 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F013 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F014 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| F015 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F016 | 1.00,0.50,0.50 | 1.00,1.00,1.00 |
| F017 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F018 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-6.67pp, +13.33pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 129,618
- Total tokens out: 24,904
- Estimated cost: $0.7624 USD (rate as of 2026-05-03)
- Wall-clock time: 683.4s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F003, F008, F016
