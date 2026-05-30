# Eval Report: 20260528T060332Z-498c156a

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `5ea1fe4756a3c842...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `917f690480ccdade...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 78.6% |
| Baseline recall | 78.6% |
| Signed delta (agent - baseline) | +0.00pp |
| 95% bootstrap CI | [-28.57pp, +28.57pp] |
| Recall with errors | 78.6% |
| Recall excluding errors | 78.6% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| X001 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| X002 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| X003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| X004 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| X005 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| X006 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| X007 | 1.00,0.50,1.00 | 0.50,0.50,0.50 |
| X008 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-28.57pp, +28.57pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 39,690
- Total tokens out: 8,328
- Estimated cost: $0.2440 USD (rate as of 2026-05-03)
- Wall-clock time: 257.9s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: X007
