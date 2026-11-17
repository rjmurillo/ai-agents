# domain-design

Designs an API, schema, or module boundary from the business behavior it must support. You decide what state is explicit, whether to use a domain operation or plain CRUD, and whether to keep history. Then you check the design against real use cases.

## When to use it

- A change adds or reshapes an API contract, a table or document schema, or a module boundary.
- You say `design this schema`, `API design`, `where should this module boundary go`, `CRUD or domain operation`, or `is this explicit state or reconstruction`.
- You need to decide whether a fact should be stored directly or rebuilt from other rows.

## When not to use it

- A change reuses an existing contract unchanged: skip this skill.
- You need abstraction discovery: use [`cva-analysis`](cva-analysis.md) instead.
- You need book-depth reference on domain-driven design or enterprise patterns: use [`software-engineering-library`](software-engineering-library.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:domain-design Design the schema for tracking which sites finished fetching each month
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/domain-design`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /domain-design skill to ...`.

The skill walks six steps: name the business question, derive state, derive operations, derive the schema, derive boundaries, and validate against three to five use cases. At the end you get a design plus the exit code and report from `evaluate_design.py`.

## What you get

A design that starts from business questions, with each first-class fact recorded as explicit state or a named safe derivation. The skill also records the use cases it walked.

`evaluate_design.py` turns your answers into a decision table. It is advisory: it cannot tell whether the answers are true.

| Exit code | Meaning |
| --- | --- |
| `0` | Adopt: no axis needs revision. |
| `1` | Revise: the report names each axis. |
| `2` | Bad input: unreadable file, invalid JSON, or invalid proposal. |

## Advanced use

### The six steps

1. Discover the business question, written as a sentence a business owner would say.
2. Derive state. A cheap computation from state you hold is a safe derivation. A first-class fact rebuilt by joining or probing incidental rows is a reconstruction. Record that fact as explicit state, and mark state that changes over time as needing history or effective-time.
3. Derive operations. Use a domain operation when the behavior has invariants or multi-step transaction semantics. Use CRUD when the entity is plain create, read, update, delete. Do not invent domain verbs to avoid CRUD.
4. Derive the schema. Model domain state and invariants first. Treat a source payload as an integration contract, not as the model.
5. Derive boundaries from behavior, invariants, ownership, and reasons to change. Reject a boundary that exists only because the payload, ORM, or transport format has that shape.
6. Validate against use cases. If a simpler adequate model exists, adopt it. Otherwise revise state or boundaries and walk again.

### Run the evaluator

Run it from the root of a checkout of this repository:

```bash
uv run python .claude/skills/domain-design/scripts/evaluate_design.py --help
```

```bash
uv run python .claude/skills/domain-design/scripts/evaluate_design.py proposal.json
```

The script takes one positional argument: a JSON file describing the proposed design. These fields are required, except `speculative_mechanism`, which may be `null` or omitted:

| Field | Meaning |
| --- | --- |
| `business_question` | The question the design must answer. |
| `state_representation` | `explicit` or `reconstructed`. |
| `fact_is_first_class` | The business must know this fact directly. |
| `api_style` | `crud` or `domain`. |
| `behavior_has_invariant` | The behavior has rules or multi-step transaction semantics. |
| `temporal_question`, `history_modeled` | The answer depends on a prior time, and the design keeps history. |
| `mirrors_source_payload`, `behavior_diverges_from_source` | The model copies the payload, and the business question differs from it. |
| `speculative_mechanism`, `mechanism_has_behavioral_need` | A proposed aggregate, event store, or abstraction (or `null`), and whether a current behavior requires it. |
| `use_cases` | Non-empty list of `{question, needs_reconstruction}` from step 6. |

`mechanism_has_behavioral_need` is still required as a boolean when there is no mechanism. The script checks for at least one use case. Walking three to five is your job.

A minimal `proposal.json`:

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

### Anti-patterns the skill flags

| Anti-pattern | Instead |
| --- | --- |
| Mirror the source payload as the internal model. | Derive the model from behavior. Keep the payload as an integration contract. |
| Rebuild a first-class fact from fact or output rows. | Record explicit state the business can read directly. |
| CRUD over a behavior with invariants or multi-step mechanics. | One domain operation that enforces the invariant. |
| A domain verb for a behavior with no invariant. | CRUD. |
| Overwrite state when the question depends on time. | Keep history or effective-time rows. |
| Event sourcing or aggregates with no current behavioral need. | Reject until a question requires them. |

### Chaining

[`autoplan`](autoplan.md) routes API, schema, and module-boundary design requests here. The [`review`](review.md) skill's architect axis calls this skill when a diff changes an API, schema, or module boundary. Quality principles such as cohesion, coupling, and YAGNI belong to [`code-qualities-assessment`](code-qualities-assessment.md). This skill applies them and does not restate them.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`cva-analysis`](cva-analysis.md): abstraction discovery, once behavior and invariants justify an abstraction.
- [`software-engineering-library`](software-engineering-library.md): book-depth reference on domain-driven design, data-intensive applications, and enterprise patterns.
- [`review`](review.md): its architect axis calls this skill.
- [`code-qualities-assessment`](code-qualities-assessment.md): owns the quality principles this skill applies.
- Source: [`SKILL.md`](../../src/claude/skills/domain-design/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
