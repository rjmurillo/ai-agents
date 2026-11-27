# A capability eval whose cases grep can answer measures case design, not skill value

**Atomicity**: 90%
**Category**: Eval design
**Source**: Agent session sweep, sessions dated 2026-10. Sweep ids E081. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a small capability delta in a with-skill eval show the skills add little value?

## Conventional answer

A with-skill against baseline capability eval was expected to demonstrate the value of the refreshed skills.

## First-principles position

The baseline passed most cases, which the eval labels `no_gap`. The prompts a reviewer sampled asked for one fact at a cited line. A baseline agent could find it with grep. Those cases tested lookups, so the small gain does not show how much the skill helps on harder tasks.

## Evidence with limits

- A 17-skill refresh ran 51 frozen cases on Haiku (2026-10-31). Baseline scored 0.88 and with-skill 0.97, a delta of +0.09.
- Statuses were 6 gain, 43 no_gap and 2 regression. The 2 regressions were grader artifacts.
- Quote: "'baseline': 0.8824, 'with_skill': 0.9739, 'capability_delta': 0.0915, 'statuses': {'gain': 6, 'no_gap': 43, 'regression': 2"
- Limits: One run, Haiku only, 2026-10-31. The reading of 5 prompts came from one reviewer agent.
- State on main at 1be533c496 (2026-11-26): no repo artifact records the case design finding. `src/claude/skills/skill-bootstrap/references/authoring-and-gates.md:214-232` defines `no_gap` as a passing baseline.

## Decision

Read no_gap as "the case is answerable without the skill", not "the skill adds nothing". Write cases that need the skill's workflow, not one-line lookups.

## Related

- `.serena/memories/eval/eval-keyword-graders-test-wording-not-behavior.md`
