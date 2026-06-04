# OntologyFragment: spec-ontology-elicitation

Reference OntologyFragment for the `/spec` ontology elicitation feature (issue #1925).
Produced by the Step 1 ontology elicitation sub-step. It is the single source of
truth for the domain vocabulary every later spec artifact reuses. The seven sections
match the O1..O7 prompts in `.claude/commands/spec.md` Step 1.

## O1 Entities

- **OntologyFragment** (entity): the durable file at `.agents/specs/ontology/<feature-slug>.md` produced by Step 1; identified by its feature slug.
- **OntologyPrompt** (value object): one of the seven elicitation questions O1..O7; identified by its label.
- **SpecArtifact** (entity): a generated `REQ-NNN`, `DESIGN-NNN`, or `TASK-NNN` file; identified by its spec id.
- **CompletenessCheck** (entity): the verdict-producing evaluation in `.github/prompts/spec-check-completeness.md`; identified by the PR it runs against.

## O2 Ubiquitous language

- OntologyFragment is the canonical name. Retire: "ontology artifact", "ontology doc", "domain model file".
- OntologyPrompt is the canonical name for a single O1..O7 question. Retire: "ontology question".
- SpecArtifact is the canonical name. Retire: "spec file" when precision matters.
- Entity coverage and decision-rule traceability are the two canonical ontology checks. Retire: "ontology gate", "ontology lint".

## O3 Relationships

- An OntologyFragment is-composed-of seven OntologyPrompts (O1..O7).
- A SpecArtifact references-by-name the entities the OntologyFragment owns (O2 canonical names).
- A CompletenessCheck derives-from both the OntologyFragment and the set of SpecArtifacts (it cross-checks entity coverage).

## O4 Aggregate boundaries

- OntologyFragment is the aggregate root for the seven OntologyPrompts; the prompts have no identity outside their fragment and the fragment owns their consistency (all seven present, O1 names reused by O2..O7).
- SpecArtifact is its own aggregate root (REQ owns its acceptance criteria and its `## Ontology` section).

## O5 Decision rules

- Every entity named in a SpecArtifact must appear in the OntologyFragment by its O2 canonical name. Enforced at: spec-generator (Step 6) on write, CompletenessCheck (CI completeness check) on verdict.
- An empty-entity feature (O1 = none) makes entity coverage vacuously satisfied only when generated REQ, DESIGN, and TASK artifacts reference zero domain entities; the CompletenessCheck must not emit PARTIAL or FAIL for that empty-entity case. Enforced at: CompletenessCheck.
- The OntologyFragment is never a halt: a missing or trivial fragment degrades gracefully and is recorded, not blocked. Enforced at: Step 1 elicitation.

## O6 Bounded-context boundaries

- This work lives in the spec-pipeline bounded context (the `/spec` command, the spec-generator skill, the completeness-check prompt). Its model stops at the generated SpecArtifacts. The build/generation context (`build/scripts/generate_*.py`) is a separate context; the seam is the directory-copy generator that mirrors `.claude/` sources into `src/copilot-cli/skills/` and needs no translation of ontology concepts.

## O7 Open ontology questions

- Whether the OntologyFragment becomes a governed deliverable (its own validator and schema) is deferred; this milestone treats it as a workflow artifact, not a schema-validated SpecArtifact. Revisit if the fragment accumulates structured fields a linter must check.
