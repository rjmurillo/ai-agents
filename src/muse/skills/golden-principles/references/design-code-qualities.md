---
source: wiki/concepts/Design Principles/Code Qualities.md
created: 2026-04-11
review-by: 2026-07-11
---

# Code Qualities

Five foundational qualities that make code maintainable, debuggable, and adaptable. Focus on defect discoverability and ease of integrating change.

## The Five Qualities

| Quality | Definition | Benefit |
|---------|------------|---------|
| Cohesion | How closely operations in a routine/class are related | Focused entities; finding bugs is easier |
| Coupling | Strength of connection between routines/classes | No unexpected side effects; logical flow |
| Non-Redundancy | Single authoritative representation (DRY) | Fix bugs once; look fewer places |
| Encapsulation | Bundling data with methods, restricting access | Hidden things change freely; fewer side effects |
| Testability | Ability to verify behavior in isolation | Reveals design problems early |

## Cohesion

Strong cohesion means a class has a single responsibility and each method has a single function.

Achieve class cohesion through Commonality Variability Analysis. Achieve method cohesion through Programming by Intention: "sergeant" methods direct workflow via well-named private methods.

## Coupling

| Type | Description |
|------|-------------|
| Identity | Coupled to another type's existence |
| Representation | Coupled to another's interface (method signatures) |
| Inheritance | Subtypes coupled to superclass changes |
| Subclass | Coupled to specific implementations |

Goal: intentional coupling (documented, necessary) over accidental coupling (unplanned side effects).

## Non-Redundancy

Redundancy includes state, functions, relationships, designs, object construction, magic numbers/strings, and configuration. When DRY is applied, modifying one element does not require changes to logically unrelated elements.

## Encapsulation

Five types: data, implementation, type, design, construction.

Principle: **Encapsulate by policy, reveal by need.** What you hide, you can change. It is easier to break encapsulation later than to add it.

Key relationships:

- Encapsulation + Coupling: hidden things cannot be directly coupled to
- Encapsulation + Cohesion: cohesive concerns are easier to hide
- Encapsulation + Redundancy: hidden things cannot be shared; shared things cannot be completely hidden

## Testability as Diagnostic

| Testing Complaint | Root Cause |
|-------------------|------------|
| "Cannot test without half the system" | Excessive coupling |
| "Class does so many things" | Weak cohesion |
| "Must test in multiple places" | Redundancy |

Even without writing tests, ask: "How would I test this?" The thought process provides leverage over code quality whether tested or not.

## References

- McConnell, 1993. Code Complete
- Hunt and Thomas, 1999. The Pragmatic Programmer
- Hevery, 2008. Writing Testable Code (Google Testing Blog)
