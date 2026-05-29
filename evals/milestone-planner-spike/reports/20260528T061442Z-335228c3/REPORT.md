# Eval Report: 20260528T061442Z-335228c3

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `6509cf87e2bafb8f...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `babf588dfd24533f...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 64.3% |
| Baseline recall | 85.7% |
| Signed delta (agent - baseline) | -21.43pp |
| 95% bootstrap CI | [-42.86pp, -7.14pp] |
| Recall with errors | 64.3% |
| Recall excluding errors | 64.3% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| L001 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| L002 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| L003 | 1.00,0.50,1.00 | 0.50,0.50,0.50 |
| L004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| L005 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| L006 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| L007 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| L008 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-42.86pp, -7.14pp]**. The interval **excludes** zero, so the observed delta is statistically distinguishable from no effect.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 42,768
- Total tokens out: 10,934
- Estimated cost: $0.2923 USD (rate as of 2026-05-03)
- Wall-clock time: 315.8s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: L003
