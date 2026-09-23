---
type: requirement
id: REQ-032
title: Consolidate code-reviewer doctrine into the review capability graph
status: draft
priority: P2
category: functional
source: GH-5395
epic: EPIC-5456
related:
  - TASK-041
  - REQ-031
  - ADR-110
created: 2026-09-22
updated: 2026-09-22
author: spec
tags:
  - review
  - capability-graph
  - agents
---

# REQ-032: Consolidate code-reviewer doctrine into the review capability graph

## Step 0 First Principles

### Q1 Demand Reality

1. `rjmurillo` opened issue #5395 and wrote its five comments, including the
   scope corrections that moved conversation policy to #5403.
2. The 2026-08-31 fleet triage kept #5395 open as P2 and named the behavior
   inventory as the first unblocked slice.
3. ADR-110 lists #5395 as one of five declared consumers of the capability
   mechanism that #5879 and #5885 shipped.

### Q2 Status Quo

A contributor who wants to change how code review judges correctness must:

1. Edit the `code-reviewer` agent's shared body and its three partials.
2. Remember that `/review` has no correctness axis, so the edit never reaches
   `/review` runs.
3. Guess which of `analyst`, `code-quality`, `qa`, and `architect` might also
   state the same rule, because nothing records an owner.

Step 2 is the gap: `/review` never runs the caller tracing, duplicate
verification, or confidence filtering that lives only in the agent.

### Q3 Desperate Specificity

