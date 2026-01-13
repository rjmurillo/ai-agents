# Skill-Retrospective-001: Recursive Learning Extraction

**Statement**: After completing work, recursively extract learnings until no novel insights remain

**Context**: Session wrap-up, retrospective analysis

**Trigger**: After main work completed, before claiming session done

**Evidence**: Session 04 - User requested Round 2 extraction after initial retrospective

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-24

**Validated**: 1

**Category**: Retrospective

## Recursive Pattern

### Round 1: Initial Extraction

Extract obvious learnings from immediate work:
- What worked?
- What failed?
- What would you do differently?

### Round 2: Meta-Analysis

Review Round 1 extractions and ask:
- What patterns emerged across learnings?
- What assumptions did we make?
- What's missing from initial extraction?

### Round 3: Deep Reflection

Review Rounds 1-2 and ask:
- What systemic issues underlie specific failures?
- What blind spots remain?
- What would help bootstrap an amnesiac agent?

### Termination Condition

Stop when extraction round produces:
- Zero novel insights
- Only restatements of existing learnings
- Diminishing returns (<20% new content)

## Example: Session 04

**Round 1 (Initial)**:
- skill-ci-001: Fail fast on infrastructure failures
- skill-ci-002: Explicit retry timing
- skill-ci-003: Job status vs verdict distinction

**Round 2 (Requested by User)**:
- skill-analysis-003: Related issue discovery
- skill-git-002: Branch recovery procedure
- skill-github-001: Bidirectional issue linking
- skill-orchestration-003: Orchestrator-first routing
- skill-retrospective-001: This very skill (recursive extraction)

**Round 3 (Would Extract)**:
- Check: Any patterns across Round 2 skills?
- Check: Missing perspectives (security, performance)?
- Likely: No novel insights beyond Round 2

## Why Recursive

**Single-Pass Problem**:
- Fresh from work → focus on immediate issues
- Miss meta-patterns (how we learned)
- Skip process improvements
- Overlook blind spots

**Recursive Benefit**:
- First pass: Tactical learnings
- Second pass: Process patterns
- Third pass: Systemic improvements
- Ensures comprehensive capture

## When to Apply

AFTER:
- Main work completed
- Initial retrospective written
- Skills extracted from obvious learnings

BEFORE:
- Claiming session complete
- Final commit
- Handoff to next session

## Questions for Each Round

### Round 1: Tactical
- What broke?
- What worked?
- What shortcuts matter?

### Round 2: Process
- How did we discover the fix?
- What could have prevented the issue?
- What patterns repeat?

### Round 3: Systemic
- What organizational knowledge gaps exist?
- What would help future agents?
- What assumptions need validation?

## Success Criteria

- Each round produces <50% novel content vs prior round
- Final round yields <10% novel insights
- All skill categories represented (analysis, implementation, process, etc.)
- Meta-learnings captured (how to learn, not just what learned)

## Related Skills

- skill-analysis-001-comprehensive-analysis-standard: Thoroughness in analysis
- skill-memory-001-feedback-retrieval: Retrieve prior learnings
- retrospective-2025-12-18: Retrospective patterns

## Anti-Pattern

**DON'T** stop after first retrospective pass:
```text
Initial Pass:
- Fixed bug X
- Skill: Always check Y
[DONE - claimed completion]

Missed:
- How we discovered bug X (process)
- Why bug X existed (systemic)
- What prevents similar bugs (meta)
```

**DO** extract recursively:
```text
Round 1: Bug fix learnings
Round 2: Discovery process learnings
Round 3: Systemic gap learnings
[DONE when Round 3 yields <10% new insights]
```

## Implementation

```python
# After main work
Task(subagent_type="retrospective", 
     prompt="Extract learnings from session")

# Review extraction
skill_count_r1 = count_new_skills()

# Round 2
Task(subagent_type="retrospective",
     prompt="Meta-analysis: What patterns emerged? What's missing?")

skill_count_r2 = count_new_skills()
novelty_ratio = (skill_count_r2 - skill_count_r1) / skill_count_r1

if novelty_ratio > 0.2:
    # Round 3 justified
    Task(subagent_type="retrospective",
         prompt="Deep reflection: Systemic issues, blind spots, amnesiac bootstrap")
```

## Related

- [retrospective-001-pr-learning-extraction](retrospective-001-pr-learning-extraction.md)
- [retrospective-002-retrospective-to-skill-pipeline](retrospective-002-retrospective-to-skill-pipeline.md)
- [retrospective-003-token-impact-documentation](retrospective-003-token-impact-documentation.md)
- [retrospective-004-evidence-based-validation](retrospective-004-evidence-based-validation.md)
- [retrospective-005-atomic-skill-decomposition](retrospective-005-atomic-skill-decomposition.md)
