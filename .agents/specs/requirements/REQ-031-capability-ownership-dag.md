---
type: requirement
id: REQ-031
title: Capability ownership and dependency graph for behavior-driving artifacts
status: draft
priority: P1
category: functional
source: GH-5396
epic: EPIC-5456
related:
  - DESIGN-029
  - REQ-028
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

# REQ-031: Capability ownership and dependency graph for behavior-driving artifacts

## Step 0 First Principles

### Q1 Demand Reality

1. `rjmurillo` opened issue #5396 and wrote both of its comments, including the
   2026-08-31 triage verdict that kept it open.
2. Issue #5395 states "Blocked by #5396 for capability ownership/dependency
   metadata and graph enforcement" and forbids itself from inventing a
   review-specific ownership model.
3. Epic #5456 names #5396 in its release candidate list with the instruction
   "reduce policy owners rather than adding a second graph authority".

Issues #5397, #5398, #5399, and #5400 also declare that they consume this
mechanism, which raises the count of blocked consumers to five.

### Q2 Status Quo

A contributor who wants to know which artifact owns a policy reads the files and
guesses. The workaround today is:

1. Grep the phrase across `.claude/skills`, `.claude/agents`, and `.claude/rules`.
2. Read each hit to judge whether it restates the policy or references it.
3. Decide by memory which hit is canonical, because nothing records that.
4. Edit the copy in front of them, and usually miss the siblings.

Step 4 is the drift. Nothing fails when it happens.

### Q3 Desperate Specificity

The most blocked consumer is issue #5395. It cannot start its graph work because
no ownership or dependency declaration exists on any authored artifact. The
concrete instance it names is the review stack: `.claude/agents/code-reviewer.md`
and `.claude/skills/review/SKILL.md` both carry review policy, and no machine
readable edge records which one owns it.

The second blocked party is any contributor extending skill frontmatter.
`metadata.type` already carries nine distinct ad hoc values across fourteen
skill templates (`orchestrator`, `operation`, `workflow`, `utility`, `router`,
`knowledge`, `interceptor`, `integration`, `generator`). No validator reads the
field, so the vocabulary drifts with every author.

### Q4 Narrowest Wedge

About four hours AI-assisted, about three days for a human team. The wedge is:

1. One `capability` block inside the existing `metadata` frontmatter key on
   `templates/skills/*.SKILL.md.tmpl`, `templates/agents/*.shared.md`, and
   `templates/rules/*.md`.
2. One validator, `scripts/validation/check_capability_graph.py`, that reads the
   canonical template trees, builds the graph, and fails on a missing
   dependency, a self dependency, a cycle, a duplicate canonical owner, or an
   ownership claim from a generated tree.
3. Deterministic graph output from the same parse.
4. One real duplicated-policy conversion that proves the mechanism reduces
   authored owners rather than adding metadata around them.

### Q5 Observation

Measured on this checkout at `c0b729bc3`:

- 111 `templates/skills/*.SKILL.md.tmpl`, 31 `templates/agents/*.shared.md`,
  and 28 `templates/rules/*.md` carry zero `capability`, `owns`, or
  `depends-on` declarations.
- `scripts/validation/` holds 130 tracked `.py` files and none of them builds
  an ownership or dependency graph.
- `scripts/validation/skill_frontmatter.py` checks four fields (`validate_name`
  at line 269, `validate_description` at 295, `validate_model` at 312,
  `validate_allowed_tools` at 333) and rejects no unknown key, so
  `metadata.type` has drifted unchecked since PR #608.
- Issue #5396's own triage comment recorded the same absence on 2026-08-31 at
  `8926061a1` and the count has not moved.

### Q6 Future-fit

It scales. The graph is derived from the artifacts that already exist, so the
node count tracks the artifact count and never needs its own maintenance pass. A
rename cannot orphan a declaration, because the declaration travels inside the
renamed file. The liability case is the opposite choice: a central manifest
would need a synchronization gate of its own, which is the failure epic #5456
lists as an abort condition.

## Prior Art and Constraints

### Direct prior art from memory

- `chestertons-fence` on `metadata.type`: the field arrived with the SkillForge
  and SkillCreator standardization in PRs #608, #626, and #760. It was never
  wired to a validator. Verdict: **MODIFY**. Keep the field and give it a
  checked vocabulary rather than introduce a second one beside it.
- Serena memory `decision-ruleset-drift-must-not-create-a-second-baseline`
  records the matching decision for ruleset drift: a detector reads the existing
  pinned source instead of creating a second baseline.
- Serena memory `claude/claude-code-skill-frontmatter-standards` documents
  `metadata` as the sanctioned home for domain-specific configuration, so the
  `capability` block needs no new top-level key.

