---
type: design
id: DESIGN-029
title: Capability frontmatter contract and the graph validator
status: draft
priority: P1
related:
  - REQ-031
  - TASK-040
  - ADR-107
created: 2026-09-22
updated: 2026-09-22
author: spec
tags:
  - governance
  - capability-graph
  - frontmatter
  - validation
---

# DESIGN-029: Capability frontmatter contract and the graph validator

## Requirements Addressed

REQ-031 acceptance criteria 1 through 13, per
`.agents/specs/requirements/REQ-031-capability-ownership-dag.md`.

## Decision summary

Capability ownership lives in the artifact that owns the policy, inside the
`metadata` frontmatter key that skill templates already use. One validator
reads the three canonical template trees, derives the graph, and gates it. No
manifest file is added, because a manifest would need its own synchronization
gate and epic #5456 lists a new registry as an abort condition.

## Schema

```yaml
metadata:
  capability:
    kind: orchestrator | specialized-implementation | reusable-primitive | cross-cutting-rule
    owns: [capability-name, ...]
    depends-on: [capability-name, ...]
    status: active | sunset | deprecated | retired
    replaced-by: capability-name          # internal successor
    replacement-platform: platform-name   # external successor, with the owner below
    replacement-owner: upstream-owner
    validation: command that proves this capability still works
```

A retiring capability names where its work goes next. `replaced-by` answers
that with one internal capability. An external successor needs both halves,
because a platform with no owner names nobody to ask.

One declaration site per artifact: a skill's `SKILL.md` template, a rule's
Markdown file, and an agent's `*.shared.md` body. A capability block found in
`templates/agents/*.claude.md.tmpl` or `*.copilot.md.tmpl` is a defect, because
it would bind one harness only.

Every field is optional at the artifact level. A file with no `capability` block
is not a node, which is what makes adoption incremental. A file with a block
declares every field it uses, and the validator rejects an unknown key inside
the block so the vocabulary cannot drift the way `metadata.type` drifted.

Capability names match `^[a-z0-9-]{1,64}$`. The pattern is the same one skill
names already use, so a capability may share a skill's name without ambiguity.

## Relationship to `metadata.type`

`metadata.type` carries nine unchecked values across fourteen skill templates.
`capability.kind` replaces it with four checked values. TASK-040 Milestone 4 performs that
conversion, because epic #5456 allows a new validator only when it removes or
consolidates an existing mechanism, and this is the mechanism it consolidates.
Until a file is converted, both keys may sit side by side; the validator reads
only `capability.kind` and never infers a kind from `metadata.type`, so a stale
`type` value cannot produce a wrong edge.

## Component design

`scripts/validation/check_capability_graph.py`, one module, four functions plus
a CLI entry point. Complexity stays at or under 10 per function.

| Function | Responsibility |
|---|---|
| `collect_nodes(roots)` | Walk the canonical template trees, parse frontmatter, return one node record per file carrying a capability block |
| `build_owner_index(nodes)` | Return the owner index, reporting a duplicate owner and a projection that claims ownership |
| `check_graph(nodes, owners)` | Return findings for missing dependency, self dependency, cycle, and a consumer repeating its owner's text |
| `survey(repo_root)` | Read the trees once and return nodes, owners, and findings, so validate and report modes cannot diverge |
| `render(nodes, graph, fmt)` | Emit the deterministic report as text or JSON, sorted by capability name |

The copied-policy check compares contiguous line windows on both sides. An
earlier form collapsed the owner's lines into a set, which discarded their
order and failed a consumer whose lines merely appeared somewhere in the owner.

The cycle check is an iterative depth-first search over the adjacency list with
an explicit stack, so a deep graph cannot exhaust the interpreter stack. Nodes
are visited in sorted order, which is what makes the reported cycle stable
across runs.

Determinism comes from sorting at every boundary: files are walked in sorted
order, `owns` and `depends-on` are sorted before comparison, and the report is
emitted from the sorted structures. Two runs on unchanged input produce
byte-identical bytes, which acceptance criterion 7 asserts directly.

## Ownership and projections

The graph reads three frontmatter classes: a skill's `SKILL.md`, an agent's
definition, and a rule's Markdown file. Skill support files are outside it,
because `.claude/skills/<name>/` holds canonical scripts and references that the
build syncs outward. Within those classes, a node's canonical status is decided
by its path, not by a field it declares about itself. Paths under `templates/`
are canonical. Paths under `src/claude/`, `src/copilot-cli/`,
`.github/instructions/`, `.github/agents/`, `src/vs-code-agents/`, and
`.claude/` are projections. A
projection declaring `owns` fails the gate. This keeps ADR-107's provenance rule
intact: the class predicate decides equivalence, and this validator decides only
that a projection makes no ownership claim.

## Registration

One row in the `_SEQUENCE` table at `scripts/validation/pre_pr_sequence.py:248`,
following the shape the existing frontmatter gates use. The gate is blocking,
because every one of its findings is deterministic and has a named fix.

## Failure handling

A malformed YAML header produces a named parse error and a non-zero exit. It is
never treated as a file with no capability block, because that would let a
syntax error silently delete a node from the graph.

## Test design

Tests live at `tests/validation/test_check_capability_graph.py` and build every
fixture with `tmp_path`, so the seven required shapes are constructed in the
test rather than committed as tree files. The shapes are: valid chain, missing
dependency, self dependency, three-node cycle, duplicate owner, projection
mirroring a canonical owner, and a consumer that both depends on a capability
and repeats a run of the owner's text. The last one blocks rather than warns:
three or more consecutive shared lines totalling 120 characters or more is the
"repeated large normative block" class issue #5396 names, and a shorter overlap
is left alone so a consumer can keep the one-line invariant inline. Each
negative fixture asserts the exit code and the specific message, so a test
cannot pass for the wrong reason.

Determinism has its own test: run `render` twice over one fixture tree and
assert byte equality.

## Alternatives rejected

| Alternative | Why rejected |
|---|---|
| Central YAML manifest under `config/` | Second source of truth. Drifts on rename. Abort condition in epic #5456 |
| Columns on the v0.7.0 disposition ledger | That ledger is scoped to one release and expires with it |
| Reusing `orphan-ref-validator` | It checks that a named reference resolves, not who owns a policy. Overloading it would couple two unrelated failure classes |
| A new top-level `capability:` frontmatter key | `metadata` is already the sanctioned home for domain configuration, and a new top-level key risks harness warnings across three harnesses |

## Blast radius

Adding a nested key under `metadata` changes no rendered behavior: the build
pipeline copies frontmatter through, and no validator rejects unknown keys
today. The risk that remains is a harness that warns on unfamiliar frontmatter.
The mitigation is that `metadata` already carries free-form domain keys on 37
skill templates today with no warning, so the shape is already proven in this
repository.
