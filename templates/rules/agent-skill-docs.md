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
returns. No generator writes these pages. PR #7416 added `sol-loop` and
`llm-council` with no page, and PR #7424 added `technical-writing` with no page
and no README row. The pre-PR gate below now blocks those misses. It cannot
tell whether a page's wording is still true.

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

Run the gate from the repository root. Pre-PR runs it as
`Agent and Skill Reference Pages (docs/skills, docs/agents)`:

```bash
uv run python scripts/validation/check_agent_skill_docs.py
```

It reads the working tree, so it sees a new skill or page you have not
committed yet. It fails when an agent or skill has no page, a page has no
agent or skill, a README table lacks the page's row, a row links a missing
page, or a page breaks the section order in MUST 3.

For MUST 2, run the advisory freshness check. Pre-PR runs it as
`Skill Page Freshness (advisory)`, and it never blocks:

```bash
uv run python scripts/validation/check_agent_skill_docs.py --freshness
```

It compares each changed skill with the base ref. It warns when a fact
changed and `docs/skills/<name>.md` did not. Facts are the frontmatter `name`
and `argument-hint`, quoted trigger phrases in `description`, file names under
`scripts/`, Exit Codes lines, and backticked paths in `SKILL.md`. A warning
means read the page. It does not prove the page is wrong, and a clean run does
not prove the page is current.

To scaffold a new skill with its page, run skillforge's `init_skill.py` with
`--docs-section "<README heading>"`.
