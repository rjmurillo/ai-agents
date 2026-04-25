---
description: Domain-Driven Design tactical and strategic patterns from Evans and Vernon. Apply when modeling agents, skills, sessions, orchestration boundaries, or any cross-context translation. Reuse existing models and bounded contexts rather than introduce parallel ones.
alwaysApply: false
---

# Domain-Driven Design

This rule consolidates the Domain-Driven Design patterns from Eric Evans's _Domain-Driven Design_ (the "Blue Book"), Vaughn Vernon's _Domain-Driven Design Distilled_, and _Implementing Domain-Driven Design_ that recur in this codebase. Use it when you change agent definitions, session lifecycle, orchestration boundaries, memory and handoff contracts, or any place where two parts of the system speak different languages and have to translate.

The codebase already has implicit bounded contexts (the agent runtime, the session log, the memory systems, the skill catalog). When you add a new concept, find the context it belongs in and use that context's language. Do not invent a parallel model.

For persistence and transactional concerns (Repository, Unit of Work, Service Layer), see `.claude/rules/enterprise-patterns.md`. This rule covers the modeling and boundary side of the same problem space and explicitly does not duplicate those patterns.

## Core Vocabulary

Use these terms consistently in code, comments, agent prompts, and PR descriptions. Mixing terms across the team makes the design harder to reason about and is the single most reliable indicator that two people are talking about different concepts.

- **Domain**: the problem space the system addresses (orchestrating AI agents to land changes in a repository).
- **Subdomain**: a coherent slice of the domain. **Core** is what differentiates the product, **Supporting** is necessary but not differentiating, **Generic** is commodity that any team would solve the same way.
- **Bounded Context**: an explicit boundary inside which a single model is valid and a single ubiquitous language applies. The same word can mean different things in two contexts; that is normal and the boundary is what makes it safe.
- **Ubiquitous Language**: the shared vocabulary inside a bounded context. Code, tests, prompts, and conversations use the same terms with the same meaning.
- **Entity**: a domain object identified by stable identity, not by the values of its fields. Two entities with identical fields are still different if their identities differ.
- **Value Object**: an immutable domain object identified by the values of its fields. Two value objects with identical fields are interchangeable.
- **Aggregate**: a cluster of entities and value objects with one **Aggregate Root**. The aggregate is the unit of consistency and the unit of transactional change.
- **Domain Event**: a fact about something that happened in the domain, named in the past tense (`SessionEnded`, `AgentDelegated`, `HandoffWritten`).
- **Domain Service**: a stateless operation that does not naturally belong on a single entity or value object.
- **Anti-Corruption Layer (ACL)**: a translation layer at the boundary between two bounded contexts that prevents the model of one from leaking into the other.
- **Context Map**: the explicit description of how bounded contexts relate (Customer-Supplier, Conformist, Shared Kernel, Partnership, Open Host Service, Published Language).

## Bounded Context

Use a Bounded Context to draw a hard line around one model and one language.

Apply when:

- Two parts of the system use the same word for different concepts (a "session" in the agent runtime is not a "session" in the chat transcript layer).
- A model that started simple is acquiring conditional logic to handle "the case for module X" and "the case for module Y."
- You need to evolve one part of the system without coordinating every change with the rest.

Rules:

- Each bounded context has exactly one model and one ubiquitous language. If two languages must coexist, you have two contexts.
- Boundaries are explicit. Name the context, document its responsibility, and identify its inputs and outputs.
- Crossing a context boundary requires translation, not assignment. The receiving context restates the concept in its own terms.
- A change inside a context should never require a coordinated change in another context. If it does, your boundary is wrong, your context map is wrong, or both.
- Prefer fewer, larger contexts at first. Split when conditional logic and naming conflicts force the split, not before.

Smell: a single class with branches like `if (mode === "agent") { ... } else if (mode === "skill") { ... }`. The conditional is the boundary trying to surface. Extract two contexts and translate at the seam.

## Ubiquitous Language

Use the Ubiquitous Language inside a context so domain experts, code, and prompts all say the same thing.

Apply when:

