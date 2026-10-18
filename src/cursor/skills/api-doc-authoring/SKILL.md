---
name: api-doc-authoring
description: Write API docs around a developer use case, with executed examples and failure recovery. Use when you say `document this API` or `write the API guide`. Do NOT use to verify doc claims (use doc-accuracy) or design the API.
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - api-documentation-authoring
    depends-on:
      - artifact-neutral-code-quality
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan's long-tail resolver matches an API documentation authoring request
    user-facing: true
    intents:
      - api documentation
      - document this api
      - api quickstart
      - api guide
      - endpoint documentation
---

# API Doc Authoring

> Document the task developers are trying to complete, prove the examples run,
> and make failure recovery first-class.

API documentation is entered through a developer use case, not through the
implementation's endpoint inventory. A tired developer should reach a working
path and recover from common failures without reverse-engineering the API.

This skill owns how API documentation is structured and validated for use. It
does not own claim checking, prose style, or API design:

| Concern | Owner | How this skill uses it |
|---------|-------|------------------------|
| Behavioral and cross-document claims | `doc-accuracy` | Runs through the existing lifecycle gates. No second accuracy gate here. |
| DRY, YAGNI, derived mutable facts | `code-qualities-assessment` | Link to the canonical fact. Do not restate it in each example. |
| Voice, banned words, dashes | `voice.md` and `universal.md` | Consumed as written. This skill adds no style guide. |
| API and schema design | the business-behavior-first design owner (#5411) | Describe the resulting contract. Never redefine it. |
| Capability graph | `check_capability_graph.py` (#5396) | This skill's `owns` and `depends-on` metadata. `doc-accuracy` declares no capability block, so it is cited, not declared. |

## Triggers

`document this API`, `write the API guide`, `quickstart for this endpoint`,
`add examples to the API docs`, `document the error responses`

## When It Applies

Apply when a developer will call the API to finish a task and the docs are new,
rewritten, or touched by an API contract change.

Skip the narrative when the artifact is a true reference listing, such as a
generated schema page, or the API is trivial or internal with one obvious call.
Write the reference, mark it as reference, and stop. Do not invent a use case to
fill space.

## Process

```text
developer goal -> minimum working request -> expected response
  -> common failures + remediation -> advanced options
  -> execute examples, then doc-accuracy through the lifecycle
```

### Phase 1: Name the use case

State the goal as a developer task ("place an order and check it"), not an
endpoint name. List the operations that together finish it. Several CRUD
endpoints that implement one workflow become one entry point, in the order a
developer calls them. Read `references/use-case-flow.md` for the entry shape.

### Phase 2: Minimum working request, then response

Show the smallest request that succeeds: required inputs only. Follow it with
the response and the next action (which field feeds the next call). Optional
parameters wait until the working path is complete.

### Phase 3: Failures with cause and action

For each operation, list the failures a developer is likely to hit. Each row
carries status or error name, likely cause, and action. Write a cause or action
only when the contract or a run supports it. Where it does not, write `Unknown`.
Never promise exhaustive error coverage the contract cannot support.

### Phase 4: Advanced and reference material

Optional knobs, rare behavior, and the exhaustive field table come after the
basic workflow succeeds. Keep similar use cases in the same order: request,
response, errors.

### Phase 5: Execute the examples

Mark each runnable example so it can be re-run (`references/example-verification.md`
has the syntax and the evidence contract), then run it against a local, test, or
mock API:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/api-doc-authoring/scripts/api_examples.py" run <doc.md> --base-url http://127.0.0.1:<port> --evidence <evidence.json>
```

Never paste console output or a response from memory. A response block with no
executed request is flagged by `lint` and cannot be called verified.

### Phase 6: Hand off to the lifecycle

Documentation written here is documentation. The `test` skill's Gate 5 and the
`review` skill's `doc-accuracy` axis (category `docs-and-instructions`) already
compose `doc-accuracy` for it; follow
`${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/test/references/doc-accuracy-gate.md`.
Do not run a parallel
accuracy gate.

When an API contract changes, find the affected examples and re-run them:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/api-doc-authoring/scripts/api_examples.py" list <docs...> --touching /orders
```

A changed request shape makes the stale example fail. It does not stay trusted
prose.

## Scripts

| Subcommand | Purpose | Exit codes |
|------------|---------|------------|
| `list` | Examples in the docs, filtered by `--touching <path prefix>` | `0` listed, `2` bad input |
| `lint` | Missing ids or status, unverified responses, error rows without cause or action | `0` clean, `1` findings, `2` bad input or no examples found |
| `run` | Execute examples, compare status and documented response, write evidence | `0` all pass, `1` stale, failing, or lint findings (verdict FAIL even when every HTTP comparison passed), `2` unverifiable |

Stdlib only. `api_examples.py` imports the parser `doc_examples.py` beside it. `run` refuses a non-loopback host unless `--allow-remote` is passed,
because a doc example can create or delete data. It sends only to the base URL host: a request path must start with `/`, and redirects are returned as replies, never followed. Loopback requests ignore proxy settings. Exit `2` (no example matched, or a stop with no failed example or lint finding found first: server unreachable, a response over 2 MiB or slower than 30 s, a run past 300 s) means unverified. It never means pass. A stop that already has a failed example or lint finding exits `1`, and its evidence file lists the examples that never ran under `deadline_exceeded`, or under `request_failed` the example that could not finish (its request may have reached the server) and the examples after it.

## Anti-Patterns

| Avoid | Instead |
|-------|---------|
| Alphabetical endpoint list as the front door | Use-case entry, reference after |
| A response block copied from memory | Run the request, keep the evidence |
| Error rows that list only a status name | Add cause and action, or `Unknown` |
| Invented remediation for an unspecified failure | `Unknown`, and file the gap |
| Optional parameters in the first example | Required inputs only, options later |
| Forcing narrative onto a reference-only page | Write the reference and say so |
| Copying doc-accuracy or style rules into the page | Cite the owner |

## Verification

- [ ] The entry point is a developer goal; the endpoint reference follows it.
- [ ] `lint` returns `PASS` and `run` returns `PASS` at the final head, with the evidence file kept.
- [ ] A changed request shape was shown to fail its example (stale-example check).
- [ ] Every failure row has a supported cause and action, or `Unknown`.
- [ ] Required inputs precede optional ones; advanced behavior follows the working path.
- [ ] `doc-accuracy` ran through the lifecycle gate, not a second gate here.
