---
source: wiki/concepts/Design Principles/Code Qualities.md
created: 2026-04-11
review-by: 2026-07-11
---

# Code Qualities

Five foundational qualities that make code maintainable, debuggable, and adaptable.

## The Five Qualities

| Quality | Definition | Diagnostic Question |
|---------|------------|---------------------|
| Cohesion | How closely operations in a routine/class are related | Does this class have a single responsibility? |
| Coupling | Strength of connection between routines/classes | Is this coupling intentional or accidental? |
| Non-Redundancy | DRY: single authoritative representation | Does this knowledge exist in exactly one place? |
| Encapsulation | Bundling data with methods, restricting access | Am I hiding by policy and revealing by need? |
| Testability | Ability to verify behavior in isolation | How would I test this? |

## Cohesion

Class cohesion: single responsibility via Commonality Variability Analysis.
Method cohesion: single function via Programming by Intention.

Programming by Intention uses "sergeant" methods that direct workflow of private methods. Benefits: method cohesion, separation of concerns, clarity through naming.

## Coupling Types

| Type | Description |
|------|-------------|
| Identity | Coupled to another type's existence |
| Representation | Coupled to another type's interface |
| Inheritance | Subtypes coupled to superclass changes |
| Subclass | Coupled to specific implementations |

Goal: intentional coupling (documented, necessary) over accidental coupling (unplanned side effects).

## Encapsulation Types

| Type | What Is Hidden |
|------|---------------|
| Data | Data needed for responsibilities |
| Implementation | How a class implements functions |
| Type | Abstract types hide implementing classes |
| Design | Simple and collaborating objects appear the same |
| Construction | How objects are built |

Principle: **Encapsulate by policy, reveal by need.** What you hide, you can change.

## Testability as Diagnostic

| Complaint | Root Cause |
|-----------|------------|
| "Cannot test without instantiating half the system" | Excessive coupling |
| "This class does so many things, test will be enormous" | Weak cohesion |
| "I'll have to test this in multiple places" | Redundancy |

Even without writing tests, ask: "How would I test this?"

## Qualities Enable Change

| Quality | Benefit |
|---------|---------|
| Strong Cohesion | Focused entities; finding bugs is easier |
| Intentional Coupling | No unexpected side effects |
| No Redundancy | Deal with each bug/change once |
| Encapsulation | What you hide you can change freely |