- A reviewer cannot tell from the code which business concept a method serves.
- The team has parallel terms ("user", "operator", "principal") for the same thing.
- Tests describe what the code does mechanically, not what the domain expects.

Rules:

- Names in code, tests, prompts, and PR descriptions match the language used by domain experts. If the team says "delegate", the method is `delegate`, not `assignWorkItem`.
- A term means one thing in one context. Reuse without translation across contexts is a bug.
- When the language changes, code changes too. Renames are a feature, not a chore.
- Resist generic names (`Manager`, `Helper`, `Handler`, `Processor`). They drain meaning and invite a god object.
- Prompts and skill instructions are part of the language. An agent prompt that uses different terms than the code teaches the model the wrong vocabulary.

Smell: a glossary that maps three internal names to one business concept. Pick the business name and rename the others.

## Subdomain Classification

Use the Core / Supporting / Generic split to decide where to invest design effort and where to accept commodity solutions.

Apply when:

- Choosing whether to build, buy, or vendor a capability.
- Allocating review depth across a multi-PR effort.
- Deciding whether a section of the codebase deserves a rich domain model or a transaction script.

Rules:

- **Core**: the part that makes the product distinct. Invest in modeling, naming, and tests. Owners review every change with care. In ai-agents, agent orchestration and session protocol are core.
- **Supporting**: necessary but not differentiating. Invest in clarity, accept simpler models, prefer reusing established patterns. In ai-agents, the GitHub integration and PR templates are supporting.
- **Generic**: solved well by any sensible library or tool. Use the off-the-shelf solution, do not model. In ai-agents, markdown linting, JSON schema validation, and HTTP clients are generic.
- A subdomain's classification can change. When a generic capability becomes a competitive differentiator, promote it to core and rebuild the model under it.

Smell: hand-rolled retry, JSON parsing, or date arithmetic in a generic subdomain. Replace with a library; spend the saved effort on the core.

## Aggregates

Use Aggregates to define what changes together transactionally and what does not.

Apply when:

- Two entities must always agree on a state transition (a session ending implies its handoff being written).
- You need a single point at which an invariant is enforced.
- A change set risks racing with another change set on the same data.

Rules:

- One Aggregate Root per aggregate. External code refers to the root only and reaches inner entities through the root.
- The aggregate is the unit of transactional change. Commit one aggregate per transaction; if you need to change two, you need two transactions or a redesigned boundary.
- Reference other aggregates by identity, not by direct object reference. Holding a pointer across aggregate boundaries makes the boundary meaningless and invites partial loads.
- Keep aggregates small. A large aggregate locks more, loads more, and is more likely to violate invariants quietly.
- Invariants live on the root. Anything that must be true about the aggregate is enforced when the root accepts a change.
- Eventual consistency between aggregates is normal. Prefer a Domain Event from one aggregate to a handler that updates another, rather than a single transaction that spans both.

Smell: a method on a child entity that mutates a sibling under another root. Move the operation to the root or split the operation into two events.

## Entities and Value Objects

Distinguish identified things from values, then default to value objects.

Apply when:

- Modeling any domain concept. The first question is: does identity matter, or do equal values mean equal things?
- A primitive is being passed around with implicit rules (`string sessionId`, `int retryCount`, `float threshold`).
- Two fields move together everywhere they appear.

Rules:

- An Entity has identity that persists through change. Two entities with the same field values are not the same entity.
- A Value Object is immutable, compared by value, and replaced rather than mutated. `new Money(10, "USD")` is the same as any other `new Money(10, "USD")`.
- Default to value objects. Reach for entities only when identity carries meaning that survives state change.
- Wrap primitives that have rules. `AgentId`, `SessionNumber`, `Confidence` are types, not raw strings, ints, or floats. The rule lives on the type.
- Validation belongs in the constructor. A value object that exists is, by definition, valid.

Smell: a `validateSessionId(...)` helper called in five places. Promote `SessionId` to a type and put the validation in its constructor.

## Domain Events

Use Domain Events to express facts about what happened, then react to them in other aggregates or contexts.

Apply when:

