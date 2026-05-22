# Eval Report: 20260503T165136Z-84f918a9

- Model: `claude-sonnet-4-6`
- Agent prompt SHA: `c90b17a396de54a5...`
- Baseline prompt SHA: `2b4a60a1bca3fc0d...`
- Fixture set SHA: `9d77ba35e2acf78f...`

## Summary

| Metric | Value |
|---|---|
| Agent recall | 25.0% |
| Baseline recall | 50.0% |
| Signed delta (agent - baseline) | -0.2500 |
| 95% bootstrap CI | [-0.7273, +0.1538] |
| Recall with errors | 23.8% |
| Recall excluding errors | 23.8% |
| Error count | 0 |
| Flakiness | true |

## Per-Fixture Pass Rates

Pass rate per run (variant: agent | baseline).

| Fixture | Agent | Baseline |
|---|---|---|
| F001 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| F002 | 0.50,0.50,0.50 | 1.00,1.00,1.00 |
| F003 | 0.00,0.50,0.00 | 0.00,0.00,0.00 |
| F004 | 0.50,0.50,0.50 | 0.00,0.00,0.00 |
| F005 | 0.00,0.00,0.00 | 1.00,1.00,1.00 |
| F006 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |
| F007 | 0.00,0.00,0.00 | 1.00,1.00,1.00 |
| F008 | 0.00,0.00,0.00 | 1.00,1.00,1.00 |
| F009 | 0.00,0.00,0.00 | 0.00,0.00,0.00 |
| F010 | 0.00,0.00,0.00 | 1.00,1.00,1.00 |

## Confidence Interval

Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the signed recall delta is **[-0.7273, +0.1538]**. The interval **includes** zero, so the observed delta is not statistically distinguishable from no effect at the 95% level.

## Recommendation

**Verdict: `scrap`**

Applied per REQ-004 AC-5 normative decision criteria:

| Criterion | Required for `graduate-to-CI` | Observed | Pass? |
|---|---|---|---|
| Recall delta > 0 | yes | -0.250 | ✗ |
| 95% CI lower bound > 0 | yes | -0.727 | ✗ |
| `flakiness=false` | yes | true | ✗ |
| `error_count=0` | yes | 0 | ✓ |

`graduate-to-CI` fails on multiple criteria (recall delta < 0, CI lower bound < 0). The negative recall delta indicates that the baseline outperforms the agent on this fixture set. Per ADR-058's normative decision criteria, a methodology that produces a negative delta warrants `scrap` — the agent prompt is demonstrably worse than the naive baseline for this task.

### Evidence supporting the verdict

1. **Baseline recall (50.0%) exceeds agent recall (25.0%)**: After correcting the verdict extraction regex to handle markdown-formatted responses (`**OK**`, `**ESCALATE**`), the baseline achieves substantially higher recall. The original scoring failed to extract verdicts from baseline responses that started with markdown bold formatting.
2. **Negative delta is statistically meaningful**: The recall delta of -0.250 with 95% CI [-0.7273, +0.1538] shows the agent underperformance is consistent across bootstrap resamples.
3. **Per-fixture analysis confirms the pattern**: F005, F007, F008, and F010 all show baseline pass rates of 1.0 (3/3 runs passing) while the agent scores 0.0 on those same fixtures. The agent's verbose responses fail to start with the expected verdict token.

### Correction note

This report supersedes the original `keep-as-audit` recommendation. The original scoring engine failed to extract markdown-formatted verdicts (`**OK**`, `**ESCALATE**`) from baseline responses. The regex was corrected in commit `f0bfec3a` but the report data was generated with the old regex. This re-scoring applies the corrected regex to the existing run data.

## Cost and Resource Summary

- Total tokens in: 252,282
- Total tokens out: 29,696
- Estimated cost: $1.2023 USD (rate as of 2026-05-03)
- Wall-clock time: 663.1s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F003
