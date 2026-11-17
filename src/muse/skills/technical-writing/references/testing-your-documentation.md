# Testing Your Documentation

A page is done when a reader can follow it and get the stated result. Test that,
not only that the Markdown renders.

## Before you submit

1. **Build or preview the page** with the site's own tool (for example
   `mkdocs serve`, `docfx`, `astro dev`, or the repository's docs script). For a
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