- A change in one aggregate should trigger a change in another aggregate or another bounded context.
- You need an audit trail of business-meaningful changes, not just technical writes.
- A workflow spans multiple aggregates and a single transaction is the wrong shape.

Rules:

- Events are named in the past tense (`SessionEnded`, `HandoffWritten`, `AgentDelegated`). Present tense is a command, not an event.
- Events carry the data a handler needs to act, plus an identity and a timestamp. Do not pass full aggregates by reference.
- Events are immutable facts. They never get amended; if the world changes again, emit another event.
- Publish events as part of committing the aggregate, not before. An event for a change that did not commit is a lie.
- Handlers are idempotent. The same event may be delivered more than once; handlers must arrive at the same outcome regardless.

Smell: an "event" with a verb in present tense that the handler can refuse. That is a request, not an event. Model it as a command instead.

## Domain Services

Use a Domain Service when behavior is significant in the domain but does not naturally belong on a single entity or value object.

Apply when:

- An operation involves several aggregates and no single aggregate owns the operation.
- A behavior is stateless but expressed in domain terms (computing a fee schedule, picking the right agent for a task, scoring a proposal).
- Putting the operation on an entity would make that entity reach into others to do its job.

Rules:

- Domain services are stateless. They take inputs, return outputs, do not own data.
- They are named in the language of the domain (`AgentSelectionPolicy`, `SessionEligibilityCheck`), not in the language of the framework.
- A domain service is not the place to host CRUD over a repository. That belongs in a Service Layer (see `.claude/rules/enterprise-patterns.md`).
- If a domain service grows state, you have an entity in disguise. Promote it.

Smell: a service named `Manager` or `Helper` that owns no data and does five unrelated things. Split it by purpose; rename each piece in domain terms.

## Anti-Corruption Layer

Use an Anti-Corruption Layer at any boundary where the model on the other side does not match the model on this side.

Apply when:

- Integrating with an external system whose data model does not fit the domain (a legacy database, a third-party API, a generated client).
- Bridging two bounded contexts in the same codebase that have evolved separately.
- Migrating off an old model while the new model is still being shaped.

Rules:

- The ACL is the only code that knows the foreign model. The rest of the bounded context speaks in its own terms.
- Translation is explicit. Map fields by name, transform values, drop concepts that have no meaning on this side.
- The ACL is symmetric when both sides write. Outbound translation is its own piece of code, even if the foreign model "looks similar."
- Failures of the foreign system surface as failures in this context's terms. Do not propagate raw HTTP errors or driver exceptions through the domain.
- An ACL is built to be removed. When the foreign model dies or the migration completes, delete the ACL with the model it served.

Smell: domain code that imports a third-party SDK type. The SDK is leaking. Wrap it.

## Context Mapping

Use Context Mapping to make relationships between bounded contexts explicit so the design choices are visible.

Apply when:

- Two contexts must talk to each other and the integration is non-trivial.
- A team is forming around a new context and needs to know how it relates to the rest.
- An ADR is being written about how two parts of the system depend on each other.

Common relationships:

- **Customer / Supplier**: downstream depends on upstream and has a voice in the upstream's roadmap. Upstream commits to the downstream's needs.
- **Conformist**: downstream depends on upstream and has no voice. Downstream conforms to whatever upstream provides; no ACL.
- **Anti-Corruption Layer**: downstream depends on upstream and isolates itself behind an ACL.
- **Shared Kernel**: two contexts share a small piece of model. Changes require agreement from both teams. Keep the kernel tiny.
- **Partnership**: two contexts succeed or fail together. Cooperate on a joint plan.
- **Open Host Service**: upstream publishes a stable protocol any number of downstreams can consume.
- **Published Language**: a documented schema or vocabulary that two contexts agree on as their lingua franca.

Rules:

- Pick a relationship per pair of contexts and document it. "We will figure it out" is not a relationship.
- A Conformist relationship is a deliberate choice, not a default. Choose it when the upstream is stable and the downstream is small.
- Shared Kernels rot. Review them every release; either keep them small and disciplined or break them apart.
- An Open Host Service is a commitment. Once you publish, breaking changes have a cost; plan for versioning.

