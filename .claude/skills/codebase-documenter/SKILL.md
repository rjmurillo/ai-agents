---
name: codebase-documenter
version: 1.0.0
model: claude-sonnet-4-5
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
description: "Scaffold project documentation (README, ARCHITECTURE, API, CODE_COMMENTS) from templates with documented standards. Use when bootstrapping docs for a new or under-documented codebase."
license: MIT
---

# Codebase Documenter

Generate documentation scaffolding for a project that has none, or has the wrong shape. This skill produces structured starters with bracketed placeholders the team fills in. It does not write prose for you.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `scaffold project documentation` | Generate README, ARCHITECTURE, API, code comment scaffolds |
| `bootstrap docs for new codebase` | Produce starter docs with placeholders |
| `add starter README` | Create README scaffold only |
| `set up documentation standards` | Drop standards references into the repo |
| `document this codebase from scratch` | Full scaffold pass |

## When to Use

Use this skill when:

- A repository has no `README.md`, `ARCHITECTURE.md`, or API reference, and you need a populated skeleton.
- A team is onboarding without a tech writer and wants documented standards alongside the templates.
- You need a starting point for code-comment conventions in a polyglot project.

Use a different skill when:

- Documentation already exists and you want to verify accuracy. Use `doc-accuracy`.
- You want to detect missing XML docs, docstrings, or JSDoc against the code. Use `doc-coverage`.
- README and CLAUDE.md indexes have drifted from the code layout. Use `doc-sync`.
- You want narrative prose generated for an existing component. Use the `explainer` agent.

## Boundaries

- Writes scaffolding and standards references only. Does not write narrative prose for the project.
- Placeholders use bracket convention `[Like this]` so a writer can search and replace.
- Templates must be filled in by a human or downstream skill. The skill does not infer project specifics.

## Process

1. Confirm the target directory and confirm no overwrite of existing docs without explicit user consent.
2. Copy `assets/templates/README.template.md` to `README.md` (or path the user requests).
3. Copy `assets/templates/ARCHITECTURE.template.md` to `ARCHITECTURE.md` if a separate architecture doc is wanted.
4. Copy `assets/templates/API.template.md` to `docs/API.md` (or equivalent) if the project exposes an API.
5. Copy `assets/templates/CODE_COMMENTS.template.md` to `docs/standards/CODE_COMMENTS.md` (or link from the README).
6. Point the team at `references/documentation_guidelines.md` and `references/visual_aids_guide.md` for voice and visual standards.

## Templates

| Template | Purpose |
|----------|---------|
| `assets/templates/README.template.md` | Project front door. Why, quick start, structure, common tasks, troubleshooting. |
| `assets/templates/ARCHITECTURE.template.md` | System overview, components, data flow, decisions, failure modes. |
| `assets/templates/API.template.md` | API reference per endpoint with conventions and examples. |
| `assets/templates/CODE_COMMENTS.template.md` | Docstring and inline comment standards across languages. |

## References

| Reference | Purpose |
|-----------|---------|
| `references/documentation_guidelines.md` | Voice, structure, audience framing, placeholder convention. |
| `references/visual_aids_guide.md` | When and how to use diagrams, tables, callouts. |

## Verification Checklist

- [ ] No environment-specific paths in any template
- [ ] All user-provided paths are validated against path traversal
- [ ] Bracketed placeholders match the `[Word or short phrase]` convention
- [ ] Code fences are balanced and use language identifiers on the opener only
- [ ] Voice is active, audience is the project's reader (not the documenter)
- [ ] No marketing language, weasel words, or filler
- [ ] Diagrams added only when they reduce ambiguity (see `references/visual_aids_guide.md`)

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Filling in placeholders speculatively | Produces fiction the team will rediscover and rewrite | Leave brackets; team fills in |
| Copying README content into ARCHITECTURE | Both files drift; readers cannot tell which is current | One concept per document |
| Adding diagrams for every section | Visual noise distracts from text | Diagram only where ambiguity is real |
| Long preamble before quick start | Readers leave before they reach the value | Quick start in the first screen |
