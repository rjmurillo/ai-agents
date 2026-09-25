---
type: requirement
id: REQ-039
title: Resolve catalog specialists before the autoplan orchestrator fallback
status: implemented
priority: P1
category: functional
source: issue-5385
related:
  - REQ-019
  - REQ-038
  - DESIGN-037
  - TASK-048
created: 2026-09-25
updated: 2026-09-25
author: spec
tags:
  - skills
  - routing
  - autoplan
---

# REQ-039: Resolve catalog specialists before the autoplan orchestrator fallback

## Step 0 First Principles

### Q1 Demand Reality

Issue #5385, filed by rjmurillo under epic #5390. Issue #5389 (the
reachability eval) is blocked on it. REQ-038 already names this resolver as
its first consumer.

### Q2 Status Quo

The `autoplan` table names a small high-traffic set. Any request that misses
the table goes to the orchestrator, including a single-domain request that one
specialist skill answers. The orchestrator is a multi-agent coordinator, so a
one-skill request pays for coordination it does not need, or it never reaches
the skill at all.

### Q3 Desperate Specificity

Four skills have no automatic route: `business-strategy`, `book-to-skill`,
`world-model-diagnostic`, and `dx-review`. Each one is `explicit-only` today
with a rationale that says it waits for this resolver. `programming-advisor`
is also unreachable from `autoplan` for its core question ("is there a library
for this?"). The table sends every new capability to `buy-vs-build-framework`,
and that skill says not to use it for that question.

### Q4 Narrowest Wedge

One optional `intents` key in the routing block, one deterministic resolver
script in the `autoplan` skill, a precedence list in the skill body, and
fixtures for every issue row. No new registry and no new MCP server.

### Q5 Observation

Measured on `main` at `3fda96cc8` on 2026-09-25: 111 skills, 26 `front-door`,
13 `explicit-only`. The `autoplan` routing table has 19 rows.

### Q6 Future-fit

At 10x the catalog, each skill carries its own intents, so the router table
stays at about 20 rows. Deterministic phrase matching stays testable at any
size. When phrase matching is too weak, an eval (#5389) measures it before
anyone replaces it.

## Problem statement

A request that misses the high-traffic table cannot reach a single specialist
skill. "No row matches" and "needs several agents" take the same route.

## User stories

- As a user, I describe a business, book, or developer-friction problem, and
  `autoplan` selects the one skill that owns it.
- As a skill author, I add intents to my skill, and `autoplan` can route to it
  without a new table row.
- As the #5389 eval author, I call one deterministic function and score its
  route against fixtures.

## Ontology

- **High-traffic table**: the routing table in the `autoplan` skill body.
- **Long-tail resolver**: `scripts/resolve_route.py` in the `autoplan` skill.
- **Intent**: a short phrase in `metadata.routing.intents`. It matches when
  every word in it appears in the request.
- **Eligible skill**: a `front-door` skill with intents, other than the router.
- **Qualified name**: `<namespace>:<skill>`, for example
  `project-toolkit:autoplan`.

## Precedence

1. An explicitly named, installed skill wins, with no rerouting.
2. A high-traffic table row wins next.
3. A single-domain miss goes to the long-tail resolver.
4. A feature, bug, or shipping request with no specialist uses the lifecycle
   chain.
5. Only multi-domain, cross-cutting, or multi-agent work goes to the
   orchestrator.
6. The router never routes to itself. The orchestrator never invokes the
   router.

## Failure modes

- PyYAML is absent in the host interpreter: the resolver exits 2 and names the
  missing module. The skill body tells the model to read skill descriptions
  instead.
- A skills root does not exist: the resolver exits 2.
- Two skills tie on the top score: the resolver returns `ambiguous` with both
  names. The model asks the user and does not guess.
- A request names a skill that is not installed: the resolver ignores the
  name, says so in the rationale, and never returns that name.

## Security

The resolver reads local `SKILL.md` files and writes JSON to stdout. It opens
no network connection and runs no subprocess. It never executes skill content.

## Acceptance criteria

1. The high-traffic table SHALL stay at 25 rows or fewer.
2. WHEN a single-domain request misses the table, THE SYSTEM SHALL run the
   resolver before any orchestrator fallback.
3. The resolver SHALL be deterministic: the same request and catalog SHALL
   give byte-identical JSON. The JSON SHALL hold `kind`, `route`,
   `candidates`, and a one-line `rationale`.
4. The resolver SHALL consider only `front-door` skills that declare
   `intents`. It SHALL never return an `explicit-only`, `nested-helper`,
   `conditional-adjunct`, `lifecycle`, or `deprecated` skill from intent
   matching.
5. `programming-advisor` and `buy-vs-build-framework` SHALL each carry
   positive and negative examples, and the fixtures SHALL prove neither
   resolves the other's positive example.
6. WHEN a new capability is requested, THE SYSTEM SHALL run
   `programming-advisor` prior-art discovery before `/spec`, and SHALL add
   `buy-vs-build-framework` only for a strategic build, buy, partner, or defer
   decision. REQ-019 criterion 3 SHALL say the same.
7. WHEN a request names an installed skill, THE SYSTEM SHALL return that skill
   as `explicit` and SHALL NOT apply intent matching.
8. WHEN a request carries a multi-domain marker, THE SYSTEM SHALL return
   `orchestrator`.
9. The resolver SHALL never return the router itself. A regression test SHALL
   prove it for a request that names the router, and SHALL prove the
   orchestrator source never invokes the router.
10. The router SHALL have the stable identity `project-toolkit:autoplan`, with
    `/autoplan` as the local alias. A mixed-catalog fixture SHALL prove that a
    routing request never selects a foreign `autoplan`, and that a request for
    the foreign review pipeline by qualified name never selects the router.
11. IF `intents` is present on a skill whose role is not `front-door`, or is
    not a non-empty list of non-empty strings, THEN the routing-role gate
    SHALL exit 1.
12. Tests SHALL cover every row of the issue #5385 fixture table, with
    positive, negative, and edge cases.
13. Generated mirrors SHALL change only through `build/scripts/build_all.py`.
