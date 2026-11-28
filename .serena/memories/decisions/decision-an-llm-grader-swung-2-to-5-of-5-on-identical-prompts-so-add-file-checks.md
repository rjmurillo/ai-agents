# An LLM grader passed 4, 4, 4, 5, then 2 of 5 on identical prompts, so file checks must back it

**Atomicity**: 90%
**Category**: Eval design, grader noise
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E035. State checked on main at 1be533c496 (2026-11-26).

## Question

Can a semantic LLM grader alone judge whether a rule stops scope creep?

## Conventional answer

The existing rules (code-quality.md, plus "State the trade-off once" in builder-ethos.md and voice.md) were assumed enough to keep edits scoped and to surface lost regression coverage.

## First-principles position

The rule alone did not stop scope creep. The agent rewrote sibling files in every run before the fix. The semantic grader also swung on identical prompts, so its verdicts are noisy. A deterministic file check caught what the grader missed.

## Evidence with limits

- Before the fix, the rule arm rewrote feeds.py and ingest.py in 5 of 5 runs (2026-11-07). With the new sentence, 11 of 11 runs left them unchanged.
- The semantic grader passed 4, 4, 4, 5, then 2 of 5 on five same-prompt sets. The 2 of 5 on the final set is variance, not an effect of the regex.
- The skip regex caused 3 failures in 10 runs.
- Limits: One task, one model, 5 to 11 runs per arm. The sentence may trade scope creep for a closing suggestion, which the grader failed in 3 of 11 with-rule runs.
- State on main at 1be533c496 (2026-11-26): fixed. src/claude/skills/build/references/rule-code-quality.md:135 carries the added scope sentence. evals/recurrence-ablation/README.md:34 pins a deterministic file_regex check.

## Decision

Pair every LLM graded ablation with deterministic checks on files and tool events. Treat a grader swing of 3 of 5 as noise until repeated.

## Related

- `.serena/memories/eval/eval-keyword-graders-test-wording-not-behavior.md`
- `.serena/memories/decision-eval-fixture-provenance-closed-loop.md`
