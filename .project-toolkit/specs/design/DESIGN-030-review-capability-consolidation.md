---
type: design
id: DESIGN-030
title: One technical-review contract, one correctness pass, one thin agent
status: draft
priority: P2
related:
  - REQ-032
  - TASK-041
  - ADR-110
created: 2026-09-22
updated: 2026-09-22
author: plan
tags:
  - review
  - capability-graph
  - agents
---

# DESIGN-030: One technical-review contract, one correctness pass, one thin agent

## Requirements Addressed

REQ-032 acceptance criteria 1 through 19.

## Components

### The contract

`.claude/skills/review/resources/technical-review.md` is a hand-maintained
support file of the `review` skill. The build mirrors it into both plugin
trees. It sits under `resources/`, not `references/`, because every file under
`references/` is auto-discovered as a Stage-2 axis and synced into a CI prompt.

### The owners

The `review` skill declares `kind: orchestrator`, owns `technical-review`, and
depends on `code-archaeology` and `untrusted-content-handling`. The
`chestertons-fence` skill declares `kind: reusable-primitive` and owns
`code-archaeology`. It depends on nothing new, so the graph stays acyclic.

### The correctness pass

`/review` step 4c dispatches `Task(subagent_type="code-reviewer")` with the
contract as the response contract. It falls back to `general-purpose` when the
harness has no such agent. The pass ends in a `VERDICT:` line that
`extract_verdict` parses, and step 7 merges it. The output table appends one
`correctness` row, so the pinned 16-row axis count does not change.

### The agent

`code-reviewer` declares `kind: specialized-implementation` and depends on
`technical-review` and `untrusted-content-handling`. It loads the contract from
the first of three candidate paths. When none resolves, it applies six
one-line invariants and says the contract was unavailable. It keeps the
canonical untrusted-content block byte-identical.

## Rejected alternatives

| Alternative | Reason rejected |
|---|---|
| New `references/correctness.md` CI axis | Adds a model call to every PR's CI gate; an operator cost decision |
| Delete `code-reviewer` | `dx-review` pins it, and three harnesses enforce its read-only tools |
| Render the contract into the agent through a partial | The contract is a skill support file, not a template; the agent loads it the way `/review` loads axis prompts |

## Verification

- `check_capability_graph.py` lists both owners and the agent edge.
- `tests/skills/review/test_technical_review_contract.py` pins the contract
  sections, the step 4c wiring, and the absence of moved doctrine in the agent.
- `tests/evals/code-reviewer-scenarios.json` carries the behavior cases.
