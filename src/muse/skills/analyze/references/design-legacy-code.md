---
source: wiki/concepts/Design Principles/Working with Legacy Code.md
created: 2026-04-11
review-by: 2026-07-11
---

# Working with Legacy Code

Most engineering work changes existing code, not writes new. Most problems come from design, not code. Time goes to finding bugs, not fixing them. Focus on what makes defects discoverable and change integrable.

## Refactoring

A behavior-preserving transformation that makes code easier to understand and cheaper to modify. Process: remove duplication, simplify complex logic, clarify unclear code.

## Bottom-Up Approach

Start at the bottom of the Software Hierarchy of Needs and work up:

| Level | Quality | What It Reveals |
|-------|---------|-----------------|
| 1 | Testability | Flaws in the design |
| 2 | Cohesion | Programming by intention, interface segregation |
| 3 | Coupling | Strength of connection between items |
| 4 | Redundancy | DRY: single authoritative representation |
| 5 | Encapsulation | Hidden things cannot be coupled to |

Then: refactor to open-closed, work up to principles and practices.

## Assertive vs Inquisitive Relationships

Prefer assertive over inquisitive. Assertive systems put responsibilities in the right places so each object is an actor carrying out a task. Keep behavior with the data.

## Inheritance vs Composition

| Approach | Relationship | Risk |
|----------|-------------|------|
| Inheritance (IS-A) | Class or interface inheritance | Creates coupling problems |
| Composition (HAS-A) | Instance variables referencing another object | Greater flexibility |

GoF wisdom: Favor delegation over class inheritance to specialize.

## Applying During Analysis

When analyzing legacy code, evaluate in this order:

1. **Testability**: Can the code be tested in isolation? Hard-to-test code signals design problems.
2. **Cohesion**: Does each class have a single responsibility? Do methods have a single function?
3. **Coupling**: Is coupling intentional (documented, necessary) or accidental (unplanned side effects)?
4. **Redundancy**: Is knowledge duplicated? Look for copy-paste patterns.
5. **Encapsulation**: Is state private? Are implementation details hidden?

## Key Books

- Feathers, *Working Effectively with Legacy Code* (2004)
- Fowler, *Refactoring* (2nd Ed, 2018)
- Kerievsky, *Refactoring to Patterns* (2004)
