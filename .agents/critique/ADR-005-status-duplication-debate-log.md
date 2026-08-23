# Owner Direction: ADR-005 Prose Status Duplication

**On this file's name.** It is called a debate log because
`git_hook_policy._is_debate_log_path` requires the substring `debate` in the
filename before it will accept an artifact as ADR-change evidence. No agent debate
happened here and none was needed: the repository owner decided. The naming is the
gate's requirement, not a description of what took place, and issue #5205 covers
the fact that the gate reads a filename pattern rather than a review.

## Governing evidence

This is not an agent debate. The repository owner (@rjmurillo) reviewed PR #5209
and left an inline comment on `.agents/architecture/ADR-005-powershell-only-scripting.md`
line 16:

> Duplicative. Already in frontmatter

That comment is the decision. It is recorded here because the change touches an
ADR and the commit gate requires an artifact under `.agents/critique/`, not
because an agent panel was needed to settle it.

## What was duplicated, and who caused it

The pre-change record carried three inline labels:

```
**Status**: Superseded by [ADR-042](./ADR-042-python-migration-strategy.md)
**Date**: 2025-12-18
**Deciders**: User, Orchestrator Agent, Implementer Agent
```

This campaign then added frontmatter restating all three (`status: superseded`,
`superseded-by: ADR-042`, `date: 2025-12-18`, `decision-makers: [...]`) and
promoted the inline `**Status**:` label into a `## Status` heading.

So the duplication is this campaign's own doing. Before the change there was one
statement of each fact; after it there were two.

## The check that mandated it, and why it is removed

`scripts/validation/check_adr_lifecycle.py` shipped a `status-section-present`
check requiring every record with frontmatter to also carry a prose status
section. Honouring the owner's edit made ADR-005 trip that check, taking the count
from 7 to 8 and failing the ratchet. The gate's own failure message says not to
raise the baseline to clear it.

The conflict is real and only one side could survive. The check loses, for two
reasons.

**It read a MUST into a citation that writes none.** ADR-073 does choose dual
representation: its Decision retains the prose `## Status` section as a secondary
rendering, so the section stays in the template and the gate reads it wherever it
appears. But the sentence the check cited, line 57, reads: "The prose `## Status`
section remains for humans and **may** carry the nuance the enum cannot." Nothing
in the ADR says every record must restate the enum in prose. Mandating presence is
a stronger rule than ADR-073 writes, and it is an amendment to that ADR rather
than a validator default. Raised again by review on PR #5209.

**What it mandated was duplication.** For a record whose frontmatter already says
`status: superseded` and `superseded-by: ADR-042`, a prose line reading
"Superseded by ADR-042" adds nothing and can drift. ADR-073's own Negative
Consequences name this: "dual representation ... introduces a sync burden and a
new drift class."

Removing the check drops the baseline from 78 to 71. That is a reduction from
deleting a bad rule, not a raised ceiling.

## Scope: the comment does not generalise

Four other records in this batch keep their prose status sections, because theirs
carry nuance the enum cannot express and are therefore what ADR-073 actually
contemplates:

| Record | What its prose carries beyond the enum |
|---|---|
| ADR-042 | Its adr-review debate-log path and the four supporting artifacts |
| ADR-024 | Its acceptance-as-ADR-014 provenance and the renumbering trail |
| ADR-025 | The measured ARM adoption figures behind the supersession |
| ADR-055 | The duplicate-slug analysis and the exception-marker decision |

ADR-005 was the only bare restatement among them. Deleting the others would lose
information; deleting ADR-005's loses nothing.

**Correction from a later review round.** The table above describes this
decision as it stood when made: ADR-024, ADR-025, ADR-042, and ADR-055 each
kept a `## Status` section carrying nuance the enum could not. Later,
unrelated edits in this same campaign moved that nuance out of `## Status`
into purpose-specific headings instead (`## Provenance` on ADR-024 and
ADR-055, `## Documented Exceptions` on ADR-055, and equivalents on ADR-025
and ADR-042). None of the four currently carries a `## Status` heading.
The decision this log records, keep the four records' nuance rather than
deleting it, still holds; only the container changed. Flagged by Copilot
review, PR #5209 round 4.

## What still holds

`prose-frontmatter-agree` survives unchanged, and it is the rule ADR-073 does
state: when prose and frontmatter both speak and disagree, frontmatter wins and
the author reconciles the prose. Absence is now fine. Contradiction is not.
