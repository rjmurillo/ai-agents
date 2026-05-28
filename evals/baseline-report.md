# Baseline Eval Report

Baseline measurement: do current agent prompts beat a naive baseline on a held-out corpus? Aggregate run across 8 agents on fixtures derived from rjmurillo/moq.analyzers, dotnet/runtime, and rjmurillo/ai-agents public PRs and issues.

## Date

2026-05-28

## Aggregate matrix

| Agent | Fixtures | Agent recall | Baseline recall | Delta | 95% CI | Significant? | Cost | Keep / Cut |
|---|---|---|---|---|---|---|---|---|
| security | 10 | 0.833 | 0.417 | **+0.417** | [+0.100, +0.727] | **YES (POS)** | $1.00 | **KEEP** |
| independent-thinker | 8 | 0.750 | 0.583 | **+0.167** | [+0.000, +0.333] | borderline | $0.29 | KEEP, audit |
| high-level-advisor | 8 | 0.583 | 0.479 | +0.104 | [-0.021, +0.250] | NO | $0.24 | KEEP, re-eval |
| architect | 8 | 0.857 | 0.857 | 0.000 | [+0.000, +0.000] | NO (saturated) | $0.65 | RE-AUTHOR fixtures or CUT |
| devops | 8 | 0.583 | 0.583 | 0.000 | [+0.000, +0.000] | NO (saturated) | $0.25 | RE-AUTHOR fixtures or CUT |
| qa | 8 | 0.833 | 0.833 | 0.000 | [-0.417, +0.333] | NO (wide CI) | $0.59 | RE-AUTHOR fixtures or CUT |
| analyst | 24 | 0.825 | 0.850 | -0.025 | [-0.100, +0.050] | NO | $1.02 | AUDIT prompt; ESCALATE bias |
| critic | 8 | 0.833 | 0.917 | **-0.083** | [-0.250, +0.000] | NO (lean negative) | $0.37 | AUDIT prompt; over-blocks |

**Total live spend**: ~$4.41 for this 8-agent batch on top of prior runs. Cumulative across all eval work on this PR: ~$9.37 USD across ~840 trials.

## Headline findings

1. **security is the only agent with measurable positive lift over a naive baseline.** Delta +0.417, CI lower bound +0.100. The agent prompt clearly adds value. KEEP.
2. **independent-thinker and high-level-advisor lean positive but CI touches zero.** Both prompts probably help on the right corpus. The fixtures here are not yet discriminating enough to prove it. KEEP and re-eval after corpus improvements.
3. **architect, devops, qa show 0.000 delta (saturated).** Both variants score the same on every fixture. The corpus is too easy for the metric to distinguish them. Two interpretations: either the prompt adds nothing the model defaults already supply (cut candidate), or the fixtures fail to surface the agent's specialization (re-author candidate). Burden of proof is on the fixtures; rebuild before deciding cut.
4. **critic and analyst lean negative.** Critic -0.083 (CI [-0.250, +0.000]); analyst -0.025 (CI [-0.100, +0.050]). The naive baseline beats the specialized agent on a measurable share of fixtures. Most likely cause is verdict-vocabulary mismatch: both agents have rich output styles that the harness's IDENTIFY|OK|ESCALATE contract penalizes when the agent's natural verdict does not match. Same class of issue as security's BLOCKED bug (see Critical Caveat). AUDIT the prompts and the harness contract before claiming the agents add no value.

## Critical caveat: harness verdict-vocabulary forces all output through IDENTIFY|OK|ESCALATE

Per `scripts/eval/eval-agent-vs-baseline.py`, the runner appends a fixed OUTPUT_SHAPE_SUFFIX to both variants: "Begin your response with exactly one word: IDENTIFY, OK, or ESCALATE." Agents whose canonical verdict vocabulary uses other tokens (security uses `BLOCKED`; critic uses verdict phrases like `REJECT`, `APPROVE`; qa uses `PASS`/`FAIL`/`BLOCKED`; analyst's per-fixture verdict shape from its prompt is structured findings) score worse on the verdict assertion than they would under their native contract.

This means the deltas above understate the true behavioral difference for any agent whose template uses a different verdict vocabulary. The security spike caught this on its first run (Cursor Bugbot, addressed in `evals/security-spike/runs/20260528T035241Z-45e0c2f3/`): security still beat baseline because the regex CWE-code assertions passed. Other agents may not have the same compensating regex assertions.

Three fix paths, none of which are in scope for this PR:

1. Extend `OUTPUT_SHAPE_SUFFIX` to accept per-agent verdict vocabularies (cheapest, breaks comparability).
2. Add a normalization step in `_VERDICT_RE` that maps agent-native verbs to IDENTIFY|OK|ESCALATE bands.
3. Align all agent templates to the harness vocabulary (most invasive; changes user-visible behavior).

## Per-agent detail

### security (KEEP)

10 fixtures covering CWE-22/77/200 plus 3 false-positive-resistance scenarios. Agent recall 0.833 vs baseline 0.417, delta +0.417, CI [+0.100, +0.727]. Statistically significant positive lift. Cost $1.00. Caveat above applies: agent's BLOCKED verbal verdict is scored as a verdict-assertion failure, but the regex assertions matching CWE codes still pass and drive most of the delta.

### independent-thinker (KEEP, audit)

8 fixtures covering popular-but-wrong claims, verify-before-claim, calibrated uncertainty. Agent 0.750 vs baseline 0.583, delta +0.167. CI [+0.000, +0.333] lower bound at zero. Suggests the contrarian prompt does help on the right fixtures (popular-but-wrong, uncertain-without-data, verify-before-claim) but the sample is too small to claim significance.

### high-level-advisor (KEEP, re-eval)

8 fixtures covering priority calls, blind-spot survey, paralysis resolution, scope explosion pushback. Agent 0.583 vs baseline 0.479, delta +0.104. CI [-0.021, +0.250] lower bound below zero. The fixtures may be too generic (a model with default training already handles "prioritize" reasonably well); re-author with cases that specifically require the high-level-advisor's "brutal honesty / no comfort" framing.

### architect (RE-AUTHOR or CUT)

8 fixtures, both variants score 0.857. Zero delta, zero variance. The fixtures (design coherence, boundary discipline, abstraction tradeoffs) are answerable by any competent model without the architect prompt. To prove the architect adds value, author fixtures where the architect's specific patterns (Cynefin classification, Conway's Law, intentional coupling vocabulary) are required to reach the right answer.

