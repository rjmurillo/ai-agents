# Eval Report: ff2936confirm

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `be36604d83651117...`
- Baseline prompt SHA: `f2837b5416a8d4cb...`
- Fixture set SHA: `cffb1c29c1e51a12...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 78.9% |
| Baseline recall | 36.8% |
| Signed delta (agent - baseline) | +42.11pp |
| 95% bootstrap CI | [+19.05pp, +66.67pp] |
| Recall with errors | 78.9% |
| Recall excluding errors | 78.9% |
| Error count | 0 |
| Flakiness | true |

## Form-Factor Comparison

| Metric | Value |
|---|---|
| Agent recall | 78.9% |
| Skill recall | 78.9% |
| Skill - baseline delta | +42.11pp |
| Agent - skill delta | +0.00pp |
| Agent - skill 95% bootstrap CI | [+0.00pp, +0.00pp] |
| Agent tokens | 595028 |
| Skill tokens | 594702 |
| Verdict | `inconclusive` |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 0.50,0.50,0.50,0.50,0.50 | 0.00,0.00,0.00,0.00,0.00 |
| F002 | 0.50,0.50,0.50,0.50,0.50 | 0.50,0.50,0.50,0.50,0.50 |
| F003 | 0.00,0.00,0.00,0.00,0.00 | 0.00,0.00,0.00,0.00,0.00 |
| F004 | 1.00,1.00,1.00,1.00,1.00 | 0.00,0.00,0.00,0.00,0.00 |
| F005 | 1.00,1.00,1.00,1.00,1.00 | 0.00,0.00,0.00,0.00,0.00 |
| F006 | 1.00,1.00,1.00,1.00,1.00 | 0.00,0.00,0.00,0.00,0.00 |
| F007 | 1.00,1.00,1.00,1.00,1.00 | 1.00,1.00,1.00,1.00,1.00 |
| F008 | 1.00,1.00,1.00,1.00,1.00 | 1.00,1.00,1.00,1.00,1.00 |
| F009 | 1.00,1.00,1.00,1.00,1.00 | 1.00,1.00,1.00,1.00,1.00 |
| F010 | 1.00,1.00,1.00,1.00,1.00 | 1.00,1.00,1.00,1.00,1.00 |
| F011 | 1.00,1.00,1.00,1.00,1.00 | 0.00,0.00,0.00,0.00,0.00 |
| F012 | 1.00,1.00,1.00,1.00,1.00 | 0.00,0.00,0.00,0.00,0.00 |
| F013 | 0.00,0.00,0.00,1.00,1.00 | 0.00,0.00,0.00,0.00,0.00 |
| F014 | 1.00,1.00,1.00,1.00,1.00 | 0.00,0.00,0.00,0.00,0.00 |
| F015 | 1.00,1.00,1.00,1.00,1.00 | 1.00,1.00,1.00,1.00,1.00 |
| F016 | 1.00,1.00,1.00,1.00,1.00 | 1.00,1.00,1.00,1.00,1.00 |

## Confidence Interval

**Note**: at least one fixture exhibited non-zero pass-rate variance; flaky fixtures are excluded from the delta computed below. The CI describes the stable subset only.

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[+19.05pp, +66.67pp]**. The interval **excludes** zero, so the observed delta is statistically distinguishable from no effect.

## Recommendation

_Pending. T4-7 records the verdict (graduate-to-CI, keep-as-audit, scrap, or halt-due-to-flakiness) with at least two pieces of evidence drawn from the data above._

## Cost and Resource Summary

- Total tokens in: 1,179,000
- Total tokens out: 35,668
- Estimated cost: $4.0720 USD (rate as of 2026-07-08)
- Wall-clock time: 1291.9s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F013
