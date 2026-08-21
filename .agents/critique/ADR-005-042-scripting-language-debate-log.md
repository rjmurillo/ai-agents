# Debate Log: ADR-005 and ADR-042 Scripting Language Records

Change-set CS-3a of the corpus-repair batch. The batch-level record and roster
are at `.agents/critique/ADR-corpus-repair-5189-5201-debate-log.md`.

## The defect

Four records spoke to scripting language policy and did not resolve to an answer.

| ADR | Prose status | Machine status before this change |
|---|---|---|
| ADR-005 powershell-only-scripting | Superseded by ADR-042 | unknown, no frontmatter |
| ADR-028 powershell-output-schema-consistency | Accepted | unknown, no frontmatter |
| ADR-031 hybrid-powershell-architecture | Proposed | unknown, no frontmatter |
| ADR-042 python-migration-strategy | Accepted | unknown, no frontmatter |

The binding answer is ADR-042. `AGENTS.md` states it under Boundaries as
"Always: Python (ADR-042)" and `.claude/rules/universal.md` SHOULD-3 enforces it.
Yet ADR-042 and the record it retired were machine-indistinguishable, and a live
`Proposed` record still argued for hybrid PowerShell.

## The change

ADR-005 gains `status: superseded`, `superseded-by: ADR-042`, and a `## Status`
section carrying its existing supersession sentence. ADR-042 gains
`status: accepted`, `supersedes: [ADR-005]`, `implemented: true`, and a `## Status`
section that now names its evidence.

ADR-028 and ADR-031 were deliberately not touched. See Deferred below.

## The central question, and why it was asked here

ADR-073 states: "A hand-edited `status: accepted` is a forgeable approval signal
unless the Phase 3 gate binds the transition to adr-review consensus evidence.
The schema is security theater until that binding exists."

ADR-042 is the one record in this batch moving to `accepted`, and it is the most
load-bearing enum in the corpus. Every role was asked whether this edit
manufactures its own authorization.

**Answer: no.** Three independent confirmations, produced by three different
reviewers.

1. `.agents/critique/ADR-042-debate-log.md` records a real six-role debate dated
   2026-01-17, `**Final Verdict**: ACCEPT`, 5 Concerns plus 1 Accept resolved
   Disagree-and-Commit, all P0 findings marked RESOLVED. Four supporting
   artifacts sit beside it.
2. The diff adds a frontmatter block and, in its first form, changed not one
   character of the `## Status` body, which already read `Accepted` at HEAD.
   Confirmed by `git show HEAD:` on the file.
3. `AGENTS.md` and `.claude/rules/universal.md` have bound on ADR-042 as accepted
   for seven months.

The deciding principle, from the tie-breaker: **frontmatter is a machine-readable
index of the record's own prose, not a decision surface. Adding it is legitimate
when the value is copied from a statement already standing in the tree under the
owner's merge, and the prose is left unedited.** Forgery is the other shape:
writing `accepted` into a record whose prose says Proposed, or says nothing.

**This log is not ADR-042's authorizing evidence and must not be cited as such.**
The authorizing evidence predates it by seven months. Were this log the only
evidence, the review would be circular, and the reviewers said so explicitly.

## Finding resolved before merge

Three roles independently raised the same P1: ADR-042 carried the enum without
citing its evidence, while ADR-073 cites its own log path inline. The record
whose enum grants binding authority was the one that could not be audited from
itself. ADR-042's `## Status` now names the debate log and its four supporting
artifacts, and states why the citation is there.

This is the one substantive edit to ADR-042's prose in this change. It adds a
citation; it does not alter the decision.

## The precedent does not extend

Six records carry `implemented: true` against `status: proposed`: ADR-075,
ADR-077, ADR-078, ADR-089, ADR-093, ADR-098. Each has a debate log that
explicitly withholds acceptance. ADR-098 states the pair is deliberate: "the flip
is mechanically available and is not taken here... the acceptance of a governance
ADR is a maintainer act."

They were left untouched, and that asymmetry is now recorded in the corpus so the
next agent does not read ADR-042 as license.

## Deferred, with the tie-breaker dissenting

**ADR-031** (`Proposed`, hybrid PowerShell architecture). Evidence gathered:
it predates ADR-042 by 19 days; its stated binding constraint is ADR-005, now
superseded; its Strategy 2 (named-pipe daemon, issue #287) was closed
`not_planned` six days **before** the ADR was authored, with the rationale
"superseded by the GitHub MCP + skills pattern"; its Strategy 1 shipped as a
migration away from PowerShell; nothing was ever built; no debate ever ran.
Recommended terminal state: `rejected`, per ADR-095's precedent of recording
rejections so they do not return.

**ADR-028** (`Accepted`, PowerShell output schema consistency). `git ls-files
'*.ps1' '*.psm1'` returns zero script files. Its motivating example,
`Get-PRReviewComments.ps1`, does not exist. It is an accepted rule governing an
empty set. Recommended: `deprecated`, not `superseded-by: ADR-056`, because
ADR-056 describes its own relationship to ADR-028 as additive rather than
replacing.

**The tie-breaker dissented from both deferrals**, holding that each is decidable
by `ls` and `grep` rather than by owner taste, and that using ADR-042 to retire
ADR-005 while declining to use it on ADR-031 in the same batch is inconsistent.
The dissent is recorded rather than acted on: both edits assign a terminal
lifecycle state to a record whose prose does not assign one, which is the shape
this batch committed to not doing without the owner.

## Verdicts

ACCEPT from architect, security, analyst, and the tie-breaker.
DISAGREE-AND-COMMIT from the independent-thinker, on the evidence-citation P1
now resolved. The critic did not block this change-set; its block was scoped to
CS-1.
