---
paths:
  - "templates/agents/**"
  - "templates/skills/**"
  - "src/claude/skills/**"
  - ".claude/skills/**"
  - "src/claude/agents/**"
  - "src/copilot-cli/agents/**"
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
and no README row. The gates below block those misses. No script can tell
whether a page's wording is still true, so a source change needs a page edit
or a recorded review.

| Source | Page |
|---|---|
| `templates/agents/<name>.shared.md` | `docs/agents/<name>.md` |
| `src/claude/skills/<name>/` (shipped) or `.claude/skills/<name>/` (repo-local) | `docs/skills/<name>.md` |

## MUST

1. **Add, remove, or rename the page in the same PR.** When a change adds,
   removes, or renames an agent or skill, make the same change to its page and
   to its row in `docs/agents/README.md` or `docs/skills/README.md`.
2. **Review the page whenever the source changes.** A change to a skill's
   `SKILL.md`, its template, an agent template, or a rendered agent under
   `src/claude/agents/` or `src/copilot-cli/agents/` needs a same-branch
   review, made at or after each change to the source. An edit to a shared
   partial counts through each file it renders into. Whitespace-only edits
   count on neither side. Edit the page or add a
   `Docs-Reviewed: <name>[, <name>...]` trailer to a commit. For a name shared
   by an agent and a skill, use `agents/<name>` or `skills/<name>`.
   Read the page before you pick, in the same session. Edit it when a fact it states changed: the
   name, the slash command and its `project-toolkit:` form, trigger phrases,
   arguments, script names, exit codes, output paths, what it does, and when
   to use it or not. Use the trailer only when the page is still true. Never
   paste the trailer the gate prints without reading every page it names. PR
   #7572 moved PR creation from `ship` to `push-pr` and left both pages
   describing the old flow.
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

For MUST 2, run the review gate. Pre-PR runs it as
`Agent and Skill Doc Review`, and the `Check agent and skill doc review` step
in `pr-validation.yml` runs it on every pull request:

```bash
uv run python scripts/validation/check_agent_skill_doc_review.py --base-ref origin/<target>
```

`<target>` is the branch the PR targets, `main` by default. Pre-PR resolves it
from the open PR. It diffs the working tree with the fork point and reads `Docs-Reviewed:`
trailers from the commits in `<base-ref>..HEAD`. It fails for each changed
source whose page did not change and whose name no trailer lists. Its output
prints the trailer line to use after reading. Put it in the final trailer
block of a commit made after your last source change, beside
`Co-Authored-By:`; git reads no trailer from an
earlier paragraph. Commit the source change first: a trailer never clears an
uncommitted change. Then amend an unpushed commit, or add a new commit with
`git commit --allow-empty`; never force-push a shared branch. A trailer on a
commit outside the branch does not count, and neither does a trailer or page
edit older than a change it must cover. A whole skill or agent that is new
or removed is left to the page check above. One source file added or removed
for an existing skill or agent counts as a change.

The advisory freshness check names which fact changed. Pre-PR runs it as
`Skill Page Freshness (advisory)`, and it never blocks:

```bash
uv run python scripts/validation/check_agent_skill_docs.py --freshness
```

It compares each changed skill with the base ref. It warns when the
frontmatter `name` or `argument-hint`, quoted trigger phrases in
`description`, file names under `scripts/`, Exit Codes lines, or backticked
paths in `SKILL.md` changed and `docs/skills/<name>.md` did not. Use it as a
hint for what to read.

To scaffold a new skill with its page, run skillforge's `init_skill.py` with
`--docs-section "<README heading>"`.
