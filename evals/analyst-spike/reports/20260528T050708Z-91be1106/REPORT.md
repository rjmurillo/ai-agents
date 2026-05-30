# Eval Report: 20260528T050708Z-91be1106

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `f802eb0f1b2155a3...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `766ba138a920717d...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 82.5% |
| Baseline recall | 85.0% |
| Signed delta (agent - baseline) | -2.50pp |
| 95% bootstrap CI | [-10.00pp, +5.00pp] |
| Recall with errors | 82.5% |
| Recall excluding errors | 82.5% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F002 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F003 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F004 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F005 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F006 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F007 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F008 | 1.00,0.50,1.00 | 0.00,0.00,0.00 |
| F009 | 1.00,1.00,1.00 | 0.50,0.50,0.50 |
| F010 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F011 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F012 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F013 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F014 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| F015 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F016 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F017 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F018 | 1.00,1.00,1.00 | 1.00,1.00,1.00 |
| F019 | 0.50,0.50,1.00 | 1.00,1.00,1.00 |
| F020 | 0.50,1.00,0.50 | 0.50,0.50,0.50 |
| F021 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |
| F022 | 1.00,0.50,1.00 | 0.50,0.50,0.50 |
| F023 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| F024 | 0.50,0.50,0.50 | 0.50,0.50,0.50 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-10.00pp, +5.00pp]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 173,178
- Total tokens out: 33,224
- Estimated cost: $1.0179 USD (rate as of 2026-05-03)
- Wall-clock time: 939.6s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F008, F019, F020, F022
