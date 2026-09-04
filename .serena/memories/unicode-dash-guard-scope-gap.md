# Unicode dash guards only see markdown

The em dash and en dash prohibition in `.claude/rules/universal.md` binds every
authored surface, including code comments and prompt strings. Both enforcement
points are narrower than the rule.

- `lefthook.yml` runs the `staged-dashes` job with `glob: "**/*.md"`.
- `scripts/validation/checks_dash.py` filters candidates with `p.endswith(".md")`.

So a `.py`, `.yaml`, or `.json` file under a shipped plugin root can carry a
prohibited dash forever and no commit-time guard objects. Issue #4079 found five
such dashes inside `planner.py` prompt strings that get emitted to models at
runtime, plus three in comments and docstrings across `run_report.py`,
`get_pr_review_threads.py`, and `test_pr_merge_ready.py`.

`tests/test_plugin_tree_no_unicode_dashes.py` now pins the cleared state across
every file type under `.claude/`, `src/claude/`, and `src/copilot-cli/`. That is
a regression pin, not a commit-time guard: it catches a regression at test time,
after the author has already written the dash.

Widening the two guards past `*.md` was deliberately left out of the #4079 fix.
Measured at the time: it would immediately block edits to 117 files across
`tests/`, `scripts/`, `build/`, and `.agents/` that still carry dashes outside
the plugin roots.

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
