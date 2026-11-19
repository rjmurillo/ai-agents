---
id: ADR-123
status: accepted
date: 2026-11-19
decision-makers:
  - rjmurillo
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-123: Skills Declare the Artifacts They Read and Write

## Status

Accepted. The panel reached consensus in round 2, confirmed in round 3.
The debate appears in `.project-toolkit/critique/ADR-123-debate-log.md`.
The maintainer selected the typed `inputs` and `outputs` option.

## Context

Skills already declare who routes to them and what they own.
`metadata.routing` (DESIGN-036) names the invoker of each skill.
`metadata.capability` (ADR-110) names owned and consumed policies.
Neither one names the files a skill hands to the next skill.

The lifecycle order spec, plan, build, test, review, ship exists only in prose.
Each description says "run it after X".
No skill states the artifact its successor reads, or where it lives.
The `spec` template says downstream skills read its ontology and data model.
No check can fail when that contract breaks.

Five skills carry free-form `metadata.inputs` and `metadata.outputs` lists.
Measured on 2026-11-19 at `ae5acffcb`: 5 of 110 shipped skills carry them.
They are `adr-generator`, `adr-review`, `retrospective`, `skill-bootstrap`, and `skillforge`.
No script reads them. None is a lifecycle skill.
The entries mix artifacts, user arguments, and directory names.
`skillforge` lists `references/` and `scripts/` as outputs.
`adr-review` and `skillforge` both list `recommendations`.
A query cannot tell which `recommendations` a consumer means.

## Decision

### 1. Typed artifact declarations under `metadata`

`metadata.outputs` and `metadata.inputs` become lists of mappings.
No new top-level key is added. No manifest is added.

```yaml
metadata:
  inputs: [{artifact: requirements-spec, required: false}, {artifact: change-request, source: user}]
  outputs: [{artifact: execution-plan, path: plans/active/}]
```

An output entry has `artifact` and an optional `path`.
An input entry has `artifact`, an optional `source`, and an optional `required`.
`source` is one of `skill`, `user`, or `repo`. The default is `skill`.
`required` is a boolean. The default is `true`.
`artifact` matches `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`.
Any other key is a defect.
The gate checks types first: `inputs` and `outputs` are lists of mappings.
`artifact`, `path`, and `source` are strings, and `required` is a boolean.
A wrong type is a defect, not a crash.
Every pattern applies with `re.fullmatch`, so a trailing newline fails.

`path` is relative to the artifact root, which `artifact_dir` in `lib/paths.py` resolves.
The root defaults to `.project-toolkit/`, and `AI_AGENTS_ARTIFACT_ROOT` moves it.
`path` matches `^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*/?$`.
That grammar rejects `..`, a leading `/`, `\`, drive letters, `~`, `$`, and control characters.
An output with no `path` is not a file under the artifact root.
It is returned in the conversation, written to git, or placed where the skill decides at run time.
The gate never opens, creates, or writes a declared path.

A declared input is data, whatever its `source`.
A declaration grants no authority. `untrusted-content-handling` still applies to its content.

The gate parses frontmatter with `instruction_budget_globs._UniqueKeySafeLoader`, so a duplicate key fails.
`yq --front-matter=extract` is a read-only query aid, never the enforcement path.

### 2. One producer per artifact

An artifact name has exactly one producing skill, across shipped and repo-local skills.
This mirrors the one-owner rule of ADR-110.
Generic names such as `recommendations` must become specific names.
A skill that edits its input in place declares no new output for that edit.
A skill that also writes the same kind of thing leaves it undeclared rather than claim a second producer.

### 3. Every skill-sourced input resolves

An input with `source: skill` must name an artifact some skill produces.
A shipped skill's input must resolve to a shipped producer.
A skill is shipped unless its template sets `metadata.distribution: repo-local`.
`user` inputs come from the request. `repo` inputs come from repository state.

### 4. The lifecycle order follows the data

This change adds `LIFECYCLE_ORDER` to `skill_routing_model.py`.
`LIFECYCLE_SKILLS` derives from it.
In this record a lifecycle skill is a member of `LIFECYCLE_ORDER`.
It is not any skill whose `routing.role` is `lifecycle`.

Each skill's outputs are credited to at most one lifecycle skill.
A lifecycle skill is credited with its own outputs.
Any other skill walks its `routing.invoker` chain one step at a time.
The walk stops at the first lifecycle skill and credits the outputs to it.
It ends with no credit at `autoplan`, `user`, `harness`, an agent, or a name that is not a skill.
A repo-local skill never credits a shipped lifecycle skill.
A shipped skill's walk ends with no credit at its first repo-local invoker.
If the walk revisits a skill, the revisited segment is a cycle.
A cycle is a defect when a skill inside that segment declares outputs.

`spec-generator` (invoker `spec`) credits `spec`.
`execution-plans` (invoker `plan`) credits `plan`.

Each lifecycle skill after `spec` must declare an input credited to an earlier lifecycle skill.
An input with `required: false` counts for that rule.
No lifecycle skill may require an artifact credited to a later lifecycle skill.
Only inputs with `required: true` count for that rule.
A data edge need not join neighbors.
`review` reads the build's change and the spec, not the test report.
The record keeps that truth rather than invent a test-to-review input.

### 5. Lifecycle skills carry a checked Handoff line

Each lifecycle skill has a `## Handoff` section with one line of fixed shape:

