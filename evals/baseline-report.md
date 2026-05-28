# Baseline Eval Report

Baseline measurement: do current agent prompts beat a naive baseline on a held-out corpus? First aggregate run across three spikes.

## Date

2026-05-27

## Scope

| Spike | Runner | Fixtures | Variants | Trials/variant | Total calls | Cost |
|---|---|---|---|---|---|---|
| security | `eval-agent-vs-baseline.py` | 10 | agent vs baseline | 3 | 60 | $0.89 |
| analyst | `eval-agent-vs-baseline.py` | 8 | agent vs baseline | 3 | 48 | $0.36 |
| reviewer-asymmetry | `eval-reviewer-asymmetry.py` | 6 | treatment (HEAD) vs control (origin/main) | 5 | 60 | ~1.50 |

**Aggregate**: 24 fixtures, 168 trials, ~$2.74 USD.

## Headline results

| Spike | Variant A | Variant B | Delta | 95% CI | Significant? | Verdict |
|---|---|---|---|---|---|---|
| security | agent recall 0.786 | baseline recall 0.405 | **+0.381** | [0.111, 0.643] | YES | Agent beats naive baseline. |
| analyst | agent recall 0.833 | baseline recall 0.917 | **-0.083** | [-0.250, 0.000] | NO | **Agent under-performs naive baseline.** |
| reviewer-asymmetry | treatment overall 1.000 | control overall 1.000 | **0.000** | (Fisher exact p=1.0) | NO | All three agents saturated. Today's templates between `main` and `HEAD` are effectively equivalent OR the corpus is too easy to detect difference. Earlier May-9 final.json (kept in repo) showed +0.45 from a stage when templates diverged. |

## Per-spike detail

### security-spike

- Run ID: `20260503T182553Z-eaa08f8d`
- 10 fixtures covering CWE-22/77/200/etc plus 3 false-positive-resistance scenarios.
- Agent recall **0.786**, baseline recall **0.405**, delta **+0.381**.
- Bootstrap 95% CI: [0.111, 0.643]. Does not cross zero -> significant.
- Flaky fixtures detected (intra-run variance >0): F001, F002, F003, F005. None excluded; sample size sufficient.
- Cost: $0.89 USD at claude-sonnet-4-6 rates.

### analyst-spike (NEW)

- Run ID: `20260528T040743Z-643d1793`
- 8 fixtures across IDENTIFY (4), OK (1), ESCALATE (3) verdicts. 4 agent-discriminating per REQ-004 AC-5.
- Agent recall **0.833**, baseline recall **0.917**, delta **-0.083**.
- Bootstrap 95% CI: [-0.250, 0.000]. Upper bound at zero means **agent at best matches baseline, at worst loses 25pp**.
- Flaky fixtures excluded: F003, F006 (intra-run variance + low sample). Remaining 6 fixtures drive the recall.
- Cost: $0.36 USD.
- **Action**: analyst prompt does not justify itself against the corpus as designed. Two follow-up paths:
  1. Tighten the corpus. Several fixtures (F001, F004, F005) tie at 1.0/1.0 or 0.5/0.5 because the verdict is obvious from the scenario alone. Replace with harder, more agent-discriminating cases.
  2. Audit the prompt. If a tightened corpus still shows null or negative delta, the analyst template carries cost (tokens, latency) without behavioral lift. Either remove specialization or refactor.

### reviewer-asymmetry-spike

- Driven by `eval-reviewer-asymmetry.py`. Final report: `evals/reviewer-asymmetry-spike/runs/final.json`.
- Per-agent verdict-pass rates:

| Agent | Control pass | Treatment pass | Delta | p (Fisher exact) | Significant? |
|---|---|---|---|---|---|
| critic | 1.000 | 1.000 | 0.000 | 1.0 | NO |
| implementer | 1.000 | 1.000 | 0.000 | 1.0 | NO |
| qa | 1.000 | 1.000 | 0.000 | 1.0 | NO |

