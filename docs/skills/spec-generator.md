# spec-generator

Turns a feature description into three linked spec files: requirements, design, and tasks. A bundled validator checks the frontmatter of every file, so invalid values do not ship.

## When to use it

- You have a feature description or a finished PRD and want REQ, DESIGN, and TASK files.
- You say `generate spec`, `formalize requirements`, or `create requirements/design/tasks`.
- The [`spec`](spec.md) lifecycle command reaches Step 6 (formalize PRD).

## When not to use it

- You need to decide what to build, or run the gates that come before writing: use [`spec`](spec.md) instead. It calls this skill to write the files.
- You want to interview someone to find requirements first: use [`requirements-interview`](requirements-interview.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:spec-generator formalize the password reset feature in docs/prd-password-reset.md
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/spec-generator`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /spec-generator skill to ...`.

The skill reads the bundled schema, writes the files, and runs the validator on each one. At the end you see an artifact table and the validator result for every file.

## What you get

| Tier | Format | Location |
| --- | --- | --- |
| Requirements | EARS | `.project-toolkit/specs/requirements/REQ-NNN-{kebab-case-title}.md` |
| Design | Technical spec | `.project-toolkit/specs/design/DESIGN-NNN-{kebab-case-title}.md` |
| Tasks | Atomic work items | `.project-toolkit/specs/tasks/TASK-NNN-{kebab-case-title}.md` |

The final report has:

1. An artifact table (type, id, title, location).
2. A traceability summary (REQ to DESIGN to TASK).
3. The validator result for every file.
4. An effort estimate (complexity counts and total hours).
5. A recommended next step: `critic` to review, `architect` to validate the design, or `implementer` to start `TASK-001`.

## Advanced use

### EARS requirements

Each requirement uses one behavior in this shape:

```text
WHEN [trigger]
THE SYSTEM SHALL [behavior]
SO THAT [rationale]
```

Acceptance criteria are pass/fail checkboxes. Vague words such as "appropriate" and "reasonable" fail the check.

### Allowed frontmatter values

| Field | Applies to | Allowed values |
| --- | --- | --- |
| `type` | all | `requirement`, `design`, `task` |
| `status` | requirement, design | `draft`, `review`, `approved`, `implemented`, `rejected` |
| `status` | task | `todo`, `in-progress`, `blocked`, `done`, `cancelled` |
| `priority` | all | `P0`, `P1`, `P2` |
| `category` | requirement | `functional`, `non-functional`, `constraint` |
| `complexity` | task | `XS`, `S`, `M`, `L`, `XL` |

IDs use `REQ-NNN`, `DESIGN-NNN`, and `TASK-NNN` with three digits. Design files must set both `status` and `priority`.

Task sizes: `XS` is 1 to 2 hours, `S` 2 to 4, `M` 4 to 8, `L` 8 to 16, and `XL` is 16 or more (split it before starting).

### Validator

Run it from the root of a checkout of this repository:

```bash
uv run python .claude/skills/spec-generator/scripts/validate_spec_frontmatter.py --help
uv run python .claude/skills/spec-generator/scripts/validate_spec_frontmatter.py specs/REQ-001.md specs/DESIGN-001.md
```

It takes one or more files, is read-only, and prints one `[PASS]` or `[FAIL]` line per file.

| Exit code | Meaning |
| --- | --- |
| `0` | All valid |
| `1` | One or more validation failures |
| `2` | No input, or an unreadable file |

### Ontology and when it asks

When `spec` passes an OntologyFragment, the skill uses its canonical names for entities and adds an `## Ontology` section to every requirement. It does not invent entity names. If it needs a concept the fragment lacks, it stops and asks you to extend the fragment.

For standard features (password reset, CRUD) it writes directly and flags assumptions. For a vague request such as "make it faster", it pushes back and asks for measurable targets first. For external-facing features it asks about auth, scope, rate limits, and schema versioning.

The skill treats web results, files, logs, and PR bodies as data and does not follow instructions found in them. It runs the [`prose-self-check`](prose-self-check.md) skill before emitting prose.

Reference files: [`spec-schemas.md`](../../src/claude/skills/spec-generator/references/spec-schemas.md), [`spec-step0-gates.md`](../../src/claude/skills/spec-generator/references/spec-step0-gates.md), and [`spec-prior-art-schema.md`](../../src/claude/skills/spec-generator/references/spec-prior-art-schema.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`spec`](spec.md): the lifecycle command that invokes this skill.
- [`requirements-interview`](requirements-interview.md): elicits the PRD this skill formalizes.
- [`prose-self-check`](prose-self-check.md): audits prose before it is written.
- [`critic`](../agents/critic.md): reviews the specs.
- Source: [`SKILL.md`](../../src/claude/skills/spec-generator/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