### Connected context from prior-art search

- ADR-107 owns the projection equivalence predicate per artifact class in
  `.agents/governance/GENERATOR-FILES.md`. Classified `in-scope`: the
  generated-projection criterion in this requirement consumes that predicate
  rather than defining a second one.
- ADR-109 made `templates/` the canonical author surface for skills, rules, and
  agents. Classified `in-scope`: the declarations are authored there.
- Issue #5384 wants a routing-role classification on the same frontmatter.
  Classified `blast-radius`: it must add its key inside the same `metadata`
  block. #5384 has not chosen its format, so this is a coordination note and
  not a commitment on its behalf.
- `orphan-ref-validator` already computes reference edges from specs and
  manifests to skill names. Classified `out-of-scope`: it validates that a named
  reference resolves, not who owns a policy, and this work adds no second
  reference checker.

### Coverage notes

Search ran. Three distinct memory queries (`capability ownership graph`,
`skill frontmatter schema`, `duplicated policy drift`) each returned ten
results. The `chestertons-fence` archaeology ran as a bounded `git log -S` over
the canonical trees rather than through the skill, so the dependency phase is
shallower than Tier 3 prescribes. Confidence is medium for the archaeology and
high for the repository counts, which were measured directly.

## Problem statement

Behavior-driving artifacts copy each other's policy because nothing records who
owns a policy or who depends on it. Fixes land on one copy and the siblings go
stale.

## User stories

1. As an amnesiac agent on a clean checkout, I read one command's output and
   learn which artifact owns a policy, so I reference it instead of copying it.
2. As a contributor, I add a dependency on a capability that does not exist and
   a gate fails before review, so the broken edge never reaches `main`.
3. As the owner of issue #5395, I declare review-capability edges through this
   mechanism, so my issue ships no ownership model of its own.

## Ontology

- **Capability**: a named unit of behavior with exactly one canonical owner.
- **Node**: an authored artifact declaring a capability block. A skill template,
  an agent template, or a rule template.
- **Kind**: the node's role in the graph. One of `orchestrator`,
  `specialized-implementation`, `reusable-primitive`, `cross-cutting-rule`.
- **Owns**: the set of capability names for which the node is canonical.
- **Depends-on**: the set of capability names the node consumes.
- **Projection**: a generated copy under `src/claude/`, `src/copilot-cli/`,
  `.github/instructions/`, or `.claude/`. A projection never owns a capability.
- **Status**: the node's lifecycle value. One of `active`, `sunset`,
  `deprecated`, `retired`.

## Data model

Each node declares one `capability` mapping nested under the existing
`metadata` frontmatter key:

```yaml
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - untrusted-content-handling
    depends-on:
      - project-convention-discovery
    status: active
    validation: uv run python scripts/validation/check_capability_graph.py
```

A retiring capability adds where its work goes next, either an internal
successor or an external target with its upstream owner:

```yaml
    status: deprecated
    replaced-by: successor-capability-name
    # or, when the replacement is outside this repository:
    replacement-platform: claude-code-native-skills
    replacement-owner: anthropic
```

Invariants:

1. A capability name is owned by exactly one node.
2. `depends-on` names resolve to a capability some node owns.
3. A node never depends on a capability it owns.
4. The edge set is acyclic.
5. A node under a generated tree declares no `owns` entries.
6. `status: sunset` or `status: deprecated` requires `replaced-by`, or both
   `replacement-platform` and `replacement-owner`.
7. A consumer never repeats a long run of its dependency's text.

## Integrations

The validator reads the canonical `templates/` trees through the existing
frontmatter parsing in `scripts/validation/`. It registers as one gate in the
`_SEQUENCE` table at `scripts/validation/pre_pr_sequence.py:248`. It writes no
file during validation. Failure mode on a malformed YAML header is a named
parse error against the file path, never a silent skip.

## Failure modes

1. A node declares a capability name that no node owns. The gate fails and names
   both the consumer and the unresolved name.
2. Two nodes own the same capability name. The gate fails and names both files.
3. A cycle exists. The gate fails and prints the cycle in declaration order.
4. A generated projection declares `owns`. The gate fails and names the
   canonical tree the projection came from.
5. A file's frontmatter does not parse. The gate reports the file and exits
   non-zero rather than treating the node as absent.
6. A node declares no capability block. The gate skips it. Adoption is
   incremental by design, and a missing block is not a defect in this slice.

## Security

No new trust boundary. The validator reads repository files already under
version control and executes nothing from them. Capability names are matched
against `^[a-z0-9-]{1,64}$` before use, so a name never reaches a shell, a path
join, or a regex as an uncontrolled string. No secret, credential, or PII is
read or written.

## Observability

