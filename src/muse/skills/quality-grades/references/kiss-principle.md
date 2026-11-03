---
source: wiki/concepts/Design Principles/KISS Principle.md
created: 2026-04-11
review-by: 2026-07-11
---

# KISS Principle

> "Keep It Simple, Stupid" -- Most systems work best if kept simple rather than made complicated.

**Origin**: U.S. Navy, 1960s (Kelly Johnson, Lockheed Skunk Works)

## Why Complexity Is Dangerous

| Problem | Consequence |
|---------|-------------|
| Harder to understand | Longer onboarding, more misunderstandings |
| Harder to debug | More time finding bugs than fixing them |
| Harder to change | Fear of unintended consequences |
| Harder to test | More edge cases, more test code |

## Principles of Simplicity

**Solve the problem at hand.** Do not solve problems you do not have yet.

**Prefer clarity over cleverness.** Explicit code beats compact code.

**Minimize moving parts.** Fewer classes, methods, and dependencies mean fewer things that can break.

**Use standard patterns.** Do not invent patterns when standard ones exist.

## KISS in Practice

| Area | Simple | Complex |
|------|--------|---------|
| Architecture | Monolith that meets needs | Microservices for a small team |
| Data access | Direct SQL/ORM | Multiple abstraction layers |
| Error handling | Exceptions with context | Custom error frameworks |
| Configuration | Environment variables | Dynamic config with hot-reload |

## KISS vs YAGNI

| Principle | Focus |
|-----------|-------|
| KISS | How you build it (simplicity of implementation) |
| YAGNI | What you build (scope of features) |

Both push toward less code, but from different angles.

## When Complexity Is Justified

- Requirements demand it (regulatory, scale)
- Proven need (you hit limits of the simple solution)
- Clear ROI (complexity pays for itself in measurable ways)

## Grading Application

When grading domain quality, KISS violations appear as:

- Unnecessary abstraction layers (over-engineering)
- Custom frameworks replacing standard library usage
- Configuration complexity exceeding actual requirements
- Test complexity disproportionate to feature complexity
