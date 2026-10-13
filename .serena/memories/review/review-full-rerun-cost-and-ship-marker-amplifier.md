# /review full re-run cost: the amplifier is the /ship marker, not pr-autofix

Derived 2026-08-15 while drafting ADR-094. Saves re-deriving the call graph.

## `pr-autofix` does NOT invoke `/review`

A common (and wrong) assumption. `git grep -n '/review' .claude/commands/pr-autofix.md`
returns only prose about review *threads* plus a `PR_REVIEW_CONFIG_PATH` variable.
Its T3 and T4 tiers walk the review-thread lifecycle; they never run the axes.
Do not attribute axis-fan-out cost to pr-autofix without re-checking this grep.

## The real amplifier

`/review` runs 15 axes per invocation with **no cross-run caching**: Stage-1
`spec-compliance`, 11 Stage-2 canonical axes discovered from
`.claude/skills/review/references/*.md`, and 3 chained skills
(`code-qualities-assessment`, `golden-principles`, `taste-lints`).
See `SKILL.md` Process steps 4, 5, 7.

`/ship` requires a SHA-bound marker whose parent must be HEAD's parent:

- `.claude/skills/review/SKILL.md:164` "the marker is valid only while its
  parent (the reviewed tip) is HEAD's parent."
- `.claude/commands/ship.md:109` "Exit `1` means no marker, a stale marker, or
  new code landed after review."

So every fix commit invalidates the marker and forces a fresh 15-axis run. At
the 18 rounds recorded for PR #1965 that is 270 axis invocations. This coupling
is correct; it is just uncached.

## The hook for a fix

The marker trailer already names the axis set:
`Reviewed-By: /review@<comma-separated-axis-list> on <reviewed-tip-sha>`
(`SKILL.md:152`). Nothing reads that list as a scope claim today.
`validate_review_marker.py` only checks the SHA binding. Any scoped-review
design can hang its safety property on that existing field instead of adding
storage.

## Status

ADR-094 (`.project-toolkit/architecture/ADR-094-scoped-re-review-axes.md`) proposes
`/review --axes=<list>` that writes no marker. Status `proposed`, awaiting
human maintainer approval. `.agents/governance/CI-FEEDBACK-SUBLOOP.md` remains
non-normative; ADR-094 recommends against promoting it wholesale.

## One review axis without a Task tool

A subagent that has no Task tool cannot fan out the axes. Ten runs in the
2026-10-12 sweep fell back to a closed-loop self-review. A fresh `claude -p`
process gives a reviewer that has not seen the author's reasoning:

```bash
git diff origin/main...HEAD | claude -p --model sonnet --tools "" \
  --system-prompt-file .claude/skills/review/references/<axis>.md \
  "Review the diff on stdin."
```

Measured 2026-10-12 on Claude Code 2.1.296: with `references/security.md` and a
one-line diff that added `eval(input())`, the process returned
`VERDICT: CRITICAL_FAIL` and a CWE-95 message. `claude --help` does not list
`--system-prompt-file`, yet the flag was accepted. Re-run this probe after a
Claude Code upgrade before relying on it. The run produces a verdict, not the
SHA-bound marker that `/ship` reads.

## Gotchas

`search_memory.py` takes the query as a POSITIONAL arg. `--query "..."` exits 2
with `unrecognized arguments`, despite several agent prompts documenting the
flag form.

`mcp__serena__write_memory` writes to the MAIN checkout's `.serena/memories/`,
not to an agent worktree, because Serena's project root is the main repo. From
a worktree, write the file with the normal file tools instead, or the memory
lands outside your branch and pollutes the main tree.