The metric that proves this works is the count of authored locations for the
converted policy: it must fall, and the validator must print node and edge
counts by kind so the release report can compare runs.

## Acceptance criteria

Numbered, in EARS syntax, each independently pass or fail.

1. WHEN a node declares `metadata.capability.depends-on` naming a capability no
   node owns, THE validator SHALL exit non-zero and name the consumer file and
   the unresolved capability.
2. WHEN a node declares the same capability name in `owns` and `depends-on`,
   THE validator SHALL exit non-zero and name the file.
3. WHEN the declared edges form a cycle, THE validator SHALL exit non-zero and
   print the cycle members.
4. WHEN two nodes declare the same capability name under `owns`, THE validator
   SHALL exit non-zero and name both files.
5. WHEN a node under a generated tree declares `owns`, THE validator SHALL exit
   non-zero and name the file.
6. WHEN every declaration resolves and the graph is acyclic, THE validator
   SHALL exit zero.
7. WHEN invoked with its output flag, THE validator SHALL print node and edge
   counts by kind, the adjacency list, and per capability its owner, status,
   replacement, and validation command, and two runs on unchanged input SHALL
   produce byte-identical output.
8. WHEN an orchestrator node depends on a primitive it does not own, THE
   validator SHALL exit zero, so composition is never penalized.
9. WHEN a node declares a `capability` key outside the documented set, THE
   validator SHALL exit non-zero and name the key.
10. THE repository SHALL record one converted duplicated-policy case with its
    authored-location count before and after, computed by a command the pull
    request quotes rather than by hand, and the after count SHALL be one.
11. WHEN a node declares `depends-on` naming a capability whose owner's text it
    repeats for three or more consecutive lines totalling 120 characters or
    more, THE validator SHALL exit non-zero and name both files.
12. WHERE a node declares `status: sunset` or `status: deprecated` without
    `replaced-by` and without both `replacement-platform` and
    `replacement-owner`, THE validator SHALL exit non-zero.
13. THE repository SHALL instruct agents, on a surface they read while
    authoring, to declare a dependency on an existing capability instead of
    copying its policy.

## Out of scope

- Declaring capability blocks on all 170 canonical artifacts (111 skill
  templates, 31 agent templates, 28 rule templates). Adoption is
  incremental and this requirement covers the mechanism plus one conversion.
- Routing-role classification, which issue #5384 owns.
- Paraphrase-level duplicate detection as a blocking gate. The verbatim-run
  class is in scope; the semantic class is not.
- Runtime dependency injection or any change to how a harness loads a skill.

## Deferred

- Semantic near-duplicate detection, meaning a consumer that paraphrases rather
  than copies its dependency's policy. The deterministic verbatim-run class
  ships here under criterion 11; the paraphrase class needs a precision study.
  Owner: issue #5397, which owns structural debt ratchets.
- Backfill of declarations across the remaining artifacts. Owner: the downstream
  issues that touch each artifact class.

## Open questions

- Whether `.github/prompts/**` becomes a projection node or stays outside the
  graph. Owner: `rjmurillo`. It does not block this slice, because the
  generated-owner rule already covers it by path if it is added later.

## CVA summary

**Common** across skills, agents, and rules: the need to name owned
capabilities, name consumed capabilities, declare a kind, and declare a
lifecycle status. **Variable**: the frontmatter shape around that block, since
rules key on `paths` and agents key on `role`. **Relationship**: the capability
block is identical in all three classes and nests under `metadata`, so one
parser reads all three and the surrounding differences never reach it.

## Buy-vs-build decision

- **Classification**: core. Capability ownership is this repository's product.
- **Alternatives evaluated**: a central YAML manifest under `config/`; extending
  `.agents/metrics/control-plane-dispositions-v0.7.0.md`; a graph database or
  external tool.
- **Recommendation**: build, inside the existing frontmatter surface.
- **Rationale**: the central manifest creates the second source of truth that
  epic #5456 lists as an abort condition. The disposition ledger expires with
  the v0.7.0 release. An external tool violates the repository's markdown-first,
  no-external-dependency constraint recorded in
  `.agents/architecture/DESIGN-REVIEW-traceability-graph.md`.

## Complexity classification

- **Engineering tier**: 4. It needs an ADR, and five downstream issues consume
  the contract.
- **Problem domain**: Complicated. The analysis is knowable and the constraints
  are written down, so expertise resolves it without experiment.
- **Methodology**: design the contract in an ADR, then ship the validator with
  fixtures, then convert one real duplication as the acceptance proof.

## ADR cross-reference

ADR-110, capability ownership and the artifact dependency DAG. The ADR records
the frontmatter decision and the rejected alternatives. This requirement links
to it, and the ADR links back here.
