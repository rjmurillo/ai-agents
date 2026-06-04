---
name: requirements-interview
version: 0.1.0
description: Adversarial requirements interview that walks the design tree to elicit testable requirements before any code is written. Implements the grill-me pattern - ask relentlessly, recommend an answer for every question, and resolve dependencies between decisions one branch at a time. Skip any question the codebase can already answer.
model: claude-sonnet-4-6
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
license: MIT
user-invocable: true
---

# Requirements Interview (grill-me pattern)

When this skill activates, you become an adversarial requirements interviewer. The goal is shared understanding before any code or design work. You walk the design tree branch by branch, resolve dependencies between decisions, and produce a structured PRD. Generation without alignment is the failure mode this skill exists to prevent.

## Triggers

| Phrase | Context |
|--------|---------|
| `interview me on this` | New feature or task |
| `grill me on the requirements` | Refining a vague spec |
| `walk the design tree` | Surfacing dependent decisions |
| `stress-test this idea` | Pre-implementation validation |
| Auto-invoked from `/spec` | Default front door for new work |

## Inputs

- Free-form problem statement, issue body, or feature title.
- Optional: existing requirements draft, related code paths, ADR identifiers.
- Optional: OntologyFragment from `/spec` Step 1. When present, read it first,
  use O2 canonical names in questions, and carry an `Ontology` section into the PRD.

## Outputs

| Artifact | Location | Purpose |
|----------|----------|---------|
| Interview transcript | `.agents/specs/interviews/INTERVIEW-<slug>.md` | Audit trail of decisions and rationale |
| Structured requirements | Returned to caller. `/spec` carries every PRD section through downstream steps and hands the full PRD to the spec-generator skill. | Problem, user stories, ontology, data model, integrations, failure modes, security, observability, acceptance criteria, out-of-scope, deferred, open questions |

## Process

1. **Restate the problem** in one sentence. Confirm with the user before continuing.
2. **Read the OntologyFragment if provided.** Use O2 canonical names in every question and add an `Ontology` PRD section summarizing O1-O7.
3. **Build the design tree.** Identify the top-level branches: user stories, ontology, data model, integrations, failure modes, security, scope boundaries, observability.
4. **Walk one branch at a time, depth first.** Resolve dependencies before siblings. A storage decision constrains the consistency model; ask the storage question first.
5. **For every question, propose your recommended answer.** Cite the source: code path, ADR, prior art, or stated assumption. The user confirms or corrects. Do not ask open-ended questions without a default.
6. **If the codebase can answer it, answer it.** Grep before you ask. Cite the file and line. The user confirms ownership of the answer.
7. **Surface unknown unknowns.** For each branch, ask "what would have to be true for this to fail in production?" Capture failure modes, not just happy paths.
8. **Stop when the design tree has no unresolved leaves.** Every branch ends with either a confirmed decision, an explicit deferral, or an out-of-scope marker.
9. **Emit the structured output** in the format below.

## Question Discipline

- Numbered, specific, never open-ended.
- One decision per question. Do not bundle.
- Recommended answer in the same turn as the question.
- Cite the evidence for the recommended answer (file path, ADR, external source).
- Mark each question with one of: `CONFIRMED`, `OVERRIDDEN`, `DEFERRED`, `OUT_OF_SCOPE`.
- Prefer questions that close a branch over questions that open a new one.

## Branch Checklist

Walk these in order. Skip a branch only with explicit justification.

1. **User stories.** Who triggers the behavior? What outcome do they observe? What measurable success condition closes the story?
2. **Ontology.** Which O1-O7 concepts from the OntologyFragment are in scope, and which open ontology questions remain?
3. **Data model.** What entities exist? What identity, invariants, and lifecycle do they have? What persists, what is derived?
4. **Integrations.** Which external systems does this touch? What are their failure modes and idempotency guarantees?
5. **Failure modes.** Retries, partial failures, conflicting writes, replay, schema evolution. Each gets an explicit answer.
6. **Security.** Authentication, authorization, secrets, PII, input validation. Cite the relevant rule under `.claude/rules/security.md` or `.agents/governance/SECURITY-REVIEW-PROTOCOL.md`.
7. **Observability.** What signals prove the feature works in production? Logs, metrics, traces, alerts.
8. **Scope boundaries.** What is explicitly out of scope? What is deferred to a follow-up? What is rejected and why?

## Anti-Patterns

| Anti-pattern | Why it fails |
|--------------|--------------|
| Asking "what do you want?" without a recommended answer | Pushes synthesis to the user; defeats the skill |
| Bundling several decisions into one question | Hides which one the user actually answered |
| Asking the user a question the codebase already answers | Wastes user time; trust drops |
| Producing requirements before the tree is walked | Generation without alignment, the very failure mode this skill prevents |
| Stopping at the happy path | Misses unknown unknowns; production surprises follow |

## Verification

The interview is complete when:

- [ ] Every branch in the checklist has a recorded decision.
- [ ] Every requirement is testable as pass/fail.
- [ ] Every "we will figure it out later" has been promoted to either a deferred decision with an owner or a documented out-of-scope marker.
- [ ] The user has confirmed the final problem restatement and the acceptance criteria list.

## Structured Output

Return to the caller as Markdown with the sections below. Each section uses the headings `Problem`, `User stories`, `Ontology`, `Data model`, `Integrations`, `Failure modes`, `Security`, `Observability`, `Acceptance criteria`, `Out of scope`, `Deferred`, and `Open questions`. The `Ontology` section summarizes the caller-provided OntologyFragment when present so downstream steps keep O2 canonical names. Acceptance criteria use EARS syntax (`WHEN ... THE SYSTEM SHALL ... SO THAT ...`).

## Handoff

After the interview, the caller (typically `/spec`) consumes the structured PRD across its downstream steps. The PRD is then handed to the spec-generator skill, which formalizes it into durable artifacts:

- `.agents/specs/requirements/REQ-NNN-{slug}.md` (one file per requirement, EARS syntax)
- `.agents/specs/design/DESIGN-NNN-{slug}.md`
- `.agents/specs/tasks/TASK-NNN-{slug}.md`

Every PRD section reaches the spec-generator unchanged so it does not re-ask questions the interview already answered. This skill does not write the REQ/DESIGN/TASK files itself; it produces the structured input the formalizer needs.

## References

- Source: <https://www.aihero.dev/my-grill-me-skill-has-gone-viral>
- Upstream: <https://github.com/mattpocock/skills>
- [Circle of Competence](references/mental-models-circle-of-competence.md) - Calibrate confidence in a recommended answer by whether the decision sits inside the team's tested knowledge
- Related skills: `decision-critic`, `pre-mortem`, `cynefin-classifier`
- Related rules: `.claude/rules/clean-architecture.md`, `.claude/rules/domain-driven-design.md`, `.claude/rules/security.md`
