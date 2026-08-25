# Retrospective: ADR-073 Phase 2 frontmatter backfill (issue #5190)

Branch `claude/autoplan-goal-vd6pmg`. 67 ADRs carrying ADR-073 lifecycle
frontmatter, one review log, a taste-lints fix, and two test files. 73 files.

## What was supposed to happen

Read each in-scope ADR's `## Status` and `## Date` sections, map the prose to
the ADR-073 enum, write a nine-line frontmatter block, run a six-agent
adr-review debate, commit in batches, push, open a draft PR. The task brief
described this as a mechanical metadata backfill.

## What actually happened

It was not mechanical. Four things bit, in descending order of how quietly they
would have shipped wrong answers.

### 1. The clone was shallow and the date rule silently depended on it

The acceptance criterion says `date` falls back to
`git log --follow -1 --format=%ad --date=short` where a record has no `## Date`
section. That command returns the date of the **most recent** commit touching
the path, following renames; `-1` caps the log at one entry and the log is
newest-first. On a complete clone that is the record's last-modified date, which
is what the field wants.

On arrival, `git rev-parse --is-shallow-repository` returned `true` with 50
commits, all dated 2026-08-18, because one commit (`2c85d254`) touches every ADR
in the tree. At a shallow boundary the most recent commit and the only visible
commit are the same commit, so the fallback would have returned 2026-08-18 for
every record it was applied to. For the `implemented` derivation, every
`git log --grep` would have searched 50 commits instead of 2630.

Nothing about this failure announces itself. The commands succeed, return
plausible ISO dates, and are wrong. It was caught only because a date of
2026-08-18 on a December 2025 ADR looked odd enough to check the commit, and the
commit turned out to be a 117-file, 35845-insertion, all-additions diff, which is
the signature of a shallow boundary rather than a real edit.

**Lesson.** Any derivation that reads git history must check
`git rev-parse --is-shallow-repository` first and `git fetch --unshallow` before
trusting a single date or `--grep` result. This is worth a rule, not just a
retrospective line: the failure is silent, plausible, and would have poisoned 53
records at once.

### 2. Both cheap proxies for `implemented` were wrong, in opposite directions

The field is defined as flipping true "at first merged change". Two proxies were
tried before the artifact test:

- **Counting ADR-id references in live files.** Reported 0 for ADR-041 and
  ADR-046, whose artifacts (`codeql-analysis.yml`, `milestone-planner.md`)
  plainly exist, and inflated ADR-011 and ADR-072, whose references are prose
  describing proposals that were never built.
- **Counting merged commits citing the id that touch code.** Credited ADR-032 to
  a commit implementing ADR-033, and ADR-018 to a commit implementing ADR-017,
  because commit messages cite neighbouring ADRs freely.

Only the artifact test held: does the thing the ADR decided exist now, or did it
provably exist and merge before removal? That test corrected six records
(ADR-021, 049, 050, 059, 060, 067), all in the same direction, all cases where a
proxy said "never built" about a decision that had shipped.

Two of the six shipped and were later *removed*
(`scripts/sync_adr_protocol.py`, `_run_rework_warning_step`), so present-tense
existence alone would also have been wrong. One (ADR-049) shipped under a
different filename than the ADR proposed, so matching the ADR's own named path
would have scored it wrong too.

**Lesson.** For a field that gates amend-versus-supersede, cheap proxies are not
merely imprecise, they are wrong in both directions and the errors do not cancel.
Verify by artifact, and check history for removal.

### 3. Sub-agent delegation was unavailable and the honest response cost nothing

The `adr-review` skill specifies a six-agent debate, and the `adr-policy`
pre-commit gate requires a debate log staged with every ADR commit. `Task` was
disabled in this session, so the roster could not be convened.

The gate would have accepted a fabricated log. Issue #5205 already documents that
its ADR-id matching is weak enough that any staged log mentioning one id
satisfies a whole batch. Writing "architect: Accept. critic: Accept." would have
passed every check and been undetectable from the diff.

What was written instead is a single-reviewer structured review that opens by
saying so, states that acceptance rests on human review of the PR, and asks the
reviewer to choose explicitly between convening the real debate and accepting
single-reviewer evidence for a mechanical backfill. The disclosure cost one
paragraph. The review still did real work: it changed six records before they
were written.

**Lesson.** When a gate can be satisfied by an artifact that misrepresents what
happened, the gate is not the audience. Write what is true and make the gap
legible; the honest version was no more expensive to produce.

