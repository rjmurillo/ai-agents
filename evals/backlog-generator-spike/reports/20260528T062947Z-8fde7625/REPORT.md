# Eval Report: 20260528T062947Z-8fde7625

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `f6b1acee0de57c09...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `73af344e10e972ee...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 75.0% |
| Baseline recall | 83.3% |
| Signed delta (agent - baseline) | -8.33pp |
| 95% bootstrap CI | [-33.33pp, +16.67pp] |
| Recall with errors | 75.0% |
| Recall excluding errors | 75.0% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| B001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| B002 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| B003 | 0.00,0.50,0.00 | 1.00,0.50,0.50 |
| B004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| B005 | 1.00,0.50,1.00 | 0.00,0.00,0.00 |
| B006 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| B007 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| B008 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-33.33pp, +16.67pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 40,452
- Total tokens out: 7,124
- Estimated cost: $0.2282 USD (rate as of 2026-05-03)
- Wall-clock time: 226.7s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: B003, B005
