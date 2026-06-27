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

- Cost: a skill is one model call; an agent dispatch is parent plus subagent.
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

Cost is reported as model calls and tokens (input plus output) per variant, not wall-clock seconds or API dollars. Tokens are the proxy this repo compares on. The `skill` variant is charged one call per (fixture, run). The `agent` variant is charged for the dispatch path the harness models. That harness dispatch model is an approximation of the production parent-to-subagent path, not a measurement of it, so the 3x token ratio reflects the harness, not necessarily production cost. The comparison is per-fixture so a single expensive fixture cannot dominate.

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
- Cost: the skill form used 123,853 tokens against the agent form's 362,804, roughly one third, consistent with one inline call versus a parent-to-subagent dispatch.

**Verdict: prefer-skill-form (directional).** For the security domain on this corpus, the skill form costs about a third of the tokens (123,853 vs 362,804) at a recall point estimate slightly above the agent (84.3% vs 82.4%). The cost gap is the deciding factor. The recall comparison does not decide it: the 95% CI on the agent-skill delta is [-26.67pp, +26.67pp], a 53pp span that includes zero. "Includes zero" means the experiment cannot detect a difference, not that the two forms are proven equivalent. The same interval is consistent with the skill losing up to 27pp of recall. So this verdict says "the skill form is cheaper and not detectably worse here," not "the skill form is as good." It supports preferring the skill form when a domain's content does not depend on subagent isolation, as a directional default to revisit, not a basis for retiring the agent form.

**Caveats.**

- **Underpowered.** Single run, wide interval (flaky fixtures excluded from the stable-subset CI). The CI is too wide to establish recall equivalence; a confirmatory rerun with more fixtures or runs is needed to narrow it. Eval non-determinism tracked at #2678 applies.
- **Content confound.** The skill artifact (`security-review/SKILL.md`) is a smaller projection of the agent (`security.shared.md`) with a different verdict taxonomy, not a byte-identical port of the agent content. So this run varies content as well as form. A clean form-only comparison needs a content-controlled skill variant (identical domain rules and output contract). Until that rerun lands, read the verdict as form-plus-content, not form alone.
- **Per-fixture skill data not persisted.** The report's per-fixture breakdown carries only `agent` and `baseline`; the skill aggregate is in the `form_factor` block but per-fixture skill rows are not in the current report schema. The aggregate numbers are verified against `report.json`, but per-fixture skill provenance is not independently auditable from the committed artifact.

These caveats are why the status stays Proposed. Promotion to Accepted is gated on a content-controlled, narrower-CI confirmatory rerun.

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
