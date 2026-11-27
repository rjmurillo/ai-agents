# Reviewer-Asymmetry Eval Spike

Statistical-significance evaluation for the reviewer-asymmetry framing
introduced to `templates/agents/{critic,qa,implementer}.shared.md` in
PR #1894.

## Question

Does the treatment template produce statistically significant behavioral
differences in critic, qa, and implementer agents vs the origin/main control?

## Method

- **Control**: agent template at `--base-ref` (default `main`). Since
  `76b7a7257a` (2026-05-07), `main` carries the treatment. Pass
  `--base-ref 76b7a7257a^` to compare against the pre-treatment templates.
- **Treatment**: agent template at HEAD (PR #1894 framing).
- **Model**: one `--model` for every agent (default `claude-sonnet-4-5`). The
  templates' `model_tier` plays no part in a run.
- **Trials**: 10 per fixture per condition (binomial design).
- **Test stack**:
  - Fisher's exact (one-sided, treatment > control) on verdict-pass rate.
  - Two-proportion z-test for cross-check.
  - Mann-Whitney U (one-sided, treatment > control) on findings-count
    when fixtures specify `min_findings_count` (continuous metric where
    binary verdict-pass saturates at 100/100).
- **Acceptance**: p < 0.05 AND treatment mean > control mean, both at
  the per-agent level and overall.

## Layout

```text
evals/reviewer-asymmetry-spike/
  fixtures/
    F001-critic-planted-issues.json     - regex-token-boundary checklist vocab
    F002-critic-context-missing.json    - canonical-source-mirror vocab
    F003-qa-edge-cases.json             - status-claim findings count
    F004-qa-status-claim.json           - imagined-contract findings count
    F005-implementer-canonical-cite.json - canonical-source citation
    F006-implementer-reviewer-aware.json - reader-aware invariant docs
    F007-critic-prose-persona-gap.json  - prose persona gap (added 2026-06-23)
  runs/
    final.json                          - 2026-05-06 run behind the report
    2026-05-27-baseline.json            - 2026-05-27 run, control = treatment
  reports/
    final-report.md                     - human-readable verdict + tables
```

## Fixture schema

```json
{
  "schemaVersion": 1,
  "id": "F001",
  "agent": "critic|qa|implementer",
  "input": "<scenario shown to the agent>",
  "provenance": "synthetic|public-cve|paraphrased-from-public",
  "planted_issues": ["<one per planted finding>"],
  "scoring_rubric": {
    "kind": "<behavior under test>",
    "treatment_floor": "<what treatment must do>",
    "control_baseline": "<what control may do>"
  },
  "expected_verdict": "<one of verdict_options>",
  "verdict_options": ["<2-4 controlled labels>"],
  "expected_reason_contains": "<substring>",   // OR
  "min_findings_count": 3,                     // alternative: count metric
  "rationale": "<why this fixture distinguishes treatment>",
  "tags": [...]
}
```

## Reproducibility

```bash
# Dry-run validation (no API calls)
python3 scripts/eval/eval-reviewer-asymmetry.py --dry-run

# Live run (10 trials × 7 fixtures × 2 conditions = 140 API calls)
python3 scripts/eval/eval-reviewer-asymmetry.py \
    --trials 10 \
    --base-ref 76b7a7257a^ \
    --output evals/reviewer-asymmetry-spike/runs/"<run-id>".json
```

Exit codes:

- `0` = treatment produced statistically significant improvement (overall p<0.05 AND all per-agent significant)
- `1` = no significant overall delta or one or more per-agent tests not significant
- `2` = configuration / fixture invalid
- `3` = external (API) failure

## Result (final round, 2026-05-06)

All three target agents show statistically significant treatment effect:

| Agent | Test | p-value |
|---|---|---:|
| critic | Fisher's exact (verdict-pass) | 0.000218 |
| implementer | Fisher's exact (verdict-pass) | <0.0001 |
| qa | Mann-Whitney U (findings count) | <10⁻⁶ |
| overall | Fisher's exact (verdict-pass) | <0.0001 |

See `reports/final-report.md` for the full breakdown.

> **Correction (2026-11-26)**: This table first showed critic p 0.0016,
> from a run whose artifact was never committed. The values above come from
> `runs/final.json`. The report's correction note keeps the published values.

### Later run (2026-05-27)

`runs/2026-05-27-baseline.json` (5 trials, 6 fixtures) shows a zero
verdict-pass delta on every agent. QA findings means were 6.4 control and 6.6
treatment (p 0.36). The run does not test the hypothesis. It used
`base_ref: main`, and the three templates were identical on `main` and on the
run's branch (`942c2440f2`). Control and treatment were the same committed
template. Commit `942c2440f2` called this saturation, but a template compared
with itself cannot show a real delta.

### Fixture wording and model tiers

F006's input says the qa reviewer runs "on a stronger model". That held when the
fixture was written. The message of `a1c306896c` (2026-05-07) says the user
directed `model_tier: opus` for implementer, so qa, critic, and implementer now
share one tier. The asymmetry is now fresh context plus adversarial stance,
independent of tier. F006 stays as recorded, because both runs measured that
text. Its score keys on the word `invariant`, not on the tier wording.

## Cross-references

- Plan: PR #1894 - `feat(agents,github-skill): reviewer-stronger asymmetry + verifiable status claims`
- Retrospective: `.project-toolkit/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- Eval framework: ADR-057 (prompt-behavioral evaluation)
- Sister eval: `evals/security-spike/` (agent-vs-baseline corpus)
