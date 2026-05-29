# Eval Report: 20260528T061135Z-94708c8e

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `d63f8177a2144c1c...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `ea86a52a60d49d55...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 85.7% |
| Baseline recall | 71.4% |
| Signed delta (agent - baseline) | +14.29pp |
| 95% bootstrap CI | [+0.00pp, +28.57pp] |
| Recall with errors | 85.7% |
| Recall excluding errors | 85.7% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| E001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| E002 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| E003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| E004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| E005 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| E006 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| E007 | 1.00,1.00,1.00 | 0.00,0.50,0.00 |
| E008 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+0.00pp, +28.57pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 93,222
- Total tokens out: 5,566
- Estimated cost: $0.3632 USD (rate as of 2026-05-03)
- Wall-clock time: 187.5s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: E007
