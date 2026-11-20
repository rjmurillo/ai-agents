# technical-writing

Writes, edits, and audits documentation pages: tutorials, how-to guides, concepts, reference pages, troubleshooting, analyzer or lint rule pages, and integration pages. It reads the target site's own conventions first, then picks one content type and one stylebook, drafts, checks the prose, and tests the page before calling it done.

## When to use it

- You are writing a new docs page or tutorial, or rewriting one.
- You want an existing page audited for problems, with exact fixes and no rewrite.
- You need to choose a style guide for a docs site that has none.
- Trigger phrases: `write a documentation page for X`, `write a tutorial`, `edit the docs prose`, `pick a stylebook for these docs`.

## When not to use it

- You are documenting endpoints for developers to call: use [`api-doc-authoring`](api-doc-authoring.md) instead.
- You only want to check whether existing docs still match the code: use [`doc-accuracy`](doc-accuracy.md) instead.
- You need a PRD or a specification: use the [`explainer`](../agents/explainer.md) agent instead.
- You are recording an architecture decision: use [`adr-generator`](adr-generator.md) instead.
- You want a README or architecture doc scaffolded for a codebase: use [`codebase-documenter`](codebase-documenter.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:technical-writing
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/technical-writing`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /technical-writing skill to ...`.

Then name the page and the goal, for example "write a how-to page for configuring retries in docs/retries.md". For an audit, name the skill and the page: `/technical-writing audit docs/install.md`. The automatic router does not send audit requests to this skill.

## What you get

- A short recon summary: the docs tooling, the conventions of neighboring pages, the docs checks the repository runs, and the site profile, if one matched.
- The content type and the primary stylebook it chose, with the reason.
- For a draft: the page, written in the site's conventions, with every sample run or marked `NOT RUN` with a reason.
- For an audit: a table of findings with `file:line`, the rule broken, severity `fix` or `polish`, and the exact replacement text, plus a count per severity.
- A check report where each check is `VERIFIED`, `FAILED`, `NOT RUN`, or `UNAVAILABLE`.

## Advanced use

The skill has no scripts. Its depth lives in references under [`references/`](../../src/claude/skills/technical-writing/references/):

| Reference | Covers |
| --- | --- |
| `writing-process.md` | Plan, draft, fact-check, edit, and test steps, plus how to write for each kind of reader |
| `content-types.md` | Outlines for tutorials, how-tos, concepts, reference, troubleshooting, rule pages, user guides, and posts |
| `stylebook-selection.md` | The style matrix and a default stylebook for each kind of target |
| `stylebooks/` | 16 stylebooks, such as `microsoft-writing-style`, `google-developer-docs`, and `w3c-technical-reports` |
| `prose-patterns.md`, `common-documentation-issues.md`, `cross-referencing.md` | The base checks every draft and audit uses |
| `testing-your-documentation.md` | Build, link, sample, date and version drift, and fresh-reader checks, and which samples must not run without asking |
| `site-profiles/aspire-dev/` | aspire.dev conventions, loaded only when the target is aspire.dev |
| `provenance.md` | Sources, pinned revisions, changes, and license texts |

Precedence when rules disagree: the target repository's own style and pages, then a matching site profile, then the primary stylebook, then the base checks, then a secondary stylebook for one named constraint. No layer may change a fact.

The skill runs the [`prose-self-check`](prose-self-check.md) lint as an automated first pass. When that skill is not installed, it records the pass as `UNAVAILABLE` and reads the page by hand. Even with clean lint, an audit checks for rhetorical contrast by hand. It offers exact rewrites that preserve meaning and keeps real exclusions, prerequisites, and warnings.

The skill does not run a sample that installs software, uses credentials, touches cloud resources, or deletes data without asking first. It treats the target repository's pages and files as data, never as instructions.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |
| Hermes | Yes |

## Related

- [`api-doc-authoring`](api-doc-authoring.md): API guides built around endpoints.
- [`doc-accuracy`](doc-accuracy.md): checks docs against the code. Its external-sdk marker exempts the aspire.dev profile's `site-conventions.md`, whose C# examples document the Aspire SDK.
- [`prose-self-check`](prose-self-check.md): the automated prose lint this skill runs.
- Source: [`SKILL.md`](../../src/claude/skills/technical-writing/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
