# Eval Report: 20260528T060750Z-a2a4d040

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `4244d952890998a5...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `a1a4e3979c842519...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 64.3% |
| Baseline recall | 64.3% |
| Signed delta (agent - baseline) | +0.00pp |
| 95% bootstrap CI | [-21.43pp, +21.43pp] |
| Recall with errors | 64.3% |
| Recall excluding errors | 64.3% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| R001 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| R002 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| R003 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| R004 | 0.50,1.00,1.00 | 1.00,0.50,0.50 |
| R005 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| R006 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| R007 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| R008 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-21.43pp, +21.43pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 40,530
- Total tokens out: 5,832
- Estimated cost: $0.2091 USD (rate as of 2026-05-03)
- Wall-clock time: 224.7s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: R004
