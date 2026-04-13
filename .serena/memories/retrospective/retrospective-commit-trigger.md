# Skill-retrospective-006: Commit Threshold Trigger

**Statement**: Trigger mini-retrospective after 10 commits on same PR without merge to identify stuck patterns.

**Context**: A PR with 10+ commits without merge signals the agent is stuck in a pattern or misunderstanding. Stop autonomous iteration and run retrospective to identify what's stuck before continuing past commit 10.

**Evidence**: PR #760 accumulated 38 commits before retrospective. If mini-retrospective triggered at commit 10, could have identified:
- Suppression attempt problem earlier
- Pattern blindness (repeated same mistake)
- User feedback wasn't being integrated
- Autonomous mode lacks security understanding

Earlier intervention could have prevented 28 additional commits and user frustration.

**Atomicity**: 93% | **Impact**: 8/10

## Pattern

Track commit count per PR during autonomous execution:

1. **Commit 1-3**: Normal iteration, building solution
2. **Commit 4-10**: Problem-solving phase, trying approaches
3. **Commit 10**: CHECKPOINT - Ask: "Am I stuck?"
   - If 8+ of 10 commits were fixes/rollbacks: YES, stuck
   - If commits are additive and making progress: CONTINUE
4. **If stuck at commit 10**: Trigger mini-retrospective
   - Why are commits failing?
   - What pattern is repeating?
   - What feedback am I not integrating?
   - Do I need expert review or different approach?
5. **Resume after clarity** - Continue autonomous work with new understanding

Mini-retrospective should take < 10 minutes and answer:
- What's failing repeatedly?
- What would break the pattern?
- Do I need human input before continuing?

## Anti-Pattern

Never ignore 10+ commits without merge. This indicates:
- Pattern blindness (repeating same mistake)
- Feedback not being integrated
- Fundamental misunderstanding of problem
- Autonomous mode spiraling

Stop and retrospect. Don't continue hoping for breakthrough.

## Related

- [retrospective-001-pr-learning-extraction](retrospective-001-pr-learning-extraction.md)
- [retrospective-001-recursive-extraction](retrospective-001-recursive-extraction.md)
- [retrospective-002-retrospective-to-skill-pipeline](retrospective-002-retrospective-to-skill-pipeline.md)
- [retrospective-003-token-impact-documentation](retrospective-003-token-impact-documentation.md)
- [retrospective-004-evidence-based-validation](retrospective-004-evidence-based-validation.md)
