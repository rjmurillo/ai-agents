# Feature training

Training for the features v0.7.0 ships. Each unit is a short tutorial that ends in a result you can check, or a how-to page for one task.

This folder is the source of truth. The GitHub wiki is a read-only mirror of it. Edit pages here, in a pull request. A wiki edit is overwritten on the next publish.

## Reading order

Start with the migration and install units if you are moving to v0.7.0. The rest can be read in any order.

Each entry names the issue that writes the page and who the page is for. An entry shown as plain code has no page yet. When a page lands, its pull request turns the code into a link.

- `migrate-v0-6-to-v0-7.md` (#7203): moving from v0.6.0 to v0.7.0. For anyone with an existing install.

- `install-on-every-host.md` (#7204): install and verify the toolkit on Claude Code, Codex, Cursor, Grok Build, Pi, Hermes, and Muse. For new users.

- `lifecycle-and-autoplan.md` (#7205): the spec to ship lifecycle and `/autoplan` routing. For contributors.

- `review-and-pr-feedback.md` (#7206): the review and PR feedback loop with `/review`, `/pr-review`, and pr-autofix. For contributors.

- `local-gates-and-hooks.md` (#7207): local gates with Lefthook, and what to do when a hook blocks. For contributors.

- `build-and-improve-skills.md` (#7208): skillforge, skillify, skillopt, skill-bootstrap, and skill-doctor. For skill authors.

- `safe-agent-actions.md` (#7209): decision briefs, destructive-change safety, and evidence provenance. For everyone who runs agents.

- `memory-and-learning.md` (#7210): memory with Serena, the retrospective nudge, and reflect. For everyone who runs agents.

- `template-first-authoring.md` (#7211): edit templates, then render generated files. For contributors.

- `maintainer-operations.md` (#7212): agent workflow approval, the promotion gate, ruleset drift, and releases. For maintainers.

- [Measure agent quality with evals and benchmarks](measure-agent-quality.md) (#7213): evals and benchmarks. For maintainers and skill authors.

- `github-skill-scripts.md` (#7214): how-to for the github skill scripts. For contributors.

## Page layout

Copy [`_template.md`](_template.md). Every page has these five headings, in this order, and no others:

1. Goal
2. Before you start
3. Steps
4. Check your result
5. Next

The Goal states the result up front. Check your result proves it with one command or observation. Next links the following page and lists the reference sources the page relies on.

## Conventions

These rules apply to every page. The publisher enforces the ones marked (enforced).

- **Flat folder (enforced).** Pages sit directly in `docs/training/`. No sub-directories, because the wiki has none.
- **Naming (enforced).** `kebab-case.md`: lowercase letters, digits, and hyphens. Name the topic, not the issue number. Use the file names in the list above.
- **Index (enforced).** Every page must be linked from this file. The order of links here is the order of the wiki sidebar. A page that this file does not link fails the publisher.
- **No front matter (enforced).** Do not start a page with `---`. The wiki shows it as text. Put the audience and issue number in this index instead.
- **Title.** The first line is one `#` heading that states the outcome. The sidebar uses it.
- **Files starting with `_` are not published.** `_template.md` is the only one today.
- **Links.** Use relative links. Link to a page as `other-page.md`, with an optional `#anchor`. Link to repo files, such as a skill, ADR, or script, with a relative path like `../../scripts/ci/publish_wiki.py`. The publisher turns repo links into absolute GitHub links. A link to a file that does not exist fails the publisher (enforced).
- **Link, do not copy.** Reference text has one owner: the skill, ADR, or script. Link to it.
- **Commands.** Run every command on `main` before you merge. Paste the output you got. A command a page asks the reader to run uses `uv run python <script>`, never bare `python3`, so a clean checkout has the dependencies. CI workflow steps are exempt when the script uses only the standard library.
- **Voice.** Follow [`docs/release-notes-styleguide.md`](../release-notes-styleguide.md): "you" and "we", short sentences, about a grade 9 reading level, and no em or en dashes.
- **Code fences.** Give every fenced block a language, such as `bash` or `text`.

## Add a page

1. Copy `_template.md` to the file name listed above.
2. Fill in the five sections. Run each command and paste the real output.
3. In this file, change your entry from plain code to a link: `[Title](your-page.md)`. Keep the entry where it is.
4. Preview the wiki output without pushing:

   ```bash
   uv run python scripts/ci/publish_wiki.py --dry-run
   ```

   The dry run prints the planned page list and the wiki diff. It fails if a page is missing from this index or a link is broken.
5. Open a pull request. Use `Fixes #<your issue>`.

## How the mirror works

A workflow, [`publish-wiki.yml`](../../.github/workflows/publish-wiki.yml), runs on a push to `main` that changes `docs/training/`, the two publisher scripts, or the workflow file. It calls [`scripts/ci/publish_wiki.py`](../../scripts/ci/publish_wiki.py). The script:

- Turns this file into the wiki `Home` page, with a banner that says the wiki is a mirror.
- Publishes every other page under its file name without `.md`.
- Rewrites relative links to wiki links, and repo links to GitHub links.
- Writes `_Sidebar.md` in the order of the links in this file.
- Deletes every top-level Markdown page in the wiki that this folder does not produce.
- Makes no commit when nothing changed.

To plan a publish by hand, start the workflow with **Run workflow** and keep `dry_run` on. The run needs no credential and prints the planned diff. A run with `dry_run` off is skipped unless it starts from `main`.

### One-time setup for the wiki

- The wiki Git repo does not exist until a person creates the first page in the GitHub UI (Wiki tab, Create the first page). Until then the workflow reports `SKIP` and publishes nothing.
- Restrict the `wiki-publish` environment to the `main` branch (Settings, Environments, Deployment branches and tags). The workflow only publishes from `main`, and this setting is the second control that keeps the credential away from other branches.
- The workflow pushes with the secret `WIKI_PUSH_TOKEN` when the `wiki-publish` environment has it, and with the workflow token otherwise. If the first publish reports `BLOCKED: auth`, add `WIKI_PUSH_TOKEN` as a secret of the `wiki-publish` environment: a personal access token that can write to the repository contents.
