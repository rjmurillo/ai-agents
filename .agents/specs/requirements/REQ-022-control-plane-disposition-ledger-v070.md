---
type: requirement
id: REQ-022
title: Control-plane disposition ledger for v0.7.0
status: draft
priority: P0
category: functional
epic: EPIC-5456
source: GH-5456
related:
  - REQ-021
  - DESIGN-021
created: 2026-09-11
updated: 2026-09-11
author: spec
tags:
  - control-plane
  - disposition
  - v0.7.0
---

# REQ-022: Control-plane disposition ledger for v0.7.0

## Step 0 First Principles

Answers below are cohort-level and identical in substance to REQ-021's Step
0 block; restated here per spec-generator's requirement that each emitted
REQ be self-contained. See REQ-021 for the full evidentiary citations.

### Q1 Demand Reality

rjmurillo (epic #5456 author); the v0.7.0 Release gates checklist item "Every
retained candidate has a recorded `KEEP` justification"; the epic's
Disposition contract section itself (defines KEEP/MERGE/DELETE/EXPERIMENT
and the five required KEEP fields); issue #5241 (named release candidate
whose items 2-4 this cohort's REQ-023 dispositions).

### Q2 Status Quo

No disposition ledger exists. Candidates are discussed ad hoc across child
issues (#5394, #5395, #5396, #5420, #5421, #5241) with no single place
recording class, owner, consumers, evidence, or KEEP justification. This
cohort's own research surfaced the risk directly: the original seed plan
proposed a fourth PR to delete a "duplicate" pre-push gate execution, based
on a Serena memory that a later commit (`becde1660`, PR #5418) had already
invalidated. Without a ledger, that stale claim would have driven a real PR;
with a ledger, it becomes one row: KEEP, with the fix's own commit and test
as evidence.

### Q3 Desperate Specificity

The epic's Release gates checklist item "Every retained candidate has a
recorded KEEP justification" and its Disposition contract's KEEP
requirements (five named fields) are unsatisfiable today because no ledger
exists to satisfy them into.

### Q4 Narrowest Wedge

Approximately 2-3 hours: one committed markdown ledger
(`.agents/metrics/control-plane-dispositions-v0.7.0.md`) with one row per
named candidate (the eight the epic lists) plus every redundancy REQ-021's
baseline surfaces, classified using REQ-021's already-computed numbers. No
new script; this REQ is a writing and classification task over existing
data, not new measurement.

### Q5 Observation

The same commit `cd0f9561d` and live-number evidence cited in REQ-021 Q5
apply here too. This cohort also made a directly observed finding, in
ancestry back to PR #5418 (`4e33c4baa`): the `FAST_STAGE_RAN_ENV` skip
mechanism. `scripts/validation/pre_pr_sequence.py:543` reads
`fast_stage_ran = os.environ.get(FAST_STAGE_RAN_ENV) == "1"`.
`lefthook.yml:590` sets `AI_AGENTS_PRE_PR_FAST_STAGE_RAN: "1"`.
`tests/validation/test_pre_pr_sequence_registry.py:133-146` defines
`FAST_STAGE_DUPLICATES`, five gate names. This is a first-hand production
signal, not a cited claim: this cohort read the code and confirmed it.

### Q6 Future-fit

Yes. An append-only, git-tracked ledger scales the same way any other
markdown record in this repository scales (history handles growth); at 10x
the candidate count, the alternative (no ledger, ad hoc discussion per
issue) becomes proportionally worse, because the stale-memory failure mode
this cohort found gets easier to hit, not harder, as more candidates
accumulate without one place recording what was already checked.

## Prior Art / Constraints

### Direct prior art from memory

- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`: see
  REQ-021's Prior Art block. Decision: propose-amend, consumed directly as
  this REQ's first ledger row (below). This is the clearest illustration in
  this cohort of why REQ-022 exists: a disposition ledger turns a stale
  claim into a recorded, evidenced KEEP instead of a re-proposed fix.
- `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`:
  same relevance as REQ-021; also directly on point for this REQ's own
  purpose (checking whether a gap is already closed before building
  something for it): the disposition ledger generalizes exactly this
  check across every named candidate rather than leaving it to be
  rediscovered per candidate.
- ADR-100 (`.agents/architecture/ADR-100-retire-pr-size-ceilings.md`):
  chestertons-fence-style verdict for the PR-size-ceiling mechanisms: item 1
  (commit-ceiling enforcement) is MODIFY-already-done ("DELIVERED, by
  ADR-099"); items 2-4 are MODIFY-pending (this cohort's REQ-023); item 5
  (`post_qa_code_changes` rebind churn) is PRESERVE-for-now, explicitly out
  of scope for this cohort (REQ-023's Out of Scope).

### Connected context from prior-art search

- Connected entity: `scripts/validation/pre_pr_sequence.py`'s
  `already_run_by` mechanism (`FAST_STAGE_DUPLICATES`: Count Ratchets,
  Unreachable Code Detection, Path Normalization, Planning Artifacts,
  Em/en-dash Prohibition). Adjudication: in-scope. This is the ledger's
  first concrete KEEP row (Acceptance Criteria below).
- Connected entity: `.agents/architecture/ADR-100-retire-pr-size-ceilings.md`
  item 5 (`post_qa_code_changes` rebind churn). Adjudication: in-scope,
  reclassified after this cohort read `qa_report.py` directly; recorded
  in the ledger as a named candidate with disposition `DELETE`, since the
  construct item 5 describes is absent from the file, not silently
  dropped.
- (Search depth: same medium/degraded search as REQ-021; see its Coverage
  notes for the method.)

### Coverage notes

- Same four grep variants as REQ-021's `control-plane-baseline` topic,
  reused here since the two REQs share a search space (one `/spec`
  invocation, one cohort). No additional topic-specific search was run for
  "disposition ledger" as a term because it names no prior system this
  cohort could search for (it does not exist yet); this is expected and not
  a degraded-search flag.

## Requirement Statement

WHEN the control-plane baseline (REQ-021) is committed,
THE SYSTEM SHALL classify every epic-named candidate mechanism plus every
redundancy the baseline surfaces as KEEP, MERGE, DELETE, or EXPERIMENT in a
committed markdown ledger, with each KEEP row carrying all five epic-required
fields,
SO THAT the epic's Release gates checklist item "Every retained candidate
has a recorded KEEP justification" is satisfiable and no candidate is
silently dropped or re-litigated from scratch by a later contributor.

## Context

Engineering tier: 3, same rationale as REQ-021 (shared cohort tier; see
REQ-021 Complexity classification). Problem domain: Complicated (classifying
a known, enumerable list of candidates against a defined rubric is expert
analysis, not experimentation). Methodology: sense-analyze-respond.

This REQ depends on REQ-021 (the ledger classifies using the baseline's
numbers) and is independent of REQ-023.

## Ontology

See `.agents/specs/ontology/control-plane-subtraction-cohort-1.md`. This
requirement's data model is the `Disposition` aggregate root (O4): one row
per `CandidateMechanism`, each carrying class, owner, consumers, evidence,
and (for KEEP) the five DR2-required fields. DR3 (already-fixed is KEEP, not
DELETE) is this requirement's central decision rule; DR2 (KEEP completeness)
gates every row's validity.

## Data model

- `DispositionRow`: `candidate` (name/path), `class` (`KEEP | MERGE |
  DELETE | EXPERIMENT`), `owner`, `consumers` (list), `evidence` (list of
  citations: commit SHA, test path, ADR id, or memory path), and for
  `KEEP` rows the five fields: `current_outcome_protected`,
  `evidence_failure_occurs`, `why_simpler_insufficient`,
  `owner_and_consumers` (may duplicate `owner`/`consumers` above for
  clarity), `cost_where_measurable`.
- `Ledger`: an ordered list of `DispositionRow`, one markdown document,
  git-tracked (append-only in spirit; a later cohort may amend a row with a
  dated addendum rather than silently rewriting history).

## Integrations

- Reads REQ-021's committed baseline JSON for `evidence` figures where a
  row's justification is numeric (for example a KEEP row citing
  `always_loaded` headroom).
- No new script; this is a hand-authored (or lightly templated) markdown
  document, not a generated artifact, because the classification judgment
  itself (KEEP vs. DELETE vs. EXPERIMENT) is not mechanically derivable from
  the baseline numbers alone: it requires the same kind of code-reading
  this cohort did for the duplicate-gate finding.
- Failure modes: a row citing evidence that later turns out wrong (as the
  original stale-memory claim would have) is corrected via a dated
  addendum in a later PR, not a silent edit, so the ledger's own history
  stays honest about what was believed when.

## Failure modes

- **Scenario**: a KEEP row is recorded without all five required fields,
  silently weakening the epic's Disposition contract. **Category**: process.
  **Early warning**: a reviewer spot-checks one row and finds a missing
  field. **Prevention**: AC-02 below requires a mechanical check (every KEEP
  row's five fields non-empty) before this REQ is marked done. **Detection**:
  the mechanical check. **Response**: fill the missing field or downgrade
  the row to EXPERIMENT pending more evidence.
- **Scenario**: a candidate is re-litigated in a future PR because the
  ledger's evidence citation was too vague to verify quickly. **Category**:
  technical/process. **Early warning**: none automatic; this is a quality
  risk, not a testable one. **Prevention**: AC-04 requires every evidence
  citation to be a concrete artifact (commit SHA, file path with line
  numbers, or test name), never a paraphrase. **Detection**: reviewer
  judgment at PR time. **Response**: request the concrete citation before
  merge.
- **Scenario**: the ledger and REQ-021's baseline diverge later (baseline
  re-run, numbers change) and nobody notices the ledger is stale.
  **Category**: process. **Prevention**: out of scope for this cohort (no
  automated staleness check is proposed, per the epic's Abort-if clause 3
  forbidding a new governance layer); recorded as Deferred below.

## Security

No new attack surface: a markdown document with no executable content, no
new write path beyond a normal PR, no new authentication or authorization
boundary. One consideration: evidence citations that quote a memory or a PR
description must not reproduce a secret if the cited source ever contained
one (none of the citations gathered for this cohort do); no redaction
script is needed because this REQ produces hand-authored prose, not a tool
that ingests untrusted external input.

## Observability

Lightweight: "what proves this works" is that every epic-named candidate (8)
plus every baseline-surfaced redundancy appears as exactly one row, and
every KEEP row's five fields are non-empty. No numeric SLO; this is a
one-time authored document, re-verified by the mechanical check in AC-02,
not a running system.

## Acceptance Criteria

- [ ] REQ-022-AC1: WHEN the ledger is committed, THE SYSTEM SHALL contain
      exactly one row for each of the eight epic-named candidates (#5394,
      #5395, #5396, #5404, #5420/#5421, #5436, #5241, redundant
      hooks/review-axes/validators/workflows/mirrors found by the
      baseline) SO THAT no named candidate is silently dropped.
- [ ] REQ-022-AC2: WHEN a row's class is `KEEP`, THE SYSTEM SHALL record all
      five epic-required fields non-empty SO THAT the epic's Disposition
      contract is satisfied for every retained candidate (DR2, mechanically
      checkable).
- [ ] REQ-022-AC3: WHEN the row for the pre-push duplicate-gate finding is
      recorded, THE SYSTEM SHALL classify it `KEEP`.
      Evidence citations: `scripts/validation/pre_pr_sequence.py:543-556`,
      `lefthook.yml:590`, and
      `tests/validation/test_pre_pr_sequence_registry.py:133-266`.
      THE SYSTEM SHALL NOT propose a deletion PR for this mechanism SO
      THAT the already-fixed finding is recorded rather than re-solved
      (DR3, this REQ's motivating example).
- [ ] REQ-022-AC4: WHEN any row's `evidence` field is populated, THE SYSTEM
      SHALL cite a concrete artifact (commit SHA, file path with line
      numbers, test name, ADR id, or memory path), never an unsourced
      paraphrase, SO THAT a future reader can verify the row without
      re-deriving it from scratch.
- [ ] REQ-022-AC5: WHEN a candidate's disposition is `DELETE` or `MERGE`,
      THE SYSTEM SHALL NOT itself perform the deletion or merge in this
      PR SO THAT REQ-022 stays within the O6 bounded-context boundary
      (classification, not mechanism implementation) and does not expand
      into a fourth deliverable this cohort did not scope.
- [ ] REQ-022-AC6: WHEN a candidate's resolution mechanism is owned by
      another issue or a time-gated measurement outside this cohort (for
      example ADR-100 item 6, owned by #5238/#5239), THE SYSTEM SHALL
      still classify it as one of the epic's four dispositions (`KEEP`,
      `MERGE`, `DELETE`, `EXPERIMENT`) with a one-line reason naming the
      owning mechanism, not invent a fifth class and not omit the row SO
      THAT the ledger distinguishes "considered, resolution owned
      elsewhere" from "not considered", without expanding the epic's
      Disposition contract.
- [ ] REQ-022-AC7: WHEN the ledger is reviewed, THE SYSTEM SHALL create no
      new child GitHub issue per finding, per the epic's "Do not create one
      child issue per finding" instruction SO THAT the ledger amends
      existing owners rather than fragmenting further.

## Out of Scope

- Performing any DELETE or MERGE disposition's actual mechanism work
  (AC-05). Owned by the respective child issue.
- An automated staleness check keeping the ledger in sync with future
  baseline re-runs (Failure modes, third scenario). Would itself be a new
  governance layer, forbidden by the epic's Abort-if clause 3.
- ADR-100 item 6 (push-ceiling telemetry re-measure): recorded as
  `EXPERIMENT` owned by #5238/#5239; the measurement itself is not run
  here.
- The reduced-configuration comparison and final release report (same
  exclusion as REQ-021).

## Deferred

- The correction to
  `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md` (its
  "same work runs twice" section predates PR #5418) is done in this PR as
  a tracked file edit, not an MCP memory write, so nothing remains for a
  main-checkout session.
- ADR-100 item 6, as noted above (owned by #5238/#5239, not run here).
- A mechanized version of this ledger (structured YAML/JSON instead of
  markdown prose) if a future cohort needs to query dispositions
  programmatically; no such consumer exists yet (YAGNI).

## Open Questions

- **OQ1**: Should the ledger's row order follow the epic's own candidate
  list order, or group by disposition class? Owner: implementer at TASK-025
  time. Assumption made here: epic's listed order, because that makes the
  ledger easiest to cross-check against the epic body directly, and a
  reader wanting a by-class view can `grep` the `class` column.
- **OQ2**: Does "every redundancy PR1 surfaces" (from the original seed
  plan) mean every dimension where the baseline's count exceeds some
  implicit threshold, or literally every item the baseline enumerates?
  Assumption: the former, narrowed to redundancies actually found during
  this cohort's own research (the pre-push duplicate-gate finding is the
  only one confirmed at spec time); TASK-025 re-reads REQ-021's committed
  baseline once it lands and adds any additional redundancy it surfaces,
  rather than speculatively listing candidates this spec has not verified.

## CVA summary

**Commonalities**: every row shares the same five-column shape (candidate,
class, owner, consumers, evidence) regardless of disposition class.
**Variabilities**: only `KEEP` rows carry the additional five-field
justification block; `DELETE`/`MERGE`/`EXPERIMENT` rows carry a shorter
rationale instead. **Relationships**: every row's `evidence` field, where
numeric, traces back to REQ-021's `Baseline` aggregate (O3 relationship
`ReleaseTarget bounds-one Baseline metric`, applied here as `Disposition
cites Baseline`).

## Buy-vs-build decision

N/A (bug fix / doc / refactor). This REQ produces a hand-authored markdown
document classifying existing candidates using existing data; it introduces
no new tool, script, scanner, or validator, so the Step 4a buy-vs-build gate
does not apply (spec-generator SKILL.md Step 4a: "pure bug fixes, doc-only
changes... skip this step").

## Complexity classification

Engineering tier: 3, same as REQ-021 (shared cohort). Problem domain:
Complicated. Methodology: sense-analyze-respond.

## Rationale

The epic's Release gates checklist cannot pass without a recorded KEEP
justification for every retained candidate, and this cohort's own research
demonstrated concretely why a ledger matters: without one, a stale claim
(the duplicate pre-push gate) would have produced a redundant fix PR for a
problem already solved. Writing the ledger from REQ-021's baseline, rather
than before it, keeps every numeric claim traceable to one committed source.

## Dependencies

- REQ-021 (baseline numbers this ledger cites)
- `.agents/architecture/ADR-100-retire-pr-size-ceilings.md`
- `scripts/validation/pre_pr_sequence.py`, `lefthook.yml`,
  `tests/validation/test_pre_pr_sequence_registry.py` (the duplicate-gate
  KEEP row's evidence)
- Epic #5456's Execution section (candidate list)
