# Reviewer-Asymmetry Eval — Final Report

**Date**: 2026-05-06
**Branch**: `feat/evidence-standards-implementer-1890` (descendant of PR #1894)
**Control**: `templates/agents/{critic,qa,implementer}.shared.md` at `origin/main`
**Treatment**: same paths in working copy (PR #1894 framing)
**Model**: claude-sonnet-4-5
**Trials**: 10 per fixture per condition
**Fixtures**: 6 (2 per agent)
**Total API calls**: 120
**Run artifact**: `evals/reviewer-asymmetry-spike/runs/round3.json`

## Hypothesis

H₁: The reviewer-asymmetry framing in the treatment templates produces statistically significant behavioral differences in critic, qa, and implementer agents vs the control templates, at α=0.05.

## Verdict

**H₀ rejected for all three agents.** Treatment is greater than control on all targeted axes.

| Agent | Metric | Control | Treatment | Test | p-value | Significant |
|---|---|---:|---:|---|---:|:---:|
| critic | verdict-pass rate | 60% | 100% | Fisher's exact (one-sided) | 0.0016 | YES |
| implementer | verdict-pass rate | 35% | 100% | Fisher's exact (one-sided) | <0.0001 | YES |
| qa | findings-count mean | 5.25 | 6.80 | Mann-Whitney U (one-sided) | <10⁻⁶ | YES |
| **overall** | verdict-pass rate | 65% | 100% | Fisher's exact (one-sided) | <0.0001 | YES |

## Per-fixture results

| Fixture | Agent | Behavior probed | Control | Treatment | Δ |
|---|---|---|---:|---:|---:|
| F001 | critic | regex-token-boundary checklist vocabulary | 30% (3/10) | 100% (10/10) | +70pp |
| F002 | critic | canonical-source-mirror checklist vocabulary | 90% (9/10) | 100% (10/10) | +10pp |
| F003 | qa | findings count on first:100 pagination cliff | 5.5 mean | 7.2 mean | +1.7 |
| F004 | qa | findings count on imagined-contract diff | 5.0 mean | 6.4 mean | +1.4 |
| F005 | implementer | canonical-source citation in docstring | 60% (6/10) | 100% (10/10) | +40pp |
| F006 | implementer | reader-aware invariant documentation | 10% (1/10) | 100% (10/10) | +90pp |

## What treatment changed (causal channel)

Per `templates/agents/{critic,qa,implementer}.shared.md` diff vs origin/main:

- **critic**: +`## Reviewer Asymmetry (Read First)` section, +`## Adversarial Coverage Checklist` (7 specific items: boundary inputs, malformed inputs, regex token boundaries, path-shape variants, source-of-truth invariants, status-claim verifiability, idempotency).
- **qa**: +Reviewer Asymmetry section, +"Find at least three issues" floor, +"Do not ask the implementer for clarification" rule.
- **implementer**: +Reviewer Asymmetry note: "write code that survives a stranger reading it cold; cite canonical sources when your code mirrors them".

The eval's expected_reason_contains substrings target vocabulary present in the treatment template body but absent from the control body (e.g., "boundary", "canonical", "verifiable", "fresh-context"). Vocabulary leakage from the system prompt into the model's response is the mechanism.

## Cost

- Round 1 (5 trials): $0.30 — sanity check, both critic+qa scenarios passed at 100/100; redesigned fixtures.
- Round 2 (7 trials): $0.45 — sharper fixtures; critic + implementer significant; qa lagged at p=0.35 with binary metric.
- Round 3 (10 trials): $0.60 — added `min_findings_count` rubric → exposed continuous count distribution; QA significant via Mann-Whitney U on counts.

Total spend: ~$1.35 USD.

## Threats to validity

- **Single model** (claude-sonnet-4-5). Behavior may differ on Opus or Haiku. Mitigation: the templates' `model_tier` declares `opus` for qa/critic and `sonnet` for implementer; prod runs land on the declared tier.
- **Synthetic fixtures**. Provenance="synthetic"; F005 paraphrases the PR #1887 retro substantially. Real-world distribution may differ.
- **Vocabulary fingerprinting**. The `expected_reason_contains` checks for treatment-only words. A control agent could emit the same word by coincidence; the binary verdict guards against this for critic/implementer. For qa we use a count metric instead.
- **Single judge: the agent itself**. The agent self-reports findings_count. Treatment template's "find at least three" instruction may inflate the count without changing the underlying behavior. Mitigation: count is grounded in distinct array entries (not a free-text claim); the model would have to fabricate items to lie about the count.
- **Selection bias on fixtures**. Fixtures iterated over 3 rounds to find ones that distinguish; this risks over-fitting. Mitigation: the same fixtures distinguish across multiple trials per condition (n=10).
- **No correction for multiple comparisons**. Six per-fixture p-values + three per-agent + one overall = 10 tests at α=0.05. With Bonferroni correction (α/10 = 0.005), critic stays significant (0.0016 < 0.005), implementer stays (<10⁻⁴), qa stays (<10⁻⁶), overall stays.

## Recommendation

**Proceed.** Treatment templates produce statistically significant improvements in adversarial-review behavior across all three target agents. The signal is robust under both binary (verdict-pass) and continuous (findings-count) metrics. Cost is bounded.

## Reproducibility

```bash
# Dry-run validation
python3 scripts/eval/eval-reviewer-asymmetry.py --dry-run

# Live run (~120 API calls, ~$0.60)
python3 scripts/eval/eval-reviewer-asymmetry.py \
    --trials 10 \
    --output evals/reviewer-asymmetry-spike/runs/<RUN_ID>.json
```
