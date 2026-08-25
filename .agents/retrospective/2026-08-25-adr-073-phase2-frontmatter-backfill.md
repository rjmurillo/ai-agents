# Retrospective: ADR-073 Phase 2 frontmatter backfill (issue #5190)

Branch `claude/autoplan-goal-vd6pmg`. 53 ADRs backfilled with ADR-073 lifecycle
frontmatter, one review log, one test fix. 15 commits.

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
section. On arrival, `git rev-parse --is-shallow-repository` returned `true`
with 50 commits, all dated 2026-08-18, because one commit (`2c85d254`) touches
every ADR in the tree. That fallback would have returned 2026-08-18 for every
record it was applied to, and for the `implemented` derivation every
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
| `scope-policy` / `branch-scope` | 55 files, hard limit 50 | Owner-authorized, scoped `SKIP_SCOPE_CHECK=1`; documented in the log and the PR |
| `python-tests` | `test_adr_063` read the title from `splitlines()[0]` | Test now finds the first H1; frontmatter legitimately precedes the title now |
| `retrospective-policy` | Test fix made the push non-documentation-only | This file |

The `python-tests` failure is the one worth noting: the ADR-073 schema puts YAML
ahead of the H1, so any test asserting a title on line 1 breaks. Exactly one test
in the suite made that assumption. The remaining 39 frontmatter-free ADRs will
not surface a second one, but a future ADR-tooling change should expect it.

## What to carry forward

1. **Check for a shallow clone before deriving anything from git history.** The
   highest-value lesson here and the only one that fails silently.
2. **`implemented` cannot be proxied.** Verify by artifact, and check whether the
   artifact was removed after merging.
3. **Four `proposed` records carry `implemented: true` and three `accepted`
   records carry `implemented: false`.** This is the schema working as designed:
   it makes visible the decisions that shipped without formal acceptance
   (ADR-038, 049, 059, 067, 070) and those accepted but never built (ADR-010,
   018, 028). Worth a triage issue; not fixable in a metadata backfill, because
   changing a status is a governance act.
4. **Two follow-ups were filed** rather than left in the transcript: ADR-073's
   dangling citation to a deleted script, and the ten ADRs carrying only a bare
   `status:` line that the #5190 record list did not cover.

## Failure-Mode Classification

**FM-10: Silent defaults and guard-clause suppression** (partial fit).

The shallow-clone failure matches FM-10's core shape: a command succeeds,
returns a plausible value, and is silently wrong. `git log --follow -1` on a
shallow boundary returns a date; the date is the boundary commit, not the file's
true origin. Nothing raises, nothing warns. The only symptom is that the value
looks implausible if you already know what it should be.

The fit is partial because FM-10 is primarily about code-level suppressions
(`except: pass`, `or default`, verdict fall-through), and this failure is an
environment precondition violation. But the unifying property holds: **the call
site has no way to know the operation didn't actually do what its name claims.**
`git log --follow -1 --format=%ad` claims to return the file's earliest date; on
a shallow clone it returns the boundary date, and there is no return code or
warning that distinguishes them.

## Evidence

| Artifact | Link |
|----------|------|
| Issue tracking the backfill | [#5190](https://github.com/rjmurillo/moq.analyzers/issues/5190) |
| Debate log with `implemented` corrections | [ADR-073-phase2-backfill-debate-log.md](./../critique/ADR-073-phase2-backfill-debate-log.md) |
| Commit exposing shallow-clone boundary | `2c85d254` (117 files, 35845 insertions, all-additions signature) |
| ADR-073 lifecycle frontmatter schema | [ADR-073](../architecture/ADR-073-adr-lifecycle-frontmatter.md) |
| Deferred supersession issues | [#5192](https://github.com/rjmurillo/moq.analyzers/issues/5192), [#5193](https://github.com/rjmurillo/moq.analyzers/issues/5193), [#5195](https://github.com/rjmurillo/moq.analyzers/issues/5195) |
| ADR-policy gate weakness | [#5205](https://github.com/rjmurillo/moq.analyzers/issues/5205) |

## Remediation

| Action | Owner/Issue | Status |
|--------|-------------|--------|
| Add shallow-clone check rule (`.claude/rules/shallow-clone-guard.md`) | TBD | Pending |
| Triage proposed-but-implemented mismatches (ADR-038, 049, 059, 067, 070) | TBD | Pending |
| Triage accepted-but-unbuilt records (ADR-010, 018, 028) | TBD | Pending |
| Fix ADR-073 dangling citation to `scripts/sync_adr_protocol.py` | TBD | Pending |
| Complete Phase 2 for ten partial-frontmatter ADRs | [#5190](https://github.com/rjmurillo/moq.analyzers/issues/5190) | Pending |
| Complete Phase 2 for six deferred ADRs | [#5192](https://github.com/rjmurillo/moq.analyzers/issues/5192), [#5193](https://github.com/rjmurillo/moq.analyzers/issues/5193), [#5195](https://github.com/rjmurillo/moq.analyzers/issues/5195) | Pending |

## Open at hand-off

The PR is a draft and references #5190 with `Refs`, not `Fixes`. Six records
(ADR-002, 024, 025, 030, 036, 039) are deferred pending #5193, #5195, and #5192,
so the issue's own acceptance criterion is not fully met. A follow-up after those
three land can pick up the remaining six plus the ten partial-frontmatter
records and close it.
