---
description: Unified software engineering rules synthesized from classic engineering literature. Apply when principles appear to conflict, when scoping work, or when judging whether a pattern in a diff should be allowed. Use as the default tiebreaker, not as an additional layer on top of every specialized rule.
alwaysApply: false
---

# Unified Software Engineering

This rule resolves conflicts between engineering principles models already know (Clean Code, DDD, Refactoring, Pragmatic Programmer, Code Complete) so that contradictions do not produce inconsistent agent behavior. Use it as a tiebreaker and as a concrete blocklist when reviewing or generating code.

Cherry-picked from [agent-rules-books](https://github.com/ciembor/agent-rules-books) (MIT). The full upstream document is intentionally not imported. Adding the entire 46KB rule set duplicates content already known to the model and degrades response quality.

## Primary Directive

When uncertain, choose the option that makes the system easier to understand, safer to change, and more honest about its real constraints.

Prefer designs that:

1. reduce the number of facts a reader must hold at once
2. put each business rule in one authoritative place
3. keep volatile details behind stable boundaries
4. make data ownership and consistency explicit
5. survive partial failure, retries, and operational stress
6. preserve behavior during structural change
7. shorten feedback loops

Reject designs that merely appear simpler by hiding complexity in callers, frameworks, databases, global state, queues, or operational assumptions.

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

## Default Work Workflow

For every non-trivial task:

1. Understand the requested behavior and the affected area.
2. Identify the current safety net: tests, types, assertions, logs, examples, or manual checks.
3. If the area is risky or unclear, characterize current behavior before redesigning it.
4. Identify the simplest change that preserves or improves architecture.
5. Make preparatory refactors only when they make the requested change safer or clearer.
6. Implement the behavior or structural change in small reviewable steps.
7. Add or update proportionate tests and checks.
8. Review the diff for duplication, naming, boundary leaks, hidden assumptions, and operational risk.
9. Stop when the requested change is done and further cleanup would be speculative.

Do not silently broaden scope beyond the task.

## Forbidden Patterns

Do not generate or preserve these patterns unless explicitly required and justified in the PR description.

### Complexity and Design

- clever code that is hard to inspect
- shallow pass-through layers
- wrappers that add names but no simplification
- one more flag, callback, or conditional instead of a better abstraction
- speculative frameworks, interfaces, or hierarchies before a real need exists
- generic `utils`, `helpers`, `common`, or `shared` packages as design escape hatches
- god classes and god services
- duplicated business rules across UI, API, services, database, and jobs

### Architecture and Domain

- business rules in controllers, views, SQL scripts, repository implementations, or serialization code
- framework or ORM types in core domain or use-case code
- domain models shaped primarily around tables, DTOs, or REST payloads
- one global company-wide domain model
- shared domain classes across contexts by default
- anemic entities in complex domains
- aggregates sized around object graphs or screens
- direct cross-context imports of domain classes
- generic repositories that erase domain meaning
- domain events for every property change
- fake DDD that renames CRUD without changing the model
- over-modeled generic subdomains

### Data and Production

- exactly-once wishful thinking
- non-idempotent handlers under retry or redelivery
- many writable copies with no source-of-truth ownership
- stale-read or conflict behavior treated as incidental
- changing contract meanings without versioning or rollout strategy
- projections that cannot be repaired or rebuilt when they need to be
- unbounded queues, buffers, batches, or resource pools
- outbound calls with no explicit timeout
- nested retries at multiple layers
- retries on non-idempotent or permanent failures
- health checks that stay green while dependencies required for serving are broken
- caches treated as always available and always correct

### Change and Legacy

- big-bang rewrites before understanding current behavior
- behavior changes hidden inside refactors
- broad edits in poorly tested legacy modules without characterization or seams
- cosmetic refactoring that leaves hard dependencies untouched
- deleting failing tests to make a refactor pass
- manual release or validation rituals that should be automated

## Relationship to Other Rules

- This rule is the default. The book-specific rules in this directory (`enterprise-patterns.md`, future refactoring or DDD rules) extend it for narrower contexts.
- When a specialized rule and this one disagree, the specialized rule wins inside its scope. Outside that scope, this rule applies.
- Do not load multiple book-specific rule sets together with this one when one rule alone is enough. Duplicated or overlapping instructions reduce model reliability.
