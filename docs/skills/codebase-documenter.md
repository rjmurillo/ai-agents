# codebase-documenter

Drops documentation starters into a project: a README, an architecture doc, an API reference, and a code comment standard. Each starter has bracketed placeholders your team fills in. The skill does not write prose for you.

## When to use it

- A repository has no `README.md`, `ARCHITECTURE.md`, or API reference and you need a skeleton.
- A team has no tech writer and wants documented standards next to the templates.
- You need a starting point for code comment conventions in a polyglot project.
- Trigger phrases: `scaffold project documentation`, `bootstrap docs for new codebase`, `add starter README`, `set up documentation standards`, `document this codebase from scratch`.

## When not to use it

- Docs exist and you want to check accuracy, find missing docstrings, or audit drift: use [`doc-accuracy`](doc-accuracy.md) instead.
- You want narrative prose for an existing component: use the [`explainer`](../agents/explainer.md) agent instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:codebase-documenter`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the codebase-documenter skill to scaffold a README and an ARCHITECTURE doc for this repository.
```

The skill confirms the target directory, asks before it overwrites any existing doc, and copies the templates. You end with files full of `[Like this]` placeholders.

## What you get

| Template | Output location (default) | Purpose |
| --- | --- | --- |
| `README.template.md` | `README.md` | Why, quick start, structure, common tasks, troubleshooting |
| `ARCHITECTURE.template.md` | `ARCHITECTURE.md` | System overview, components, data flow, decisions, failure modes |
| `API.template.md` | `docs/API.md` | API reference per endpoint with conventions and examples |
| `CODE_COMMENTS.template.md` | `docs/standards/CODE_COMMENTS.md` | Docstring and inline comment standards across languages |

The skill creates parent directories such as `docs/` and `docs/standards/` before it copies into them. It also points your team at two reference guides for voice and visual standards.

## Advanced use

The skill only scaffolds. It never infers project specifics, so it leaves placeholders in the `[Word or short phrase]` form for a person or a downstream skill to fill. It validates user-provided paths against path traversal.

Its own checklist for the result: balanced code fences with a language on the opener only, active voice, no marketing language, and diagrams only where they reduce ambiguity.

Chaining: [`world-model-diagnostic`](world-model-diagnostic.md) points here for an engineering-org documentation pass after the diagnostic. After you fill the templates, run [`doc-accuracy`](doc-accuracy.md) to verify claims against code.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`doc-accuracy`](doc-accuracy.md): verifies the docs after you fill them in.
- [`world-model-diagnostic`](world-model-diagnostic.md): invokes this skill for a documentation pass.
- [`explainer`](../agents/explainer.md): writes narrative prose for a component.
- Source: [`SKILL.md`](../../src/claude/skills/codebase-documenter/SKILL.md)
- Voice and structure: [`documentation_guidelines.md`](../../src/claude/skills/codebase-documenter/references/documentation_guidelines.md)
- Diagrams and callouts: [`visual_aids_guide.md`](../../src/claude/skills/codebase-documenter/references/visual_aids_guide.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
