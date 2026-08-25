# ADR-073 Phase 2 backfill: review and debate log

Subject: adding ADR-073 lifecycle frontmatter to 53 existing ADRs that carry no
frontmatter block. Issue #5190. Branch `claude/autoplan-goal-vd6pmg`.

ADR-073 (`.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md`) is Accepted
(2026-06-19) and is not reopened here. Its schema is taken as given. This review
covers one question only: is the prose-to-enum mapping proposed for each of the
53 records correct, and are the derivation rules behind it sound?

## How this review was conducted

**Read this section before treating this document as consensus evidence.**

The `adr-review` skill specifies a six-agent debate (architect, critic,
independent-thinker, security, analyst, high-level-advisor). That roster could
not be convened: sub-agent delegation was unavailable in the session that
produced this change, so no agent other than the authoring one participated.

What this document is instead: a single-reviewer structured review worked
through the six adr-review axes in sequence, in which every factual claim was
verified against a file or a git command rather than asserted. It is review
evidence and it is not a six-agent consensus artifact. A reviewer weighing it
should discount it accordingly, and the acceptance of this change rests on human
review of the PR, not on a consensus that did not happen.

The review was not a formality. It changed six of the fifty-three records before
they were written. Those corrections are recorded under "Findings" below.

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

**`date`.** The most recent date the record states in a date-bearing field: the
`## Date` section (its last value when it lists several) or an inline `**Date**:`
or `**Revised**:` line. Where no such field exists, and only there, the value is
`git log --follow -1 --format=%ad --date=short`. Two records needed the git
fallback: ADR-001 (2025-12-13) and ADR-026 (2026-07-27).

Amendment dates appearing only inside `## Status` prose are deliberately not
used. This is a real trade and it is recorded rather than hidden: ADR-040's
prose records a partial supersession dated 2026-07-11 while its frontmatter
`date` reads 2026-01-03, and ADR-062 and ADR-063 have the same shape. The rule
was kept because the issue's acceptance criterion names the `## Date` section as
the source, and because a rule that scrapes narrative prose for dates is exactly
the brittleness ADR-073 exists to remove. The cost is that `date` means "last
dated field", not "last touched".

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
documentation cross-reference fixes), ADR-011, ADR-012, ADR-048 (three MCP
servers, none built; there is no `mcp/` tree), ADR-018 (the decision was
session-local caching and no git-tracked cache, which left no artifact),
ADR-022, ADR-028 (zero artifacts and zero commits of any kind citing it),
ADR-031, ADR-052, ADR-061, ADR-064, ADR-065 (`success_criterion` appears
nowhere in the tree), ADR-072.

### Records carrying a status/implementation mismatch, deliberately

Four records are `proposed` with `implemented: true`: ADR-038, ADR-049, ADR-059,
ADR-067, plus ADR-070. This is not an error. It is the field behaving as ADR-073
specifies, and it surfaces a real governance gap the schema was built to make
visible: decisions that shipped without ever being formally accepted. ADR-070 is
the clearest case, since its own Implementation Notes read "It documents an
already-landed gate; it does not change the gate."

Three records are `accepted` with `implemented: false`: ADR-010, ADR-018,
ADR-028. These are the mirror image, decisions accepted and never built.

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
own `## Status` section recording that choice and its precedent. This is the
only body edit in the change. It exists so the coercion leaves a trace in the
document a human reads, rather than only in the machine-readable block. ADR-073
line 57 requires that reconciliation happen by editing prose and never by a gate
silently rewriting it; this edit is that reconciliation, performed by hand.

### ADR-052 and ADR-055: supersession left deliberately empty

ADR-052's prose reads "Proposed. Supersedes ADR-036." ADR-055's reads "Accepted
(supersedes ADR-024, ADR-025)". All three targets are deferred from this PR
pending issue #5192, so they have no frontmatter to hold a reciprocal
`superseded-by`. Writing `supersedes: [ADR-036]` now would create exactly the
one-sided reference ADR-073's Phase 3 bidirectional check is meant to catch.

Both fields are therefore left `[]`, and the supersession remains recorded in
prose where it already was. Whichever of #5190 or #5192 lands second owes the
reciprocal edit on both ends. This is a known, deliberate incompleteness, not an
oversight.

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

Result on the 53 records this PR touches: zero errors.

The same pass reports pre-existing problems in records this PR does not touch,
recorded here because they were seen and should not be lost:

- Ten ADRs carry a partial frontmatter block with a bare `status:` line and none
  of the other five fields: ADR-003, ADR-020, ADR-023, ADR-027, ADR-034, ADR-057,
  ADR-058, ADR-066, ADR-069, ADR-071. They were excluded from issue #5190's
  59-record list because they are not frontmatter-free, but they are not
  ADR-073-conformant either. ADR-071 additionally has no `date`. Completing
  Phase 2 requires a pass over these ten.
