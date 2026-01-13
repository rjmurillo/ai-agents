# Law of Demeter (Principle of Least Knowledge)

**Created**: 2026-01-10
**Category**: Mental Models / Coupling

## The Law

"Only talk to your immediate friends." A method should only invoke methods of:

1. Its own class
2. Objects passed as parameters
3. Objects it creates
4. Its direct component objects

**Attribution**: Ian Holland, Northeastern University, 1987

## Core Insight

Reduce coupling by limiting knowledge between components. The fewer objects a class knows about, the fewer ripple effects from changes.

## Violation Example

```csharp
// BAD: Train wreck, reaching through collaborators
var modifier = character.Stats.Strength.Modifier.Value;

// GOOD: Tell, don't ask
var modifier = character.GetStrengthModifier();
```

## Application to This Project

**In PowerShell scripts**:

```powershell
# BAD: Reaching into nested properties
$reviewerName = $pr.reviews[0].user.login

# GOOD: Encapsulate access
$reviewerName = Get-PrimaryReviewerName -PR $pr
```

**In agent interactions**:

- Agents should not reach into another agent's internal state
- Use explicit handoff protocols, not direct memory access
- Encapsulate complex queries in skills

## Warning Signs

- Long property chains (a.b.c.d)
- Feature envy (method more interested in another class's data)
- Inappropriate intimacy (classes knowing internal structure)

## Benefits

- Reduced coupling
- Easier refactoring (internal changes don't propagate)
- Better testability (fewer dependencies to mock)

## Related

- [foundational-knowledge-index](foundational-knowledge-index.md): Overview
- [coupling-types-intentional-coupling](coupling-types-intentional-coupling.md): Coupling decisions
- `.agents/analysis/foundational-engineering-knowledge.md`: Full context
