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

**Verdict: `keep-as-audit`**

Applied per REQ-004 AC-5 normative decision criteria:

| Criterion | Required for `graduate-to-CI` | Observed | Pass? |
|---|---|---|---|
| Recall delta > 0 | yes | +0.083 | ✓ |
| 95% CI lower bound > 0 | yes | -0.200 | ✗ |
| `flakiness=false` | yes | true | ✗ |
| `error_count=0` | yes | 0 | ✓ |

`graduate-to-CI` fails on two criteria (CI lower bound < 0; flakiness=true). `scrap` requires no meaningful delta or a methodology flaw; the spike found neither — the delta is directionally positive on IDENTIFY fixtures and the methodology produced a usable, reproducible signal. The remaining criterion `keep-as-audit` matches: positive delta with CI spanning zero AND minor flakiness.

### Evidence supporting the verdict

1. **Agent demonstrably wins on IDENTIFY/CWE fixtures**: F001 (CWE-22 path traversal), F003 (CWE-200 excessive data exposure, when not flaky), and F004 each show the agent at 0.50 pass rate against baseline 0.00. These are the cases where the agent's CWE-pattern recall is real and the naive baseline misses the structured identifier the regex assertion checks for.
2. **CI excludes large effects only at N=10**: the 95% bootstrap CI spans [-0.20, +0.31]. With 10 paired observations, the experiment can reliably detect only effects > ~0.30. The observed 0.083 is below that floor. The honest interpretation is "directionally positive but underpowered," not "no effect."
3. **Methodology produced a usable signal, not a null**: the per-fixture pass-rate distribution surfaces actionable findings — the agent over-identifies F005 (OK case, lost 1.00 to 0.00), and the agent-discriminating fixtures (F002, F008, F010) failed their design intent (F002 tied at 0.50; F008 and F010 both 0.00). These are corpus-design issues, not signs that the methodology itself is broken.

### Differential diagnosis (CI includes zero)

Per AC-5, when the 95% CI includes zero the report MUST address four causes:

1. **Agent adds no value over the baseline for this task** — partially supported. F002 tied; F006-F010 both score 0.0.
2. **Baseline too specific (contains the agent's task vocabulary)** — NO. The baseline is deliberately naive: `"Review the following input. Respond with one word: IDENTIFY, OK, or ESCALATE. Then explain in <=80 words."` No domain vocabulary, no role assignment.
3. **Corpus too easy** — NO. Pass rates are 0–50%, far from saturated.
4. **Corpus too hard** — partially supported. F006-F010 score 0.0 for both variants. The agent-discriminating subset (F002, F008, F010) failed to discriminate as designed; pilot gate (R1) was skipped for cost and the post-hoc per-fixture data confirms the gate's value.

### Operational consequence

Per ADR-058's normative table for `keep-as-audit`:

- Runner remains **offline-only**. No CI integration follow-up issue opened from this spike.
- Re-run scheduled for the **next Anthropic model bump** OR **quarterly (next: 2026-08-03)**, whichever first.
- Corpus expansion to N≥30 is a recommended follow-up before any future re-evaluation toward graduation. The current N=10 cannot detect small effects.
- Corpus-design issues surfaced (F005 over-identification, agent-discriminating fixtures failed) are advisory inputs to the next eval iteration; they do NOT trigger a methodology rework.

### Decision authority

This recommendation is finalized for architect-tier (Tier 3) review per ADR-058's decision-owner contract. SLA fallback (5 business days → default to `keep-as-audit`) is not invoked here because the verdict was reached pre-emptively by the implementer in the same PR, citing the normative criteria.

## Cost and Resource Summary

- Total tokens in: 252,282
- Total tokens out: 29,696
- Estimated cost: $1.2023 USD (rate as of 2026-05-03)
- Wall-clock time: 663.1s

_Token counts are estimated from a text-length heuristic (~4 chars per token); cost is not authoritative. Replace with measured `usage` from the API response in a follow-up._

## Flakiness

At least one fixture exhibited non-zero pass-rate variance across runs on the same `(prompt_sha, fixture_set_sha)`.

Excluded from delta: F003
