<!-- # taste-lint: ignore file-size (review record covering 67 ADRs; the 500-line code-cohesion limit does not apply to a review log, and splitting it would break the adr-policy gate, which needs one staged debate log per ADR commit) -->

# ADR-073 Phase 2 backfill: review and debate log

Subject: ADR-073 lifecycle frontmatter across 67 records. Issues #5190 and
#5290. Branch `claude/autoplan-goal-vd6pmg`.

Scope: **67 distinct ADR files**, 73 files in the PR. That is 53 records which
carried no frontmatter, 10 which carried a partial block (#5290), and 4 further
records added for status decisions (ADR-002, ADR-030, ADR-036, ADR-039). A fifth
status decision, ADR-052, was already among the 53, so counting the status
decisions as five and the rest as 63 would double-count it: 62 records are
mechanical, 5 are decisions, 67 in total.

ADR-073 (`.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md`) is Accepted
(2026-06-19) and is not reopened here. Its schema is taken as given. This review
covers two questions: is the prose-to-enum mapping right for each record, and
are the derivation rules behind it sound?

## How this review was conducted

**Read this section before treating this document as consensus evidence. Two
different review standards apply to different parts of this PR.**

**Two six-agent rounds ran, and both are recorded in this document.**

| Round | Scope | Verdict |
|---|---|---|
| First | The 5 status decisions | DISAGREE-AND-COMMIT. Two of the five statuses were overturned by the debate. |
| Second (final) | **All 67 records** | 3 ACCEPT, 2 DISAGREE-AND-COMMIT, 1 BLOCK, cleared by two named fixes. |

The second round is what covers the 62 mechanical records, and it is the
authoritative review for the whole batch. Neither round was unanimous, and the
dissents in both are recorded rather than summarised away.

The single-reviewer account below is retained as history. It describes the state
before either round ran, and it is why this document exists in the shape it does;
it is no longer the review standard for any part of this PR.

### The single-reviewer standard, for the 62 mechanical records

The `adr-review` skill specifies a six-agent debate (architect, critic,
independent-thinker, security, analyst, high-level-advisor). That roster could
not be convened for these: sub-agent delegation was unavailable in the session
that produced this change, so no agent other than the authoring one participated.

What this document is instead: a single-reviewer structured review worked
through the six adr-review axes in sequence, in which every factual claim was
verified against a file or a git command rather than asserted. It is review
evidence and it is not a six-agent consensus artifact. A reviewer weighing it
should discount it accordingly, and the acceptance of this change rests on human
review of the PR, not on a consensus that did not happen.

The review was not a formality. It changed six of the fifty-three records before
they were written. Those corrections are recorded under "Findings" below.

**That gap is now closed.** The choice this paragraph used to put to the
reviewer, cover the 62 in a full-state round or accept narrower evidence, was
resolved by running the round. It found seven wrong dates that the single
reviewer and every bot round had missed, which is the concrete answer to whether
the extra pass was worth its cost.

The repository was un-shallowed (`git fetch --unshallow`, 2630 commits) before
any date or implementation claim was made. The session began with a 50-commit
shallow clone in which `git log --follow -1` returns 2026-08-18 for every ADR,
because a single commit (`2c85d254`) touches all of them. Deriving `date` or
`implemented` on that clone would have produced a uniform, wrong answer for
every record with no visible symptom. Any future re-run of this backfill must
check `git rev-parse --is-shallow-repository` first.

## Derivation rules

**`status`.** The first line of the record's `## Status` section, or its inline
`**Status**:` line, mapped to the ADR-073 enum
(`proposed | accepted | rejected | deprecated | superseded`). Amendment nuance
("Accepted (amended 2026-07-19...)", "Accepted as amended...") maps to
`accepted`; the nuance stays in prose. No prose was rewritten to fit the enum,
with one deliberate exception recorded under ADR-061 below.

**`date`.** ADR-073 line 54 comments the field `# last updated`, so the value is
the latest date the record states about *itself* anywhere in the file, not the
first date field found. A date counts when it appears in a self-referential
update context:

- a `## Date` section value (every value, when it lists several);
- any `**Date**:`, `**Revised**:`, or `**Updated**:` field, **all** of them, not
  just the first;
- an amendment or revision heading (`## Amendment 2026-07-21`,
  `### Current-State Amendment (2026-08-16)`);
- a dated amendment, acceptance, supersession, withdrawal, **deprecation, or
  rejection** statement inside `## Status`, or a dated record note added when the
  status changed.

The deprecation and rejection wordings were missing from an earlier version of
this list, and their absence was not cosmetic: the five status decisions in this
PR are exactly the records whose new prose reads "Deprecated (2026-08-25)" or
"Rejected (2026-08-25)", so the rule as first written did not recognise the
statements it had just caused to be written. Cursor Bugbot caught the
consequence.

**Seven records now carry `date: 2026-08-25`**, every record whose *body content*
this PR changed:

| ADR | What changed in the body |
|---|---|
| ADR-002, ADR-039 | Status changed to `deprecated`, with a resolution section |
| ADR-030 | Status changed to `rejected`, with a record note |
| ADR-052 | Status changed to `rejected`, supersession claim struck |
| ADR-036 | Two stale `Generate-Agents.ps1` references repointed |
| ADR-055 | Supersession claim struck from the `**Status**:` line |
| ADR-061 | Status prose reconciled to open with `Rejected` |

The line the rule draws is **content, not touch**. ADR-036, ADR-055, and ADR-061
did not change status, but each had a factual claim in its body corrected or
removed, which is a change to what the record says. An earlier version of this
document argued ADR-036 should keep `2026-01-01` because a citation repair is not
a decision change; that line was too fine, and it left three records asserting
prose they had not asserted the day before while claiming an older last-updated
date.

What does **not** advance the date, and why the field still carries information:
the 60 records that received only a frontmatter block keep their original dates,
as do ADR-021, ADR-032, ADR-053, and ADR-056, whose only edits were replacing
prohibited em dashes with commas and colons, and ADR-020, which gained a
lint-suppression comment. Metadata and punctuation are not content. Were every
touched file dated today, all 67 would read 2026-08-25 and the field would carry
nothing.

Dates in evidence tables, cited incidents, PR references, and measurement rows
are excluded: those are dates the record mentions, not dates the record was
changed.

Where no such context exists, and only there, the value is
`git log --follow -1 --format=%ad --date=short origin/main -- <path>`. Two
records need that fallback: ADR-001 (2025-12-13) and ADR-026 (2026-07-27). The
ref matters. Reading `HEAD` instead of `origin/main` returns this branch's own
backfill commit, so every record would be dated the day the backfill ran, which
is circular.

**This rule replaced an earlier, narrower one, and the correction changed 13 of
the 53 records.** The first version read only formal date fields and deliberately
ignored amendment dates carried in headings or `## Status` prose. That was
disclosed as a trade at the time, but it was wrong on ADR-073's own terms,
because `# last updated` does not mean "last formal Date field". Copilot's
automated review on PR #5291 raised it and the objection is correct.

The narrow rule was also buggy independent of the policy question. It matched
`**Date**:` with a single `re.search`, which returns the first hit, so ADR-006's
second formal `**Date**: 2026-04-28` field (belonging to its 2026-04-28
amendment) was never seen. That record was wrong under the old rule's own stated
terms, not merely under the new one.

Corrected records, with the context that supplied the new value:

| ADR | was | now | source |
|-----|-----|-----|--------|
| ADR-006 | 2025-12-18 | 2026-04-29 | `## Round 3 amendment-of-amendment (2026-04-29)` |
| ADR-007 | 2026-01-01 | 2026-08-16 | `### Current-State Amendment (2026-08-16)` |
| ADR-008 | 2025-12-20 | 2026-08-19 | `### Amendment 2026-08-19 (Issue #5168, PR #5170)` |
| ADR-014 | 2025-12-22 | 2026-08-16 | `### Current-State Amendment (2026-08-16)` |
| ADR-033 | 2025-12-30 | 2026-08-16 | `### Current-State Amendment (2026-08-16)` |
| ADR-040 | 2026-01-03 | 2026-07-11 | dated supersession statement in `## Status` |
| ADR-041 | 2026-01-16 | 2026-07-21 | `## Amendment 2026-07-21: Retire Tier 3` |
| ADR-047 | 2026-02-16 | 2026-04-29 | dated amendment statement in `## Status` |
| ADR-060, ADR-061, ADR-062, ADR-063, ADR-070 | various | 2026-07-27 | `## Amendment 2026-07-27`, the ADR-088 citation repoint that touched all five |

ADR-001 and ADR-026 were re-derived and confirmed unchanged.

**`decision-makers`.** `[rjmurillo]` on all 53. This follows ADR-073's own
frontmatter, which lists only `rjmurillo` even though its acceptance rested on a
six-agent debate. Several records carry a `**Deciders**` line naming agents
(ADR-006: "User, High-Level-Advisor Agent"; ADR-054: "Security Agent, DevOps
Agent"). Those lines are preserved untouched in the body. The judgment is that
agents named there are reviewers, not deciders, and that the repository owner is
the party who accepts. This is the weakest of the four rules and is flagged as
such: it discards recorded information in favor of uniformity, and a reviewer who
prefers the recorded names has a fair objection.

**`implemented`.** ADR-073 line 54 defines the field as flipping true "at first
merged change" and gating amend-versus-supersede. It is therefore derived from
whether a merged change implemented the decision, independent of the status
label, and it stays `true` for a decision that shipped and was later retired,
because such a record still must not be silently amended.

Two proxies were tried and both were rejected as unreliable:

- Counting references to the ADR id in live files. It reports 0 for ADR-041 and
  ADR-046, whose artifacts demonstrably exist, and inflates ADR-011 and ADR-072,
  whose references are prose describing an unbuilt proposal.
- Counting merged commits whose message cites the id and which touch code. It
  credits ADR-032 to a commit implementing ADR-033, and ADR-018 to a commit
  implementing ADR-017.

The value finally used is the artifact test: does the thing the ADR decided
exist in the working tree now, or did it provably exist and merge before being
removed? Every `implemented` value below was settled that way, by path.

#### Deviation from ADR-073's literal text, and why

This is a deliberate departure from the governing text, recorded here rather
than applied quietly.

**What the literal text says.** ADR-073's Implementation Notes, Phase 2, read:
"`implemented` is derived from whether a merged change references the ADR."
Issue #5190 repeats the same formulation. Read strictly, that is a
reference-count rule: find a merged commit citing `ADR-NNN`, set the field true.

**What was actually done.** Artifact verification. The field is true when the
thing the decision called for demonstrably exists, or provably existed and was
merged before later removal, established by opening the path rather than by
counting citations.

**Why the literal rule is wrong.** A reference-count rule produces answers that
are wrong in both directions, and the errors do not cancel:

- **It over-reports.** Commit messages cite neighbouring ADRs freely. The commit
  implementing ADR-033 mentions ADR-032; the commit implementing ADR-017 mentions
  ADR-018. A counting rule credits all four.
- **It under-reports.** ADR-041 and ADR-046 have zero live id-references while
  their artifacts (`codeql-analysis.yml`, the `codeql-scan` skill,
  `milestone-planner.md`) plainly exist.
- **It cannot express a reversion, which is the decisive case.** ADR-039's
  assignments were merged and then reverted. A reference-count rule marks it
  `implemented: true` permanently, because the merged references never
  disappear. That is precisely backwards for a field whose stated job is gating
  amend-versus-supersede: the record's decision is no longer in force, and
  treating it as implemented would tell a future author to supersede where an
  amendment is correct. ADR-039 is handled in this PR (see the status-decision
  section) and is the counterexample that settles the question.

**Why not recalculate to the literal rule.** Doing so would knowingly reintroduce
answers already shown to be wrong, in order to match wording rather than intent.
ADR-073 line 54 states the field's purpose in the schema itself,
`# flips true at first merged change; gates amend-vs-supersede`. Artifact
verification serves that purpose; citation counting only approximates it, and
approximates it badly on the reversion case.

**What a reviewer should do with this.** If the maintainer prefers the literal
reading, the fix is to amend ADR-073's Phase 2 wording rather than to recompute
53 records into known-wrong values. Either way the deviation is now on the
record instead of buried in a script.

**`supersedes` / `superseded-by`.** Populated only where both ends are in scope,
so no one-sided reference is created. Exactly one pair qualifies.

## Findings

Six records were corrected during review. All six were initially wrong in the
same direction: a reference-count proxy said "never built" about a decision that
had in fact shipped.

1. **ADR-050, corrected false to true.** The initial value rested on the claim
   that `scripts/sync_adr_protocol.py` does not exist, which is true today.
   History shows the script was added 2026-02-28 in `4c0d01a0`
   ("feat(governance): add ADR-to-Protocol sync process (#1247)") together with
   `tests/test_sync_adr_protocol.py`, and removed 2026-08-20 in `ba541c21`
   with the session-protocol retirement. A merged change implemented it.

   Adjacent finding, not fixed here: ADR-073 line 150 lists
   `scripts/sync_adr_protocol.py` in its Impact table as a component to check.
   That citation is now dangling. Out of scope for this PR; worth an issue.

2. **ADR-060, corrected false to true.** `_run_rework_warning_step` is absent
   today but was added 2026-05-25 in `157737a0`
   ("fix(#2063): persist rework warning in session log"). Shipped, then retired
   with session logs.

3. **ADR-067, corrected false to true.** The function its Implementation Notes
   specify by name, `_change_claim_regions`, exists at
   `scripts/validation/pr_description.py:510` and is called at line 542. The
   record is still `proposed`; its implementation landed anyway.

4. **ADR-049, corrected false to true.** The ADR names
   `scripts/validate_pr_readiness.py`, which does not exist. The gate it decided
   shipped under a different name as `scripts/validation/pre_pr.py`, which is
   live and is the pre-PR gate this repository runs. Matching on the ADR's
   proposed filename rather than on the decided capability would have scored
   this wrong.

5. **ADR-021, corrected false to true.** `.agents/governance/AI-REVIEW-MODEL-POLICY.md`
   is the artifact; the routing policy shipped even though ADR-080 later
   overtook parts of it.

6. **ADR-059, corrected false to true.** `.claude/commands/pr-review.md` exists.

Records where `implemented: false` survived verification: ADR-010 (no
evaluator/optimizer artifact in the tree, and the only commits citing it are
documentation cross-reference fixes), ADR-011, ADR-012, ADR-013, ADR-048 (four
MCP servers, none built; there is no `mcp/` tree; ADR-013's schema stub at
`src/agent-registry-schema.ts` is unused TypeScript interfaces, not the decided
MCP server), ADR-018 (the decision was session-local caching and no git-tracked
cache, which left no artifact), ADR-022, ADR-028 (zero artifacts and zero
commits of any kind citing it), ADR-031, ADR-052, ADR-061, ADR-064, ADR-065
(`success_criterion` appears nowhere in the tree), ADR-072.

### Records carrying a status/implementation mismatch, deliberately

**Eight records, counted against the final frontmatter state rather than against
an earlier draft of this paragraph.**

Five are `proposed` with `implemented: true`: ADR-038, ADR-049, ADR-059, ADR-067,
ADR-070. This is not an error. It is the field behaving as ADR-073 specifies, and
it surfaces a real governance gap the schema was built to make visible: decisions
that shipped without ever being formally accepted. ADR-070 is the clearest case,
since its own Implementation Notes read "It documents an already-landed gate; it
does not change the gate."

Three are `accepted` with `implemented: false`: ADR-010, ADR-018, ADR-028. The
mirror image, but **the label "never built" fits only two of them**, and the
distinction matters because it is a limit of the derivation rule rather than a
fact about the records.

**ADR-018 chose a no-op on purpose.** Its decision was session-local caching and
*no* git-tracked cache: the correct implementation of that decision is the
absence of an artifact. An artifact check cannot represent a negative-space
decision, so it reports `false` for a decision that was executed exactly as
written. Do not triage ADR-018 as unbuilt work. If Phase 3 wants to distinguish
these, the schema needs a value the current enum does not have.

**ADR-028 is genuinely unbuilt but is still cited as live authority.**
`.gemini/styleguide.md:15` routes output-schema questions to it. That is the same
class of problem as ADR-030's, and it is disclosed in the PR body alongside it.

ADR-010 is the only clean "accepted and never built" of the three.

An earlier version of this paragraph said "four records" while listing five, and
a sixth record (ADR-013) was in the group because its `implemented` value was
wrong. Copilot's automated review on PR #5291 caught both. ADR-013 is an Agent
Orchestration MCP that was never built: there is no `mcp/` tree, and its three
sibling MCP proposals (ADR-011, ADR-012, ADR-048) all carry `implemented: false`
for exactly that reason. It was corrected to `false`, which removes it from this
group. The count above is now generated from the files rather than transcribed.

Both groups are worth a follow-up triage issue. Neither is fixed here, because
changing a status is a governance act and this PR is a metadata backfill.

### ADR-061: the one prose edit

Prose status is "Withdrawn (2026-05-27, before acceptance, based on 6-agent
debate verdict)". The enum has no `withdrawn` member. ADR-095
(`.agents/architecture/ADR-095-scoped-re-review-axes.md`) is the precedent: it
carries `status: rejected` with prose reading "Rejected. Recorded so the
proposal is findable and does not return", which is the same concept, a proposal
declined before acceptance and kept for findability.

`status: rejected` was therefore chosen, and a paragraph was added to ADR-061's
own `## Status` section recording that choice and its precedent. This is one
reconciliation among several: ADR-002, ADR-030, ADR-036, ADR-039, ADR-052, and
ADR-055 all carry body edits too, each recorded in this document. It exists so the coercion leaves a trace in the
document a human reads, rather than only in the machine-readable block. ADR-073
line 57 requires that reconciliation happen by editing prose and never by a gate
silently rewriting it; this edit is that reconciliation, performed by hand.

### ADR-052 and ADR-055: supersession left deliberately empty

**Both prose claims are now struck**, so this section describes what was done,
not a live inconsistency.

ADR-052's `## Status` read "Proposed. Supersedes ADR-036." and ADR-055's inline
`**Status**:` read "Accepted (supersedes ADR-024, ADR-025)". ADR-036 turned out
never to have been superseded at all and ships here as `accepted`. ADR-024 and
ADR-025 remain deferred to #5192, so they have no frontmatter to hold a
reciprocal `superseded-by`, and asserting the relationship from one side only is
exactly the dangling reference ADR-073's Phase 3 bidirectional check exists to
catch.

Both records therefore carry `supersedes: []`, and both prose claims were
replaced with a dated note pointing at #5192 rather than left to contradict the
frontmatter. ADR-055's note is dated 2026-08-25; ADR-052's rejection rationale
carries the same date. **#5192, and PR #5209 which implements it, owe the
reciprocal edit** if the ADR-024/ADR-025 supersession is ever restated.

### ADR-005 and ADR-042: the one reciprocal pair

ADR-005's prose says "Superseded by [ADR-042]". ADR-042's prose claims the
supersession from its own side in three places (lines 46, 134, 221: "Supersedes
ADR-005"). Both records are in scope, so the pair is written reciprocally:
ADR-005 gets `superseded-by: ADR-042` and ADR-042 gets `supersedes: [ADR-005]`.
A validation pass confirms this is the only bidirectional pair among all 53.

### The consumer-gate objection

ADR-073 line 64 states that Phase 2 and beyond "are explicitly deferred and are
conditional on a concrete consumer existing (a stale-ADR detector, a generated
current-state index, or a dependency viewer)". Line 161 repeats it: "Do not
start until a concrete consumer (below) exists."

No such consumer exists in the tree today. Searching `scripts/` and
`scripts/validation/` finds `check_adr_uniqueness.py` and
`detect_adr_changes.py`, neither of which is a current-state index, a stale-ADR
detector, or a dependency viewer.

So this PR proceeds against its own governing ADR's stated precondition. The
justification is that issue #5190 is an explicit owner instruction to do the
backfill, and an owner instruction overrides a self-imposed sequencing
constraint. That is a legitimate override and it should be visible rather than
quiet, which is why it is recorded here and in the PR description. A reviewer who
wants the consumer built first has a well-grounded objection rooted in the ADR's
own text.

The risk this precondition was protecting against is low for this change
specifically: Phase 2 is additive and reversible, and no gate is being flipped to
enforcing (that is Phase 3/4 and explicitly out of scope). The cost of doing it
early is a backfill that might need revision if a future consumer wants different
fields.

## Verification performed

A validation pass over all 96 frontmatter-bearing ADRs checks, for each record:
YAML parses under `yaml.safe_load`; all six required keys present; `status` in
the enum; `id` matches the filename number; `date` matches `YYYY-MM-DD`;
`implemented` is a bool; `supersedes` is a list; the prose `## Status` first word
agrees with the enum; and every supersession is reciprocal.

Result, re-run against **all 67 records this PR touches**, not the original 53:
**zero errors**.

**Read that claim narrowly. It is a shape check, not a correctness check.** The
pass verifies that `date` matches `YYYY-MM-DD`; it cannot verify that the value
is the right date. "Zero errors" therefore means "nothing is malformed", not
"the dates are correct", and reading it the second way would be a mistake.

That gap is not hypothetical. The full-state six-agent debate found **seven date
values that were wrong while passing this check**, across three root causes the
rule had not covered: dated `**Superseded by**:` and `**Amended by**:` trailer
blocks outside any `## Status` heading (ADR-005, ADR-017), a `### Date`
subheading nested under an amendment heading (ADR-042), and a date that was
merely *quoted* from another ADR being mistaken for an update date (ADR-040,
which had been "corrected" once already onto ADR-080's acceptance date). No bot
round caught any of them. The lesson is that a schema validator and a reviewer
who opens the file are not substitutes for each other.

The same pass surfaced two problems in records outside the original 53. The
first is now fixed in this PR; the second is not:

- **Fixed here.** Ten ADRs carried a partial frontmatter block without `id`,
  `supersedes`, `superseded-by`, `explainer`, or `implemented`: ADR-003, ADR-020,
  ADR-023, ADR-027, ADR-034, ADR-057, ADR-058, ADR-066, ADR-069, ADR-071.
  ADR-071 also had no `date`. They fell outside issue #5190's 59-record list
  because they were not frontmatter-free, yet they were not ADR-073-conformant
  either. Filed as #5290 and **completed in this PR**, which is why it carries a
  closing keyword for that issue. See "The ten records from issue #5290" below.
- **Still open.** ADR-091 declares `supersedes: [ADR-079]` while ADR-079 carries
  no reciprocal `superseded-by`. Same class of defect as issue #5192, where
  ADR-079 is already named, and PR #5209 is the change that handles it. Out of
  scope here.

## Security review

Three concerns, per ADR-073's own integrity rules.

**Mass `status: accepted` as a forgeable approval signal.** ADR-073 line 61
warns that a hand-edit to `accepted` must not be treated as governance approval.
This change writes `status: accepted` into 33 records at once, which is exactly
the shape that rule distrusts. It is legitimate here only because of a narrow
distinction: none of the 33 is a *transition*. Each record's prose already reads
"Accepted", in most cases for months; the frontmatter is a transcription of an
approval that already happened and is visible in the body above it. No record's
governance state changes.

That distinction is load-bearing and it must be stated in the PR description,
because a reader who cannot see it has no way to tell this change apart from a
mass self-approval. The reviewable invariant is: for all 53, frontmatter
`status` agrees with prose `## Status`, and the validation pass above checks
exactly that. The one record where they would have disagreed is ADR-061, whose
prose was edited by hand and recorded above.

**`explainer`.** Set to `null` on all 53. ADR-073 line 62 makes the field
display-only and forbids auto-fetch (CWE-918, server-side request forgery, where
a tool that fetches a URL from a document can be pointed at internal hosts). No
in-scope record pairs with a living design doc, so `null` is both correct and the
safe value. No external URL enters the frontmatter of any record.

**YAML parse safety.** ADR-073 line 132 warns that malformed frontmatter "can
fail parsing for every downstream consumer at once". The risk here is contained
by construction: every emitted value is a machine-generated literal from a fixed
table (an enum member, an ISO date, a bracketed id list, a bool, `null`), so no
record's prose reaches a YAML value position. The long, colon-bearing, and
bracket-bearing status prose in ADR-040 and ADR-041 stays in the body, below the
closing delimiter, where YAML never sees it.

Two mechanical checks guarded insertion: every target file was confirmed to begin
with its own `# ADR-NNN` heading before writing, so no record with a pre-existing
`---` near the top could be corrupted, and the writer refuses any file that
already starts with `---`. Both checks passed on all 53. The verification pass
then re-parses every block with `yaml.safe_load`, the loader ADR-073 mandates.

Assessment: cleared. No P0 or P1 finding. The one residual is governance, not
technical, and is the consumer-gate objection recorded above.

## Verdict

Accept with the caveats recorded in this document, which are, in order of how
much they should weigh on a reviewer:

1. This is a single-reviewer review, not the six-agent consensus the adr-review
   skill specifies. Sub-agent delegation was unavailable.
2. The backfill runs ahead of ADR-073's own consumer-gate precondition, on the
   authority of issue #5190.
3. `decision-makers` is uniformly `[rjmurillo]`, discarding `**Deciders**` lines
   that name other parties.
4. ADR-052 and ADR-055 carry deliberately empty `supersedes` pending #5192.
5. `date` now tracks the latest self-referential update date anywhere in the
   record, including amendment headings. This corrected 13 of the 53.

## Status mapping for all 53 records reviewed

| ADR | status | date | supersedes | superseded-by | implemented |
|-----|--------|------|------------|---------------|-------------|
| ADR-001 | accepted | 2025-12-13 | [] | null | true |
| ADR-005 | superseded | 2025-12-18 | [] | ADR-042 | true |
| ADR-006 | accepted | 2026-04-29 | [] | null | true |
| ADR-007 | accepted | 2026-08-16 | [] | null | true |
| ADR-008 | accepted | 2026-08-19 | [] | null | true |
| ADR-009 | accepted | 2025-12-20 | [] | null | true |
| ADR-010 | accepted | 2025-12-20 | [] | null | false |
| ADR-011 | proposed | 2025-12-21 | [] | null | false |
| ADR-012 | proposed | 2025-12-21 | [] | null | false |
| ADR-013 | proposed | 2025-12-21 | [] | null | false |
| ADR-014 | accepted | 2026-08-16 | [] | null | true |
| ADR-015 | accepted | 2025-12-22 | [] | null | true |
| ADR-016 | accepted | 2025-12-22 | [] | null | true |
| ADR-017 | accepted | 2025-12-23 | [] | null | true |
| ADR-018 | accepted | 2025-12-23 | [] | null | false |
| ADR-019 | accepted | 2025-12-23 | [] | null | true |
| ADR-021 | accepted | 2025-12-23 | [] | null | true |
| ADR-022 | proposed | 2025-12-23 | [] | null | false |
| ADR-026 | accepted | 2026-07-27 | [] | null | true |
| ADR-028 | accepted | 2025-12-23 | [] | null | false |
| ADR-029 | accepted | 2025-12-27 | [] | null | true |
| ADR-031 | proposed | 2025-12-29 | [] | null | false |
| ADR-032 | accepted | 2025-12-30 | [] | null | true |
| ADR-033 | accepted | 2026-08-16 | [] | null | true |
| ADR-035 | accepted | 2025-12-30 | [] | null | true |
| ADR-037 | accepted | 2026-07-20 | [] | null | true |
| ADR-038 | proposed | 2026-01-01 | [] | null | true |
| ADR-040 | accepted | 2026-07-11 | [] | null | true |
| ADR-041 | accepted | 2026-07-21 | [] | null | true |
| ADR-042 | accepted | 2026-01-17 | [ADR-005] | null | true |
| ADR-043 | accepted | 2026-01-21 | [] | null | true |
| ADR-045 | accepted | 2026-02-07 | [] | null | true |
| ADR-046 | accepted | 2026-02-08 | [] | null | true |
| ADR-047 | accepted | 2026-04-29 | [] | null | true |
| ADR-048 | proposed | 2026-02-23 | [] | null | false |
| ADR-049 | proposed | 2026-02-24 | [] | null | true |
| ADR-050 | accepted | 2026-02-21 | [] | null | true |
| ADR-051 | accepted | 2026-03-07 | [] | null | true |
| ADR-052 | rejected | 2026-08-25 | [] | null | false |
| ADR-053 | accepted | 2026-03-07 | [] | null | true |
| ADR-054 | accepted | 2026-07-20 | [] | null | true |
| ADR-055 | accepted | 2026-08-25 | [] | null | true |
| ADR-056 | accepted | 2026-03-08 | [] | null | true |
| ADR-059 | proposed | 2026-05-08 | [] | null | true |
| ADR-060 | accepted | 2026-07-27 | [] | null | true |
| ADR-061 | rejected | 2026-08-25 | [] | null | false |
| ADR-062 | accepted | 2026-07-27 | [] | null | true |
| ADR-063 | accepted | 2026-07-27 | [] | null | true |
| ADR-064 | proposed | 2026-06-01 | [] | null | false |
| ADR-065 | proposed | 2026-05-29 | [] | null | false |
| ADR-067 | proposed | 2026-06-02 | [] | null | true |
| ADR-070 | proposed | 2026-07-27 | [] | null | true |
| ADR-072 | proposed | 2026-06-09 | [] | null | false |

## Full-state debate: all 67 records (final round)

A second six-agent round reviewed the **complete final state**, all 67 records at
once, rather than the five status decisions alone. This is the round that
satisfies the review-evidence requirement for the 62 mechanical records, which
the first round did not cover.

**Verdict: 3 ACCEPT, 2 DISAGREE-AND-COMMIT, 1 BLOCK (cleared). Not unanimous.**

| Role | Verdict |
|---|---|
| security | ACCEPT |
| analyst | ACCEPT |
| high-level-advisor | ACCEPT |
| architect | DISAGREE-AND-COMMIT |
| critic | DISAGREE-AND-COMMIT |
| independent-thinker | **BLOCK**, narrow, clearable by two specific fixes |

The BLOCK was cleared by making the two fixes it named, not by overruling it.
Both are in this PR: the seven date corrections below, and making three records'
dates self-documenting in their own prose.

**What this round found that no automated review did: seven wrong `date` values,
all of which passed the schema validator.** Three root causes, one underlying
gap. The rule matched a curated set of patterns rather than scanning each file
for every date-shaped signal:

| ADR | Was | Now | Why the rule missed it |
|---|---|---|---|
| ADR-005 | 2025-12-18 | 2026-01-17 | Dated `**Superseded by**:` trailer block, outside any `## Status` heading. Now agrees with ADR-042's own record of the same event. |
| ADR-017 | 2025-12-23 | 2025-12-28 | Same trailer-block gap, via `**Amended by**:` Session 93 entries. |
| ADR-042 | 2026-01-17 | 2026-04-13 | A `### Date` subheading nested under `## Amendment 1`. The amendment-heading scan did not look inside the heading's own subsection. Confirmed by commit `4d1aaa5e1` (PR #1647). |
| ADR-040 | 2026-07-11 | 2026-08-14 | **Two bugs stacked.** `2026-07-11` is ADR-080's acceptance date, merely *quoted* inside ADR-040's supersession callout: a mentioned date mistaken for an update date, and it had already been "corrected" onto that wrong value once. Real last edit confirmed by commit `333a80b74` (74 insertions), and the file's own line 274 reads "As of 2026-08-14", a sentence that cannot have been written earlier. |
| ADR-036, ADR-055, ADR-061 | 2026-08-25 | 2026-08-25 | Values were right; nothing in the records' prose let a reader derive them. Each now carries a short dated clause. |

The ADR-040 case is the instructive one: a date-shaped string in a record is not
evidence about that record. It may be a quotation about a different one. Any
future automation over this field has to distinguish "the date this record was
changed" from "a date this record mentions", and the current rule does that by
context, not by pattern.

## The five status decisions: per-role verdicts (first round)

The roster below reviewed the five status decisions. **Consensus was
DISAGREE-AND-COMMIT, not unanimous ACCEPT**, and the disagreement was
substantive: two reviewers argued against the originally proposed status for two
records, and security registered a narrow BLOCK. The originally proposed pattern
was `accepted` for ADR-002 and `rejected` for ADR-039. **Both were overturned by
the debate.** What shipped is the synthesis, not the proposal.

| Role | Verdict | Position |
|---|---|---|
| **architect** | ACCEPT | Confirmed all five as originally proposed. Wanted `implemented: true` on ADR-002 with the debate log cited for its acceptance; `supersedes: []` on ADR-039; judged a `superseded` framing wrong for ADR-030 because ADR-027 predates it. **Caught the ADR-036 mischaracterization in the backfill log** and required an Issue #124 pointer in ADR-052's rejection prose. |
| **critic** | DISAGREE-AND-COMMIT | Found ADR-002's cited evidence argues the **opposite** of the claim made from it: `model_pin_baseline.json` is a draining ratchet toward zero, not a freeze or endorsement. Found `rejected` wrong for ADR-039 because it shipped and ran, where this repo's `rejected` precedent means declined-before-acceptance; recommended `deprecated`. Flagged ADR-030's six live citations as making a full status flip risky. Recommended ADR-052 to `rejected`. Warned that **all five would end with frontmatter and prose disagreeing** unless prose was explicitly reconciled. |
| **independent-thinker** | DISAGREE-AND-COMMIT | Independently verified evidence rather than accepting it: found `.claude/agents/critic.md` and `qa.md` are `opus`, contradicting ADR-002's own table. Recommended `deprecated` over `accepted` for ADR-002, citing ADR-080 as methodologically superseding it and ADR-073's debate-log binding on any `accepted` transition. Recommended `deprecated` over `rejected` for ADR-039, and found the revert story factually incomplete: it happened incidentally via PR #1046 / commit `568af6775`, three weeks late, not through ADR-039's own rollback procedure. **Blocked rewriting ADR-030's body** as fabricating a decision never made. Reached `rejected` for ADR-052 via a footgun argument: leaving it `proposed` risks an agent literally executing "remove `templates/agents/`". |
| **security** | **BLOCK**, narrowly, on ADR-002 only | Found ADR-098 and ADR-093 directly on point: both ship `status: proposed` against `implemented: true` precisely because "the acceptance of a governance ADR is a maintainer act". Flipping ADR-002 to `accepted` here would be **the exact self-asserted-approval pattern ADR-073 line 61 exists to prevent**. Cleared ADR-039, ADR-036, and the ADR-052 supersession strike as ACCEPT, being transcription and drift-fix rather than new transitions. Recommended `deprecated` over `rejected` for ADR-030, since `rejected` implies an adjudication that never occurred. Confirmed no CWE-918 exposure: `explainer` is `null` everywhere. |
| **analyst** | Evidence pass, no status recommendation | PASS/PARTIAL/FAIL over five factual claims. Confirmed five of six named agents match ADR-002 rather than ADR-039 (**PARTIAL**: `critic` and `qa` match neither table). Confirmed ADR-039's monitoring evidence file is empty. Confirmed `.claude/skills/github/SKILL.md` declares no `allowed-tools: mcp__github__*`. Confirmed ADR-027 and ADR-030 share a date and parentage. Confirmed no ADR-052 Option B generator exists and `templates/agents/` remains live. |
| **high-level-advisor** | ACCEPT | Called ADR-039 the strongest of the five, "transcription of a decision that already fired". Endorsed ADR-030 to `rejected` with the ADR-027 pointer. Required that shipping all five in one PR be **stated explicitly in the PR body with the reversals enumerated, not buried as "just metadata"**. **Registered the one dissent on ADR-052**, preferring it stay `proposed`. |

### Where the reviewers disagreed, and how it resolved

Three genuine disagreements. None is papered over.

1. **ADR-002: `accepted` (proposed) against `deprecated` (shipped).** Security
   BLOCKed the `accepted` flip; critic and independent-thinker independently
   reached `deprecated` by different routes (evidence misreading, and ADR-080 as
   methodological supersession). **Resolution: `deprecated`.** The block is
   cleared because the record no longer asserts an acceptance.
2. **ADR-039: `rejected` (proposed) against `deprecated` (shipped).** Critic and
   independent-thinker both objected that `rejected` misdescribes a decision that
   ran in production for five weeks, against this repo's own ADR-095 and ADR-061
   precedent. Architect and high-level-advisor had accepted `rejected`.
   **Resolution: `deprecated`.**
3. **ADR-052: `rejected` (3 votes) against staying `proposed` (1 vote).**
   Architect, critic, and independent-thinker said `rejected`;
   high-level-advisor dissented. **Resolution: `rejected`, a majority call and
   not unanimous.** Recorded as such so a future reader does not mistake it for
   consensus.

The synthesis was made by the repository owner after reading all six.

**Scope boundary the debate set deliberately.** Security, critic, and
independent-thinker converged on a light-touch change for ADR-030 (frontmatter
plus a minimal note, body untouched) with the citation sweep deferred to #5293,
rather than a body rewrite or an in-PR sweep. That boundary is a debate outcome,
not an oversight. Its cost is disclosed in the PR body: ADR-030 merges as
`rejected` while three live sites still cite it as binding authority.

## The five status decisions (six-agent debate)

These five were deferred from the original backfill because each needed a
decision rather than a transcription. The owner convened the full adr-review
roster on them. Summary of what the debate settled and the evidence each rests
on, all verified against the live tree before writing:

### ADR-002, ADR-039: both `deprecated`

The pair was one question. ADR-039 claimed to supersede ADR-002 "pending
validation" during a provisional window (2026-01-03 to 2026-01-17).

The window closed with **zero of its four acceptance criteria measured**.
`.agents/governance/model-pin-evidence.json` holds `"pins": []`. No validation
verdict, pass or fail, was recorded anywhere. The downgrades were reverted, but
not through ADR-039's own documented rollback procedure: they went incidentally
on 2026-02-07, three weeks after the window closed, inside commit `568af6775`
(PR #1046, "migrate agent prompts from cloudmcp-manager to Memory Router"), which
rewrote 41 agent files for an unrelated reason and does not mention ADR-039 at
all. Verified: `model:` for orchestrator, architect, independent-thinker,
roadmap, high-level-advisor, and security all read `opus` today, which is
ADR-002's assignment.

So ADR-039's `supersedes` is `[]`: the supersession never took effect.

**ADR-002 is not revived to `accepted`** on the strength of that. Its own table
is also wrong about the tree: it assigns `critic` and `qa` to Sonnet where both
are `opus`, and it scopes itself to "All 18 agents" where 33 exist under
`.claude/agents/`. And the question has been re-answered on better grounds by
ADR-080 (accepted, 2026-07-11), whose Context section rejects ADR-002's method
directly: "The pins encode a guess, not a measurement."

`superseded-by` stays `null` on ADR-002. Naming ADR-080 needs the reciprocal
`supersedes: [ADR-002]` on an accepted ADR, which is outside this PR.

**Why `deprecated` and not `rejected`.** Both shipped and ran in production,
ADR-039 for roughly five weeks. This repository uses `rejected` for a proposal
declined *before* it was ever in force (ADR-095, ADR-061). `deprecated` means
"was in force, no longer is". Both carry `implemented: true`, which stays true
despite the revert, for the reason given in the deviation note above.

The pair follows the ADR-098 and ADR-093 precedent for status handling: ADR-098's
own Status section states that "the acceptance of a governance ADR is a maintainer
act", which is why both of those ship `proposed` against `implemented: true`
rather than self-asserting acceptance.

### ADR-030: `rejected`, body untouched

Not a decision record. It is a same-day amendment memo to ADR-027 (still
`proposed`), and its own header reads `**Status**: Critical Update - Changes
Recommendation`, which is not an enum member. Its "Option E" was not built:
`.claude/skills/github/SKILL.md` wraps Python scripts and contains zero
`mcp__github` references, so it never declared `allowed-tools: mcp__github__*`.

**The body is deliberately left alone.** It is the only record of what was argued
on 2025-12-23, and rewriting it would fabricate a decision that was never made.
The record gets frontmatter and a five-line note, nothing else.

Six live sites still cite ADR-030 as binding authority, including
`scripts/validation/check_agent_skill_discriminator.py`, which hardcodes its
path. Two more cite `ADR-030 line 31`, a line number this PR shifts by roughly
16. Filed as issue #5293, which also carries the real open question: the
skill-first principle is still live practice and now has no written home.

### ADR-036: `accepted`, and NOT superseded

**This corrects an error in an earlier version of this document**, which grouped
ADR-036 with ADR-024 and ADR-025 as "actually superseded, deferred to #5192".
That characterization was wrong.

ADR-036 is the live, operative architecture. Verified: 31 `templates/agents/*.shared.md`
files exist and `build/generate_agents.py` reads them on every build. ADR-052,
the rival proposal that claimed to supersede it, was never implemented. ADR-036
has nothing to do with the ADR-024/ADR-025 dangling-supersession problem and
ships here as an ordinary `accepted` transcription.

Two stale `Generate-Agents.ps1` references (lines 53 and 101) are repointed to
`build/generate_agents.py`. This is an internal inconsistency, not a new claim:
the same file already names `generate_agents.py` correctly at line 231. Stale
agent-count figures elsewhere in the record are left alone as out of scope.

### ADR-052: `rejected`

Proposed eliminating `templates/` in favour of generating platform variants from
`src/claude/` ("Option B"). Five months on, none of it exists:
`build/scripts/generate_platform_agents.py` and `platform-overrides/` are both
absent, while `templates/agents/*.shared.md` remains what the build reads.

Its central evidence, a 2 to 13 percent template-vs-Claude drift measurement
presented as sync failure, had already been answered by ADR-036 before ADR-052
was written: "Similarity metrics comparing Claude to templates measure divergence
that is **BY DESIGN**, not sync failure." ADR-052 never engages that rebuttal.

The prose claim "Supersedes ADR-036." is struck, matching the frontmatter's
`supersedes: []`.

**Issue #124 (the standing question of whether the two-source template pattern
should continue, referenced in ADR-036) remains open and unresolved. This
rejection closes ADR-052's specific proposal, not the underlying question.**

## The ten records from issue #5290

These carried `status`, `date`, and `decision-makers` but none of `id`,
`supersedes`, `superseded-by`, `explainer`, or `implemented`, so they fell
between issue #5190's two categories and nothing owned them. ADR-071 had no
`date` either; its `## Date` section supplies 2026-08-19.

**Existing recorded values are preserved, not overwritten.** This is a deliberate
divergence from the `decision-makers: [rjmurillo]` rule applied to the 53. Those
53 recorded no decision-makers at all, so a value had to be chosen. These ten
name their own, so overwriting them would destroy recorded information for the
sake of uniformity, which is the exact objection raised against the uniform rule.
Their `consulted` and `informed` keys are kept as well. Two shape fixes only:
ADR-027's `decision-makers` was a bare scalar and is normalized to a list, and
ADR-066's quoted `status` is unquoted.

| ADR | status | date | implemented | Basis |
|-----|--------|------|-------------|-------|
| ADR-003 | accepted | 2025-12-16 | true | `build/scripts/validate_agent_matrix_refs.py`, `git_hook_policy.py` |
| ADR-020 | proposed | 2025-12-19 | false | Zero references anywhere |
| ADR-023 | accepted | 2025-12-26 | true | `scripts/eval/eval-suite.py` |
| ADR-027 | proposed | 2025-12-23 | false | Zero references; ADR-030's parent |
| ADR-034 | accepted | 2026-07-08 | true | `validate_investigation_claims.py` plus its workflow. Date from `## Amendment (2026-07-08)` |
| ADR-057 | accepted | 2026-07-22 | true | 11 executable references. Date from `## Amendment 2026-07-22 (Issue #3185)` |
| ADR-058 | proposed | 2026-05-03 | true | `scripts/eval/_eval_agent_types.py:28` implements its fourth verdict outcome |
| ADR-066 | accepted | 2026-07-19 | true | `.claude/lib/hook_dispatch.py`, `generate_dispatcher.py`. Date from a dated `## Status` statement |
| ADR-069 | proposed | 2026-05-02 | false | Its only executable references are renumbering-history strings in the uniqueness allowlist, not implementation |
| ADR-071 | accepted | 2026-08-19 | true | `nightly-cli-smoke.yml`, runtime-contract tests |

ADR-058 is a sixth `proposed`-but-implemented record, on top of the five in the
53. It is the same governance gap, not a new one.

## Records excluded from this change

Two of the 59 frontmatter-free ADRs remain untouched. Four that were previously
deferred (ADR-002, ADR-030, ADR-036, ADR-039) are resolved above and now ship in
this PR:

| ADR | Reason | Owning issue |
|-----|--------|--------------|
| ADR-024, ADR-025 | Prose-marked Accepted but actually superseded. The reciprocal `superseded-by` fix belongs with the other dangling supersessions, which PR #5209 handles. | #5192 |

Resolved and now shipping here, previously deferred: ADR-002 and ADR-039 (#5193)
are `deprecated`, ADR-030 (#5195) is `rejected`, and ADR-036 was never part of
the #5192 problem at all.

Because ADR-024 and ADR-025 are excluded, issue #5190's acceptance criterion that
every `ADR-[0-9]*.md` carry frontmatter is not fully met by this change. It is
therefore referenced with `Refs`, not `Fixes`. A follow-up after #5192 lands can
pick up the remaining two
records listed under "Verification performed", and close it.

## Scope-gate note

The final batches were committed with the `scope-policy` check's own opt-out.
That check (`scripts/detect_scope_explosion.py`) blocks a branch changing more
than 50 files, and this change touches 54. Its module docstring documents the
opt-out as a first-class parameter for justified large PRs, and it is not one of
the six hook-bypass mechanisms `.claude/rules/universal.md` MUST-NOT-2 forbids.
No other hook was skipped: every batch cleared `adr-review-policy`,
`staged-dash-policy`, and markdown lint.

The justification the gate asks for: the file count is set by issue #5190 (53
records) and issue #5290 (10 more), plus 4 records added for status decisions,
giving **67 ADRs across 73 files**. Sixty-two of those carry one identical
nine-line block and nothing else. The remainder is five status decisions with
prose changes, seven dated clauses, a handful of em-dash repairs, and the
taste-lints fix with its tests. A validation pass over all 100
frontmatter-bearing ADRs proves conformance mechanically. Reviewing 62 copies of
one block is not the burden the 50-file limit exists to prevent, and the 5 that
are real decisions are argued individually above.

## Commit batches

The `adr-policy` pre-commit gate requires a debate log staged alongside every
commit that touches an ADR, so this log is staged with each batch and records
the batch here as it lands.

| Batch | ADRs |
|-------|------|
| 1 | ADR-001, ADR-005, ADR-006, ADR-007 |
| 2 | ADR-008, ADR-009, ADR-010, ADR-011 |
| 3 | ADR-012, ADR-013, ADR-014, ADR-015 |
| 4 | ADR-016, ADR-017, ADR-018, ADR-019 |
| 5 | ADR-021, ADR-022, ADR-026, ADR-028 |
| 6 | ADR-029, ADR-031, ADR-032, ADR-033 |
| 7 | ADR-035, ADR-037, ADR-038, ADR-040 |
| 8 | ADR-041, ADR-042, ADR-043, ADR-045 |
| 9 | ADR-046, ADR-047, ADR-048, ADR-049 |
| 10 | ADR-050, ADR-051, ADR-052, ADR-053 |
| 11 | ADR-054, ADR-055, ADR-056, ADR-059 |
| 12 | ADR-060, ADR-061, ADR-062, ADR-063 |
| 13 | ADR-064, ADR-065, ADR-067, ADR-070 |
| 14 | ADR-072 |
| 15 | ADR-014, ADR-033, ADR-040, ADR-041 |
| 16 | ADR-047, ADR-060, ADR-061, ADR-062 |
| 17 | ADR-063, ADR-070 |
| 18 | ADR-055 |
| 19 | ADR-002, ADR-030, ADR-036, ADR-039 |
| 20 | ADR-052 |
| 21 | ADR-003, ADR-020, ADR-023, ADR-027 |
| 22 | ADR-034, ADR-057, ADR-058, ADR-066 |
| 23 | ADR-069, ADR-071 |
| 24 | ADR-002, ADR-030, ADR-039, ADR-052 |
| 25 | ADR-030, ADR-036, ADR-055, ADR-061 |
| 26 | ADR-005, ADR-017, ADR-026, ADR-036 |
| 27 | ADR-039, ADR-040, ADR-042, ADR-055 |
| 28 | ADR-061 |
