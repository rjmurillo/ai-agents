---
source: /home/richard/Documents/Mobile/wiki/concepts/Design Principles/DRY Principle.md
created: 2026-04-11
review-by: 2026-07-11
---

# DRY Principle

Every piece of knowledge must have a single, unambiguous, authoritative representation within the system. Attribution: Andy Hunt and Dave Thomas, The Pragmatic Programmer (1999).

## Scope of Redundancy

Redundancy is not just duplicated code. It includes:

- **State**: Same data stored in multiple places
- **Functions**: Same logic implemented multiple times
- **Relationships**: Same object references duplicated
- **Design**: Same patterns re-implemented
- **Construction**: Same object creation duplicated

## Why It Matters

When DRY is applied: modifications to a single element do not require changes to unrelated elements, bugs are fixed in one place, and changes are isolated and predictable.

## Common Violations

| Type | Example |
|------|---------|
| Magic numbers | `if (status == 3)` repeated throughout |
| Magic strings | `"production"` literal in multiple files |
| Configuration | Connection strings in multiple places |
| Object construction | `new Connection(url, port)` repeated |
| Validation logic | Same rules in UI and backend |

## How to Apply

**Extract constants**: Replace magic values with named constants.

```csharp
private const int CompletedStatus = 3;
if (status == CompletedStatus) { ... }
```

**Extract methods**: Replace repeated construction or logic with a single method.

```csharp
var connection = CreateConnection(config);
```

**Extract classes**: When logic is duplicated across classes, use inheritance (if variations of a common concept) or delegation (if shared need resolved in a common way).

## DRY vs Other Qualities

| Relationship | Impact |
|--------------|--------|
| DRY and Encapsulation | Hidden things cannot be shared; shared things cannot be completely hidden |
| DRY and Coupling | Eliminating redundancy may introduce intentional coupling, a good trade-off |
| DRY and Cohesion | DRY often improves cohesion by extracting focused responsibilities |

## When NOT to DRY

- **Accidental duplication**: Code looks similar but serves different purposes
- **Different rates of change**: Code that changes for different reasons should remain separate
- **Premature abstraction**: Wait until you see the pattern three times (Rule of Three)
