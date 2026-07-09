---
id: ADR-075
status: proposed
date: 2026-06-19
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-075: Form-Factor Evaluation Methodology (Agent vs Skill)

## Status

Proposed. Requested by issue [#1875](https://github.com/rjmurillo/ai-agents/issues/1875). Follow-on to ADR-058 (agent eval discipline), which scoped the form-factor question out and tracked it here.

This ADR records a methodology and a first result. It requires adr-review before its status moves to Accepted.

## Date

2026-06-19

## Context and Problem Statement

ADR-058 measured whether a specialized agent system prompt beats a naive content baseline (the content question). It deliberately left out the form-factor question (ADR-058 lines 107 to 109):

Would the same domain content, delivered as a `skill` loaded into the parent's context and reasoned over inline, produce recall equivalent to dispatching it to a subagent, at lower cost (one model call instead of a parent-to-subagent dispatch) and without subagent-isolation complexity?

The content and the form are different axes. A positive content verdict justifies investing in the content. It does not, on its own, say whether that content should ship as an agent (subagent system prompt) or a skill (parent-inline `SKILL.md`). This ADR defines how to decide, and applies it to the security domain.

## Decision Drivers

- Cost: in production a skill is one model call and an agent dispatch is parent plus subagent. Note the eval harness in this ADR does not model that production dispatch overhead; it measures tokenized prompt content per variant (see the Confirmation section).
- Recall parity: the form must not lose findings the agent form catches.
- Isolation: subagents add context-isolation complexity and a known 1M-context failure mode (anthropics/claude-code#55694).
- Comparability: the comparison must reuse the exact fixtures and judge as the content eval, so only the form-factor varies.

## Decision

Adopt a three-variant eval. For one domain, hold the content and the model constant and vary only the delivery form:

1. `baseline`: a deliberately naive content prompt (the ADR-058 baseline).
2. `agent`: the agent's `templates/agents/<name>.shared.md` as a subagent system prompt.
3. `skill`: the domain `SKILL.md` read into the parent's context and reasoned over inline.

All three are scored against the same held-out fixtures with the same judge. The harness supports this via `scripts/eval/eval-agent-vs-baseline.py --include-skill --skill-path <SKILL.md>` (issue #1875).

### Decision criteria

| Verdict | Condition | Action |
|---------|-----------|--------|
| prefer-skill-form | skill recall is within the agent's confidence interval (no significant loss) AND skill cost is lower | Ship the content as a skill; retire or stop investing in the agent form for this domain. |
| prefer-agent-form | agent recall exceeds skill recall beyond overlapping confidence intervals | Keep the agent form; the isolation or dispatch buys real recall. |
| inconclusive | confidence intervals overlap and cost delta does not decide it | Keep both, re-run with more fixtures or runs before deciding. |

Note on the statistics: "within the agent's confidence interval (no significant loss)" is a non-significance test (the CI includes zero), not a proof of equivalence. An underpowered run with a wide CI will pass this gate even when a real loss exists, which perversely rewards running fewer fixtures. A future revision should add an equivalence margin (for example, reject the verdict if the CI half-width exceeds a set threshold in percentage points) so a wide-CI run resolves to `inconclusive` rather than a `prefer-skill-form` that the data cannot support. Until that margin is encoded, a `prefer-skill-form` verdict from a wide-CI run is directional and the cost delta, not the recall comparison, is what decides it.

### Cost accounting

Cost is reported as model calls and tokens (input plus output) per variant, not wall-clock seconds or API dollars. Tokens are the proxy this repo compares on. Each variant is charged one call per (fixture, run); the harness does not add a parent-to-subagent dispatch multiplier for the `agent` variant. It measures the tokenized prompt content per variant, so the token count reflects how much text each artifact carries, not a production dispatch cost. The comparison is per-fixture so a single expensive fixture cannot dominate. Any token gap between variants (for example the 3x gap in the first Confirmation run) is a content-size difference between the two artifacts, not a form cost; see the Confirmation section for the content-controlled check.

## Considered Options

- Three-variant eval (chosen): isolates form-factor by holding content and model constant.
- Infer from the content eval alone: rejected. The content eval cannot separate form from content; it only compares specialized vs naive content in the agent form.
- A/B in production: rejected for a first verdict. No held-out scoring, contaminated by real-traffic variance, slow to read.

## Consequences

- Good: a repeatable, cheap way to decide agent vs skill per domain, reusing existing fixtures and judge.
- Good: makes the cost argument explicit (one call vs dispatch) instead of assumed.
- Bad: a single-domain, single-run verdict is low-N and within-noise risk (see ADR-058 corpus caveats and the eval non-determinism tracked at #2678). Treat one run as directional, not final.
- Neutral: the methodology says nothing about domains it was not run on; each domain needs its own run.

## Confirmation

First application: the security domain, run 2026-06-19.

- Agent variant: `templates/agents/security.shared.md`.
- Skill variant: `.claude/skills/security-review/SKILL.md` (the skill-form artifact created under #1875).
- Fixtures: `evals/security-spike/fixtures/` (F001 to F016), 3 runs per (fixture, variant), model claude-sonnet-4-6.
- Command: `scripts/eval/eval-agent-vs-baseline.py --agent security --fixtures evals/security-spike/fixtures --n-runs 3 --model claude-sonnet-4-6 --include-skill --skill-path .claude/skills/security-review/SKILL.md`.

Run: `20260619T161735Z-ad60bbe5` (16 fixtures, 3 runs, 144 calls, 0 errors). Report: `evals/security-spike/reports/20260619T161735Z-ad60bbe5/REPORT.md`.

| Metric | Agent | Skill |
|--------|-------|-------|
| Recall | 82.4% | 84.3% |
| Tokens | 362,804 | 123,853 |

- Agent minus skill recall: -1.96pp, 95% bootstrap CI [-26.67pp, +26.67pp]. The interval includes zero, so the skill form shows no significant recall loss versus the agent form on this corpus.
- Skill minus baseline recall: +43.14pp. The skill form keeps the full content benefit the agent form delivers (agent minus baseline was +41.18pp).
- Cost: the skill form used 123,853 tokens against the agent form's 362,804, roughly one third. The original interpretation was "consistent with one inline call versus a parent-to-subagent dispatch"; the content-controlled rerun below shows this gap was a content-size difference between the two artifacts, not a form or dispatch cost.

**First-run verdict (superseded by the content-controlled rerun below): prefer-skill-form (directional).** The first run reported the skill form at about a third of the tokens (123,853 vs 362,804) and a recall point estimate slightly above the agent (84.3% vs 82.4%), with a 95% CI on the agent-skill delta of [-26.67pp, +26.67pp] that includes zero. That verdict rested on two confounds the first run could not remove: the skill artifact carried different (smaller) content than the agent, so both the token gap and the recall point estimate mixed form with content. The content-controlled rerun below removes the content variable and overturns the token interpretation.

### Content-controlled confirmatory rerun (#2936)

The first run's headline caveat was the content confound: the skill artifact was a smaller projection of the agent, so form and content varied together. Issue [#2936](https://github.com/rjmurillo/ai-agents/issues/2936) built a content-controlled skill variant whose body is byte-identical to the agent body, so only the form label differs.

- Agent variant: `templates/agents/security.shared.md`.
- Skill variant: `evals/security-spike/skill-content-controlled/SKILL.md`, whose body (frontmatter stripped) hashes identically to the agent body.
- Content parity, verified: both the agent prompt and the content-controlled skill prompt strip to SHA `be36604d83651117bc5bffd29ac1c95ce3a64bf5cc0f9bf2106009cf00b0a7e1`. The harness recorded `agent_prompt_sha = be36604d...`. Parity is enforced by `tests/evals/test_form_factor_eval.py::TestContentControlledPromptParity`.
- The content-controlled fixture is a deliberate non-skill artifact: its body is an agent body reused verbatim, so it lacks SkillForge Triggers/Process sections by construction and is reconstructable from `templates/agents/security.shared.md`. The pre-commit skill validator exempts `evals/` fixtures from structural validation for this reason (see `.githooks/pre-commit`, `STAGED_SKILL_FILES`).
- Fixtures: `evals/security-spike/fixtures/` (F001 to F016), 5 runs per (fixture, variant), model claude-sonnet-4-6.
- Command: `scripts/eval/eval-agent-vs-baseline.py --agent security --fixtures evals/security-spike/fixtures --n-runs 5 --model claude-sonnet-4-6 --include-skill --skill-path evals/security-spike/skill-content-controlled/SKILL.md`.

Run: `ff2936confirm` (16 fixtures, 5 runs, 240 calls, 0 errors, ~$4.07). Report: `evals/security-spike/reports/ff2936confirm/REPORT.md`.

| Metric | Agent | Skill | Baseline |
|--------|-------|-------|----------|
| Recall | 78.95% | 78.95% | 36.84% |
| Tokens in | 582,040 | 582,040 | (naive) |

- Agent minus skill recall: 0.0pp, 95% bootstrap CI [0.0pp, 0.0pp]. With content held byte-identical, the two forms return the same recall on every stable fixture in the aggregate. One fixture, F013, was detected flaky and excluded from the stable-subset CI (eval non-determinism tracked at #2678); the 0.0 delta is over the 15 stable fixtures.
- Tokens: input tokens identical (582,040 vs 582,040); output tokens differ only by 326 (agent 12,988, skill 12,662), sampling noise. The first run's ~3x token gap was a content-size artifact, not a dispatch cost. This harness path charges one call per (fixture, run) for both forms and does not model a parent-to-subagent dispatch multiplier, so the token comparison in the first run measured only how much text each artifact carried.
- Both forms beat baseline by +42.11pp (78.95% vs 36.84%), so the content itself carries the full benefit, as before.

**Corrected verdict: no measurable form effect once content is controlled.** For the security domain on this corpus, agent form and skill form are indistinguishable in recall (delta 0.0, CI [0,0]) and identical in input tokens (582,040 each) when they carry the same content. The first run's prefer-skill-form signal mixed form with content and is not interpretable as a form effect: the skill artifact was smaller (explaining the token gap) and its content scored a hair higher (a difference the rerun cannot attribute to form; sampling non-determinism at #2678 is an equally consistent explanation). The `form_factor.verdict` field reads `inconclusive`: the 326-token output difference (skill 12,662 vs agent 12,988 output tokens) is below the 1% minimum-savings guard (`FORM_FACTOR_MIN_COST_SAVINGS_FRACTION`), so the cost tiebreak does not fire on run-to-run sampling noise, and the verdict reflects no form advantage. Read the methodology's output as: for this security corpus, this byte-identical content body, this model, and this harness path, form factor (agent vs skill) shows no measured effect on recall or input tokens. That is not a general claim that form can never matter: subagent isolation, context budget, tool access, and a production dispatch path that this harness does not model could all make form a lever. What moved the numbers here was content. Choose the form on those operational grounds, not on an expected recall or token difference measured by this harness.

**Caveats.**

- **Single domain, single content set.** This is the security corpus with one content body, one model, one harness path. What follows from the harness charging both forms identically is the input-token equality: that part generalizes to any content on this harness path. The recall equivalence (delta 0.0) is a single-run observation on this corpus, not a general result; it has not been rerun on another domain, content body, or a harness that models production dispatch.
- **Harness does not model dispatch cost.** The token equality shows this path does not add a parent-to-subagent multiplier. If a future harness models real dispatch overhead, the token comparison would change. Whether recall stays equivalent under a real dispatch path is not established here and would need to be remeasured: a production dispatch path can change prompt framing, context boundaries, and tool availability, any of which could move recall.
- **Per-fixture skill data not persisted.** The report's per-fixture breakdown carries only `agent` and `baseline`; the skill aggregate is in the `form_factor` block but per-fixture skill rows are not in the current report schema. The aggregate numbers are verified against `report.json`, but per-fixture skill provenance is not independently auditable from the committed artifact.

The content confound that kept the first run at Proposed is now resolved. Promotion to Accepted is gated on adr-review of this corrected verdict.

## Reversibility Assessment

Fully reversible. This ADR adds a methodology and a record; it ships no runtime behavior. A later ADR may supersede the decision criteria or add a contamination-detection step.

## Vendor Lock-in Assessment

None. The harness uses the repo's own `call_api` transport (`scripts/eval/_anthropic_api.py`), not a vendor SDK. The methodology is model-agnostic; `--model` is a parameter.

## Impact on Dependent Components

- ADR-058: this ADR closes the form-factor gap ADR-058 left open (lines 107 to 109). ADR-058's pointer is updated to reference this ADR.
- `scripts/eval/eval-agent-vs-baseline.py`: the `--include-skill` / `--skill-path` flags are the supported entry point.

## Related Decisions

- ADR-058 (agent eval discipline): the content-question methodology this extends.
- ADR-057 (referenced by ADR-058): prompt-change eval scenarios.

## References

- [Issue #1875](https://github.com/rjmurillo/ai-agents/issues/1875): form-factor methodology tracker.
- ADR-058 lines 107 to 109: the deferred form-factor scope.
- [Issue #2678](https://github.com/rjmurillo/ai-agents/issues/2678): skill-overlap eval non-determinism, a caution on low-N verdicts.
