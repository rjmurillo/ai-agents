---
description: Data ownership, consistency, schema evolution, and idempotency rules from Kleppmann's Designing Data-Intensive Applications. Apply when changing how state is stored, replicated, or exchanged between agents, sessions, memory, or workspaces.
alwaysApply: false
---

# Data-Intensive Applications

This rule consolidates the patterns from Martin Kleppmann's _Designing Data-Intensive Applications_ (DDIA) that recur in this codebase. Apply it whenever you change how data is owned, written, replicated, exchanged, or replayed across agent boundaries.

ai-agents has multiple persistent and semi-persistent stores: session logs on disk, agent memory (Serena, Forgetful), workspace files, git history, and event-driven inter-agent traffic. Each one has an implicit consistency model. The point of this rule is to make those models explicit and force every author to answer the same questions before adding a new write path: who owns this data, what happens on retry, and how does the schema evolve.

## Core Vocabulary

Use these terms consistently in code, comments, ADRs, and PR descriptions.

- **System of record (SoR)**: the one store that is authoritative for a piece of data. Every other copy is a derivative.
- **Derived data**: data computed or projected from a system of record. Caches, search indices, materialized views, snapshots. Always reproducible by replay.
- **Idempotent**: applying the operation twice yields the same observable state as applying it once.
- **At-least-once delivery**: the system guarantees a message arrives, but it may arrive more than once. Receivers must dedupe.
- **At-most-once delivery**: the system may drop a message but never duplicates. Senders must accept loss.
- **Exactly-once semantics**: an end-to-end property achieved by combining at-least-once delivery with idempotent receivers. It is a property of the whole pipeline, never of a single hop.
- **Schema evolution**: changing the shape of stored data without breaking readers or writers that have not been upgraded yet.
- **Backward compatible**: new code reads old data.
- **Forward compatible**: old code reads new data, ignoring fields it does not understand.
- **Causal order**: A happened before B if A could have influenced B. Weaker than total order, stronger than no order.

If you find yourself reaching for a stronger guarantee word ("transactional," "atomic," "consistent"), name the boundary across which it holds. A guarantee without a boundary is marketing.

## Source of Truth Ownership

Every piece of data in the system has exactly one owner. Make the owner obvious in code and documentation.

Apply when:

- You add a new field, file, table, or memory entry.
- You introduce a cache, snapshot, or projection of existing data.
- Two components both read and write the same logical entity and you can no longer answer "who is right when they disagree."

Rules:

- Name the system of record in the file or component header. One sentence: "The session log is the SoR for protocol compliance evidence; agent memory is a derived index."
- Derived stores are rebuildable. If you cannot regenerate the cache or index from the SoR, the cache has become a second SoR by accident. Either write the rebuild path or promote it to first-class.
- Writes flow through the SoR, never around it. A consumer that writes directly to a cache is a bug.
- A second writer requires a written-down conflict resolution policy: last-writer-wins with a tiebreaker, CRDT merge, or explicit human escalation. "Last commit wins" by accident is not a policy.
- Cross-store invariants need a single owner. If two stores must agree on a fact, decide which one is the SoR and which is the projection, then build the projection from the SoR.

Smell: a bug report that says "X says A but Y says B, which is correct?" The answer must be findable without paging the original author. If it is not, the ownership is unclear.

## Idempotency

Every write handler should be safe to call twice. Build for replay, not for hope that retries will not happen.

Apply when:

- A handler writes to disk, the network, or a memory store.
- A handler emits events that other handlers consume.
- A workflow can be retried automatically, manually, or by replaying a log.

Rules:

- Identify the natural idempotency key for the operation: a request id, a session-and-step pair, a content hash, an issue number plus action. Reject the operation on second arrival or apply the no-op branch.
- Side effects are wrapped, not assumed. A handler that issues a CLI call to create a pull request twice creates two PRs unless you guard it. Look up by branch or title before creating.
- "Insert if not exists" is fine for sets. For mutable values, prefer compare-and-set or a versioned write. Blind upserts on mutable rows lose the lost-update case.
- Idempotency keys are persisted. Storing them in process memory is fine for a single run; for cross-process or cross-session retries, persist them where the SoR lives.
- A handler that cannot be made idempotent (sending an irreversible external command, charging money, posting a one-shot notification) needs an explicit barrier: a claim row written before the side effect, checked on every retry.

Smell: comments that say "this should not happen twice." If your code relies on it, prove it; if it cannot, defend it.

## Consistency Model per Boundary

Every read or write boundary has a consistency model. State which one.

Apply when:

- You introduce a new component that reads or writes shared state.
- You replicate, cache, or shard data.
- A user-visible operation reads from a store other than the one it just wrote.

Rules:

- Name the model. _Read-your-writes_, _monotonic reads_, _bounded staleness_, _causal_, _eventual_, _strict serializable_. Pick the weakest one that is correct, then document it.
- Strong consistency costs latency and availability. Buy it where you must (write throughput per session, money, identity), not by default.
- A read-after-write that crosses a replication boundary is eventual unless you proved otherwise. Either route the read to the leader, version the write, or accept the staleness in the UX.
- Document the staleness window where it matters. "Up to N seconds behind the writer" is a contract; "eventually consistent" alone is not.
- Cross-store reads compose the weakest model of the parts. If you read from a strong store and a cache, the result is cache-consistent.

Smell: code that retries a read in a loop until it sees the value it just wrote. That is a missing read-your-writes guarantee, not a flaky read.

## Schema Evolution

Schemas change. Plan for both ends of the change to be deployed at the same time.

Apply when:

- You add or remove a field on a stored object (session log, memory entry, configuration file, message envelope).
- You rename a field or change its type.
- You introduce a new event or message variant.

