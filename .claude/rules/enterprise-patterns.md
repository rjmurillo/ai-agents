---
description: Enterprise application architecture patterns from Fowler's PEAA. Apply when designing or changing persistence boundaries, transactional scope, or use-case orchestration. Reinforce existing repositories rather than introduce competing abstractions.
alwaysApply: false
---

# Enterprise Patterns

This rule consolidates the patterns from Martin Fowler's _Patterns of Enterprise Application Architecture_ (PEAA) that recur in this codebase. Use it when you change persistence, transactional, or orchestration code, or when you introduce a new component that touches a data store, an external service, or a long-running workspace.

The codebase already uses several of these patterns implicitly. Make them explicit in new code rather than create competing shapes (for example, a second class that loads the same entity through a different path). When in doubt, find the existing collaborator and extend it.

## Core Vocabulary

Use these terms consistently in code, comments, and PR descriptions. Mixing terms across the team makes the design harder to reason about.

- **Domain object**: an in-memory object that represents a business concept (Order, Session, Agent). It owns business behavior, not persistence concerns.
- **Repository**: a collection-like interface that hides the data store. Returns domain objects, accepts domain objects.
- **Unit of Work**: an object that tracks the changes you intend to commit, then writes them as a single transaction.
- **Data Mapper**: the object that knows how to translate between a domain object and a persistence row, message, or document.
- **Identity Map**: a per-unit-of-work cache keyed by identity, ensuring you load each entity at most once.
- **Service Layer**: the use-case boundary. Orchestrates repositories, domain logic, and external collaborators on behalf of a single request or task.

## Repository

Use a Repository when callers should interact with a collection of domain objects without knowing how those objects are stored.

Apply when:

- More than one caller needs the same query.
- The query has a meaningful name in the domain (`findActiveSessionsForAgent`, not `select * from session where ...`).
- You want to swap the backing store (in-memory for tests, durable for production) without changing callers.

Rules:

- Repositories return and accept domain objects. They do not leak rows, ORM entities, or query builders.
- Methods read like collection operations: `add`, `remove`, `find...`, `exists`. Do not name them after SQL verbs.
- Each domain aggregate has at most one repository. If you find yourself writing a second repository for the same aggregate, you are usually missing a query method on the first one.
- Repositories do not commit. Commits belong to the Unit of Work or the calling Service Layer.
- Filtering and projection live behind named methods. Avoid passing predicates or query objects across the boundary unless you have a Specification pattern in place and the caller actually composes them.

Smell: a repository with `getDb()`, `getSession()`, or `executeRaw()` is leaking. Move the call inside a named method.

## Unit of Work

Use a Unit of Work to make a set of related changes atomic, ordered, and observable as one operation.

Apply when:

- A single use case touches multiple aggregates and partial writes would corrupt state.
- You need ordering guarantees (insert parent before children, delete children before parent).
- You need a durable audit of what changed in a request.

Rules:

- Open one Unit of Work per use case. Do not nest them. Pass the Unit of Work down through the Service Layer; do not let it become an ambient global.
- Track three sets explicitly: new, dirty, and removed. Resolve order at commit time so callers do not have to think about it.
- Commit at the boundary of the use case, not inside repositories or domain methods.
- On failure, roll back and surface the failure. Never partially commit. Never swallow the error and continue.
- A Unit of Work is short-lived. If yours spans HTTP requests, agent turns, or user interactions, you are using it for caching; use an Identity Map for that instead.

Smell: every method takes a `transaction` parameter "just in case." Lift the transaction to the Service Layer and pass the Unit of Work, not raw transaction handles.

## Data Mapper

Use a Data Mapper to keep domain objects free of persistence concerns.

Apply when:

- The persistence shape differs from the domain shape (relational schema, message envelope, file-on-disk format).
- You want to evolve the schema independently of the domain model.
- Multiple stores hold the same logical entity (cache plus database; primary plus replica with a different shape).

Rules:

- Domain objects do not know how they are saved. They have no `save()` method, no `__tablename__`, no decorators tying them to a store.
- The Data Mapper is the only code that reads or writes the persistence shape. Keep it boring and testable in isolation.
- Translation is symmetric: `toRecord(domain)` and `toDomain(record)`. Round-trip the same object through both halves and assert equality.
- Field-level mapping is explicit. Reflection or generic copying hides bugs and breaks under schema evolution.
- Validation belongs in the domain. The mapper assumes its input is already valid on the way out and untrusted on the way in.

Active Record (the domain object knows its own persistence) is acceptable for small, stable schemas. Switch to Data Mapper as soon as you need to vary either side independently.

## Service Layer

Use a Service Layer to express each use case as a single, named operation.

Apply when:

- A request requires more than one repository or external call.
- You need a clear seam for transactions, authorization, telemetry, or retries.
- Multiple entry points (CLI, API, agent orchestrator) need to invoke the same business operation without duplicating logic.

