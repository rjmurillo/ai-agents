---
description: Unified software engineering rules synthesized from classic engineering literature. Apply when principles appear to conflict, when scoping work, or when judging whether a pattern in a diff should be allowed. Use as the default tiebreaker, not as an additional layer on top of every specialized rule.
applyTo: '**/*.py,**/*.cs,**/*.ts,**/*.tsx,**/*.js,**/*.jsx,**/*.go,**/*.rs,**/*.java,**/*.rb,**/*.c,**/*.h,**/*.cpp,**/*.ps1,**/*.psm1,**/*.psd1,**/*.sh,**/*.sql'
---

# Unified Software Engineering

This rule resolves conflicts between engineering principles that models already know (Clean Code, DDD, Refactoring, Pragmatic Programmer, Code Complete) so that contradictions do not produce inconsistent agent behavior. Use it as a tiebreaker when reviewing or generating code.

Cherry-picked from [agent-rules-books](https://github.com/ciembor/agent-rules-books) (MIT). The full upstream document is intentionally not imported. Adding the entire 46KB rule set duplicates content already known to the model and degrades response quality.

## Primary Directive

When uncertain, choose the option that makes the system easier to understand, safer to change, and more honest about its real constraints.

## Conflict Resolution Rules

Apply these rules when engineering principles appear to disagree.

### Simplicity vs Rich Modeling

- Use the simplest design that honestly represents the problem.
- Simple CRUD or administrative workflows may use transaction scripts or simple service-layer code.
- Complex business rules, lifecycles, invariants, and language distinctions require richer domain modeling.
- Do not use DDD patterns as ceremony in generic or low-complexity subdomains.
- Do not flatten real domain complexity into passive records and procedural services.

### Small Functions vs Deep Modules

- Functions and routines should be cohesive and understandable.
- Prefer small units when they clarify intent, isolate responsibility, or simplify testing.
- Avoid chains of tiny pass-through functions that force readers to jump constantly.
- A module may contain internal complexity when its public interface is small, meaningful, and stable.

### DRY vs Premature Abstraction

- Remove duplicated knowledge, not merely duplicated text.
- Centralize business rules, validation semantics, mappings, status meanings, and calculations.
- Keep similar code separate when the similarity is coincidental or the shared abstraction would be vague.

### Boundaries vs Overengineering

- Introduce explicit boundaries around volatility, external systems, persistence, frameworks, time, randomness, and cross-context translation.
- Do not add layers that only forward calls.
- Every abstraction must reduce coupling, hide complexity, clarify ownership, or protect a contract.

### Strong Consistency vs Eventual Consistency

- Protect invariants that must hold immediately inside the smallest useful consistency boundary.
- Prefer one aggregate or one local transaction as the default atomic unit.
- Use eventual consistency across aggregates, services, or contexts when immediate consistency is not a real product requirement.
- Always make consistency, staleness, conflict, and retry semantics explicit.

### Comments vs Self-Documenting Code

- Improve names and structure before adding comments.
- Use comments for contracts, invariants, rationale, non-obvious constraints, legal requirements, and external protocol assumptions.
- Delete comments that narrate obvious code, repeat names, or describe obsolete behavior.

### Refactor vs Preserve Behavior

- Refactoring must preserve observable behavior.
- If behavior must change, keep the behavior change distinct from structural cleanup where practical.
- Use small, verified transformations instead of big-bang rewrites.

Do not generate forbidden patterns (see `references/forbidden-patterns.md` in the `software-engineering-library` skill) unless explicitly required and justified in the PR description. The highest-risk ones stay named here: outbound calls with no explicit timeout, retries nested at multiple layers or applied to non-idempotent or permanent failures, and unbounded queues, buffers, or pools. When you encounter them in code you are not actively touching, leave them alone unless removing them is part of the task; track separately rather than expand scope.

## Relationship to Other Rules

- This rule is the default. Pragmatic Programmer's depth and the forbidden-patterns blocklist now live in the `software-engineering-library` skill and extend it for narrower contexts.
- Concurrency edits invoke testing MUST 12-13.
- When a specialized rule and this one disagree, the specialized rule wins inside its scope. Outside that scope, this rule applies.
- Do not load multiple book-specific rule sets together with this one when one rule alone is enough. Duplicated or overlapping instructions reduce model reliability.
