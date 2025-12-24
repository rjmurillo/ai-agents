# Skill-Analysis-001: Comprehensive Analysis Standard

## Statement

Analysis documents containing options analysis, trade-off tables, and evidence enable 100% implementation accuracy

## Context

Before implementation tasks requiring design decisions

## Evidence

Session 19 (2025-12-18): Analysis 002 (857 lines, 5 options) → 100% match to spec
Session 20 (2025-12-18): Analysis 003 (987 lines) → 100% match to spec
Session 21 (2025-12-18): Analysis 004 (1347 lines, 3 options) → 100% match to spec

## Metrics

- Atomicity: 95%
- Impact: 10/10
- Category: analysis, planning, quality
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Orchestration-001 (Parallel Execution Time Savings)
- Skill-Testing-002 (Test-First Development)

## Comprehensive Analysis Structure

### 1. Options Analysis (3-5 alternatives)

**Template**:

```markdown
## Option 1: [Name]

**Description**: [What this option does]

**Pros**:
- [Advantage 1]
- [Advantage 2]

**Cons**:
- [Disadvantage 1]
- [Disadvantage 2]

**Effort**: [Low/Medium/High]

**Risk**: [Low/Medium/High]
```

### 2. Trade-Off Tables

**Template**:

```markdown
| Option | Complexity | Maintainability | Scalability | Effort | Recommendation |
|--------|------------|-----------------|-------------|--------|----------------|
| Option 1 | Low | High | Medium | Low | Recommended |
| Option 2 | High | Low | High | High | Consider |
| Option 3 | Medium | Medium | Low | Medium | Avoid |
```

### 3. Evidence (Verified Facts)

**Template**:

```markdown
## Evidence

### Current State
- [Verifiable fact 1: checked via grep, git log, etc.]
- [Verifiable fact 2: observed behavior]

### Constraints
- [Constraint 1: from ADR, memory, protocol]
- [Constraint 2: technical limitation]

### Historical Context
- [Relevant past decision]
- [Similar approach tried before]
```

### 4. Recommendation with Rationale

**Template**:

```markdown
## Recommendation

**Recommended Option**: Option 1

**Rationale**:
1. [Primary reason with evidence]
2. [Secondary reason with evidence]
3. [Addresses constraint X]

**Implementation Guidance**:
- [Step 1]
- [Step 2]
- [Success criteria]
```

## Quality Thresholds

| Threshold | Metric | Target | Evidence |
|-----------|--------|--------|----------|
| Comprehensive | Line count | 500+ lines | Analysis 002-004 averaged 1064 lines |
| Options | Count | 3-5 options | All three analyses had 3-5 options |
| Trade-offs | Tables | 1+ table | All analyses included trade-off tables |
| Evidence | Citations | 5+ facts | All analyses cited ADRs, memories, protocols |

## Anti-Pattern: Shallow Analysis

**Insufficient**:

```markdown
We should create PROJECT-CONSTRAINTS.md because it's needed.

Implementation: Create file with constraints.
```

**Why it fails**: No options considered, no trade-offs analyzed, no evidence

## Success Criteria

- Analysis contains 3-5 options with pros/cons
- Trade-off table compares options quantitatively
- Evidence section cites 5+ verifiable facts
- Recommendation includes rationale with evidence
- Implementation accuracy: 100% match to spec
