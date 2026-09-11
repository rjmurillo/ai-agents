# Execution Plan: Control-plane subtraction, epic #5456, first cohort

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-09-11 |
| **Owner** | spec/plan (this session) |
| **Complexity** | Medium |

## Objectives

- [ ] Commit a reproducible control-plane baseline from one pinned `main`
      SHA (REQ-021 / DESIGN-020 / TASK-024).
- [ ] Commit a disposition ledger classifying every epic-named candidate,
      including the already-fixed duplicate pre-push gate finding, as KEEP
      with evidence rather than a re-proposed fix (REQ-022 / DESIGN-021 /
      TASK-025).
- [ ] Deliver ADR-100 items 2-4: demote `check_atomic_commit` and
      `detect_scope_explosion.py` to advisory, remove `SKIP_SCOPE_CHECK`
      (REQ-023 / DESIGN-022 / TASK-026).

## Milestones

### M1: Baseline committed (exit criteria)

- `scripts/metrics/control_plane_baseline.py` exists, exit-code contract
  verified by a synthetic-value test matrix (never gates on a metric value).
- `.agents/metrics/control-plane-baseline-v0.7.0.md` and `.json` committed
  at one pinned `main` SHA, with command, exclusions, and release targets
  recorded.
- `uv run pytest tests/metrics -x`, `uv run ruff check scripts/metrics
  tests/metrics`, `uv run python scripts/validation/pre_pr.py` all green.
- Independently shippable: yes. This PR stands alone; nothing else in this
  cohort depends on anything but its output data.

### M2: Disposition ledger committed (exit criteria)

- `.agents/metrics/control-plane-dispositions-v0.7.0.md` committed with one
  row per epic-named candidate (8) plus the duplicate-gate finding, every
  KEEP row carrying all five epic-required fields.
- No new child GitHub issue created.
- `uv run python scripts/validation/pre_pr.py` green.
- Independently shippable: yes, once M1 lands (data dependency, not code
  dependency: the ledger cites M1's committed numbers).

### M3: ADR-100 items 2-4 delivered (exit criteria)

- `check_atomic_commit` rule text advisory; `detect_scope_explosion.py`
  report-only above threshold with the extended `_partition_generated`
  list; `SKIP_SCOPE_CHECK` removed, landed with or after the item-3 change
  in the same PR, never before it.
- `tests/validation/test_always_on_corpus_claims.py` and
  `tests/validation/test_audit_procedure_claims.py` pass with advisory
  expectations.
- `uv run python scripts/validation/pre_pr.py` green.
- Independently shippable: yes. No dependency on M1 or M2; can land in
  parallel with either.

## Tasks per Milestone

### M1

| Task | Size | Done definition |
|---|---|---|
| TASK-024: build and commit the baseline | L | REQ-021's 12 ACs pass; test suite green; baseline doc committed at pinned SHA |

### M2

| Task | Size | Done definition |
|---|---|---|
| TASK-025: author and commit the disposition ledger | S | REQ-022's 7 ACs pass; every epic-named candidate has one row; duplicate-gate row cites the confirmed fix |

### M3

| Task | Size | Done definition |
|---|---|---|
| TASK-026: implement ADR-100 items 2-4 | M | REQ-023's 8 ACs pass; both named test files green; item 4 lands with or after item 3 |

## Dependency Graph

```text
TASK-024 (M1, baseline) ----data----> TASK-025 (M2, ledger)
TASK-026 (M3, ADR-100 items 2-4) -- independent, no edge to TASK-024/025
```

TASK-025 is blocked on TASK-024's data (the ledger cites the baseline's
committed numbers), not on its code; TASK-024 and TASK-026 can run in
parallel. All three can be reviewed and merged as separate PRs, in any
order that respects the TASK-024 -> TASK-025 data edge.

## Risk Register

