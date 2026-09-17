# Unicode dash guards only see markdown, and only in the diff

The em dash and en dash prohibition in `.claude/rules/universal.md` binds every
authored surface, including code comments and prompt strings. Both enforcement
points are narrower than the rule, on two independent axes.

## Axis 1: file type

- `lefthook.yml` runs the `staged-dashes` job with `glob: "**/*.md"`.
- `scripts/validation/checks_dash.py` filters candidates with `p.endswith(".md")`.

So a `.py`, `.yaml`, or `.json` file under a shipped plugin root can carry a
prohibited dash forever and no commit-time guard objects. Issue #4079 found five
such dashes inside `planner.py` prompt strings that get emitted to models at
runtime, plus three in comments and docstrings across `run_report.py`,
`get_pr_review_threads.py`, and `test_pr_merge_ready.py`.

`tests/test_plugin_tree_no_unicode_dashes.py` now pins the cleared state across
every file type under the four prefixes in its `_SCANNED_PREFIXES` tuple:
`.claude/`, `src/claude/`, `src/copilot-cli/`, and `.serena/memories/`. That is
a regression pin, not a commit-time guard: it catches a regression at test time,
after the author has already written the dash.

Widening the two guards past `*.md` was deliberately left out of the #4079 fix.
Measured at the time: it would immediately block edits to 117 files across
`tests/`, `scripts/`, `build/`, and `.agents/` that still carry dashes outside
the plugin roots.

## Axis 2: the scan is the branch diff, not the tree

Found 2026-09-16 at `659097d6d`. `_branch_markdown_files` in
`scripts/validation/checks_dash.py` builds its candidate list from
`git diff --name-only --diff-filter=ACMR {base_ref}...HEAD`, and returns `None`
(fail open, pass without scanning) when no base ref resolves or git fails.

A markdown file already in the tree therefore never trips the guard, no matter
how many dashes it holds, because it never appears in a diff until someone edits
it. The pin in `tests/test_plugin_tree_no_unicode_dashes.py` does not close this
for `.agents/`: its `_SCANNED_PREFIXES` tuple is `.claude/`, `src/claude/`,
`src/copilot-cli/`, and `.serena/memories/`, and none of the four is `.agents/`.

That fourth prefix cuts the other way for this file: this memory lives at
`.serena/memories/unicode-dash-guard-scope-gap.md`, so the document making the
claim above is itself inside the pinned set, unlike the `.agents/` tree the
template trap below sits in. `.serena/memories/` being covered narrows the gap
this section describes to `.agents/` and any other tree outside all four
prefixes; it does not close the gap, and it does not make `.agents/` covered.
Do not read this section as claiming a three-prefix pin; the pin is four
prefixes wide, and `.agents/` still falls outside all of them.

**The template trap.** `.agents/templates/HANDOFF.md` sat in that intersection and
carried three em dashes, on lines 1, 13 and 23. It is markdown, so axis 1 did not
save it; it was never in a diff, so axis 2 did not either; it is under `.agents/`,
so the pin did not cover it. Meanwhile
`.agents/sessions/handoffs/README.md` instructs every author to copy that template,
which means the documented convention produced a file the pre-commit hook rejects,
with no hint of why: the author never typed the character.

Measured cost: eight handoffs were drafted from it in one session and three
inherited the line 1 dash verbatim. Fixed in PR #5805 (`3c883601e`).

**Generalization.** A diff-scoped guard cannot see a violation that predates it.
Whenever such a guard is added, the tree it protects needs a one-time sweep, and
seed files (templates, scaffolds, fixtures that get copied) need it most, because
each copy re-injects the violation into someone else's diff and blames them for it.
Before assuming a guard covers a tree, check both what it filters on and what set
it draws from.

## Quotations are not exempt

Substituting a comma inside a quoted external title or passage is a misquote,
not a fix. `.claude/rules/universal.md` MUST NOT item 4 now carries the
procedure: end the quoted span before the dash, elide it with a bracketed
ellipsis, or split the quotation and carry the dash's job in your own words
outside the quotation marks.

## complete_session_log.py resolves the wrong worktree

`.claude/skills/session-end/scripts/complete_session_log.py` auto-detects the
most recent session log against the main checkout, not the worktree it runs
from. Invoked from `.claude/worktrees/<name>/` it edited a session log belonging
to a different branch in the parent checkout. Always pass `--session-path`
explicitly when working in a worktree.