Rules:

- Each method on the Service Layer represents one use case (`approveOrder`, `enqueueAgentRun`, `closeSession`). Name them after what the user or system asked for.
- The Service Layer orchestrates: it loads aggregates through repositories, calls domain methods, and commits a Unit of Work. It does not contain business rules.
- Cross-cutting concerns attach here, not inside domain objects: transactions, authorization checks, idempotency keys, structured logging, metric emission, retry policies.
- Services depend on abstractions. Inject repositories and external clients; do not new them up inline.
- A Service method should be short. If it grows past a screen, the use case is doing too much; split it into a domain method or a smaller service.

In ai-agents, the agent orchestrator is the canonical Service Layer. New use cases that coordinate repositories, sessions, or external tools belong there or in a sibling service, not scattered across hooks and skills.

## Identity Map

Use an Identity Map to load each entity at most once per unit of work.

Apply when:

- A single use case may dereference the same entity through multiple paths and you want object identity, not value equality.
- You need to avoid duplicate database hits for the same key.
- You need a single point at which an entity exists, so two callers that mutate it see each other's changes.

Rules:

- The Identity Map is per-Unit-of-Work, never global. Sharing it across requests turns it into a stale cache.
- Key on the natural identity of the aggregate (`SessionId`, `AgentId`), not on object hash.
- Repositories consult the Identity Map before issuing a load. On miss, they load and register the entity. On hit, they return the existing instance.
- Removal is explicit. When the Unit of Work deletes an entity, evict it from the map.
- Do not use the Identity Map as application-level cache. It exists to preserve identity for one operation, not to speed up reads across operations.

Smell: an entity has stale fields and "the second load fixed it." You loaded twice; the second load shadowed the first. Add the Identity Map and reload nothing.

## Pattern Selection

Pick patterns by the problem in front of you, not by the diagram in a book.

- One aggregate, one store, simple schema: Active Record may be enough. Skip the mapper and the Identity Map.
- Multiple aggregates per use case, transactional integrity required: Repository plus Unit of Work plus Service Layer.
- Schema must evolve independently of the domain: add a Data Mapper.
- Same entity reachable through multiple paths in one operation: add an Identity Map.
- Use case orchestration crossing several entry points: lift logic into the Service Layer first, then look at finer-grained patterns.

If you cannot name the pattern you are using, you do not have one yet. Add the structure or accept that you are writing a transaction script and keep it short.

## Anti-Patterns

These shapes appear in greenfield code more often than they should. Reject them in review.

- **Anemic Domain Model with thick services**: domain objects are bags of getters and setters; all behavior sits in services. Move behavior back onto the domain object that owns the data.
- **Smart UI / Smart Skill**: business logic embedded in the entry point (HTTP handler, agent skill, CLI command). Promote it to the Service Layer.
- **Repository as DAO**: methods named `executeQuery`, `runUpdate`, or `getConnection`. Replace with named, intention-revealing operations.
- **Ambient transactions**: a global or thread-local `currentTransaction()` that any code may read or write. Pass the Unit of Work explicitly.
- **Cross-aggregate transactions stretched across services**: do not paper over a missing aggregate boundary with a longer transaction. Redraw the boundary.
- **Pattern stacking**: every read goes through five layers because "the patterns say so." If a layer never varies and never gets tested in isolation, delete it.

## Boundaries with Existing Codebase

ai-agents already has implicit versions of these patterns. Reuse, do not duplicate.

- Sessions and the session log live behind a session-management seam. Treat that seam as the Repository for session state and the Service Layer for session lifecycle.
- The orchestrator is the Service Layer for agent runs. New use cases that need a transactional or retryable boundary go here, not into a hook or skill.
- Skills and hooks are entry points. Keep them thin: parse inputs, call a service, format output. They are not the place for business rules.
- Memory systems (Serena, Forgetful) act as Repositories of long-lived knowledge. Do not bypass them with direct file reads when the named operation already exists.

When you find a place where the codebase deviates from this rule, prefer a small focused refactor on the path you are already touching over a large rewrite. Note the deviation in the PR description so future readers see your reasoning.

## Quick Self-Review

Before opening a PR that touches persistence, transactions, or orchestration, walk this list.

- Does the code touch a data store directly, or through a repository?
- If it changes more than one aggregate, is there exactly one Unit of Work that commits the whole change?
- Do domain objects depend on persistence types, or only on other domain types?
- Is the use case named, single-purpose, and visible at the Service Layer?
- Could the same entity be loaded twice in this operation? If yes, is the Identity Map handling that?
- Did you add a new repository, mapper, or service when an existing one would have done?
- Are entry points (skills, hooks, handlers) thin?

If any answer is "no" or "not sure," fix the design before review.