Smell: two services in the same codebase calling each other through five layers of generic plumbing. Draw the context map and decide what relationship you actually want.

## Pattern Selection

Pick patterns by the problem in front of you, not by the diagram in a book.

- One context, one team, simple model: do not formalize bounded contexts yet. Keep the language tight, watch for naming conflicts.
- Two parts of the system disagree on what a word means: extract two bounded contexts and a translation.
- Two entities must always agree on a state transition: aggregate.
- A behavior involves multiple aggregates and no aggregate owns it: domain service.
- A change in one place should trigger work elsewhere without a single transaction: domain event with idempotent handler.
- An external system has the wrong model: anti-corruption layer.
- Two contexts must integrate and you have not decided how: write the context map first; choose a relationship.

If you cannot name the pattern you are using, you do not have one yet. Add the structure or accept that you are writing a transaction script and keep it short.

## Anti-Patterns

These shapes appear in greenfield code more often than they should. Reject them in review.

- **Anemic Domain Model**: entities are bags of getters and setters; behavior lives in services that mutate them from outside. Move the behavior onto the entity that owns the data, then the service shrinks to orchestration.
- **God Aggregate**: one aggregate root holds half the model and locks the world on every change. Split by invariant; reference siblings by identity.
- **Single Database, Single Model**: every team writes to one schema and shares one set of types. Boundaries are imaginary. Introduce contexts and translate at the seam.
- **Generic Subdomain Glamour**: investing core-level effort in JSON parsing, retry, or HTTP plumbing. Use a library; spend the time on the core.
- **Leaky Boundary**: returning third-party SDK types or ORM entities from a domain method. The boundary exists in name only. Wrap.
- **Past-Tense Command**: an "event" called `SaveSession` whose handler can refuse. That is a command. Rename or restructure.
- **Pattern Stacking**: every read goes through five layers because "DDD says so." If a layer never varies and never gets tested in isolation, delete it.

## Boundaries with Existing Codebase

ai-agents already has implicit bounded contexts. Reuse, do not duplicate.

- **Agent runtime**: agent definitions, agent invocation, the orchestrator, and the agent's view of the world. The ubiquitous language uses _agent_, _delegation_, _skill_, _tool_. New behavior that lives in this context belongs in `templates/agents/`, `.claude/agents/`, or the orchestrator service.
- **Session lifecycle**: session start, session end, handoff, retrospective. The language uses _session_, _handoff_, _retrospective_, _gate_. Session state is its own aggregate; the session log is the audit trail. New session-shape concepts go behind the session-management seam, not into hooks or skills.
- **Memory**: long-lived knowledge across sessions. The language uses _memory_, _entity_, _observation_, _relation_. Serena and Forgetful are repositories of long-lived knowledge in this context; the named operation already exists for most use cases.
- **Skills and hooks**: entry points that translate between user or harness input and the agent runtime. Treat them as ACLs from the harness to the agent runtime. Keep them thin: parse, call a service, format output.
- **GitHub integration**: a supporting subdomain. Reuse the established `gh` CLI patterns and PR template; do not invent a parallel issue model.

When you find a place where the codebase deviates from this rule, prefer a small focused refactor on the path you are already touching over a large rewrite. Note the deviation in the PR description so future readers see your reasoning.

## Quick Self-Review

Before opening a PR that touches agent definitions, session protocol, memory, orchestration boundaries, or cross-context translation, walk this list.

- Which bounded context does this change belong in? If you cannot name one, draw the boundary first.
- Does the code use the ubiquitous language of that context? If not, rename before merging.
- If the change touches two aggregates, is one driving the other through a domain event, or are you about to span a transaction?
- Are entity identities and value-object equalities used correctly, or are primitives smuggling rules?
- Does any new boundary need an ACL, or is a foreign model leaking through?
- Did you add a new aggregate, service, or event when an existing one would have done?
- Are entry points (skills, hooks, handlers) thin, or are they making domain decisions?

If any answer is "no" or "not sure," fix the design before review.