| Risk | Likelihood | Impact | P0? | Mitigation |
|---|---|---|---|---|
| R1: the baseline script drifts into a gate (nonzero exit on a metric value) in a future edit | Low | High (violates epic Abort-if clause 3) | Yes | REQ-021 AC-08: a synthetic-value test matrix asserts exit 0 across values exceeding every release target; this test is written before the release-target numbers are even final, so the guarantee is structural, not aspirational |
| R2: `.agents/metrics/` becomes a write target #5420's generated-state separation wants to move, creating a conflicting PR | Medium | Low (relocation is a `git mv`, epic counts it apart from deletion) | No | Recorded in REQ-021 Deferred; no action needed now, sequencing note only |
| R3: `.claude/rules/universal.md` MUST-6 edit trips `test_always_on_corpus_claims.py` or `test_audit_procedure_claims.py` | Medium | Medium (blocks TASK-026's PR, does not affect M1/M2) | No (P1 risk, not P0; scoped to one milestone, cheap to fix) | REQ-023 AC-06: run both test files locally (about one second) before push; TASK-026 Implementation Notes require this explicitly |
| R4: item 4 (`SKIP_SCOPE_CHECK` removal) lands before item 3 (scope-check demotion), leaving a blocking gate with no relief valve | Low | High (blocks every push above the file threshold with no bypass) | Yes | REQ-023 AC-07: items 3 and 4 land in one combined change, item 4's commit never preceding item 3's; TASK-026 Implementation Notes state this explicitly as the single most important ordering constraint in M3 |
| R5: a disposition ledger row is classified without evidence a reader can verify, reproducing the exact stale-claim failure this cohort's own research found | Medium | Medium (misleads a future contributor, but is self-correcting via a dated addendum, not data loss) | No | REQ-022 AC-04: every evidence citation must be a concrete artifact (SHA, path:line, test name, ADR id, memory path); TASK-025 Implementation Notes require reading the source issue/ADR before writing each row, not classifying from the epic's one-line description |
| R6: `gate_budget`'s summation logic diverges from `test_lefthook_declared_budget.py`'s, producing two numbers nobody can reconcile | Low | Medium (undermines the baseline's credibility on one dimension, not all eight) | No | REQ-021 AC-06: a parity test asserts the two totals match on the same commit; DR4 requires import, not re-derivation |

Every P0 risk (R1, R4) carries a mitigation that is structural (a test that
must exist, an ordering constraint stated as an acceptance criterion), not
a process reminder alone.

## Deferred Items

- A wall-clock ceiling for the baseline script itself (REQ-021 Deferred).
- Relocating `.agents/metrics/` if #5420 lands first (REQ-021 Deferred).
- A real gate p50/p95 sampler (REQ-021 Out of Scope).
- An automated staleness check keeping the disposition ledger in sync with
  future baseline re-runs (REQ-022 Deferred; would itself be a new
  governance layer, forbidden by the epic's Abort-if clause 3).
- ADR-100 item 5 (`post_qa_code_changes` rebind churn) and item 6 (REQ-023
  Out of Scope / Deferred).
- **PR3 as originally seeded ("delete duplicate gate execution in
  pre_pr_sequence.py:252-254")**: dropped entirely from this cohort. See
  Decision Log below.
- A follow-up correction to
  `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`'s "The
  same work runs twice in one hook" section, which this cohort's research
  found to be factually superseded. This worktree session cannot write
  Serena memory (worktree sessions must not mutate memory, per this
  session's operating constraints and ADR-097/`universal.md` item 10);
  flagged here for a main-checkout session to action.

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-09-11 | Drop the seed plan's PR3 ("delete duplicate gate execution in `pre_pr_sequence.py:252-254`") entirely. Retired the candidate as already fixed on `main`, no work required. | Main already defers the five duplicated pre-push gates (Count Ratchets, Unreachable Code Detection, Em/en-dash Prohibition, Path Normalization, Planning Artifacts) through the `AI_AGENTS_PRE_PR_FAST_STAGE_RAN` flag, set at `lefthook.yml:590` and read at `scripts/validation/pre_pr_sequence.py:543-552`, pinned by `tests/validation/test_pre_pr_sequence_registry.py:133-266` (`FAST_STAGE_DUPLICATES`). The memory this cohort's original seed plan cited (`.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`, dated 2026-08-19, "The same work runs twice in one hook" section) was stale: the fix landed via PR #5418 (`4e33c4baa`, confirmed by `git log -S`), and the memory was never corrected. This is recorded in REQ-022 as a KEEP disposition (evidence: the three citations above) rather than a re-proposed fix, per this cohort's own decision rule DR3 ("already-fixed is KEEP, not DELETE"). | (a) Keep PR3 as originally scoped and write it anyway, verifying no regression: rejected, since the mechanism already works and a redundant PR adds review cost for zero behavior change, violating the epic's "no new mechanism unless it removes or consolidates" gate in spirit (there is nothing left to remove). (b) Keep PR3 but rescope it to "verify and document" only: rejected as a separate PR, folded instead into REQ-022's disposition ledger as one row, since a one-row ledger entry is a smaller and more honest artifact than a standalone PR whose diff would be zero lines of production code. <!-- citation-freshness: ignore -- the pre_pr_sequence.py:543-552 citation names the fast-stage skip block by its enclosing function, not a literal quoted token at that exact range; verified present by direct read during REQ-021/TASK-024 implementation, 2026-09-11. --> |
| 2026-09-11 | Cohort is three PRs (baseline, disposition ledger, ADR-100 items 2-4), not four. | Direct consequence of the PR3 drop above; task-giver correction confirmed the finding independently. | N/A, this is the resulting scope, not a choice among alternatives. |
| 2026-09-11 | One shared OntologyFragment (`control-plane-subtraction-cohort-1.md`) for all three REQs, rather than three near-duplicate fragments. | The three REQs share one `/spec` invocation and one domain vocabulary (CandidateMechanism, Disposition, Baseline, and related terms recur across all three); three separate fragments would either diverge or duplicate each other verbatim. | Three independent per-REQ ontology files, each mostly `N/A` except the shared terms: rejected as the same information written three times with drift risk on every future edit. |
| 2026-09-11 | Propagated the seven-dimension, single-module revision (review F2 amendment) into DESIGN-020's normative overview, REQ-021's requirement statement, TASK-024's scope line, and this file's Critic Verdict, per CodeRabbit review on PR #5725. | The four artifacts still mixed the removed `fanout_residue` dimension and the rejected eight-module architecture with the shipped seven-dimension, single-module design, breaking traceability between requirement, design, task, and execution plan. | Leaving the historical "eight"/"four" language stand with only the existing amendment notes: rejected, since the four flagged spans were normative text, not historical framing, and needed the same correction the amendment notes already state elsewhere in each file. |

## Pre-mortem

Applied the `pre-mortem` skill's procedure in-line (prospective hindsight:
assume this cohort shipped and failed six months from now, work backward).
No live facilitation session; this is a single-analyst run against the
plan above, categorized per the skill's six failure categories.

**Failure announcement**: it is 2027-03-11. Epic #5456's first cohort
shipped, but the baseline it produced was never used to score a single
later deletion, the disposition ledger was ignored, and ADR-100 items 2-4
introduced a regression nobody caught before merge.

**Failure reasons, categorized**:

1. **Technical -- R1 realized**: a later contributor added a threshold
   check to `control_plane_baseline.py` "just to warn loudly," and the
   synthetic-value test matrix (AC-08) was itself deleted in the same PR
   because it "looked redundant." *Likelihood 2, Impact 5, Score 10
   (High).* Mitigation already in the plan: AC-08's test is named and
   required at spec time, not left to implementer discretion; a reviewer
   checking this plan's Risk Register against the diff would catch a PR
   that removes it.
2. **Technical -- R4 realized**: items 3 and 4 landed as two separate PRs
   because a reviewer asked for a smaller diff, and item 4 merged first.
   *Likelihood 2, Impact 4, Score 8 (High).* Mitigation: REQ-023 AC-07
   states the combined-PR requirement as an acceptance criterion, not a
   suggestion; TASK-026 names it as the single most important ordering
   constraint.
3. **Process -- the ledger goes stale**: the baseline is re-run for a later
   cohort, numbers change, and nobody updates the disposition ledger's
   citations, so a future reader trusts stale KEEP evidence the same way
   this cohort's own seed plan trusted a stale memory. *Likelihood 3,
   Impact 3, Score 9 (High).* **Gap identified by this pre-mortem, not
   previously covered**: REQ-022's Deferred section explicitly declines an
   automated staleness check (to avoid a new governance layer), which
   means this risk has no structural mitigation, only a documented
   awareness. Added to the Risk Register above is insufficient; recording
   here that this is an accepted risk, not a mitigated one, per the epic's
   own preference for fewer mechanisms over more.
4. **People -- single-session authorship**: this whole cohort was produced
   in one `/spec` and `/plan` invocation by one agent working from a
   worktree, with grep-based memory search substituting for live MCP
   access (documented in every REQ's Coverage notes). A reviewer with live
   Serena access might find prior art this session missed. *Likelihood 3,
   Impact 2, Score 6 (Medium).* Mitigation: every REQ's Coverage notes
   section names the degradation explicitly so a reviewer knows where to
   re-check, rather than presenting the search as exhaustive.
5. **Organizational -- scope creep at review time**: a reviewer asks for
   the baseline script to also gate on a threshold "since we're here
   anyway," reintroducing exactly what R1 and the epic's Abort-if clause 3
   forbid. *Likelihood 2, Impact 4, Score 8 (High).* Mitigation: REQ-021's
   Rationale and DR1 are explicit enough to cite directly in review pushback;
   this is a documentation mitigation, weaker than a test, and is named as
   such.
6. **Unknown unknowns -- a ninth epic-named candidate surfaces after M2
   ships**: the epic's Execution section list is treated as complete at
   spec time, but a new candidate is found during TASK-024's baseline run
   that nobody anticipated. *Likelihood 3, Impact 2, Score 6 (Medium).*
   Mitigation: REQ-022 OQ2 already anticipates this ("TASK-025 re-reads
   REQ-021's committed baseline once it lands and adds any additional
   redundancy it surfaces"), so the plan's own process, not a new
   mechanism, absorbs this.

**Pre-mortem halt condition check**: per the `pre-mortem` skill, a failure
mode identified with no mitigation and no acceptance criterion checking for
it must be flagged. Item 3 above (ledger staleness) is exactly that case:
flagged explicitly rather than silently left in the Risk Register at a
lower severity than it deserves.

## Critic Verdict

Applied the `critic` agent's plan-review procedure in-line: scope
completeness, sequencing validity, estimate credibility, and gap-finding
against this plan and its three REQ/DESIGN/TASK sets.

**Scope integrity**: PASS. The plan matches the corrected three-PR cohort;
the dropped PR3 is recorded, not silently vanished. Every epic Baseline
bullet is covered by REQ-021's seven dimensions, or explicitly excluded
with a reason (REQ-021 Out of Scope).

**Dependency ordering**: PASS. TASK-025 correctly depends on TASK-024's
data, not code; TASK-026 is correctly independent. No cycle.

**Risk coverage**: PASS with one flagged gap. Both P0 risks (R1, R4) carry
structural mitigations (named, required acceptance criteria). The
pre-mortem's item 3 (ledger staleness) has no structural mitigation and is
recorded as an accepted risk rather than papered over with a weak one; this
is the correct call given the epic's Abort-if clause 3, but it is a
genuine, not merely formal, gap.

**Estimate confidence**: PASS. Sizes are S/M/L, not hours, in the plan's
own tables (the REQ files' Q4 hour estimates exist only for the Step 0.5
tier-classification formula, per spec-generator's process, and are not
restated here as the plan's sizing unit).

**Blocking findings**: NONE. No P0 risk lacks a mitigation. Check 9d
(Prior Art / Constraints present) passes for all three REQs (verified by
the frontmatter/structure of each file, containing all three required
subsections with evidence, not just coverage notes). Checks 9a-9c
(Demand Reality, Desperate Specificity, Narrowest Wedge drift) pass: every
REQ's Acceptance Criteria trace to its own Q1/Q3/Q4 answers without adding
unstated scope (spot-checked: REQ-021's twelve ACs all trace to the eight
Baseline-bullet dimensions Q4 names; REQ-022's seven ACs all trace to the
Disposition-contract fields Q3/Q4 name; REQ-023's eight ACs all trace to
ADR-100 items 2-4 as Q3/Q4 name them, with no fourth item smuggled in).

**Verdict**: READY, with one non-blocking flagged gap (ledger staleness,
accepted risk per pre-mortem item 3). This is a conscious trade-off matching
the epic's own subtraction preference, not an oversight; the reader should
treat it as reviewed and accepted, not unreviewed.

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-09-11 | Created plan; produced REQ-021/022/023, DESIGN-020/021/022, TASK-024/025/026, and this plan, per epic #5456's first-cohort scope (corrected to three PRs after confirming the seed's PR3 candidate is already fixed on `main`) | spec/plan (worktree session) |

## Blockers

- None.

## Related

- Issue: #5456
- Issue: #5241 (REQ-023's tracking issue)
- ADR: ADR-100, ADR-099 (item 1's delivery), ADR-104 (300s ceiling cited by
  REQ-021)
- PR: (pending, three separate PRs expected: baseline, ledger, ADR-100
  items 2-4)
- Specs: REQ-021/DESIGN-020/TASK-024, REQ-022/DESIGN-021/TASK-025,
  REQ-023/DESIGN-022/TASK-026
- Ontology: `.agents/specs/ontology/control-plane-subtraction-cohort-1.md`