### devops (RE-AUTHOR or CUT)

8 fixtures, both 0.583. Same pattern as architect. The fixtures (action pinning, concurrency missing, secret leak risk, shell injection) are well-known general security/CI patterns. Re-author with fixtures requiring the devops agent's specific framing (Hook Maturity Model tiers, pipeline gate philosophy, ADR-006 thin-workflow patterns).

### qa (RE-AUTHOR or CUT)

8 fixtures, both 0.833. CI wide (-0.417 to +0.333) on a small sample. The fixtures (edge cases, status claims, missing tests) are detectable by any competent reviewer. Re-author with cases that need the qa agent's specific reviewer-asymmetry framing (planted issues that require fresh-context adversarial review, not the implementer-confirmation bias).

### analyst (AUDIT)

24 fixtures across three rounds (8 synthetic, 10 moq.analyzers, 18 mixed, 24 with feature/refactor additions). Final delta -0.025, CI crosses zero. The analyst over-IDENTIFIES on ESCALATE-shaped fixtures: F014 (CS1591 cascade) -0.50, F016 (scope explosion, flaky) -0.33. The "Investigate what you have / Unknown is a finding" framing biases against ESCALATE. Either tighten the prompt's ESCALATE trigger for unknown-scope cases or accept the bias and revise fixture expectations.

### critic (AUDIT)

8 fixtures covering planted issues, missing tests, status claims, race conditions, silent fallbacks. Agent 0.833 vs baseline 0.917, delta -0.083, CI [-0.250, +0.000] lean negative. The critic's verdict vocabulary (`REJECT`, `APPROVE`, sometimes `BLOCKING`) does not align with IDENTIFY|OK|ESCALATE. Verdict assertions probably fail for the agent variant even when the critic correctly finds the planted issue. Audit cheapest: rerun under a runner that scores findings_count, not verdict.

## Methodology

Per spike: 3-5 independent runs per fixture per variant at default temperature. Verdict assertion passes when output starts with the expected verdict from IDENTIFY|OK|ESCALATE (harness-enforced). Regex assertions pass when the pattern matches anywhere in the body. Recall is the mean per-fixture pass rate. Bootstrap CI uses 1000 resamples of fixture-level deltas.

Flaky fixtures (intra-run variance > 0 within a single variant) are detected and selectively excluded by the runner when their inclusion would push error rate above MAX_ERROR_RATE (REQ-004 AC-3).

Baseline prompt is fixed across all spikes: `Review the following input.` plus the OUTPUT_SHAPE_SUFFIX. Specialization (the agent's system prompt loaded from `templates/agents/<agent>.shared.md`) is the only free variable between variants.

## What this PR ships

- 8 spike directories (1 existing + 7 new) under `evals/<agent>-spike/` with authored fixtures and live-run reports.
- 60 fixtures total (10 security + 24 analyst + 8 each for architect, critic, devops, high-level-advisor, independent-thinker, qa).
- 2 triage docs (`evals/skill-triage.md`, `evals/agent-triage.md`) classifying every skill and agent in the repo.
- This baseline report.
- Reviewer-asymmetry-spike kept as historical reference (today's run shows saturation at 1.000/1.000; the May-9 final.json captures a stage when templates diverged).

## What this report is NOT

- Not a verdict that any agent should be deleted. The deltas are noisy at this sample size and the harness vocabulary is a known confound. AUDIT means "the eval cannot answer this yet"; it does not mean "the agent is useless."
- Not a coverage claim for all skills and agents. Skills are not evaluated here; see `evals/skill-triage.md` for the deferred plan.
- Not a substitute for unit tests. Eval signal is behavioral, not correctness.

## Followups

1. **Fix the verdict-vocabulary confound** for critic, qa, analyst. This is the single biggest source of measurement noise across spikes.
2. **Re-author fixtures for architect, devops, qa** to require the agent's specific framing. The current fixtures are too easy.
3. **Address the analyst ESCALATE bias** in the prompt itself, or revise fixture expectations.
4. **Wire a quarterly cron** to detect drift in security-spike now that it has a real positive delta to protect.
5. **Convert retrospective agent to skill** per [issue #2080](https://github.com/rjmurillo/ai-agents/issues/2080); not in scope here.

## Cross-references

- [evals/skill-triage.md](./skill-triage.md) - 71-skill classification.
- [evals/agent-triage.md](./agent-triage.md) - 23-agent classification.
- [evals/security-spike/](./security-spike/) - reference implementation.
- [evals/analyst-spike/](./analyst-spike/) - 24-fixture corpus from moq.analyzers + dotnet/runtime + ai-agents.
- [scripts/eval/eval-agent-vs-baseline.py](../scripts/eval/eval-agent-vs-baseline.py) - runner.
- [ADR-057](../.agents/architecture/ADR-057-prompt-behavioral-evaluation.md) - prompt behavioral evaluation.
- REQ-004 / DESIGN-004 / [PLAN-1854](../.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md) - harness origin.
