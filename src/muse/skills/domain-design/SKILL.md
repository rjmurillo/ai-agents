---
name: domain-design
description: Design an API, schema, or module boundary from the business behavior it must support, not from source payload shape or generic CRUD. Decides explicit state, domain operation versus CRUD, and history, then checks the design against use cases. Use when you say `design this schema`, `API design`, or `CRUD or domain operation`. Do NOT use for abstraction discovery (use cva-analysis).
---

# Domain Design

> Design from the behavior the business must observe and control. Source shape and implementation convenience are inputs, not the domain model.

Owns one invariant: an API, schema, or module boundary is derived from business
questions and operations, then validated against them. It does not mandate DDD
tactical patterns, ban CRUD, or replace architecture review or the ADR
workflow. Quality principles (cohesion, coupling, YAGNI, minimal
implementation) belong to the `code-qualities-assessment` skill; this skill
applies them and does not restate them.

## Triggers

`design this schema`, `API design`, `where should this module boundary go`,
`CRUD or domain operation`, `is this explicit state or reconstruction`

## When It Applies

A change adds or reshapes an API contract, a table or document schema, or a
module boundary. A change that reuses an existing contract unchanged skips this
skill.

## Decision flow

```text
business question or operation
  -> observable behavior + invariant
  -> state that must be explicit
  -> API/module contract, and schema/history model
  -> validate against use cases
  -> simpler adequate model? yes: adopt. no: revise boundaries and state.
```

## Process

1. **Discover the business question.** Name the decisions, actions, and
   questions the system must support. Who observes or invokes each? Which
   outcomes, invariants, and time semantics matter? Write each question as a
   sentence a business owner would say.
2. **Derive state.** For each fact a question needs, decide: safe derivation or
   hidden reconstruction. A value computed cheaply from state you already hold
   is a derivation. A first-class fact rebuilt by joining or probing incidental
   rows (for example, "what have we fetched?" answered by scanning fact rows)
   is a reconstruction obligation. Row presence cannot tell a partial fetch from
   a complete one. Record that fact as explicit state. Mark
   which state changes over time and so needs history or effective-time.
3. **Derive operations.** Use a domain operation when the behavior carries
   invariants or multi-step transaction semantics that generic CRUD would leak
   (for example, "replace this site's reporting window"). Use CRUD when the
   entity is plain create, read, update, delete with no extra invariant. Do not
   invent domain verbs to avoid CRUD.
4. **Derive the schema.** Model domain state and invariants first. Treat an
   external or source payload as an integration contract that feeds the model,
   not as the model. Make important business facts queryable without rebuilding
   them from incidental traces.
5. **Derive boundaries.** Align module and API boundaries with behavior,
   invariants, ownership, and reasons to change. Reject a boundary that exists
   only because the payload, ORM, or transport format has that shape.
6. **Validate against use cases.** Walk three to five representative questions
   and commands through the design. Record any that need unrelated-table joins,
   inferred time, derived-state reconstruction, or coordination across
   boundaries. Treat repeated reconstruction or change amplification as design
   evidence, not query inconvenience. If a simpler adequate model exists,
   adopt it. Otherwise revise state or boundaries and walk again.

## Scripts

