# Ship eval scenarios passed although the evaluated text never held the judgment, consistent with model priors

**Atomicity**: 90%
**Category**: Eval design, skill rewrites
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E028. State checked on main at 1be533c496 (2026-11-26).

## Question

Does an eval pass show that the evaluated text carries the judgment the scenario tests?

## Conventional answer

The eval README said the base ship text already led the model to the push-pr answers. So the carried set eval was thought to cover retained judgment.

## First-principles position

Scenarios P2 and P3 passed 3 of 3. The base ship text never held the terms the scenarios need, so the pass showed nothing about retained judgment. The pass is consistent with model priors, but it is not isolated: keyword counts cannot rule out paraphrased guidance, and expected answers sat mostly in the first option position, which is another explanation.

## Evidence with limits

- Grep counts over the base ship text (2026-11-25): 0 hits for "criteri" and 0 for "bypass". push-pr/SKILL.md has 3 and 5.
- Quote from the run: "force 1 | acceptance 0 | criteri 0 | bypass 0 | description 1"
- In 13 of 14 scenarios (2026-11-25), the expected verdict was the first listed option. A grader could reward always picking first.
- Limits: One eval at one branch state on 2026-11-25, with three runs per scenario. The spread labels fix and the README live on unmerged branch commits, not on main.
- State on main at 1be533c496 (2026-11-26): no repo artifact. evals/skill-rewrites/ship/README.md does not exist on main. tests/evals/ship-scenarios.json holds 8 S scenarios and no P1 to P3. The fix commit is not an ancestor of main.

## Decision

Before trusting an eval pass, grep the evaluated text for the terms the scenario needs. Spread expected labels across option positions and run a baseline on every surface the claim covers.

## Related

- `.serena/memories/eval/eval-keyword-graders-test-wording-not-behavior.md`
