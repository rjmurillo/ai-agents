# Neither session store tells you who wrote a prompt

Verified 2026-07-27 against the live stores. Issue #3509, PR #3513 (withdrawn).

## Question

Can either session store measure what an operator has actually typed, so that
stored prompts can be treated as human input?

## Conventional answer

Both stores look like they answer it. Copilot's `turns.user_message` reads as
the human half of the turn by construction, so no provenance filter appears
necessary. Claude's transcripts carry an explicit `promptSource` label, so
filtering on it appears sufficient. Four attempts adopted one of those two
premises and went straight to the matcher.

## First-principles position

Neither store carries usable authorship, and provenance binds before any
matcher does. Copilot has no author field at all, and the harness writes
machine text into the column named for the human. Claude's label is trustworthy
where present but covers 1% of entries, so accepting only it leaves too little
to measure, while keeping the unlabelled majority is an assumption rather than
a filter. Every one of the four attempts produced a confident number that was
wrong for this single reason.

## Evidence

### The Copilot store: `turns.user_message` is not the human turn

`~/.copilot/session-store.db` is SQLite. Tables: `sessions`, `turns`,
`checkpoints`, `session_files`, `session_refs`, `assistant_usage_events`,
`search_index`. Open read-only with
`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.

The tempting premise is that `turns.user_message` holds the human half of the
turn by construction, so it needs no provenance filter. That is false. The
column has **no author field**, and the harness writes machine text into it.

Scoped to `sessions.repository LIKE '%ai-agents%'`, the column holds 264
unique texts. Two injected shapes account for 100 of them:

| Injected shape | Texts |
|---|---|
| `Additional context from PreToolUse hook ...` | 88 |
| `Autopilot objective: ...` | 12 |
| **Total machine-authored** | **100 of 264** |

By volume it is worse, because injected context is long and human turns are
short: **304,939 of 353,725 characters, 86%**. A corpus built from this column
is mostly machine text wearing a human column name.

Prefix rejection is not a fix. It is a blacklist against an open set, and it
cannot be validated because there is nothing to validate against. Any hook
added tomorrow writes a shape the list does not know.

### The Claude store: the label exists but covers 1%

`~/.claude/projects/**/*.jsonl`. Entries with `type == "user"` and no `isMeta`
carry an optional `promptSource`. Counted directly:

| Scope | Non-meta user entries | Labelled | `typed` |
|---|---|---|---|
| All projects | 16,669 | 604 | 55 |
| `ai-agents` only | 12,285 | 120 | 26 |

Observed `promptSource` values across all projects: `sdk` (394), `system`
(140), `typed` (55), `queued` (14), `suggestion_accepted` (1).

So the ground truth exists and is trustworthy where present, but it is present
on **1.0%** of the ai-agents entries. Two readings follow, and the choice
between them is the whole design:

- **Accept only `promptSource == "typed"`.** Sound, and yields 26 instances /
  23 unique texts for ai-agents. Far too few to measure anything.
- **Reject known non-human sources, keep the unlabelled majority.** Yields a
  usable count, but the unlabelled majority is unverified by definition. It is
  an assumption, not a filter.

An earlier note in this repo recorded the denominator as "120 of 3,331". That
was wrong. It is 120 of 12,285.

### Why the two stores cannot be pooled or compared

They differ on every axis that matters, so a difference between them attributes
to nothing:

| | Copilot store | Claude transcripts |
|---|---|---|
| Author label | none | `promptSource`, 1% coverage |
| Machine text | injected into the human column | separate entry kinds |
| Share of a pooled operator corpus | 92% | 8% |

A comparison across them changes source, harness, workflow, and register at
once. Pooling them hides that under one label.

### Exposure, not authorship, drives phrase-match counts

A finding from the same review, worth keeping because it generalizes past this
eval. When you count "how many of N documented phrases appear at least once",
the answer scales with how much text you searched, not only with who wrote it.

Two corpora at 358,399 and 2,614,603 characters, a 7.3x gap, produced 3 and 28
phrase matches. Subsampling the larger corpus down to the smaller one's
character count, 50 iterations, collapsed 28 to a mean of **7.6** with a 95%
range of 1 to 13. Most of the apparent effect was exposure.

Two further traps in the same shape:

- **Pseudo-replication.** 428 phrases are not 428 independent trials. They
  cluster into 93 skills, and near-duplicates within a skill covary perfectly.
  Rolled up to skills the gap fell from 9.3x to 4.3x before any volume
  correction. Confidence intervals computed over the phrase count are far too
  narrow.
- **One-armed guards.** A minimum-corpus guard on the treatment arm only will
  happily publish `0 of 428 (0.0%)` for an empty control. Guard every arm you
  intend to print.

## Decision

PR #3513 was withdrawn rather than repaired, and the question was reported as
not yet measurable. That is a real answer. A number from a corpus nobody has
audited is not.

A valid instrument does not start from the matcher. It starts from provenance,
and all four of these are required:

1. An authoritative event-level author label distinguishing typed input from
   hook, autopilot, scheduled, and agent-authored injection. Not a prefix list.
2. One source, or a per-source result that is never pooled.
3. Equal exposure fixed in advance, measured in characters, not prompt counts.
4. Eligibility guards on every arm that appears in the output.

## The pattern worth remembering

Every one of the four failures had the same shape: a premise about where clean
data lives, adopted without checking, then built on. The corpus was assumed
human because of a column name, a store choice, or a filter that looked
principled. Verifying takes one query. Each failure cost a full rework.

Check the data before the code. Then check that your test of the check can
fail.
