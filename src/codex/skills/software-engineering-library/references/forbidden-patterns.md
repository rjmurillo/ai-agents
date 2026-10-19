# Forbidden Patterns

This is the review blocklist that pairs with the always-on `unified-software-engineering` rule's tiebreaker. That rule stays always-on for code files and states the primary directive and conflict-resolution rules; this reference holds the concrete list of patterns it points to, moved out of the always-on path so a routine code edit does not pay for the whole catalog (issue #5951). Open it when reviewing a diff or generating code against the design, architecture, data-and-production, or change-and-legacy blocklist below.

Do not generate these patterns unless explicitly required and justified in the PR description. When you encounter these patterns in code you are not actively touching, leave them alone unless removing them is part of the task; track separately rather than expand scope.

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

## Complexity and Design

- clever code that is hard to inspect
- shallow pass-through layers
- wrappers that add names but no simplification
- one more flag, callback, or conditional instead of a better abstraction
- speculative frameworks, interfaces, or hierarchies before a real need exists
- generic `utils`, `helpers`, `common`, or `shared` packages as design escape hatches
- god classes and god services
- duplicated business rules across UI, API, services, database, and jobs

## Architecture and Domain

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

## Data and Production

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

## Change and Legacy

- big-bang rewrites before understanding current behavior
- behavior changes hidden inside refactors
- broad edits in poorly tested legacy modules without characterization or seams
- cosmetic refactoring that leaves hard dependencies untouched
- deleting failing tests to make a refactor pass
- manual release or validation rituals that should be automated
