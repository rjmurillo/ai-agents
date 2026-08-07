# Union merge hides semantic duplicates in append-only docs

## The conventional position

`merge=union` is the standard answer for an append-only file that many
contributors touch. Changelogs, gotcha lists, index tables. Git concatenates
both sides instead of raising a conflict, and the received wisdom is that this
is safe precisely because nobody edits existing lines.

This repo has two such files, and they cause more conflicts than anything else:
`.agents/governance/GOTCHAS.md` (5 open PRs conflicting at once) and
`.serena/memories/memory-index.md` (6). Union looks like the obvious fix.

## Why that is wrong here

Union solves a *lexical* problem. The duplicate risk in these files is
*semantic*, and no merge driver can see it.

Measured directly, PR #4603, merge commit `30573028cd`. The conflict in
`GOTCHAS.md` was diff3 with an **empty base region**: ours appended six
sections at lines 547 to 652, theirs appended two at 655 to 763. Pure appends
on both sides. Exactly the shape union exists to handle.

Two of those sections documented the same fact under different headings:

- ours: "Editing an always-on rule moves the doctrine figures"
- theirs: "Editing any `.claude/rules/*.md` file changes a number the doctrine
  asserts"

Different line numbers, different wording, one fact. Union sees two clean
appends on disjoint lines and concatenates both. There is no same-line
modification, so there is nothing for it to flag. The duplicate ships silently.

The conflict is what caught it. A human had to read both sides to resolve the
merge, and the duplicate was visible only during that read.

## The trade being made

Applying union to a file like this converts a **loud** failure (a conflict
somebody resolves) into a **silent** one (a document that says the same thing
twice under two names). That is the fail-open shape, applied to documentation
instead of to a gate.

For `memory-index.md` the failure is different and lexical: union duplicates
rows that both sides modified, because the token counts change on both sides.
That one a post-merge repair can fix (`scripts/update_memory_index_tokens.py`
then `scripts/ci/memory_index_token_ratchet.py`). The `GOTCHAS.md` failure has
no mechanical repair.

## What to do instead

Decide per file, and decide by what the failure mode costs:

- Duplicate detectable mechanically (index rows, sorted tables): union plus a
  dedupe pass in the file's own repair script is fine.
- Duplicate only detectable by reading (prose sections, gotchas, ADR bodies):
  keep the conflict. The conflict is the review step. If the conflict volume is
  genuinely intolerable, pair union with a heading-similarity check in a gate,
  so the duplicate is caught after the merge rather than never.

## Secondary finding, correct but narrower

`.gitattributes` (around lines 365 to 390) records that `merge=ours` and
`merge=handoff-aggregate` were deleted because a `merge=<name>` attribute
resolves through `git config merge.<name>.driver`, which lives in an
uncommitted per-clone config, so the attribute silently does nothing for a
fresh clone. That reasoning is correct for **custom** drivers.

It over-generalizes to built-ins. Git's built-in merge attribute values are
`text`, `binary`, and `union`. `union` needs no `git config` entry and works in
a fresh clone. So the "no custom merge strategies" note is not itself a reason
union cannot be used. The reason is the semantic-duplicate finding above.

## Evidence

- Merge commit `30573028cd`, branch `fix/3972-4441-memory-metrics`, PR #4603.
- Conflict markers observed at `.agents/governance/GOTCHAS.md` lines 546
  (`<<<<<<< ours`), 653 (`||||||| base`), 654 (`=======`), 764
  (`>>>>>>> theirs`). Base region between 653 and 654 was empty.
- Resolution kept all seven distinct sections and collapsed the two duplicates
  into one, preferring the richer version.
