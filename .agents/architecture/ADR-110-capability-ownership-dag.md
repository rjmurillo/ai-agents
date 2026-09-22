---
id: ADR-110
status: proposed
date: 2026-09-22
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-03-22
---

# ADR-110: Capability Ownership and the Artifact Dependency DAG

## Status

Proposed. The record defines where capability ownership is declared and what a
gate may refuse. The gate ships with it and finds nothing yet, because no
artifact declares a capability block until TASK-040 Milestone 3 converts the
first policy.

## Evidence labels

This record uses ADR-107's four labels, and every load-bearing claim carries
one.

| Label | Meaning |
|---|---|
| `repo-observed` | Read in this repository at the cited path, at `c0b729bc3`, while drafting this record |
| `docs-say` | Asserted by a repository document or an issue, not independently reproduced here |
| `runtime-verified` | Reproduced by running the code, with the command and result recorded |
| `hypothesis` | Reasoned, not verified. Never load-bearing for a MUST |

## Context

Behavior-driving artifacts copy each other's policy. Issue #5396 names the
failure: a repository of duplicated executable policy instead of a composable
set of capabilities, where a fix lands on one copy and the siblings go stale
(`docs-say`, issue #5396).

The duplication is measurable. Thirteen authored files under `templates/` state
the same untrusted-content invariant (`repo-observed`,
`grep -rlE 'data, not instructions' templates/`). A diff of the thirteen shows
two prose variants, a generic one in eleven files and a review-specific one in
two, each carrying a shared core plus consumer-specific procedure
(`repo-observed`). Forty-two authored files restate the dash prohibition
(`repo-observed`). Nothing records which file owns either policy, so a fix to
one variant leaves the other stale.

The classification vocabulary has drifted for the same reason. `metadata.type`
carries nine distinct values across fourteen skill templates (`orchestrator`,
`operation`, `workflow`, `utility`, `router`, `knowledge`, `interceptor`,
`integration`, `generator`) (`repo-observed`). It arrived with the SkillForge
standardization in PRs #608, #626, and #760 and was never wired to a validator
(`repo-observed`, `git log -S`). `scripts/validation/skill_frontmatter.py`
checks four fields and rejects no unknown key (`repo-observed`, lines 269, 295,
312, 333).

Five issues are blocked on the mechanism this record defines: #5395, #5397,
#5398, #5399, and #5400 each state that they consume it and must not invent a
local one (`docs-say`).

Two constraints bound the solution space. Epic #5456 lists "the work creates a
new registry, evaluator, ratchet, or governance layer before deleting the
mechanism it was meant to simplify" as an abort condition (`docs-say`). ADR-109
made `templates/` the canonical author surface for skills, rules, and agents,
with generated projections under `src/claude/`, `src/copilot-cli/`, and
`.claude/` (`docs-say`).

## Decision

Behavior-driving artifacts compose a capability DAG, and each capability has one
canonical owner that declares itself in its own frontmatter. No manifest, no
second registry.

### 1. Ownership is declared in the artifact that owns the policy

A behavior-driving artifact declares its capability role inside the `metadata`
frontmatter key it already supports:

```yaml
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - untrusted-content-handling
    depends-on:
      - project-convention-discovery
    status: active
```

`metadata` is the sanctioned home for domain-specific configuration, and 37
skill templates already carry free-form keys under it with no harness warning
(`repo-observed`). No new top-level frontmatter key is introduced, and no
manifest file is created.

Each artifact class has exactly one declaration site. A skill declares in its
`SKILL.md` template, a rule in its Markdown file, and an agent in its
`*.shared.md` body rather than in either per-harness template. The per-harness
templates render beside the shared body, so a block in one of them would
declare the capability for one harness only, and a block in both would read as
two owners of one capability. The gate refuses a block found in either.

### 2. Four kinds, and the list is closed

`orchestrator`, `specialized-implementation`, `reusable-primitive`,
`cross-cutting-rule`. A validator refuses any other value and refuses any
unknown key inside the `capability` block. This is the one place the record
takes something away: the nine-value `metadata.type` vocabulary is superseded by
four checked values.

### 3. The path decides provenance, not the file

The graph reads three frontmatter classes and nothing else: a skill's
`SKILL.md`, an agent's definition, and a rule's Markdown file. Support files
beside a skill are outside it, which matters because `.claude/skills/<name>/`
holds canonical scripts and references that
`sync_claude_plugin_skill_support` copies outward
(`repo-observed`, `build/scripts/generate_skills.py:129`). Within those three
classes, a file under `templates/` is canonical and a file under `src/claude/`,
`src/copilot-cli/`, `.github/instructions/`, `.github/agents/`,
`src/vs-code-agents/`, or `.claude/` is a projection. A projection declaring
`owns` is a defect. This extends ADR-107's provenance rule
("loaded is not authoritative, and the path is not the class") to ownership
without redefining its equivalence predicate: the predicate stays in
`.agents/governance/GENERATOR-FILES.md`, and this record adds only the rule that
a projection makes no ownership claim.

### 4. Six invariants a gate may refuse

1. A capability name has exactly one canonical owner.
2. Every `depends-on` name resolves to some node's `owns` entry.
3. No node depends on a capability it owns.
4. The edge set is acyclic.
5. No projection declares `owns`.
6. `status: deprecated` requires `replaced-by`.

### 5. Adoption is incremental

A file with no `capability` block is not a node and is not a defect. The graph
grows as artifacts are converted, and the gate never blocks a file for staying
out of it. This is what keeps the mechanism from becoming its own migration
project.

### 6. Consumers keep the invariant, not the policy

A consumer that depends on a capability may keep a one-line statement of the
invariant inline. It may not restate the full policy. The one-line retention is
deliberate: a harness that does not load the owning rule still carries the
invariant, so composition never thins a safety control.

## Prior Art Investigation

### What currently exists

- `scripts/validation/skill_frontmatter.py` validates four skill fields and
  rejects no unknown key (`repo-observed`).
- `scripts/validation/check_rule_scope_keys.py` enforces the `paths:` scope key
  shape on rules (`repo-observed`).
- `scripts/validation/validate_copilot_agent_frontmatter.py` enforces `name`,
  `description`, and a closed `role` set on the Copilot agent mirror
  (`repo-observed`, lines 38 and 43).
- The `orphan-ref-validator` skill computes reference edges from specs and
  manifests to skill names and script paths (`repo-observed`, `scan.py`).
- `scripts/skill_registry.py` builds a skills-only catalog;
  `scripts/validation/agent_registry.py` parses the agent tree. Neither
  combines classes, and neither records ownership (`repo-observed`).
- No file in `scripts/validation/`, of the 130 `.py` files tracked at HEAD,
  builds an ownership or dependency graph (`repo-observed`,
  `git ls-tree -r --name-only HEAD scripts/validation | grep -c '\.py$'`).

### Historical rationale

`metadata.type` came from the SkillCreator and SkillForge standards, which
described a skill's shape for humans rather than for a gate. Nothing validated
it, so nine values accumulated. The Chesterton verdict on that field is MODIFY,
not REMOVE: the intent was right and the enforcement was missing.

### Why change now

Five issues are blocked and each would otherwise invent a local convention,
which is the mesh this record exists to prevent (`docs-say`). The measured
duplication is not shrinking: issue #5396's triage recorded zero declarations at
`8926061a1` on 2026-08-31, and the count is still zero (`repo-observed`).

## Rationale

### Alternatives considered

| Alternative | Single source of truth | Survives rename | Adds a sync obligation | Verdict |
|---|---|---|---|---|
| **`metadata.capability` in the canonical templates (selected)** | Yes | Yes, the declaration travels in the file | No | **Chosen** |
| Central YAML manifest under `config/` | No, duplicates artifact facts | No | Yes | Rejected. Epic #5456 abort condition |
| Columns on `.agents/metrics/control-plane-dispositions-v0.7.0.md` | Partly | No | Yes | Rejected. That ledger expires with v0.7.0 |
| Extend `orphan-ref-validator` | Yes | Yes | No | Rejected. It answers "does this reference resolve", not "who owns this policy" |
| External graph tooling | Yes | Yes | Yes | Rejected. Breaks the markdown-first, no-external-dependency constraint |

### Trade-offs

Reading the whole graph needs a script run, because the facts live in 170
canonical files rather than one (`repo-observed`: 111 `templates/skills/*.SKILL.md.tmpl`,
31 `templates/agents/*.shared.md`, 28 `templates/rules/*.md`). That is the price of not having a second source of truth,
and the deterministic report pays it back in one command.

## Consequences

### Positive

- One canonical owner per policy becomes checkable rather than remembered.
- Five downstream issues consume one mechanism instead of five.
- The nine-value `metadata.type` vocabulary collapses to four checked values.
- A rename cannot orphan a declaration.

### Negative

- Every converted artifact carries four more frontmatter lines.
- A stale declaration is worse than none, because it claims an ownership that
  is not real. The gate catches an unresolved name; it cannot catch a name that
  resolves to the wrong owner.

### Neutral

- Adoption is gradual, so the graph is incomplete for as long as the conversion
  takes. An incomplete graph still answers correctly for the nodes in it.

## Impact on Dependent Components

| Component | Impact | Action |
|---|---|---|
| `templates/skills/*.SKILL.md.tmpl` | Direct | Gains an optional `metadata.capability` block |
| `templates/agents/*.md` | Direct | Same block, same parser |
| `templates/rules/*.md` | Direct | Same block, same parser |
| `scripts/validation/pre_pr_sequence.py` | Direct | One new gate row |
| `.agents/governance/GENERATOR-FILES.md` | None | The equivalence predicate stays where ADR-107 put it |
| Issue #5384 | Coordination | #5384 states its format is an implementation choice and leans toward a manifest plus a reviewed override file (`docs-say`). If it instead chooses frontmatter, a routing key is a sibling under `metadata` and nothing here claims that name (`hypothesis`). This record commits #5384 to nothing |

## Implementation Notes

REQ-031, DESIGN-029, and TASK-040 carry the schema, the component design, and
the three-milestone sequence. The first conversion is the untrusted-content
policy: 13 authored locations to one canonical owner in
`templates/rules/security.md`, with each consumer keeping a one-line MUST.

## Related Decisions

- ADR-107. Canonical skill contracts and generated harness projections. Owns the
  projection equivalence predicate this record consumes.
- ADR-109. Template-first plugin distribution. Establishes `templates/` as the
  canonical author surface this record declares against.
- ADR-078. Routing and orchestration boundary. Unchanged; the graph explains
  ownership, it does not route.

## References

- Issue #5396. The capability DAG requirement.
- Issue #5384. Routing-role classification on the same frontmatter surface.
- Issues #5395, #5397, #5398, #5399, #5400. Declared consumers.
- Epic #5456. The v0.7.0 subtraction release and its abort conditions.
