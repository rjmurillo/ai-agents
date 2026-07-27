---
id: ADR-088
status: proposed
date: 2026-07-27
decision-makers: []
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-088: Progressive Disclosure for Book-Derived Rules

## Status

Proposed

## Date

2026-07-27

## Context

Phase 1 of issue #3419 added the always-on instruction budget gate. The gate
showed that a single `.py` edit loaded about 218 KB of instruction text, about
54k tokens. That is roughly 27x over the AGENTS.md target that says knowledge
belongs under 8 KB and actions belong in skills.

The largest removable chunk was eight situational book-derived rules:

- `clean-architecture`
- `domain-driven-design`
- `enterprise-patterns`
- `refactoring`
- `release-it`
- `philosophy-of-software-design`
- `data-intensive-applications`
- `working-with-legacy-code`

Those rules applied to code globs, so every routine `.py`, `.cs`, and `.ps1`
edit paid for all eight books before the model knew whether the task needed
that depth. This contradicted ADR-069, which says the curated context corpus is
the product and curation matters more than bulk. It also contradicted the
upstream corpus author's task-based selection guidance: do not enable all book
rules at once, select the book reference that fits the task.

Empirical project memory also warns that agents underfollow indirection.
Passive context has higher adherence than skills when the rule is needed every
turn. That means critical every-task rules must stay inline. Situational depth
can move behind a trigger only when the trigger is precise and the everyday
synthesis remains always-on.

## Decision

Move the eight situational book-derived rules from always-on instruction files
to one progressively-disclosed skill named `software-engineering-library`.

Keep these rules always-on:

- code-quality
- pragmatic-programmer
- unified-software-engineering

Those three provide the everyday synthesis and conflict resolution for routine
engineering work. The new skill acts as a task-to-book router. It loads only
when the task needs book depth, such as architecture review, layer boundaries,
domain modeling, persistence patterns, refactoring, legacy seams, data-system
consistency, schema evolution, or production resilience.

The instruction budget ratchet is lowered in the same change. The lower ceiling
locks in the reduction and prevents the removed book corpus from silently
returning to the always-on surface.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: Eight book-derived rules lived under
  `.claude/rules/` and generated mirrored always-on instruction files for
  GitHub Copilot and Copilot CLI.
- **When introduced**: The rules were added as part of the repository's
  cross-harness instruction corpus before the issue #3419 budget gate existed.
- **Original author and context**: The rules captured useful engineering
  principles, but their path globs made them load for routine code edits even
  when the task did not need that book's depth.

### Historical Rationale

- **Why was it built this way?** Rule mirrors were the common cross-harness
  surface. Putting material in `.claude/rules/` made it available in Claude and
  Copilot without relying on a skill trigger.
- **What alternatives were considered?** The old shape chose maximum
  availability over context cost. There was no byte budget to expose the cost.
- **What constraints drove the design?** Critical project behavior must be
  present before decisions. At the time, rules were the simplest portable
  mechanism.

### Why Change Now

- **Has the original problem changed?** Yes. The instruction budget gate gives
  a measured cost: code edits loaded about 218 KB against a 220 KB ceiling.
- **Is there a better solution now?** Yes. Skills provide progressive
  disclosure: description text is always-on, the skill body loads on trigger,
  and book references load only when opened.
- **What are the risks of change?** The risk is late retrieval. A model may fail
  to trigger the skill. The mitigation is a concrete description with task
  triggers, post-investigation routing from `analyze`, and keeping the everyday
  synthesis rules always-on.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep all eight books as rules | Highest chance the model sees every book before acting | Routine code edits pay about 124 KB of avoidable instruction cost | Fails the budget goal and contradicts task-based selection |
| Create eight sibling skills | Each book has a separate trigger | Adds catalog noise and makes routing harder for agents | The user asked for one umbrella router, and one router matches task-based selection |
| Move the eight books into one skill | Cuts always-on bytes and keeps a single routing surface | Depends on trigger quality for retrieval | Chosen because the books are situational depth, not every-task policy |

### Trade-offs

This change trades passive availability for lower context cost. The trade is
acceptable because the always-needed synthesis remains in always-on rules.
The moved content is depth material for specific tasks. The new skill
description carries concrete trigger phrases so the model can retrieve it when
that depth affects a decision.

The retrieval path has two gates. Autoplan can select
`software-engineering-library` directly when the initial request names a matching
design domain. Analysis can also invoke it after investigation discovers a
condition that was not visible in the initial request, such as low coverage, old
file age, an external API call, a queue, a retry, a transaction boundary, event
ordering, schema evolution, a dependency boundary, or module interface shape.

## Consequences

### Positive

- Always-on code-extension instruction bytes drop from about 218 KB to about
  95 KB, a cut of about 57 percent.
- The budget gate ratchets down to a 99 KB ceiling for `.py`, `.cs`, and `.ps1`.
  Future PRs cannot restore the old 218 KB baseline without an explicit raise.
- Book-specific guidance now follows task-based selection. The model opens one
  reference first and adds a second only when it changes a decision.

### Negative

- The model can miss the skill trigger and lose book-specific depth on a task
  that needs it.
- Skill retrieval happens after intent classification. Critical every-task
  rules would be weaker in this shape, which is why they stay always-on.
- Activation measurement must keep proving reachability. If the rule activation
  eval reports fewer than 7 of 8 moved references passing in two consecutive
  runs, or any one moved reference has no positive activation signal in a run,
  revert this ADR's move and restore the affected guidance to always-on rules
  until the routing path is fixed.

### Neutral

- The book content is not deleted. It moves from rule bodies to
  `software-engineering-library` references.
- Generated Copilot instruction mirrors for the eight books are removed.
- Copilot CLI receives the same skill through the existing skill generator.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/rules/` | Direct | Remove the eight situational book rules | Low |
| `.github/instructions/` | Generated | Remove the eight generated book instruction mirrors | Low |
| `src/copilot-cli/instructions/` | Generated | Remove the eight generated book instruction mirrors | Low |
| `.claude/skills/` | Direct | Add `software-engineering-library` with eight references | Medium |
| `src/copilot-cli/skills/` | Generated | Mirror the new skill and references | Medium |
| `scripts/validation/instruction_budget_constants.py` | Direct | Lower code extension ceilings to 99 KB | Low |
| Plugin manifests | Direct | Bump the paired project-toolkit manifests to 0.6.141 | Low |

## Implementation Notes

The skill must remain an umbrella router, not eight sibling skills. Its
description is the always-on trigger surface, so it names concrete tasks and
file types. The reference files preserve the moved book bodies without the rule
frontmatter.

Autoplan routes initial design-depth requests to the skill. Analyze performs the
post-investigation handoff when file evidence discovers hidden trigger
conditions that front-door routing could not know.

## Related Decisions

- ADR-030: Skills Pattern Superiority.
- ADR-069: The Curated Context Corpus IS the Product, Orchestration Is Plumbing.
- Issue #3419: Instruction budget and progressive disclosure.

## References

- `memory/context-engineering-principles`: progressive disclosure and
  just-in-time retrieval.
- `claude/claude-code-skills-official-guidance`: skill description and
  references loading behavior.
- `memory/passive-context-vs-skills-vercel-research`: caution that passive
  context has stronger adherence than skills for always-needed rules.
