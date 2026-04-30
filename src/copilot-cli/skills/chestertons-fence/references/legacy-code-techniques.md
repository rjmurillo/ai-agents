---
source: wiki/concepts/Design Principles/Working with Legacy Code.md
created: 2026-04-11
review-by: 2026-07-11
---

# Working with Legacy Code

Most engineering work involves changing existing code, not writing new. The key insight: most problems come from the *design*, not the code itself. Focus on what makes defects discoverable and change integrable.

## Refactoring Definition

> "A behavior-preserving transformation ... a change made to the internal structure of software to make it easier to understand and cheaper to modify without changing its observable behavior."
> -- Joshua Kerievsky, *Refactoring to Patterns*

The process: remove duplication, simplify complex logic, clarify unclear code.

## Bottom-Up Approach

Start at the bottom of the Software Hierarchy of Needs and work up:

1. **Testability** -- reveals flaws in the design
2. **Cohesion** -- programming by intention + interface segregation
3. **Coupling** -- strength of connection between items
4. **Redundancy** -- DRY: single authoritative representation
5. **Encapsulation** -- hidden things cannot be coupled to

Then: refactor to open-closed. Work up to principles and practices.

## Assertive vs Inquisitive Relationships

Prefer assertive over inquisitive relationships. Each object is an actor carrying out a task. Keep behavior with the data.

## Inheritance vs Composition

| Approach | Relationship | Risk |
|----------|-------------|------|
| Inheritance (IS-A) | Class inheritance | Creates coupling problems |
| Composition (HAS-A) | Instance variables | Greater flexibility |

Key wisdom (GoF): Favor delegation over class inheritance to specialize.

## Application to Investigation

When investigating legacy code with Chesterton's Fence:

1. Assess current design quality using the five qualities above
2. Determine if the "fence" exists due to design constraints or intentional choice
3. Recommend MODIFY when purpose is valid but implementation needs the bottom-up treatment
4. Recommend PRESERVE when refactoring risk exceeds benefit

## Recommended Reading

- Feathers, *Working Effectively with Legacy Code* (2004)
- Martin, *Clean Code* (2008)
- Fowler, *Refactoring* (2nd Ed, 2018)
- Kerievsky, *Refactoring to Patterns* (2004)
