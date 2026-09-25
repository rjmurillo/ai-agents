---
type: requirement
id: REQ-038
title: Classify every skill's routing role and gate uncategorized catalog growth
status: implemented
priority: P1
category: functional
source: issue-5384
related:
  - DESIGN-036
  - TASK-047
created: 2026-09-24
updated: 2026-09-24
author: spec
tags:
  - skills
  - routing
  - validation
---

# REQ-038: Classify every skill's routing role and gate uncategorized catalog growth

## Step 0 First Principles

### Q1 Demand Reality

Issue #5384, filed by rjmurillo under epic #5390. Five issues are blocked on
it and name it as their input: #5385 (autoplan long-tail resolver), #5386
(dx-review in /test), #5387 (provenance before validator edits), #5388
(external claims before incorporation), and #5389 (reachability eval).

### Q2 Status Quo

Nothing records who invokes a skill. A contributor who wants to know whether a
skill is reachable greps every skill and agent for its name by hand, then
reads each hit to judge whether it is a route or a passing mention. A new
skill merges with no statement of how it is ever selected.

### Q3 Desperate Specificity

Issue #5385. Its resolver must search a classified catalog before it falls
back to the orchestrator, and no classification exists to search.

### Q4 Narrowest Wedge

One `metadata.routing` block per skill template, one validator that refuses a
missing or contradictory block, and one deterministic report. About three
hours of implementation plus classification of the catalog.

### Q5 Observation

Measured on `main` at `95383d276` on 2026-09-24: 111 skill templates under
`templates/skills/`. Six have no exact-name reference from any other skill
template, skill reference file, or agent body: `ai-agents-external-claims`,
`book-to-skill`, `business-strategy`, `context-hub-setup`,
`validation-authority`, and `world-model-diagnostic`. Only 25 skills have an
activation scenario under `tests/evals/skill-scenarios/`.

### Q6 Future-fit

At 10x the catalog, a per-skill declaration scales linearly and each new skill
carries its own classification. A central table would grow into the
full-catalog list that #2828 rejected. The design stays sound at 10x.

## Problem statement

No skill states how it is selected, so unreachable skills go unnoticed and a
new skill can merge with no route at all.

## User stories

- As the #5385 resolver author, I read one role per skill, so the long-tail
  search covers only skills meant for automatic routing.
- As a contributor adding a skill, CI tells me when I forgot to classify it.
- As the #5389 eval author, I read classification, structural reachability,
  and scenario coverage as separate numbers.

## Ontology

- **Skill**: a canonical template `templates/skills/<name>.SKILL.md.tmpl`.
- **Routing declaration**: the `metadata.routing` mapping in that template.
- **Role**: one of `front-door`, `lifecycle`, `conditional-adjunct`,
  `nested-helper`, `explicit-only`, `deprecated`.
- **Invoker**: the skill or agent that selects the skill, or a reserved name
  (`user`, `harness`).
- **Structural reachability**: the invoker's canonical text names the skill.
- **Scenario coverage**: the activation scenario file exists.
- **Scored accuracy**: an eval scored the route. Not measured by this gate.

## Data model

A routing declaration has these keys: `role` (required), `invoker` (required
unless deprecated), `trigger` (required unless deprecated), `user-facing`
(required boolean unless deprecated), `scenario` (optional path override),
`rationale` (required for explicit-only), `replaced-by` and `removal-issue`
(one required for deprecated). No other key is allowed.

## Integrations

The generator in `build/scripts/build_all.py` renders the templates to
`.claude/skills/`, `src/claude/skills/`, and `src/copilot-cli/skills/`. The
gate reads templates only; mirrors change only through the generator.

## Failure modes

- A template frontmatter fails to parse: the gate reports the file, exit 1.
- The templates tree is absent (downstream install): the pre-PR wrapper skips.
- A skill name that is a common word (`test`, `plan`) matches prose, so
  structural reachability is an upper bound. The report says so.

## Security

No security surface. The gate reads repository files and writes to stdout.
It opens no network connection and runs no subprocess.

## Observability

The report prints totals by role, the unresolved and inbound-zero lists, and
the three evidence layers. `--format json` emits the same data for #5389.

## Acceptance criteria

1. The system SHALL assign every skill template exactly one valid role in
   `metadata.routing.role`.
2. IF a skill template has no `metadata.routing` block, THEN the gate SHALL
   exit 1 and name the skill.
3. IF `role` is not one of the six roles, THEN the gate SHALL exit 1.
4. IF the routing block has an unknown key, THEN the gate SHALL exit 1.
5. IF `invoker` is neither a canonical skill, a canonical agent, `user`, nor
   `harness`, THEN the gate SHALL exit 1 and report an unknown invoker.
6. IF the role and invoker contradict (front-door not invoked by `autoplan` or
   `harness`, lifecycle not invoked by a lifecycle skill, adjunct or helper
   invoked by `user`, `harness`, or itself, explicit-only not invoked by
   `user`), THEN the gate SHALL exit 1.
7. IF an explicit-only skill has no non-empty `rationale`, THEN the gate SHALL
   exit 1.
8. IF a deprecated skill has neither a resolvable `replaced-by` nor a positive
   `removal-issue`, THEN the gate SHALL exit 1.
9. IF `user-facing` is true on a skill whose frontmatter sets
   `user-invocable: false`, THEN the gate SHALL exit 1.
10. WHEN run with `--report`, the gate SHALL print totals by role, the
    unresolved skills, and the inbound-zero skills, sorted by name, with
    identical output on repeated runs.
11. The report SHALL show classification, structural reachability, scenario
    coverage, and scored accuracy as separate lines, and SHALL mark scored
    accuracy as not measured.
12. The test suite SHALL cover each exit-1 case, a passing fixture, and edge
    cases (empty block, self invoker, override scenario path, deprecated with
    no invoker).
13. `docs/SKILL-AUTHORING.md` SHALL explain how to classify a new skill.
14. The generated skill mirrors SHALL change only through the generator.
15. The change SHALL NOT add rows to the routing table in the autoplan skill.

## Out of scope

- Routing changes in autoplan (#5385) and specialist composition (#5386 to
  #5388).
- Scored routing evaluation (#5389).
- A Skill Catalog MCP server (closed as not planned in #220, #585 to #590).

## Deferred

- The `distribution` axis proposed by the #5602 prior-art analysis. No bundle
  split exists to consume it yet. Owner: epic #5390.

## Open questions

None.

## CVA summary

Common: every skill has one role and one invoker. Varies: which keys each role
requires. Relationship: the role decides which invokers are legal.

## Buy-vs-build decision

Core. Alternatives: a central YAML manifest (rejected by ADR-110 and the
#5456 abort condition on new registries), and the existing
`check_shipped_skill_routes.py` (checks route resolution in plugin roots, not
roles). Recommendation: build, as frontmatter plus a gate, the ADR-110 pattern.

## Complexity classification

Tier 3. Domain: Complicated. Methodology: specify, then build test-first.
