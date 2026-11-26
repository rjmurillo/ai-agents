# The old recurrence ablation could not see the guard clause because its implementer agent wrote tests in both arms

**Atomicity**: 90%
**Category**: Eval design, ablation controls
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E034. State checked on main at 1be533c496 (2026-11-26).

## Question

Can an ablation show a rule's effect when the control arm already carries the behavior by another route?

## Conventional answer

The existing ablation control and the grader verdict were trusted to show whether a rule changes agent behavior.

## First-principles position

The old control used an implementer agent whose prompt asks for tests. Both arms wrote tests, so the control could not detect a rule that adds tests. A neutral control showed the effect. The grader also passed a shorter wording whose replies still ended on the banned next step line.

## Evidence with limits

- With the rule the agent wrote a test in 5 of 5 runs. Without it, 0 of 5 did (2026-11-07). Fisher's exact test, two sided, gave p = 0.008.
- The old control could not show this, because the implementer asks for tests in both arms.
- The grader passed a shorter wording whose replies still ended on the banned line. Reading the replies caught it.
- Quote from the run: "Fisher's exact test, two-sided: p = 0.008."
- Limits: One task, one model (claude-sonnet-5-5), one harness, 5 runs per arm. The Copilot harness did not run.
- State on main at 1be533c496 (2026-11-26): fixed. `evals/recurrence-ablation/README.md:16` gives Fisher p = 0.008. Line 20 explains why both arms wrote tests. The pair now uses `neutral-editor`.

## Decision

Check that the control arm lacks the behavior by other routes before trusting an ablation. Read the replies, because the grader verdict alone missed a banned ending.

## Related

- `.serena/memories/eval/eval-keyword-graders-test-wording-not-behavior.md`
- `.serena/memories/decision-eval-fixture-provenance-closed-loop.md`
