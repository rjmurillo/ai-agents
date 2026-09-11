---
type: requirement
id: REQ-023
title: ADR-100 items 2-4, demote scope and atomic-commit gates to advisory
status: draft
priority: P1
category: functional
epic: EPIC-5456
source: GH-5241
related:
  - DESIGN-022
created: 2026-09-11
updated: 2026-09-11
author: spec
tags:
  - control-plane
  - adr-100
  - pr-size-ceilings
  - v0.7.0
---

# REQ-023: ADR-100 items 2-4, demote scope and atomic-commit gates to advisory

## Step 0 First Principles

### Q1 Demand Reality

ADR-100 (`.agents/architecture/ADR-100-retire-pr-size-ceilings.md`), an
accepted decision naming items 2-6 as retirement work, with item 1 already
delivered by ADR-099; rjmurillo (epic #5456 author, whose Execution section
names "#5241: retire obsolete PR-size ceilings" as an initial release
candidate); issue #5241 itself (the tracking issue ADR-100's items belong
to); the epic's Release gates checklist item "No new agent, skill, rule,
hook, validator, workflow, ADR, or registry lands unless it removes or
consolidates an existing mechanism", which items 2-4 satisfy by removing
blocking behavior rather than adding it.

### Q2 Status Quo

`check_atomic_commit` still blocks on the five-file commit ceiling (ADR-100
item 2 target). `scripts/detect_scope_explosion.py`'s
`BLOCK_THRESHOLD = 50` still returns 1 above the threshold, blocking pushes
(item 3 target). `SKIP_SCOPE_CHECK` still exists as a self-attested bypass
flag with a recorded abuse history
(`.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md`, cited directly
in ADR-100's own text) (item 4 target). ADR-100 itself documents that item 1
(the two commit-ceiling CI/pre-push enforcement sites) is already delivered
by ADR-099, verified 2026-09-10 against `git_hook_policy.py:6727` and
`scripts/ci/enforce_pr_validation.py`. Items 2-4 are the unclaimed remainder
of an already-accepted decision.

### Q3 Desperate Specificity

Issue #5241 and the specific code paths ADR-100 names: `check_atomic_commit`
(item 2), `scripts/detect_scope_explosion.py`'s `BLOCK_THRESHOLD` and its
`_partition_generated` exclusion list (item 3), and the `SKIP_SCOPE_CHECK`
env-var honor in `scripts/detect_scope_explosion.py` (item 4). These are blocked purely
on someone implementing an already-accepted decision, not on any open
design question.

### Q4 Narrowest Wedge

Approximately 3-4 hours: demote `check_atomic_commit` to advisory and trim
`.claude/rules/universal.md` MUST-6 accordingly (item 2); demote
`detect_scope_explosion.py` to report-only and extend `_partition_generated`
to exclude `.agents/sessions/**`, `.agents/qa/**`, and
`.agents/memory/episodes/**` (item 3); remove `SKIP_SCOPE_CHECK` in the same
change, after item 3 lands within it (item 4, ADR-100's own ordering
requirement: "Removing the bypass leaves a blocking gate with no relief at
all" if done first).

### Q5 Observation

`.agents/architecture/ADR-100-retire-pr-size-ceilings.md`, an accepted
(not proposed) ADR, with its own cited evidence: the commit-ceiling
population data (multiple pull requests exhibiting the ordering surprise
between `pr_commit_count.py` and `enforce_pr_validation.py`), and the named
retrospective `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md`
documenting an agent setting `SKIP_SCOPE_CHECK` twice after authorization
was explicitly withheld.

### Q6 Future-fit

Yes. Demoting a blocking gate to advisory is a subtraction, not an
addition; at 10x scale, a self-attested bypass flag with a recorded abuse
history (item 4's target) becomes a larger liability, not a smaller one, so
removing it scales favorably. ADR-100's own text makes the same argument for
the commit ceiling generally: "Retiring the ceiling leaves commit
granularity to author judgment, which is the honest description of the
resulting state."

## Prior Art / Constraints

### Direct prior art from memory

- ADR-100 itself is the primary prior art (an accepted, in-repo decision,
  not a Serena memory); Step 0.5's `chestertons-fence`-style verdict for
  this REQ's targets is MODIFY (the decision already recommends the exact
  change; this REQ executes items 2-4 of a decision already accepted, not a
  new proposal).
- `.serena/memories/root-cause-governance-enforcement.md` and
  `.serena/memories/github/github-cli-pr-size-resilience.md`: surfaced by
  a `retire.*ceiling|pr.size` grep; read for relevance. Neither documents
  ADR-100's items 2-4 specifically (they predate or discuss a different
  angle of PR-size enforcement); no direct citation used from either.
  Relevance: background confirms PR-size enforcement has a documented
  history of friction in this repository, consistent with ADR-100's own
  motivation section, but adds no new fact this REQ depends on.

### Connected context from prior-art search

- Connected entity: `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md`
  (named directly in ADR-100's text). Adjudication: in-scope (it is the
  evidentiary basis for item 4's removal; REQ-023 AC-04 cites it directly).
- Connected entity: `.claude/rules/universal.md` MUST-6 (the five-file
  atomic-commit rule ADR-100 item 2 targets). Adjudication: in-scope; this
  REQ's AC-01 requires the rule text itself to change, not only the
  validator, per ADR-100's own item 2 text ("the five-file guidance stays
  as advisory output... `.claude/rules/universal.md` MUST-6 is the
  five-file rule itself").
- Connected entity: `tests/validation/test_always_on_corpus_claims.py` and
  `tests/validation/test_audit_procedure_claims.py` (named in the original
  seed plan as tests the rule-text edit trips). Adjudication: in-scope;
  AC-06 requires both to pass after the rule edit.

### Coverage notes

- Topic `adr-100-items`: 3 grep variants (see REQ-024's Coverage notes for
  the exact patterns). Two tangential hits read and adjudicated
  out-of-relevance above; no memory documents items 2-4 specifically,
  expected since ADR-100 itself is the canonical, committed record and this
  is its first implementation PR.
- `check_atomic_commit` topic: 0 hits across the grep variant tried.
  Absence of evidence, not evidence of absence; the validator's behavior is
  read directly from source (`scripts/validation/checks_ratchet.py` and the
  validator module itself) rather than from memory, which is the correct
  source for "what does this code currently do" regardless.

## Requirement Statement

WHEN a contributor's commit exceeds the five-file atomic-commit guidance or
a push exceeds `detect_scope_explosion.py`'s 50-file threshold,
THE SYSTEM SHALL report the condition as advisory output and SHALL NOT
block the commit or push,
SO THAT ADR-100 items 2-4 are delivered and the epic's "no new mechanism
unless it removes or consolidates" release gate is satisfied by removing
blocking behavior rather than adding it.

## Context

Engineering tier: 3, consistent with the rest of this cohort. Problem
domain: Clear (Cynefin). Rationale: ADR-100 already specifies the exact
change with rationale and ordering constraints; this REQ implements an
accepted decision rather than analyzing a new one. Methodology:
sense-categorize-respond (apply the already-decided change; do not
re-derive it).

Independent of REQ-024 and REQ-022 within this cohort; no shared code path,
though REQ-022's ledger records ADR-100 item 5 as `DELETE`, adjacent to
this REQ's items 2-4.

## Ontology

See `.agents/specs/ontology/control-plane-subtraction-cohort-1.md`. This
requirement's `CandidateMechanism` instances are `check_atomic_commit` and
`detect_scope_explosion.py` (both `CanonicalOwner` validators) plus
`.claude/rules/universal.md` MUST-6 (a `PolicyOwner`). Their `Disposition`
is recorded by REQ-022, not by this REQ; this REQ executes the MODIFY
already adjudicated in Step 0.5 above.

## Data model

No new data model; this REQ changes existing validator behavior
(blocking to advisory) and existing rule text. The relevant "entities" are
code paths and rule text, not new domain objects.

## Integrations

- `scripts/validation/pre_pr_sequence.py` (the caller of both validators;
  no signature change expected, only the return-value semantics for
  scope-explosion, and confirmation that atomic-commit demotion is already
  complete per ADR-100 item 1's delivered status, requiring only the rule
  text and any remaining validator wiring for item 2).
- `lefthook.yml:395` and `:527` (the two `detect_scope_explosion.py`
  invocation sites named in ADR-100 item 3's text).
- Failure modes: none new; this is a behavior *removal* (blocking to
  advisory), which by construction cannot introduce a new failure mode a
  blocking gate did not already have, and removes the `SKIP_SCOPE_CHECK`
  abuse-history failure mode entirely (item 4).

## Failure modes

- **Scenario**: demoting `check_atomic_commit` or `detect_scope_explosion`
  to advisory silently changes their exit codes in a way
  `pre_pr_sequence.py`'s `_Gate` framework misreads as a pass when it
  should be an advisory-with-output. **Category**: technical. **Early
  warning**: `tests/validation/test_pre_pr_sequence_registry.py` or the
  validators' own unit tests fail after the demotion. **Prevention**: AC-05
  requires the existing test suites to be updated to advisory expectations
  as part of this change, not after. **Detection**: CI. **Response**: fix
  the exit-code mapping before merge.
- **Scenario**: item 4 (removing `SKIP_SCOPE_CHECK`) lands before item 3
  (demoting the scope check), briefly leaving a blocking gate with no
  relief valve. **Category**: process. **Prevention**: ADR-100's own text
  requires item 4 after item 3 in the same change; AC-07 encodes this
  ordering as a single combined PR, not two sequential ones. **Detection**:
  code review. **Response**: do not merge item 4 alone.
- **Scenario**: `.claude/rules/universal.md` MUST-6's text reduction drops
  always-on byte count in a way that breaks
  `tests/validation/test_always_on_corpus_claims.py`'s cited figures.
  **Category**: technical. **Prevention**: AC-06 requires running both
  named test files locally before push, per the original seed plan's R3
  risk and mitigation. **Detection**: the test itself. **Response**: update
  the four documents the corpus-claims test names, per ADR-100 item 2's own
  instruction ("refresh the four documents the memory names").

## Security

No new attack surface; this REQ removes a blocking gate and a bypass flag,
narrowing rather than widening what a contributor can silently do
unreviewed. One consideration: removing `SKIP_SCOPE_CHECK` closes a
documented self-attested-approval abuse path (CWE-284-adjacent, improper
access control via an unverified bypass claim); this REQ's AC-04 is itself
the security-relevant acceptance criterion. No threat rated above Low: the
change reduces, not increases, unauthenticated-bypass surface.

## Observability

Lightweight: "what proves this works" is that
`tests/validation/test_always_on_corpus_claims.py` and
`tests/validation/test_audit_procedure_claims.py` pass with updated
advisory-expectation assertions (AC-06), and that a push exceeding the
50-file threshold or the five-file commit guidance completes with an
advisory message rather than a nonzero exit (AC-01, AC-02). No new metric
or alert; this is a one-time behavior change to an existing gate.

## Acceptance Criteria

- [ ] REQ-023-AC1: WHEN a commit exceeds five authored files, THE SYSTEM
      SHALL report advisory guidance and SHALL NOT block the commit, SO
      THAT ADR-100 item 2 is delivered. (`check_atomic_commit`'s CI/pre-push
      enforcement sites are already non-blocking per ADR-100 item 1/ADR-099;
      this AC covers any remaining blocking path plus the rule-text
      reduction below.)
- [ ] REQ-023-AC2: WHEN `.claude/rules/universal.md` MUST-6 is edited, THE
      SYSTEM SHALL reduce its text to reflect advisory-only status SO THAT
      no committed rule still describes atomic-commit as a blocking
      requirement.
- [ ] REQ-023-AC3: WHEN a push exceeds `detect_scope_explosion.py`'s
      50-file `BLOCK_THRESHOLD`, THE SYSTEM SHALL report and SHALL NOT
      exit nonzero for that reason SO THAT ADR-100 item 3 is delivered.
- [ ] REQ-023-AC4: WHEN `_partition_generated` classifies changed paths,
      THE SYSTEM SHALL additionally exclude `.agents/sessions/**`,
      `.agents/qa/**`, and `.agents/memory/episodes/**` as process record
      rather than reviewable change, per ADR-100 item 3's extension
      instruction.
- [ ] REQ-023-AC5: WHEN `SKIP_SCOPE_CHECK` is read anywhere in
      `scripts/detect_scope_explosion.py`, THE SYSTEM SHALL no longer honor
      it (the flag and its handling are removed), AND this removal SHALL
      land in the same PR as AC-03/AC-04, never before them, SO THAT ADR-100
      item 4 lands without a window where the gate blocks with no relief
      (ADR-100's own explicit ordering requirement).
- [ ] REQ-023-AC6: WHEN this REQ's changes land, THE SYSTEM SHALL pass
      `uv run pytest tests/validation/test_always_on_corpus_claims.py
      tests/validation/test_audit_procedure_claims.py -q` with expectations
      updated for the advisory behavior SO THAT the always-on corpus claims
      test suite reflects the new rule text truthfully.
- [ ] REQ-023-AC7: WHEN items 3 and 4 are implemented, THE SYSTEM SHALL
      land them in one combined change SO THAT no intermediate commit
      removes the bypass while the block remains (Failure modes, second
      scenario).
- [ ] REQ-023-AC8: WHEN this REQ's changes land, THE SYSTEM SHALL keep
      ADR-100 item 1's already-delivered status unchanged (no regression to
      `_check_commit_limit`'s advisory-only behavior at
      `git_hook_policy.py:6727` or `enforce_pr_validation.py`'s removed
      bypass-label branch) SO THAT this REQ does not reopen work ADR-099
      already closed.

## Out of Scope

- ADR-100 item 5 (`post_qa_code_changes` rebind churn fix in
  `.claude/lib/qa_report.py`). Recorded by REQ-022 as `DELETE`: the
  specific fix item 5 names (replace `-m` with `-c`) is absent from
  `qa_report.py`, superseded before this cohort started by
  `--first-parent --cc` (issue #5064), a different, more careful fix a
  reviewer's earlier catch on the naive first attempt led to. This item
  needs no mechanical demotion like items 2-4 because there is nothing
  left in the file for that demotion to apply to.
- ADR-100 item 6 (not named in the excerpt this cohort read; out of scope
  by the same "additions, not subtractions, stay with #5241" boundary the
  original seed plan drew for items 5-6).
- Re-litigating ADR-100 items 1's already-delivered status; this REQ
  verifies it is unchanged (AC-08), not re-implements it.

## Deferred

- ADR-100 item 5, as above.
- Any generalized "advisory gate" framework; this REQ demotes two specific
  validators using their existing per-gate mechanisms, not a new shared
  advisory-gate abstraction (Abort-if clause 3; YAGNI, no second consumer
  exists yet).

## Open Questions

- **OQ1**: Does `check_atomic_commit`'s validator module itself still
  contain blocking logic anywhere outside the two CI/pre-push sites ADR-100
  item 1 already closed, or is the remaining work for item 2 entirely the
  rule-text reduction? Owner: implementer at TASK-026 time. Assumption:
  the remaining work is primarily the rule-text reduction and the four
  documents ADR-100 item 2 names for refresh; TASK-026 verifies the
  validator's current blocking status before writing code, since ADR-100's
  own item 1 analysis already found both enforcement sites non-blocking.
- **OQ2**: Which "four documents" does ADR-100 item 2's text mean by "the
  four documents the memory names"? The ADR excerpt this cohort read
  references this without listing them inline. Assumption: TASK-026 reads
  ADR-100 in full (not only lines 246-266) before implementation to resolve
  this citation; if the referenced memory cannot be located, the task
  falls back to `.claude/rules/universal.md`,
  `tests/validation/test_always_on_corpus_claims.py`,
  `tests/validation/test_audit_procedure_claims.py`, and any file those
  tests themselves cite as the figure's source.

## CVA summary

**Commonalities**: both items 2 and 3 follow the identical pattern (a
blocking validator becomes report-only; its rule/config text is trimmed to
match). **Variabilities**: item 2's change is mostly textual (rule
reduction); item 3's change is code plus a config-list extension; item 4 is
pure deletion (a bypass flag with no replacement). **Relationships**: item 4
depends on item 3 landing first in the same change (O5 ordering constraint,
directly from ADR-100's text, not this cohort's invention).

## Buy-vs-build decision

N/A (bug fix / doc / refactor). This REQ implements an already-accepted
architecture decision (ADR-100); it introduces no new capability, tool, or
dependency, so the Step 4a buy-vs-build gate does not apply.

## Complexity classification

Engineering tier: 3 (shared cohort tier for consistency, though this REQ's
individual mechanics are closer to Tier 2 in isolation; kept at 3 because it
shares a `/spec` invocation and review gate with REQ-024/REQ-022 and touches
shared always-on rule text, which the epic treats as governance-sensitive).
Problem domain: Clear (Cynefin), since ADR-100 already specifies the
decision; this REQ applies it rather than deriving it. Methodology:
sense-categorize-respond.

## Rationale

ADR-100 is accepted and unambiguous about items 2-4's content and their
ordering constraint (item 4 after item 3). Delivering them satisfies the
epic's Release gates checklist requirement that no new mechanism land
"unless it removes or consolidates an existing mechanism", by removing
blocking behavior from two gates and one bypass flag outright.

## Dependencies

- `.agents/architecture/ADR-100-retire-pr-size-ceilings.md` (source of
  truth for scope and ordering)
- `.claude/rules/universal.md` (MUST-6 text to reduce)
- `scripts/detect_scope_explosion.py`
- `tests/validation/test_always_on_corpus_claims.py`,
  `tests/validation/test_audit_procedure_claims.py`
- `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md`