### 4. The commit gate shape forced the batch structure

`check_adr_review_policy` requires the debate log in `git diff --cached` for
every commit touching an ADR, not merely once on the branch. Combined with the
five-authored-file limit from `AGENTS.md`, that fixes the batch size at four ADRs
plus the log. The log therefore had to change in each of the 14 commits, which
was resolved by having it record each batch as it landed, so the edit is real
content rather than a touch to satisfy the gate.

## Gates hit, and how each was resolved

| Gate | Cause | Resolution |
|------|-------|------------|
| `adr-policy` | ADR commits need a staged debate log | Review log staged with all 14 batches |
| `staged-dash-policy` | Four in-scope ADRs carried pre-existing em dashes | Replaced with colons and commas in ADR-021, 032, 053, 056 |
| `scope-policy` / `branch-scope` | 73 files at final count, hard limit 50 | Owner-authorized, scoped `SKIP_SCOPE_CHECK=1`; documented in the log and the PR |
| `python-tests` | `test_adr_063` read the title from `splitlines()[0]` | Test now finds the first H1; frontmatter legitimately precedes the title now |
| `retrospective-policy` | Test fix made the push non-documentation-only | This file |

The `python-tests` failure is the one worth noting: the ADR-073 schema puts YAML
ahead of the H1, so any test asserting a title on line 1 breaks. Exactly one test
in the suite made that assumption. The two ADRs still deferred will not surface
a second one, but a future ADR-tooling change should expect it.

## Failure mode classification

Classified against `.agents/governance/FAILURE-MODES.md`. Both classes below
were **near misses**: each was caught before merge, so this retro records what
almost shipped rather than what did. That is worth writing down precisely
because nothing external would have caught either one.

| Failure | Class | Severity | Why it fits |
|---|---|---|---|
| Shallow clone read as complete history | **10. Silent defaults and guard-clause suppression** | High | The class covers absence-of-signal treated as signal. `git log --follow -1` on a shallow clone does not error; it returns the boundary commit's date, so missing history is indistinguishable from a real answer. Had it shipped, all 53 records carry one wrong date and no gate objects. |
| Both `implemented` proxies trusted | **9. Confident-incorrectness recurrence** | High | The class shape is "partial signal, premature conclusion, confident delivery, multi-round correction". A reference count is partial signal; it was nearly delivered as fact for 53 records. Six were wrong and were only caught by opening the artifacts. |

The unifying property across both, and the reason they belong together: **the
call site has no way to know the operation did not do what its name claims.**
`git log --follow -1` returns a date whether or not the history behind it is
complete, and a reference count returns a number whether or not the references
mean what the caller assumes. Neither has a return code, a warning, or any other
channel that distinguishes the good case from the bad one. This framing is taken
from the parallel retrospective draft in commit `e51e34f9`, which reached the
same class by a different route.

**Proposed addition to class 10, no new class needed.** Class 10's shape list
enumerates six suppression forms, all of them in-process (`try/except: pass`,
`value or default`, `dict.get` with a default, guard-clause early exit, schema
fall-through, verdict parser emitting PASS on no output). It has no entry for
*a truncated external data source read as complete*, which is what a shallow
clone, a paginated API returning page 1, or a `grep` over a partial checkout all
produce. Suggested seventh bullet:

> - A query against a truncated data source (shallow git clone, unpaginated API
>   result, partial checkout) whose truncation is not an error condition, so the
>   partial answer is returned with the same shape and confidence as a complete
>   one

This is an addition to an existing class rather than a new class, so per
`.claude/rules/retros.md` MUST-2 it does not require a linked ADR. Tracked as a
remediation item below.

## Evidence

Commits and artifacts, all on branch `claude/autoplan-goal-vd6pmg` in
`rjmurillo/ai-agents`:

| Item | Reference |
|---|---|
| The PR | rjmurillo/ai-agents#5291 |
| Driving issue | rjmurillo/ai-agents#5190 |
| Deferred-record issues | rjmurillo/ai-agents#5192, #5193, #5195 |
| Follow-ups filed from this work | rjmurillo/ai-agents#5289 (ADR-073 dangling script citation), #5290 (ten partial-frontmatter ADRs) |
| Weak debate-log gate, not exploited | rjmurillo/ai-agents#5205 |
| The shallow-boundary commit that made every ADR read as 2026-08-18 | `2c85d254` |
| ADR-050's artifact: added, then removed | `4c0d01a0` (2026-02-28, #1247), `ba541c21` (2026-08-20, #5179) |
| ADR-060's artifact: added | `157737a0` (2026-05-25, #2063) |
| ADR-067's artifact, still live | `scripts/validation/pr_description.py:510` |
| Review log with the full mapping and findings | `.agents/critique/ADR-073-phase2-backfill-debate-log.md` |
| Test broken and fixed by the schema change | `tests/test_adr_063_memory_skill_decomposition.py` |