`/review` itself. Its analyst axis assigns logic bugs, caller breakage, and
concurrency hazards to no axis (`references/analyst.md`, "Scope and
Non-Overlap"), so a `/review` PASS today says nothing about correctness.

### Q4 Narrowest Wedge

One canonical technical-review contract owned by the `review` skill, run by
`/review` as an always-on correctness pass, and consumed by a thinned
`code-reviewer` agent. About 4 hours AI-assisted.

### Q5 Observation

- `.claude/agents/code-reviewer.md` holds 174 lines of review doctrine with no
  capability declaration (`check_capability_graph.py --report text` lists no
  review node at `efd148e89`).
- `select_axes.py` `ALWAYS_ON_CANONICAL = ("analyst",)`: no correctness owner.
- The Claude agent renders with no `tools:` field, so the session lists it as
  "Tools: All tools". Its read-only promise is prose on that harness.

### Q6 Future-fit

At 10x more axes the contract gets more valuable: each new axis consumes one
finding and verdict contract instead of inventing one.

## Problem statement

Review doctrine lives in an agent that `/review` never runs, so the review
orchestrator cannot judge correctness and fixes to one copy leave the other
stale.

## User stories

1. As a `/review` caller, I get a correctness verdict merged into the final
   verdict, so a PASS covers logic, callers, and edge cases.
2. As a maintainer, I edit review doctrine in one file, and the gate names its
   owner.
3. As a `dx-review` caller, the read-only reviewer I dispatch applies the same
   contract `/review` applies.

## Ontology

- **technical-review contract**: the canonical text. Owned by the `review`
  skill as capability `technical-review`.
- **correctness pass**: one `/review` Stage-2 step that applies the contract.
- **reviewer agent**: `code-reviewer`, an execution boundary. Owns nothing.
- **code archaeology**: evidence gathering. Owned by `chestertons-fence` as
  capability `code-archaeology`.
- **yell-test proposal**: a child of code-intent analysis inside the contract.
- Boundary: publication and thread conduct belong to #5403; quality principles
  to #5397 and `code-qualities-assessment`; claim checks to `doc-accuracy`.

## Data model

Capability nodes, declared under `metadata.capability` per ADR-110:

| Artifact | kind | owns | depends-on |
|---|---|---|---|
| `review` skill | orchestrator | `technical-review` | `code-archaeology`, `untrusted-content-handling` |
| `chestertons-fence` skill | reusable-primitive | `code-archaeology` | none |
| `code-reviewer` agent | specialized-implementation | none | `technical-review`, `untrusted-content-handling` |

Invariant: the graph stays acyclic, so `chestertons-fence` does not depend on
`technical-review`.

## Integrations

- `check_capability_graph.py` validates the three new nodes.
- `build_all.py` renders the templates and mirrors the new resource file into
  both plugin trees.
- CI PR-quality gate: unchanged. The correctness pass is local to `/review`,
  so no new CI prompt and no new per-PR model cost.

## Failure modes

- The agent cannot find the contract file (VS Code tree ships no skills). It
  applies its inline invariants and states that the contract was unavailable.
- The correctness pass returns unparseable output. `/review` records UNKNOWN.
- Doctrine drifts back into the agent. The contract test fails on restated
  doctrine lines.

## Security

Reviewed content stays untrusted. The contract keeps a one-line invariant and
depends on `untrusted-content-handling`; the agent keeps its byte-identical
canonical block per `templates/rules/security.md` "Approved residue".

## Observability

What proves it works: the graph report lists the three nodes and their edges,
and a `/review` output table carries a `correctness` row.

## Acceptance criteria

1. The system shall hold one technical-review contract at
   `review/resources/technical-review.md`, declared by the `review` skill as
   capability `technical-review`.
2. The contract shall state convention discovery, caller tracing, duplicate
   verification, observable-impact filtering, and untrusted content, each once.
3. The contract shall define one finding shape: location, disposition,
   evidence, impact, remediation, and confidence.
4. The contract shall approve on net code-health improvement with no blocking
   finding, and shall not require perfection.
5. The contract shall classify each finding as blocking, non-blocking, or
   polish, and preference alone shall never be blocking.
6. The contract shall rank evidence: correctness, repository rule, local
   convention, general principle, preference.
7. The contract shall evaluate necessity and design proportionality before line
   detail, and require a current consumer for each new abstraction.
8. When a diff changes concurrency-sensitive behavior, the contract shall
   require an explicit hazard check or an UNKNOWN routed to a specialist.
9. The contract shall evaluate each behavior test for the defect it catches, not
   for its existence.
10. The contract shall account for every human-authored changed line or state an
    exclusion, and partial context shall not yield PASS.
11. When a specialist risk is not evaluated, the contract shall report it as
    unverified, never as PASS.
12. The contract shall state the post-2023 prior: complexity, polish, and human
    authorship are not evidence of purpose.
13. When suspicious code is new, the contract shall trace it to AC, REQ, or
    design before inventing a rationale.
14. When suspicious existing code has no found rationale, the contract shall
    produce a yell-test proposal and leave removal to a human.
15. The `chestertons-fence` skill shall declare capability `code-archaeology`
    and shall treat git history as provenance, not intent.
16. `/review` shall run an always-on correctness pass through the
    `code-reviewer` subagent and merge its verdict.
17. The `code-reviewer` agent shall restate no doctrine the contract owns,
    beyond one-line invariants, and shall record its retention evidence.
18. The capability gate shall pass with the three new nodes and no cycle.
19. Eval scenarios shall cover the six cases issue #5395 names in its scope
    correction comment, plus caller tracing, duplicate verification,
    preference suppression, and the code-intent cases.

## Out of scope

- A new CI PR-quality axis. It changes per-PR model cost; that is an operator
  decision.
- Review-comment wording, thread conduct, and pushback: #5403.
- Enforcing a Claude `tools:` allowlist on `code-reviewer`. Removing Bash
  changes the default working-tree scope; recorded as a residual.
- Deleting `code-reviewer` (retention evidence below).

## Deferred

- Measured model-tier evidence for the `haiku` pin: owner `rjmurillo`.

## Open questions

None blocking.

## CVA summary

Common: every review surface needs scope, evidence, a finding shape, and a
verdict. Varies: the domain each axis judges and the harness that runs it.
Relationship: axes and the agent consume one contract; the orchestrator merges.

## Agent retention evidence

| Test from #5395 | Evidence | Result |
|---|---|---|
| Independent context | `dx-review` Review Gate and the new correctness pass dispatch it as a separate subagent | holds |
| Model selection | `model: haiku` with an ADR-080 cost rationale | intentional, not measured |
| Tool restriction | Copilot, VS Code, GitHub copies list read and search tools only; Claude copy has no `tools:` | holds on three harnesses |
| Handoff identity | `dx-review` pins the `code-reviewer` subagent type in a test | holds |

Decision: retain as a thin execution boundary that consumes `technical-review`.

## Buy-vs-build decision

N/A (refactor). Core-vs-context: context. The work moves existing doctrine and
consumes the ADR-110 mechanism; nothing is bought or newly built.

## Complexity classification

Tier 3. Cynefin: Complicated. Method: analyze, then act on a known pattern.
