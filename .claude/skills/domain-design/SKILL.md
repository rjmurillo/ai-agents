---
name: domain-design
version: 0.1.0
description: Design APIs, schemas, and module boundaries from business behavior first, not from source-system shape, transport DTOs, persistence convenience, or generic CRUD. Use for `domain design`, `API design`, `schema design`, `database design`, `module boundary`, `business behavior`, `explicit state vs reconstruction`, `CRUD vs domain operation`, `effective-time`, `temporal history`, and `use-case validation` of a proposed model. Distinguishes explicit business state from hidden reconstruction, treats source/transport shape as an integration concern, prefers domain operations over CRUD only when invariants justify it (CRUD stays correct when it fits), and surfaces temporal modeling. Do NOT use for abstraction discovery (use cva-analysis), build-vs-buy (use programming-advisor), or book-depth reference routing (use software-engineering-library).
license: MIT
---

# Domain Design (business-behavior-first)

Design from the behavior the business must observe and control. Data-source
shape and implementation convenience are inputs, not the domain model. Model
what the business needs to know and do, then derive storage and transport from
that model, not the reverse.

This skill owns the design semantics only. It consumes quality/YAGNI doctrine
from `golden-principles` (issue #5397), routes to book-depth material in
`software-engineering-library`, and hands abstraction discovery to
`cva-analysis`. It does not restate SOLID, DRY, or YAGNI.

## Triggers

| Phrase | Context |
|--------|---------|
| `design this API/schema/module` | A new contract, table, or boundary is being shaped |
| `should this be CRUD or a domain operation` | An operation carries rules and you must choose |
| `is this explicit state or reconstruction` | A business fact is derived by joins/probes |
| `does this question depend on time` | The answer differs by effective-time |
| `validate this design against the use cases` | Walk business questions against a proposal |

## Decision flow

```text
business question / operation
          |
          v
observable behavior + invariant
          |
          v
state that must be explicit
          |
          +------------------+
          |                  |
          v                  v
     API/module contract   schema/history model
          |                  |
          +--------+---------+
                   v
        validate against use cases
                   |
             simpler adequate model?
              |             |
             yes            no
              |             |
              v             v
            adopt      revise boundaries/state
```

## Process

1. **Business question discovery.** Name the decisions, actions, and questions
   the system must support. Who observes or invokes the behavior? What outcome,
   invariant, and time semantics matter?
2. **State derivation.** For each fact the business needs, decide: is it a safe
   derivation, or a hidden reconstruction obligation? If the business must know
   it directly, record it as explicit state. Reconstructing a first-class fact
   from incidental fact/output rows is a hidden obligation, not a derivation.
3. **Operation derivation.** Prefer a domain operation when the behavior carries
   invariants or multi-step transaction semantics that CRUD would leak. When the
   entity is simple create/read/update/delete with no extra invariant, CRUD is
   the correct answer. Do not invent domain verbs to avoid CRUD.
4. **Schema derivation.** Model domain state and invariants first. Treat an
   external or source payload as an integration contract, not automatically as
   an internal entity. Make important business facts queryable without
   reconstructing them from incidental implementation traces.
5. **Boundary derivation.** Align module/API boundaries with behavior,
   invariants, ownership, and change reasons. Reject a boundary that exists only
   because the payload, ORM, or transport has that shape.
6. **Temporal derivation.** When a question depends on what was true at a prior
   time, model history or effective-time. Overwriting current state loses the
   answer.
7. **Validate against use cases.** Walk representative questions and commands
   against the proposal. Excessive required joins, hidden temporal assumptions,
   derived-state reconstruction, or cross-boundary coordination is design
   evidence, not mere query inconvenience. If a simpler adequate model exists,
   adopt it; otherwise revise boundaries/state.

## Scripts

`scripts/evaluate_design.py` encodes the axes above so a proposal can be
checked, not just argued. It reads a JSON proposal and reports which axes need
revision.

```bash
python3 .claude/skills/domain-design/scripts/evaluate_design.py proposal.json
```

Proposal fields: `business_question` (non-empty string),
`state_representation` (`explicit` | `reconstructed`), `fact_is_first_class`,
`api_style` (`crud` | `domain`), `behavior_has_invariant`, `temporal_question`,
`history_modeled`, `mirrors_source_payload`, `behavior_diverges_from_source`,
`mechanism_has_behavioral_need`, and optional `speculative_mechanism`.

Exit codes: `0` adopt as-is, `10` at least one axis needs revision, `1` tool
error (bad input).

## Before/after example

Source-shaped (rejected): the ingestion payload has `raw_fetch_events` rows, so
the schema stores `raw_fetch_events` and answers `what have we fetched?` by
joining and de-duplicating those rows on every read. The business question is
forced through reconstruction.

Behavior-shaped (adopted): the business must know fetch progress, so record
`fetch_progress` as explicit state keyed by source and window. The payload
stays an integration contract feeding an ingestion step. `what have we
fetched?` is one indexed read.

## CRUD stays correct

A `tag` entity supports create, read, rename, and delete with no invariant
beyond a unique name. This is genuine CRUD. Do not wrap it in
`RegisterTag`/`RetireTag` domain commands. Ceremony without an invariant is
over-engineering the issue's YAGNI control rejects.

## Anti-patterns

| Anti-pattern | Instead |
|--------------|---------|
| Mirror the source payload as the internal model | Derive the internal model from behavior; keep the payload as an integration contract |
| Reconstruct a first-class fact from fact/output rows | Record explicit state the business can read directly |
| CRUD for a behavior with invariants/transaction steps | One domain operation that enforces the invariant |
| A domain verb for a behavior with no invariant | CRUD; do not manufacture ceremony |
| Overwrite state when the question depends on time | Model history/effective-time |
| Add event-sourcing/aggregates with no current need | Reject per #5397 YAGNI doctrine |

## Composition and deferred work

- **Consumes #5397** (golden-principles) for YAGNI/minimal-implementation and
  generic quality doctrine. This skill references those, it does not copy them.
- **Routes to `software-engineering-library`** for book-depth on
  domain-driven-design, data-intensive-applications (schema evolution,
  consistency), and enterprise-patterns.
- **Hands abstraction discovery to `cva-analysis`** once behavior and
  invariants justify an abstraction.
- **Deferred to #5396**: capability DAG/ownership metadata wiring. This skill
  will consume that registry once it exists; it defines no dependency registry
  of its own.
- **Deferred to #5395**: technical review composition may consume this skill
  when APIs/schemas/boundaries change.
- **Deferred to #5398**: documentation-accuracy lifecycle composition.

## Extension Points

- Add a new axis by writing one `check_*` function in `evaluate_design.py` and
  a proposal field it reads, then a positive, negative, and mutation test.
- Keep the skill body the decision procedure; put longer worked examples in a
  `references/` file if they grow past this page.

## Verification

- [ ] Design starts from a business question, its observable outcome, and its invariant.
- [ ] Explicit state versus reconstruction is decided for each first-class fact.
- [ ] Source/transport shape is treated as an integration concern.
- [ ] Domain operation is chosen only when an invariant justifies it; CRUD is kept when it fits.
- [ ] Temporal questions surface history/effective-time modeling.
- [ ] The proposal is walked against representative use cases.
- [ ] Speculative mechanisms with no behavioral need are rejected per #5397.
