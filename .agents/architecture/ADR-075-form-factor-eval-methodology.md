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

### Cost accounting

Cost is reported as model calls and tokens per variant, not wall-clock. The `skill` variant is charged one call per (fixture, run). The `agent` variant is charged for the dispatch path the harness models. The comparison is per-fixture so a single expensive fixture cannot dominate.

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
- Fixtures: `evals/security-spike/fixtures/` (F001 to F010), 3 runs per (fixture, variant), model claude-sonnet-4-6.
- Command: `scripts/eval/eval-agent-vs-baseline.py --agent security --fixtures evals/security-spike/fixtures --n-runs 3 --model claude-sonnet-4-6 --include-skill --skill-path .claude/skills/security-review/SKILL.md`.

Run: `20260619T161735Z-ad60bbe5` (16 fixtures, 3 runs, 144 calls, 0 errors). Report: `evals/security-spike/reports/20260619T161735Z-ad60bbe5/REPORT.md`.

| Metric | Agent | Skill |
|--------|-------|-------|
| Recall | 82.4% | 84.3% |
| Tokens | 362,804 | 123,853 |

- Agent minus skill recall: -1.96pp, 95% bootstrap CI [-26.67pp, +26.67pp]. The interval includes zero, so the skill form shows no significant recall loss versus the agent form on this corpus.
- Skill minus baseline recall: +43.14pp. The skill form keeps the full content benefit the agent form delivers (agent minus baseline was +41.18pp).
- Cost: the skill form used 123,853 tokens against the agent form's 362,804, roughly one third, consistent with one inline call versus a parent-to-subagent dispatch.

**Verdict: prefer-skill-form.** For the security domain on this corpus, delivering the content as a parent-inline skill matches the agent form's recall within the confidence interval while costing about a third of the tokens. This justifies the `security-review` skill as the primary form for this domain and supports preferring the skill form when a domain's content does not depend on subagent isolation.

**Caveat.** This is a single run with a wide interval (flaky fixtures excluded from the stable-subset CI). Treat it as directional. The eval non-determinism tracked at #2678 applies: a confirmatory rerun is advised before this verdict drives retiring the agent form.

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
