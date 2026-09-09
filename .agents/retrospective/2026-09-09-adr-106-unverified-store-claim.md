# Retrospective: a six-seat debate passed a claim the code refutes

**Date**: 2026-09-09
**Scope**: PR #5656 (issue #5574 Stage 3), commits `ca69c7d28` and `d0d107839`
**Failure mode classification**: #9, Confident-incorrectness recurrence
(`.agents/governance/FAILURE-MODES.md:27`). Secondary touch on #6, Multi-agent
rubber-stamping (line 24): six independent seats read the sentence and none
opened the file it described.

## What happened

ADR-106 retires a memory backend. Its Decision item 2 shipped as:

> There is no supplementary tier and no second store to consult, augment from,
> or fall back to.

A second store is consulted on every search.
`.claude/skills/memory/scripts/search_memory.py:296` runs
`results += search_episodes(query, episodes_path, max_results)` over
`.agents/memory/episodes`, which holds 750 files.

The same ADR contradicted itself three paragraphs later. Decision item 3 already
called the episode store surviving and ADR-038-governed, so item 2's absolute
was refuted by item 3 without anyone leaving the document.

Item 3 carried its own error: it said the unified entry point "also reads" the
episode store. `grep -i episode` over
`.claude/skills/memory/memory_core/memory_router.py` returns nothing. Episode
retrieval lives in `scripts/search_memory.py`. The sentence attributed a read to
a module that does not perform it.

Both were found by Devin Review after the PR left draft, not by the gate built
to catch exactly this.

## The measurement

| Reviewer | Seats | Caught the false quantifier |
|---|---|---|
| adr-review debate (round 1) | 6 | No |
| Devin Review (post-draft) | 1 | Yes, both sentences |

The round-1 debate was not idle. It raised 19 P1 findings, and four seats
independently falsified a *different* unbounded quantifier in the same draft:
"Every memory instruction an agent reads now names a store it can actually
reach." That one was measured against the tree and removed.

So the corpus contained two sentences of identical shape. One was checked and
died. The other was read by the same six seats and lived.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Architecture record accuracy | High | An accepted ADR would have described a retrieval topology the code does not implement |
| Self-consistency | Medium | Decision items 2 and 3 of one record contradicted each other |
| Attribution | Medium | A read was credited to `memory_router.py`, sending a reader to the wrong module |
| Review confidence | Medium | Six seats and a 19-finding debate produced a false-negative on a one-command check |

Nothing shipped to `main`: the PR was still open when the review landed, and the
correction is `d0d107839`.

## Root cause, five whys

1. Why did a false claim survive? Because no seat ran the call path it described.
2. Why not? Because the sentence reads as a design statement, and design
   statements are argued rather than executed.
3. Why did that pass when the sibling quantifier failed? Because the sibling
   named a countable surface ("every memory instruction"), which invites a grep.
   "No second store to consult" names an absence, and an absence has no obvious
   thing to count.
4. Why does that matter? Because an absence claim is unfalsifiable by reading.
   Confirming it requires enumerating what the code *does* call and finding the
   set empty, which is a different and less natural motion than checking a
   quoted count.
5. Why was there no gate? Because `adr-review` scores argument quality across
   six seats, and nothing in the pipeline resolves a prose claim about runtime
   behavior against the runtime.

Root cause: **the review had no step that converts an absence claim into a call
path**. Its 19 findings show the seats were reading hard; they were reading the
wrong artifact for this class of sentence.

This is the same shape `universal.md` MUST NOT 9 already forbids for memories:
"MUST NOT assert an absence from a single probe." The rule binds memory files.
Nothing extended it to ADR prose.

## What went well

- **The correction was verified, not assumed.** The httpx2 fix in the same push
  was proved by discriminating test: reverting only `uv.lock` brought back
  exactly the three CVEs, restoring it cleared them. The ADR fix quotes the call
  site and the empty grep rather than asserting the new text is right.
- **The external reviewer was treated as a bug report, not an obstacle.** All
  four findings were checked against the files. One was confirmed and fixed, one
  was refuted with repository precedent (ADR-004, ADR-056 and ADR-036 all
  interpret in their Status blocks), two were real but out of contract and left
  open rather than resolved away.
- **The debate log was appended, not rewritten.** Round 2 records what round 1
  missed, so the miss is legible to the next reader instead of being edited into
  a clean history.

## What to improve

- An ADR sentence asserting that something is *not* consulted, read, or reached
  needs a named call path or a cited empty search, in the record itself. Prose
  confidence is not evidence about a runtime.
- Self-consistency is cheap and was skipped: items 2 and 3 disagreed inside one
  file. A reader comparing a record's own decision items against each other
  would have caught this without leaving the document.
- Six seats agreeing is a weaker signal than one seat executing. The round-1
  debate's own success came from the seats that measured, not from the count.

## Remediation

| Action | Owner | Tracking |
|---|---|---|
| Extend the absence-claim discipline of `universal.md` MUST NOT 9 from memory files to ADR prose, so a "not consulted" claim needs a cited call path or search | rjmurillo | Needs an owner decision; rule change, not an agent edit |
| Add a self-consistency pass to `adr-review`: check a record's Decision items against each other before scoring argument quality | rjmurillo | Skill change to `.claude/skills/adr-review/` |
| Validator: resolve a skill's declared `metadata.adr` against that ADR's status, so a superseded record cannot stay declared silently | rjmurillo | Issue #5665 (filed from the same review) |
| Repoint the 8 SKILL.md files and 44 agent lines still naming the retired records | rjmurillo | Issue #5574, Stage 2 surface |

## Evidence

- PR #5656, review by `devin-ai-integration[bot]`, 2026-09-09T01:06Z, four findings
- `ca69c7d28`: the commit carrying the false claim
- `d0d107839`: the correction, and the Round 2 section of
  `.agents/critique/ADR-106-debate-log.md`
- `.claude/skills/memory/scripts/search_memory.py:296`: the call that refutes it
- `.claude/skills/memory/memory_core/memory_router.py`: `grep -i episode` returns
  nothing, refuting the attribution
- `.agents/critique/ADR-106-debate-log.md`: round 1, 6 seats, 3 ACCEPT /
  3 DISAGREE_AND_COMMIT / 0 BLOCK, 0 P0 / 19 P1 / 14 P2
- `.agents/governance/FAILURE-MODES.md:27`: failure mode 9
- `.claude/rules/universal.md` MUST NOT 9: the absence-claim rule this extends
