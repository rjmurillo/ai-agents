# Use-Case Flow

Read this when you write the entry point for an API guide. The procedure is in
`SKILL.md`; this file holds the shapes.

## Entry shape

Every use case uses the same order, so a developer learns it once.

```text
## <Goal as a developer task>

Goal: one sentence naming the outcome.
Before you start: required credentials, base URL, prior state.

### Step N: <action>
  Minimum request (required inputs only)
  Response (what the developer needs from it)
  Next: which field feeds the next step

### If something goes wrong
  Table: Status | Cause | Action

### Options
  Optional parameters and rare behavior, after the working path

## Reference
  Exhaustive field and endpoint tables
```

## Choosing the front door

| Situation | Front door |
|-----------|-----------|
| Several endpoints implement one workflow | Use-case entry, endpoints as steps |
| One obvious call, internal or trivial | A single example and the reference |
| Generated reference page (schema, OpenAPI render) | Reference only. Do not add narrative |
| Mixed audience | Use cases first, alphabetical reference second |

A reference-only page is the right artifact when the reader looks things up
instead of finishing a task. Do not duplicate the same content as a narrative.

## Progressive disclosure

1. The common path appears first and uses required inputs only.
2. Optional parameters follow the first successful workflow.
3. Advanced and rare behavior come last, with the reference.

## Error recovery rows

Cover the failures a developer is likely to hit for this operation: bad input,
missing prerequisite state, auth, conflict, and the domain errors the contract
names.

| Rule | Reason |
|------|--------|
| One row per failure: status or error name, cause, action | Names alone do not tell the developer what to do |
| Cause and action come from the contract, code, or a run | Invented remediation sends developers down a wrong path |
| Write `Unknown` when evidence stops | `Unknown` is an honest answer; a guess is not |
| Do not claim "all errors" | A contract rarely lists every server failure |

## Consistency of shape

Similar use cases keep the same order: request, response, errors. Use the
terms the API contract uses. If the docs say "order" and the schema says
"purchase", fix the docs to match the contract, or raise the mismatch with the
owner of the contract. Do not coin a third term.

## Composition

| Need | Go to |
|------|-------|
| Check a behavioral claim in the prose | `doc-accuracy`, via the `test` and `review` gates |
| Avoid restating a derived or mutable fact | `code-qualities-assessment` (non-redundancy) |
| Voice and banned words | `.claude/rules/voice.md` |
| Change the API contract | The API design owner, not this skill |