Rules:

- Adding an optional field is backward and forward compatible. Make new fields optional, with a documented default that older readers can ignore.
- Removing a field is a two-step operation: stop writing it, wait until no reader depends on it, then drop it.
- Renaming is two operations: add the new name, dual-write, migrate readers, stop writing the old name. Never a one-shot rename in a shared store.
- Type changes are migrations, not edits. Widening (int to long) may be safe; narrowing or semantic changes require a versioned migration plan.
- Version the envelope, not just the payload. A `schemaVersion` field on every persisted document and event makes future migrations diagnosable.
- Old data does not retroactively update. If you depend on a field that did not exist last year, your reader handles its absence, or you backfill explicitly with a recorded migration.

Smell: a code review comment that says "old session logs will not have this field." Either backfill or make the reader tolerant. Do not ship a reader that crashes on history.

## Event Ordering and Delivery

Order is a property you assert, not one you assume.

Apply when:

- You design inter-agent messaging, hooks, or any pipeline of side effects.
- A consumer cares whether event A was processed before event B.
- A producer fans out to multiple consumers.

Rules:

- Default to at-least-once delivery and idempotent consumers. At-most-once is acceptable only when loss is genuinely safe (telemetry, debug logs).
- Total order across the whole system is expensive. Ask for the weakest order that makes the consumer correct: per-key (per-session, per-agent, per-aggregate) order is usually enough.
- Causal order requires explicit metadata: a vector clock, a logical timestamp, or a parent reference on each event. Wall-clock timestamps are not causal.
- Do not assume two queues are ordered relative to each other. If a consumer reads from both, it must merge by key and timestamp, not by arrival.
- Replays must be deterministic given the input log. Side effects driven by `random()`, current time, or external state break replay; capture those inputs in the event itself.

Smell: a fix that says "we added a sleep so the second event arrives after the first." Order has to be expressed in the data, not the wall clock.

## No Exactly-Once Wishful Thinking

There is no exactly-once delivery. There is at-least-once delivery plus idempotent receivers, which together yield exactly-once **effects**.

Rules:

- If a design relies on a message being delivered exactly once, the design is wrong. Refactor it into "at-least-once delivery, idempotent application."
- The boundary at which exactly-once is observable is the receiver's persistent state. Anything before that boundary may have run zero, one, or many times.
- "We have not seen a duplicate yet" is not a guarantee. Engineer for the duplicate that arrives in week six, after a partial outage, when the dedupe table is the only thing standing between you and a double charge.
- External effects (HTTP calls, notifications, file writes outside the SoR) are at-least-once. Wrap them with a claim-then-execute pattern: write the claim before, the result after, and skip on retry if either is present.

Smell: an architecture diagram with an arrow labeled "exactly once." Replace it with "at-least-once + idempotent" and describe the dedupe key.

## Application to ai-agents

The codebase already has implicit consistency contracts. Make them explicit; do not invent parallel ones.

- **Session logs** are the system of record for protocol compliance and per-session work history. Memory entries that summarize a session are derived data. Rebuild from the log; do not write to the summary independently.
- **Agent memory (Serena, Forgetful)** is an indexed projection of decisions and patterns. Treat memory as a cache of long-lived knowledge; the source artifacts (ADRs, code, session logs) are the SoR. When memory and source disagree, source wins, and the memory entry is stale.
- **Workspace state** (files in the working tree, scratch directories) is process-local. Do not assume another agent or another session sees it. Either commit, push, or persist through a known store.
- **Inter-agent messaging via hooks, skills, and orchestrator handoffs** is at-least-once. Idempotency keys belong on every handler that mutates state outside its own process. Issue numbers, branch names, and PR numbers are good natural keys.
- **Git** is the durable, content-addressed event log. Treat the commit graph as the canonical event ordering for code and config. Anything that needs durable order should be written through git or anchored to a commit SHA.

When a new component blurs one of these boundaries, do not paper over it with retries and hopes. Name the SoR, name the consistency model, and add the dedupe key.

## Anti-Patterns

These shapes show up in greenfield code and should not survive review.

- **Two writers, no policy**: two components write to the same field with no documented conflict rule. Pick a SoR or write a CRDT.
- **Cache as SoR by accident**: a cache that grows divergence from its source over months because the rebuild path was never written. Build the rebuild before you ship the cache.
- **Retry without idempotency**: a handler wrapped in a retry decorator with no dedupe key. The first failure is now a thundering herd of duplicates.
- **Schema-by-accident**: data shapes drift because every writer adds optional fields and every reader silently ignores unknowns. Pin a schema and version it.
- **Total-order fantasy**: assuming all events are seen in the same order by all consumers because "they came from the same producer." Per-key order is the strongest free guarantee.
- **Exactly-once labels**: any design artifact that promises exactly-once delivery. Replace with at-least-once plus idempotent.
- **Wall-clock causality**: deciding "A happened before B" by comparing timestamps from two machines. Use logical clocks or explicit parent links.

## Quick Self-Review

Before opening a PR that adds or changes a write path, walk this list.

- Who owns this data? Is the system of record obvious from the code or the file header?
- If this handler runs twice, what happens? Where is the idempotency key persisted?
- What consistency model does each read and write boundary have, and is it weaker than callers assume?
- If the schema changes next quarter, what reads and writes break? Is the field optional, versioned, and tolerant of absence?
- What ordering does this consumer rely on? Is it per-key, causal, or total, and is that ordering enforced by the data or by hope?
- Is there an arrow in the design that promises exactly-once delivery? Replace it.
- For each external side effect, is there a claim row written before and a result row written after?

If any answer is "not sure," fix the design before review, not after the first incident.
