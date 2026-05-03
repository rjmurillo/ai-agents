# Eval Report: 20260503T165136Z-84f918a9

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `c90b17a396de54a5...`
- Baseline prompt SHA: `2b4a60a1bca3fc0d...`
- Fixture set SHA: `9d77ba35e2acf78f...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 25.0% |
| Baseline recall | 16.7% |
| Signed delta (agent - baseline) | +0.0833 |
| 95% bootstrap CI | [-0.2000, +0.3077] |
| Recall with errors | 23.8% |
| Recall excluding errors | 23.8% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| F002 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F003 | 0.00,0.50,0.00 | 0.00,0.00,0.00 |
| F004 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| F005 | 0.00,0.00,0.00 | 1.00,1.00,1.00 |
| F006 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |
| F007 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |
| F008 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |
| F009 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |
| F010 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |

## Confidence Interval

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-0.2000, +0.3077]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending — T4-7 records the verdict (graduate-to-CI | keep-as-audit | scrap) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 252,282
- Total tokens out: 29,696
- Estimated cost: $1.2023 USD (rate as of 2026-05-03)
- Wall-clock time: 663.1s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F003
