---
source: wiki/concepts/Design Principles/Pit of Success.md
created: 2026-04-11
review-by: 2026-07-11
---

# Pit of Success

> "We want our customers to simply fall into winning practices by using our platform and frameworks." -- Rico Mariani

## Core Principle

Make correct behavior the path of least resistance. The developer who does the obvious, easy thing should end up with a correct result. Wrong behavior should require deliberate effort.

## The Asymmetry

| Design | What Happens When You Do the Easy Thing |
|--------|----------------------------------------|
| Pit of despair | The easy thing is wrong. Developers must learn tricks to avoid traps. |
| Neutral | The easy thing is mediocre. Correctness requires extra work. |
| Pit of success | The easy thing is right. Getting it wrong requires deliberate effort. |

## Planner Application

Apply pit-of-success thinking when designing milestones, interfaces, and migration plans.

### Plan Quality Checklist

When reviewing a plan (TW + QR review phase), verify:

1. **Default behavior is correct**: Does each milestone produce a working, deployable state? If a team stops after milestone N, is the system still functional?
2. **Pretty names for right types**: Are the recommended approaches named clearly? Is the golden path obvious?
3. **Wrong thing looks wrong**: Do anti-patterns in the plan stand out visually? Are risks flagged, not buried?
4. **Limited surface area**: Does each milestone have minimal scope? Fewer moving parts means fewer ways to fail.
5. **Recovery is automatic**: If a milestone fails, does the plan include rollback steps?

### Milestone Design Patterns

| Pattern | Pit of Success | Pit of Despair |
|---------|---------------|----------------|
| Migration | Strangler fig with incremental rollout | Big bang cutover on a deadline |
| Configuration | Defaults work out of the box | Manual setup required before first use |
| Testing | Tests run automatically in CI | Tests require manual invocation |
| Dependencies | Pinned versions with automated updates | Floating versions with manual audits |
| Documentation | Generated from code, always current | Manually maintained, drifts from reality |

### AI-Native Planning

When AI agents execute plans, they follow the path of least resistance more aggressively than humans. A plan that requires careful reading of caveats will produce wrong output at scale. A plan where each milestone has clear inputs, outputs, and success criteria produces correct output at scale.

Design plans so that an agent following the obvious steps produces the right result.

### Anti-Patterns

- **Pit of despair with guardrails**: Adding warnings to a fundamentally fragile plan. Fix the plan structure, not the warnings.
- **Pit of success with no escape hatch**: Making it impossible to deviate for legitimate edge cases. The pit should be easy to stay in, not impossible to leave.
- **Enforcement over design**: Blocking wrong behavior at review time is a gate. Pit-of-success design makes wrong behavior impossible to express at authoring time.

## Related Concepts

- Golden Path: the platform practice that implements the pit
- Shift Left: move the pit closer to the point of creation
- Gall's Law: start simple, evolve based on real feedback