- **Today's overall**: control 1.000 vs treatment 1.000, delta **0.000**, p = 1.0. All three agents fully saturated. The runner's dry-run warning that "templates for qa and implementer are identical" applies to today's branch; the corpus was authored against an older template divergence and no longer discriminates.
- **For historical context only**: the repo also contains `evals/reviewer-asymmetry-spike/runs/final.json` from 2026-05-09, which captured control 0.550 vs treatment 1.000 (delta +0.450, driven by critic +0.50 and implementer +0.85). That run reflects a template state that has since merged or converged. It is NOT today's baseline; do not cite it as such.
- findings_count_stats (qa): control_mean 6.4 vs treatment_mean 6.6 (Mann-Whitney U, p=0.362). Qualitative findings count also shows no significant difference today.

## What this means

| Spike | Carry forward? | Why |
|---|---|---|
| security | Yes. | The agent prompt clearly adds value. Use it; consider further specialization on the false-positive-resistance fixtures where delta is smaller. |
| analyst | **No, not as-is.** | Agent loses to baseline. Tighten the corpus OR audit the prompt. Either change is cheap (<$1 to re-run) and required before claiming analyst evaluation is "covered". |
| reviewer-asymmetry | **No, not as-is.** | Today's run: all three agents saturated (1.000 / 1.000). No detectable delta. The corpus was authored against a template divergence (May-9) that has since converged or merged. Either re-establish a control template (capture pre-merge `main` SHA) or author harder fixtures that today's saturated variants can still fail on. |

## Methodology

Both runners use the same naive baseline contract: a single sentence `Review the following input.` plus the harness-enforced output shape `IDENTIFY | OK | ESCALATE` (for agent-vs-baseline) or `verdict_options` (for reviewer-asymmetry). Specialization is the only free variable between the two variants.

Per fixture, 3-5 independent runs at temperature default. Verdict pass = output begins with the expected verdict AND (when applicable) any regex assertions match. Recall is the mean per-fixture pass rate, averaged across fixtures (not weighted by per-fixture trial count). Bootstrap CI uses 1000 resamples of fixture-level pass-rate differences.

Flaky fixtures (intra-run variance > 0 within a single variant) are detected, recorded, and selectively excluded by the runner if their inclusion would push error rate above MAX_ERROR_RATE (REQ-004 AC-3).

## What this report is NOT

- Not a coverage baseline for "all skills and agents". This is three spikes out of 71 skills + 23 agents.
- Not a recommendation to ship or block any change. It is a measurement.
- Not a substitute for unit tests; eval signal is behavioral, not correctness.

## Followups

1. **Tighten or audit `analyst`**: the most actionable finding here. Either fix the corpus or audit the prompt; re-run is ~$0.40.
2. **Replace saturated `qa` fixtures**: reviewer-asymmetry's qa corpus passes 100% on both variants. The fixture set is too easy to detect change. Author harder qa fixtures (deeper edge cases, more planted issues) and re-run.
3. **Author next spikes**: next high-leverage targets per the triage docs would be `threat-modeling` (skill, security-adjacent), `architect` (agent, largest prompt = biggest change surface), `code-qualities-assessment` (skill, structured output). Skill spikes require either extending `eval-agent-vs-baseline.py` to look up `.claude/skills/<name>/SKILL.md` instead of `templates/agents/<name>.shared.md`, or a new runner.
4. **Per-spike cron**: once 2+ spikes per axis exist, wire `scripts/eval/eval-suite.py` cron entry to detect drift quarterly.

## Cross-references

- [evals/skill-triage.md](./skill-triage.md) - skill classification matrix (71 skills).
- [evals/agent-triage.md](./agent-triage.md) - agent classification matrix (23 agents).
- [evals/security-spike/](./security-spike/) - reference implementation for agent-vs-baseline.
- [evals/reviewer-asymmetry-spike/](./reviewer-asymmetry-spike/) - reference implementation for A/B prompt-change.
- [evals/analyst-spike/](./analyst-spike/) - new spike from this PR.
- [evals/security-spike/reports/20260503T182553Z-eaa08f8d/REPORT.md](./security-spike/reports/20260503T182553Z-eaa08f8d/REPORT.md) - per-fixture detail.
- [evals/analyst-spike/reports/20260528T040743Z-643d1793/REPORT.md](./analyst-spike/reports/20260528T040743Z-643d1793/REPORT.md) - per-fixture detail.
- [.agents/architecture/ADR-057-prompt-behavioral-evaluation.md](../.agents/architecture/ADR-057-prompt-behavioral-evaluation.md).
- REQ-004 / DESIGN-004 / [.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md](../.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md).
