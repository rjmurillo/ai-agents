# Second-Order Thinking

**Created**: 2026-01-10
**Category**: Mental Models / Decision Making

## The Principle

Think beyond immediate outcomes. First-order thinking solves immediate problems. Second-order thinking asks "And then what?"

**Attribution**: Howard Marks, "The Most Important Thing" (2011)

## Framework

| Order | Question |
|-------|----------|
| First | What happens immediately? |
| Second | What happens as people adapt? |
| Third | What happens as patterns form? |

## Time-Based Analysis

| Horizon | Consider |
|---------|----------|
| 10 minutes | Immediate effect |
| 10 days | Adaptation effects |
| 10 months | Systemic effects |

## Application to This Project

**Before implementing features**:

1. What's the immediate benefit?
2. How will users adapt their behavior?
3. What maintenance burden does this create?
4. What precedent does this set?

**Before changing protocols**:

1. What breaks immediately?
2. How will agents adapt?
3. What patterns will emerge?

## Practical Technique

Create a consequence map:

```text
Decision: [description]
├── 1st Order: [immediate effect]
│   ├── 2nd Order: [adaptation]
│   │   └── 3rd Order: [pattern]
│   └── 2nd Order: [side effect]
│       └── 3rd Order: [consequence]
```

## Common Violations

- Optimizing for today's deadline at tomorrow's expense
- Adding features without considering maintenance cost
- Fixing symptoms rather than root causes

## Related

- [foundational-knowledge-index](foundational-knowledge-index.md): Overview
- [analysis-002-rca-before-implementation](analysis-002-rca-before-implementation.md): Root cause before fixing
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