```markdown
## Handoff

Writes: `execution-plan`. Next: `/build`.
```

`Writes:` lists backticked artifacts, or `none`.
It must name every output the skill declares itself.
It may name only artifacts credited to the skill.
So a helper that declares a new output later never forces an edit to the lifecycle skill.
`Next:` names the next lifecycle skill. For `ship` it reads `none`.
An agent that runs the skill reads its body, so the hand-off sits beside the procedure.
The template partials take no variables, so the line is written by hand.
The gate compares it with the metadata, so it cannot drift silently.

### 6. Scope of adoption

This change migrates the five existing skills to the typed shape.
It also declares data on the six lifecycle skills, `spec-generator`, and `execution-plans`.
This change declares data on those eight. Every other skill may declare later.
A skill outside the lifecycle with no `inputs` or `outputs` is not a defect.

### 7. Enforcement

A new gate, `scripts/validation/check_skill_artifact_flow.py`, enforces items 1 to 5.
It reads `templates/skills/*.SKILL.md.tmpl`, the canonical source.
It exits 0 on success, 1 on a violation, and 2 on a configuration error.
It prints the number of skills and declarations it examined.
`--report` prints artifacts with no consumer, which is evidence and not a defect.
`--format json` prints the full graph for queries.
The gate runs in `pre_pr.py`.

## Routing changes in the same change, outside this record

Two report-only evidence changes amend DESIGN-036, not this record.
Reachability credits a front door when the resolver routes one of its intents to it.
A phrase report lists description trigger phrases the resolver cannot route.
DESIGN-036 rejected refusing on prose, so both stay report-only.

Data fixes ship with them.
`pr-review` becomes a routed front door, which breaks the `pr-review` and `pr-autofix` invoker cycle.
The six phrases that miss today gain matching intents.
Four shipped skills keep their repo-local invokers.
PR #5922 set those invokers on 2026-09-24.
PR #6273 marked their triggers repo-local on 2026-10-11.

## Prior Art Investigation

ADR-107 lists inputs and outputs as part of a skill's semantic contract.
It places that contract in the canonical file and forbids a second registry.
This record fills those fields in the canonical file.

ADR-110 owns `metadata.capability` and closes its key set.
Adding `produces` and `consumes` there would amend ADR-110.
The maintainer chose the existing `inputs` and `outputs` keys instead.

DESIGN-036 owns the routing roles and reports reachability rather than refuse.
`git log -S` shows the `pr-review` and `pr-autofix` cycle came from PR #5922.
That PR classified all skills at once and gave no reason for the cycle.

## Rationale

| Alternative | Benefit | Cost | Decision |
|---|---|---|---|
| Keep free-form string lists. | No migration. | Nothing can check or query them. | Rejected. |
| Add `produces` and `consumes` to `capability`. | One block per skill. | Amends ADR-110's closed key set. Mixes policy and data. | Not selected. |
| Add a manifest of artifacts. | One place to read. | A second registry, which ADR-107 forbids. | Rejected. |
| Type the existing `inputs` and `outputs`. | Reuses five existing declarations. Queryable with `yq`. | Migrates five skills and adds eight. | Selected. |
| Generate the Handoff line. | No drift by construction. | Partials take no variables today. | Deferred. |
| Drop the Handoff line. | No second copy of the data. | The hand-off stays invisible in the body an agent reads. | Rejected. |

## Consequences

A reader can list a skill's inputs and outputs with one `yq` query.
A rename of an artifact fails the gate until every consumer follows.
The lifecycle order becomes checkable from data, not prose.
A stale declaration is worse than none. Declare only what the body states.
Some writers stay undeclared because of the one-producer rule.
The graph is therefore a lower bound on real data flow.

The byte budgets are tight.
At `ae5acffcb` on 2026-11-19, rendered `review` is 24443 bytes and `ship` is 24456.
The `SKILL.md` cap is 24576 bytes.
Instruction Bytes fixtures F1, F2, and F6 load `review`. F6 had 29 bytes of headroom.
A PR that grows a fixture must leave 100 bytes free, so `review` cannot grow at all.
Declarations use flow-style YAML to stay short.
`review` and `ship` offset their growth by removing duplicated text in the same change.
No ceiling is raised.

### Reversibility

Removing the gate restores current behavior.
The typed declarations are inert data without the gate.
No data migration or installed-plugin change is required.

## Impact on Dependent Components

| Component | Impact | Action |
|---|---|---|
| `templates/skills/*.SKILL.md.tmpl` | Direct | Typed `inputs` and `outputs`; required on eight skills |
| `scripts/validation/skill_routing_model.py` | Direct | Gains `LIFECYCLE_ORDER` |
| `scripts/validation/check_skill_artifact_flow.py` | New | Enforces items 1 to 5 |
| `scripts/validation/pre_pr_sequence.py` | Direct | One new gate row |

## Confirmation

The new gate runs over the full corpus and prints its examined counts.
Tests cover each invariant with a passing and a failing fixture.
`eval_autoplan_routes.py` scored 38 of 38 at `ae5acffcb`; it must stay at 100 percent.

## Related Decisions

- ADR-107: canonical skill contracts and harness projections.
- ADR-110: capability ownership DAG.

## References

- `.project-toolkit/specs/design/DESIGN-036-skill-routing-roles.md`
- `.project-toolkit/specs/requirements/REQ-039-autoplan-long-tail-resolver.md`
- `tests/evals/autoplan-routes/routes.json`