`evaluate_design.py` turns the answers above into a decision table so a
reviewer can read them. It is advisory: it cannot tell whether the answers are
true.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/domain-design/scripts/evaluate_design.py" proposal.json
```

| Field | Meaning |
|-------|---------|
| `business_question` | The question the design must answer |
| `state_representation` | `explicit` or `reconstructed` |
| `fact_is_first_class` | The business must know this fact directly |
| `api_style` | `crud` or `domain` |
| `behavior_has_invariant` | The behavior has rules or multi-step transaction semantics |
| `temporal_question` / `history_modeled` | The answer depends on a prior time / the design keeps history |
| `mirrors_source_payload` / `behavior_diverges_from_source` | The model copies the payload / the business question differs from it |
| `speculative_mechanism` / `mechanism_has_behavioral_need` | A proposed aggregate, event store, or abstraction (or null) / a current behavior requires it |
| `use_cases` | Non-empty list of `{question, needs_reconstruction}` from step 6 |

All fields are required except `speculative_mechanism`, which may be null or
omitted. `mechanism_has_behavioral_need` is still required as a boolean when
there is no mechanism. The script checks for at least one use case; walking
three to five is the author's job. A minimal `proposal.json`:

```json
{
  "business_question": "Which sites finished fetching for March?",
  "state_representation": "explicit",
  "fact_is_first_class": true,
  "api_style": "domain",
  "behavior_has_invariant": true,
  "temporal_question": false,
  "history_modeled": false,
  "mirrors_source_payload": false,
  "behavior_diverges_from_source": false,
  "speculative_mechanism": null,
  "mechanism_has_behavioral_need": false,
  "use_cases": [{"question": "Is site 7 done for March?", "needs_reconstruction": false}]
}
```

| Exit | Meaning |
|------|---------|
| `0` | Adopt: no axis needs revision |
| `1` | Revise: the report names each axis |
| `2` | Bad input: unreadable file, invalid JSON, or invalid proposal |

## Worked examples

**Source-shaped, then behavior-shaped.** An ingestion payload arrives as
`raw_fetch_events`. The source-shaped design stores those rows and answers
"what have we fetched?" by de-duplicating them on every read. The business must
know fetch progress, and row presence cannot tell a partial fetch from a
complete one, so the behavior-shaped design records `fetch_progress` per
source and window as explicit state. The payload stays an integration contract
that feeds an ingest step. The question becomes one indexed read.

**CRUD stays correct.** A `tag` has a unique name and nothing else. Create,
read, rename, delete is the whole behavior. Adopt CRUD. Wrapping it in
`RegisterTag` and `RetireTag` adds ceremony with no invariant.

**Temporal.** "Which plan was the customer on when we billed them?" depends on a
prior time. Overwriting `current_plan` loses the answer. Keep effective-dated
plan rows.

**Speculative mechanism.** A proposal adds event sourcing for a screen that
reads the latest value. No current question needs replay. Reject it under the
quality principles; add it when a question requires it.

## Anti-Patterns

| Anti-pattern | Instead |
|--------------|---------|
| Mirror the source payload as the internal model | Derive the model from behavior; keep the payload as an integration contract |
| Rebuild a first-class fact from fact or output rows | Record explicit state the business can read directly |
| CRUD over a behavior with invariants or multi-step mechanics | One domain operation that enforces the invariant |
| A domain verb for a behavior with no invariant | CRUD |
| Overwrite state when the question depends on time | Keep history or effective-time rows |
| Event sourcing or aggregates with no current behavioral need | Reject until a question requires them |

## Extension Points

Add an axis by writing one `check_*` function in `evaluate_design.py`, the
proposal field it reads, and a positive, negative, and mutation test. Append the
function to the `CHECKS` tuple, or `evaluate` never calls it. Add the field to
`_BOOL_KEYS` or `_STRING_KEYS`, or a missing or mistyped field is not validated
and does not exit 2. Keep this
page the decision procedure; move long worked examples into a reference file.

## Related skills

- `cva-analysis`: abstraction discovery, once behavior and invariants justify an abstraction.
- `software-engineering-library`: book-depth reference on domain-driven design, data-intensive applications, and enterprise patterns.
- `review`: its architect axis calls this skill when a diff changes an API, schema, or module boundary.

## Verification

- [ ] Design starts from a business question, its observable outcome, and its invariant.
- [ ] Each first-class fact is explicit state or a named safe derivation.
- [ ] Source and transport shape is treated as an integration concern.
- [ ] A domain operation is chosen only where an invariant justifies it; CRUD is kept where it fits.
- [ ] Questions that depend on time have history or effective-time modeling.
- [ ] Three to five representative questions were walked and recorded.
- [ ] `evaluate_design.py` exit code and report are quoted for the final design.
