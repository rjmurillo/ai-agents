---
paths:
  - "templates/agents/**"
  - "templates/skills/**"
  - "src/claude/skills/**"
  - ".claude/skills/**"
priority: high
---

# Agent And Skill Reference Pages

<!-- vendor-portability: contributor-facing rule for the rjmurillo/ai-agents repo
     itself; its subject is this repository's docs tree, which no plugin install
     carries. Paths: docs/agents/, docs/skills/, docs/agent-catalog.md -->

Each agent and each skill has one hand-written reference page. People read the
page, not the template, to learn how to start the agent or skill and what it
returns. No generator writes these pages and no gate compares them to their
source, so a change that skips the page leaves it wrong with nothing to flag it.
PR #7416 added `sol-loop` and `llm-council` with no page.

| Source | Page |
|---|---|
| `templates/agents/<name>.shared.md` | `docs/agents/<name>.md` |
| `src/claude/skills/<name>/` (shipped) or `.claude/skills/<name>/` (repo-local) | `docs/skills/<name>.md` |

## MUST

1. **Add, remove, or rename the page in the same PR.** When a change adds,
   removes, or renames an agent or skill, make the same change to its page and
   to its row in `docs/agents/README.md` or `docs/skills/README.md`.
2. **Update the page when a fact it states changes.** Facts are the name, the
   slash command and its `project-toolkit:` form, trigger phrases, arguments,
   script names, exit codes, output paths, and when to use it or not. Read the
   page before you decide. A wording change that leaves every fact alone needs
   no page edit.
3. **Keep the page shape.** A new page uses its siblings' sections in order:
   `When to use it`, `When not to use it`, `Quick start`, `What you get`,
   `Advanced use`, `Where it runs`, `Related`. Copy an existing page.
4. **Do not hand-edit `docs/agent-catalog.md`.** `build_all.py` renders it from
   `templates/agents/*.shared.md`.

## Checking

List agents and skills with no page, from the repository root. It reads the
working tree, so it sees a new skill or page you have not committed yet:

```bash
export LC_ALL=C
comm -13 <(ls docs/skills | sed 's/\.md$//' | sort) \
  <(find src/claude/skills .claude/skills -mindepth 1 -maxdepth 1 \( -type d -o -type l \) -exec basename {} \; | sort -u)
comm -13 <(ls docs/agents | sed 's/\.md$//' | sort) \
  <(ls templates/agents | sed -n 's/\.shared\.md$//p' | sort)
```

Empty output means every agent and skill has a page. It does not prove a page
is current; rule 2 is a manual check.
