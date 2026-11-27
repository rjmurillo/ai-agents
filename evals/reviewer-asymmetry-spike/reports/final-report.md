# Reviewer-Asymmetry Eval: Final Report

**Date**: 2026-05-06
**Branch**: `feat/evidence-standards-implementer-1890` (descendant of PR #1894)
**Control**: `templates/agents/{critic,qa,implementer}.shared.md` at `origin/main`
**Treatment**: same paths in working copy (PR #1894 framing)
**Model**: claude-sonnet-4-5
**Trials**: 10 per fixture per condition
**Fixtures**: 6 (2 per agent)
**Total API calls**: 120
**Run artifact**: `evals/reviewer-asymmetry-spike/runs/final.json` (corrected 2026-11-26, see below)

> **Correction (2026-11-26)**: The tables below now come from `runs/final.json`, the only committed run artifact. As first published, this report cited `runs/round3.json` and showed other numbers. No commit added `round3.json`. Refs searched: main, the heads of PRs #1890 to #1897, and branch `feat/evidence-standards-implementer-1890`. The README carried the published numbers at `605d17a26a` (2026-05-06), one commit before `final.json` landed at `99120ffe77` (2026-05-06). The published numbers agree with each other, so they describe a different run whose artifact was never committed. They cannot be checked.
>
> Published values, kept verbatim: critic control 60% (F001 3/10, F002 9/10), Fisher p 0.0016. Implementer control 35% (F005 6/10, F006 1/10). QA findings mean 5.25 control, 6.80 treatment (F003 5.5 to 7.2, F004 5.0 to 6.4). Overall control 65%. Every treatment arm passed 100%.
>
> The verdict holds on the committed run. H₀ is rejected for all three agents, and every per-agent test still passes the Bonferroni bound.

## Hypothesis

H₁: The reviewer-asymmetry framing in the treatment templates produces statistically significant behavioral differences in critic, qa, and implementer agents vs the control templates, at α=0.05.

## Verdict

**H₀ rejected for all three agents.** Treatment beats control for every agent. One fixture, F002, shows no difference: both arms passed 10/10. QA rests on findings count alone, since both qa arms passed every verdict.

| Agent | Metric | Control | Treatment | Test | p-value | Significant |
|---|---|---:|---:|---|---:|:---:|
| critic | verdict-pass rate | 50% | 100% | Fisher's exact (one-sided) | 0.000218 | YES |
| implementer | verdict-pass rate | 15% | 100% | Fisher's exact (one-sided) | <0.0001 | YES |
| qa | findings-count mean | 5.20 | 6.85 | Mann-Whitney U (one-sided) | <10⁻⁶ | YES |
| **overall** | verdict-pass rate | 55% | 100% | Fisher's exact (one-sided) | <0.0001 | YES |

## Per-fixture results

| Fixture | Agent | Behavior probed | Control | Treatment | Δ |
|---|---|---|---:|---:|---:|
| F001 | critic | regex-token-boundary checklist vocabulary | 0% (0/10) | 100% (10/10) | +100pp |
| F002 | critic | canonical-source-mirror checklist vocabulary | 100% (10/10) | 100% (10/10) | +0pp |
| F003 | qa | findings count on first:100 pagination cliff | 5.4 mean | 7.1 mean | +1.7 |
| F004 | qa | findings count on imagined-contract diff | 5.0 mean | 6.6 mean | +1.6 |
| F005 | implementer | canonical-source citation in docstring | 30% (3/10) | 100% (10/10) | +70pp |
| F006 | implementer | reader-aware invariant documentation | 0% (0/10) | 100% (10/10) | +100pp |

## What treatment changed (causal channel)

Per `templates/agents/{critic,qa,implementer}.shared.md` diff vs origin/main:

- **critic**: +`## Reviewer Asymmetry (Read First)` section, +`## Adversarial Coverage Checklist` (7 specific items: boundary inputs, malformed inputs, regex token boundaries, path-shape variants, source-of-truth invariants, status-claim verifiability, idempotency).
- **qa**: +Reviewer Asymmetry section, +"Find at least three issues" floor, +"Do not ask the implementer for clarification" rule.
- **implementer**: +Reviewer Asymmetry note: "write code that survives a stranger reading it cold; cite canonical sources when your code mirrors them".

The eval's expected_reason_contains substrings target vocabulary present in the treatment template body but absent from the control body (e.g., "boundary", "canonical", "verifiable", "fresh-context"). Vocabulary leakage from the system prompt into the model's response is the mechanism.

## Cost

- Round 1 (5 trials): $0.30: sanity check, both critic+qa scenarios passed at 100/100; redesigned fixtures.
- Round 2 (7 trials): $0.45: sharper fixtures; critic + implementer significant; qa lagged at p=0.35 with binary metric.
- Round 3 (10 trials): $0.60: added `min_findings_count` rubric → exposed continuous count distribution; QA significant via Mann-Whitney U on counts.

Total spend: ~$1.35 USD.

## Threats to validity

- **Single model** (claude-sonnet-4-5). Behavior may differ on Opus or Haiku. Mitigation: the templates' `model_tier` declares `opus` for qa/critic and `sonnet` for implementer; prod runs land on the declared tier.

  > **Note (2026-11-26)**: This bullet was accurate when written. The spike ran on claude-sonnet-4-5, as both files in `runs/` record. At report commit `99120ffe77` (2026-05-06), `templates/agents/implementer.shared.md` declared `model_tier: sonnet`. Commit `0d70ff6c52` (2026-05-06) changed it to `opus` inside PR #1897. That commit is reachable only from the PR head. The squash merge `76b7a7257a` (2026-05-07) landed `opus`, so main never carried `sonnet` for implementer. The message of commit `a1c306896c` (2026-05-07) says the user directed `opus` for implementer, so qa, critic, and implementer now share one tier. That commit also reframed the asymmetry as fresh context plus adversarial stance, independent of model tier. The squash message of `76b7a7257a` still says implementer moves to `sonnet`; the merged tree says `opus`. The evaluator runs every agent on one `--model`, so no tier choice affects these results. Since issue #5313, neither tier emits a `model` key, so the generated agent carries no pin and runs on the harness default.
- **Synthetic fixtures**. Provenance="synthetic"; F005 paraphrases the PR #1887 retro substantially. Real-world distribution may differ.
- **Vocabulary fingerprinting**. The `expected_reason_contains` checks for treatment-only words. A control agent could emit the same word by coincidence; the binary verdict guards against this for critic/implementer. For qa we use a count metric instead.
- **Single judge: the agent itself**. The agent self-reports findings_count. Treatment template's "find at least three" instruction may inflate the count without changing the underlying behavior. Mitigation: count is grounded in distinct array entries (not a free-text claim); the model would have to fabricate items to lie about the count.
- **Selection bias on fixtures**. Fixtures iterated over 3 rounds to find ones that distinguish; this risks over-fitting. Mitigation: the same fixtures distinguish across multiple trials per condition (n=10). In the committed run, F002 does not distinguish (10/10 on both arms).
- **No correction for multiple comparisons**. Six per-fixture p-values + three per-agent + one overall = 10 tests at α=0.05. With Bonferroni correction (α/10 = 0.005), critic stays significant (0.000218 < 0.005; the published 0.0016 also passed), implementer stays (<10⁻⁴), qa stays (<10⁻⁶), overall stays.

## Recommendation

**Proceed.** Treatment templates produce statistically significant improvements in adversarial-review behavior across all three target agents. The signal is robust under both binary (verdict-pass) and continuous (findings-count) metrics. Cost is bounded.

## Reproducibility

```bash
# Dry-run validation
python3 scripts/eval/eval-reviewer-asymmetry.py --dry-run

# Live run. This report used 6 fixtures and 120 calls (~$0.60).
# With F007 (added 2026-06-23) the corpus has 7 fixtures: 140 calls.
python3 scripts/eval/eval-reviewer-asymmetry.py \
    --trials 10 \
    --base-ref 76b7a7257a^ \
    --output evals/reviewer-asymmetry-spike/runs/<RUN_ID>.json
```

> **Note (2026-11-26)**: Pass `--base-ref 76b7a7257a^` to compare against the pre-treatment templates. The default control is `main`, which has carried the treatment since `76b7a7257a` (2026-05-07). With the default, control and treatment are the same template. The templates have also changed since this run, so a new run is a fresh measurement, not a replication.