Every issue reference above is in `rjmurillo/ai-agents`.

**Correction, and a lesson in its own right.** Copilot's second review round
reported the issue links in this file as pointing at `rjmurillo/moq.analyzers`.
Checked against the local working tree, that looked like a false positive: no
such string was present. It was not a false positive. A second agent was editing
the same branch concurrently and had pushed `e51e34f9`, which added an Evidence
table whose six links all pointed at `moq.analyzers`, plus a Remediation table
with four `TBD` owners. Copilot was reviewing the pushed branch; the local tree
was behind it.

Both versions of those sections survived the merge, and this file briefly
carried the duplicate and its wrong links. The duplicates are removed and this
file keeps the corrected version.

The lesson: **on a shared branch, "I checked and it is not there" is a statement
about your working tree, not about the branch.** Fetch before ruling a review
finding a false positive. The same shape as the shallow-clone failure above, one
level up: a local view that is silently incomplete, and an answer that looks
authoritative because the command succeeded.

## Remediation

Per `.claude/rules/retros.md` MUST-4, each item carries an owner or an issue.

| # | Action | Kind | Owner / issue | Status |
|---|---|---|---|---|
| 1 | Add the shallow-clone precondition to the rule tree, so any git-derived value checks `git rev-parse --is-shallow-repository` before it is trusted | Rule change | rjmurillo, needs an issue filed before a rule lands | Open |
| 2 | Add the truncated-source bullet to FAILURE-MODES class 10 (text drafted above) | Governance change | rjmurillo | Open |
| 3 | Repair ADR-073's dangling citation to `scripts/sync_adr_protocol.py` | ADR amendment | rjmurillo/ai-agents#5289 | Filed |
| 4 | Complete Phase 2 across the ten partial-frontmatter ADRs | Backfill | rjmurillo/ai-agents#5290 | Filed, folded into PR #5291 |
| 5 | Triage the eight status/implementation mismatches surfaced by the schema (five `proposed` but shipped, three `accepted` but never built) | Governance triage | rjmurillo, needs an issue; not fixable in a metadata backfill because a status change is a governance act | Open |
| 6 | Decide the review-evidence question for PR #5291: convene the full six-agent debate, or record acceptance of narrower evidence | Process decision | rjmurillo, on PR #5291 | Open |
| 7 | Sweep the six ADR-030 citation sites, and decide where skill-first lives now that ADR-030 is rejected | Cleanup plus a governance decision | rjmurillo/ai-agents#5293 | Filed |

## What to carry forward

1. **Check for a shallow clone before deriving anything from git history.** The
   highest-value lesson here and the only one that fails silently.
2. **`implemented` cannot be proxied.** Verify by artifact, and check whether the
   artifact was removed after merging.
3. **Five `proposed` records carry `implemented: true` and three `accepted`
   records carry `implemented: false`.** This is the schema working as designed:
   it makes visible the decisions that shipped without formal acceptance
   (ADR-038, 049, 059, 067, 070) and those accepted but never built (ADR-010,
   018, 028). Worth a triage issue; not fixable in a metadata backfill, because
   changing a status is a governance act.
4. **Two follow-ups were filed** rather than left in the transcript: ADR-073's
   dangling citation to a deleted script, and the ten ADRs carrying only a bare
   `status:` line that the #5190 record list did not cover.

## Open at hand-off

The PR references #5190 with Refs, not a closing keyword, and closes #5290.

**Two records remain deferred: ADR-024 and ADR-025**, both owned by #5192, which
is also where PR #5209 is doing the reciprocal-supersession work. Four records
that were deferred when this retro was first written are no longer: ADR-002 and
ADR-039 ship as `deprecated`, ADR-030 as `rejected`, and ADR-036 turned out never
to have belonged to the #5192 problem at all. The ten partial-frontmatter records
from #5290 are complete.

So #5190's criterion that every `ADR-[0-9]*.md` carry frontmatter is met except
for those two. A follow-up after #5192 lands closes the gap.