- ADR-091 declares `supersedes: [ADR-079]` while ADR-079 does not carry the
  reciprocal `superseded-by`. This is the same class of defect as issue #5192
  and ADR-079 is named there.

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
5. `date` tracks the last dated field, not the last amendment recorded in prose.

## Status mapping for all 53 records reviewed

| ADR | status | date | supersedes | superseded-by | implemented |
|-----|--------|------|------------|---------------|-------------|
| ADR-001 | accepted | 2025-12-13 | [] | null | true |
| ADR-005 | superseded | 2025-12-18 | [] | ADR-042 | true |
| ADR-006 | accepted | 2025-12-18 | [] | null | true |
| ADR-007 | accepted | 2026-01-01 | [] | null | true |
| ADR-008 | accepted | 2025-12-20 | [] | null | true |
| ADR-009 | accepted | 2025-12-20 | [] | null | true |
| ADR-010 | accepted | 2025-12-20 | [] | null | false |
| ADR-011 | proposed | 2025-12-21 | [] | null | false |
| ADR-012 | proposed | 2025-12-21 | [] | null | false |
| ADR-013 | proposed | 2025-12-21 | [] | null | true |
| ADR-014 | accepted | 2025-12-22 | [] | null | true |
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
| ADR-033 | accepted | 2025-12-30 | [] | null | true |
| ADR-035 | accepted | 2025-12-30 | [] | null | true |
| ADR-037 | accepted | 2026-07-20 | [] | null | true |
| ADR-038 | proposed | 2026-01-01 | [] | null | true |
| ADR-040 | accepted | 2026-01-03 | [] | null | true |
| ADR-041 | accepted | 2026-01-16 | [] | null | true |
| ADR-042 | accepted | 2026-01-17 | [ADR-005] | null | true |
| ADR-043 | accepted | 2026-01-21 | [] | null | true |
| ADR-045 | accepted | 2026-02-07 | [] | null | true |
| ADR-046 | accepted | 2026-02-08 | [] | null | true |
| ADR-047 | accepted | 2026-02-16 | [] | null | true |
| ADR-048 | proposed | 2026-02-23 | [] | null | false |
| ADR-049 | proposed | 2026-02-24 | [] | null | true |
| ADR-050 | accepted | 2026-02-21 | [] | null | true |
| ADR-051 | accepted | 2026-03-07 | [] | null | true |
| ADR-052 | proposed | 2026-03-01 | [] | null | false |
| ADR-053 | accepted | 2026-03-07 | [] | null | true |
| ADR-054 | accepted | 2026-07-20 | [] | null | true |
| ADR-055 | accepted | 2025-12-29 | [] | null | true |
| ADR-056 | accepted | 2026-03-08 | [] | null | true |
| ADR-059 | proposed | 2026-05-08 | [] | null | true |
| ADR-060 | accepted | 2026-05-25 | [] | null | true |
| ADR-061 | rejected | 2026-05-27 | [] | null | false |
| ADR-062 | accepted | 2026-05-31 | [] | null | true |
| ADR-063 | accepted | 2026-06-01 | [] | null | true |
| ADR-064 | proposed | 2026-06-01 | [] | null | false |
| ADR-065 | proposed | 2026-05-29 | [] | null | false |
| ADR-067 | proposed | 2026-06-02 | [] | null | true |
| ADR-070 | proposed | 2026-05-31 | [] | null | true |
| ADR-072 | proposed | 2026-06-09 | [] | null | false |

## Records excluded from this change

Six of the 59 frontmatter-free ADRs are deliberately not touched, because each
needs a decision that belongs to another open issue:

| ADR | Reason | Owning issue |
|-----|--------|--------------|
| ADR-002, ADR-039 | Status is a "provisional" window that expired 2026-01-17. No enum member represents it. | #5193 |
| ADR-030 | Not a decision record. Skill documentation carrying a "Critical Update" status. Its fate is being decided elsewhere. | #5195 |
| ADR-024, ADR-025, ADR-036 | Prose-marked Accepted but actually superseded. The reciprocal `superseded-by` fix belongs with the other dangling supersessions. | #5192 |

Because these six are excluded, issue #5190's acceptance criterion that every
`ADR-[0-9]*.md` carry frontmatter is not fully met by this change. It is
therefore referenced with `Refs`, not `Fixes`. A follow-up after #5192, #5193,
and #5195 land can pick up the remaining six, plus the ten partial-frontmatter
records listed under "Verification performed", and close it.

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
