# Testing Your Documentation

A page is done when a reader can follow it and get the stated result. Test that,
not only that the Markdown renders.

## Before you submit

1. **Build or preview the page** with the site's own tool. Prefer a one-shot
   build (`mkdocs build`, `docfx build`, `astro build`, or the repository's docs
   script). A preview server such as `mkdocs serve` or `astro dev` never exits:
   start it as a background process and stop it when testing ends. For a
   repository with plain Markdown, render it the way the host shows it.
2. **Check every edited link.** Run the site's link checker when it has one.
   Otherwise open each internal target and confirm it exists.
3. **Run every safe code sample and command** you added or changed, in the stated
   environment. Copy the output you show from a real run, not from memory.
4. **Run the repository's docs gates**: markdown lint, spell check, sample
   compilation, snippet tests, and any docs CI job.
5. **Check navigation**: table of contents, sidebar, index pages, and redirects
   for moved pages.
6. **Run a fresh-reader pass**: give the page, and nothing else, to a reader
   with no context (a fresh subagent works). Ask them to follow it and report
   where they had to guess. Fix each guess.

### Markdown links and style

In `rjmurillo/ai-agents`, run `check_md_links.py` from the validation scripts.
It checks only `docs/**`, skill `references/**`, and skill `SKILL.md` files under `src/claude/skills/`.
Run it with no file arguments.
A no-argument run catches new broken links, including inbound links after renames.
When every path is outside that scope, the run names the files on stderr.
The exit code stays 0.
Passing paths still reports an inbound link broken by a rename, a deletion, or a removed heading.
Use `--tree` to audit existing debt, including baseline entries.
Markdownlint checks same-file anchors and vague text such as "click here".

Run `prose_lint.py --docs-style` from the `prose-self-check` skill on every page you edited.
It reports advisory findings for headings, link text, openers, emails, and credentials.
Review changed lines when evaluating an existing page.

### Check documentation dates and versions

<!-- vendor-portability-exec: the date gate lives in this repository and is absent from a plugin install -->

Run this command from the ai-agents repository after committing documentation changes:

```bash
uv run python scripts/validation/check_doc_date_drift.py
```

The pre-PR sequence runs the same check after Measurement Anchoring.
Warnings cite both locations and suggest a replacement value.

- `header-pair`: Next Review fails to follow Last Updated or predates the commit date.
- `subject-drift`: one source has conflicting years or updated dates within its skill.
- `version-drift`: one tool has conflicting versions within its skill.
- `stale-as-of`: a verification date predates another date added within three lines.
- `adr-date`: frontmatter predates an added amendment or changed Decision section.

The pre-PR gate is advisory; the standalone command exits 1 for findings.
Use `--tree` to measure existing drift before promoting the gate.
Promotion requires removing its advisory licence and returning failure for findings.
Same-day ADR edits and distant provenance claims require manual review.

## Samples you must not run unasked

Run samples in a scratch directory. Ask the user first, or mark the sample
`NOT RUN` with the reason, when it would:

- install software or pipe a remote script to a shell;
- use credentials, tokens, or a signed-in account;
- create, change, or delete cloud resources or anything that bills;
- delete data or change state outside the workspace.

## Pick the smallest proof

| Change | Proof |
|---|---|
| Copy edit with no technical claim | Lint and a read-through |
| New or changed technical claim | The source line, test, or run that shows it |
| New or changed code sample | Compile or run it, and keep the output |
| New or changed procedure | Follow it start to finish on a clean setup |
| Moved or renamed page | Link check plus the redirect |
| Site component or theme change | The site's component tests and a rendered preview |

## Report what ran

List each check with its result: `VERIFIED`, `FAILED`, `NOT RUN`, or
`UNAVAILABLE`. A check you did not run is never "passed". If a sample needs a
service you cannot reach, say so and leave the sample marked for the maintainer.
