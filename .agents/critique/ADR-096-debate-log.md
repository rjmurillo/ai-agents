# ADR-096 Debate Log

**Subject**: `.agents/architecture/ADR-096-relax-qa-evidence-commit-equality.md`, addressing issue #5164.

**Round**: 1 of up to 10 (per adr-review debate protocol).

**Participants**: architect, critic, independent-thinker, security, analyst, high-level-advisor.

**Round 1 tally**: 6 ACCEPT-WITH-CHANGES, 0 ACCEPT, 0 BLOCK.

## The single most convergent finding: a fail-open regression on the dominant call path

Five of six agents (architect, critic, independent-thinker, security, analyst) independently found the same P0: `scripts/validate_session_json.py:976-977` returns early, with no staleness check at all, whenever `validation_head is None`. Today that is safe because `validate_qa_report()`'s equality raise (the check this ADR proposes deleting) still runs unconditionally beforehand. After the proposed change, that early return means **no check runs on that path at all**.

Security traced this to `validation_head` only auto-resolving to live `HEAD` when `not existing_log and not args.creation_mode` (`:1651-1653`), and characterized `--existing-log` as the path every real committed-log caller uses (`git_hook_policy.py:1966`, `:7060-7066`; `checks_tooling.py:86-87`).

**Post-round-1 correction, made during implementation.** That characterization overstates the reachable severity: `validate_session_log()` gates the call to `validate_qa_report_evidence()` behind `not existing_log and not creation_mode` one level up (`scripts/validate_session_json.py:1169,1178`), so `--existing-log` never reaches this function at all, by design (a deliberate record-vs-compliance-claim split, issue #3385). None of the five agents who raised this as convergent traced the call one level further up before characterizing its reach. The gap was still real: it fires on the *fresh* validation path whenever live-`HEAD` resolution fails for any reason, which is a narrower but still genuine case worth closing.

This is fixed in the revision below by requiring a head at the point `validate_qa_report` performs staleness checking, with a well-defined fallback (the session's own resolved `QaBinding.commit`, already computed at both call sites) rather than an optional parameter a caller can omit.

## Other convergent findings

- **The round-15 citation is wrong** (critic, architect independently verified against `.agents/sessions/2026-08-15-session-14706-b47f72afe-continue-4954-autofix-work-rounds.json:219`). Round 15 names `session_qa_binding()`'s `endingCommit`/`comparison.head` equality (`qa_report.py:170-178`) as the fix needed, not `validate_qa_report()`'s equality (`qa_report.py:193-197`, the one this ADR removes). Independent-thinker separately measured that this specific gap is not empirically firing in the available (shallow, 50-commit) history, so it is not re-scoped into this ADR, but the citation and the residual must both be named accurately.
- **`complete_session_log.py` already has the value the ADR's Implementation Notes says needs a new `git rev-parse HEAD` call** (critic, architect, analyst). `_get_ending_commit()` runs at `complete_session_log.py:815`, before the QA-evidence block, and the resulting `ending_commit` is already threaded into `QaBinding(commit=ending_commit)` at line 891. The "new I/O, new failure mode" cost claims (Implementation Notes step 3, the Alternatives Cons column, Negative consequence 1) are all incorrect and are corrected below.
- **Catch-up merges are cited as motivating evidence but are not fixed** (independent-thinker, architect). `post_qa_code_changes` walks `git log -m`, diffing a merge against both parents, so a catch-up merge from `main` still reports every path `main` touched as non-evidence and still forces a rebind. Security independently confirmed `-m` is the *correct* choice for the security question (it fails closed, never under-reports), so this is named as an accepted, unfixed residual, not a design defect.
- **Rebase still forces a rebind, with a worse error message than today's** (independent-thinker, security). `post_qa_code_changes` raises a generic ancestry error, naming neither SHA, versus today's equality message which names both.
- **The contract-narrowing footgun is real and self-referential**: `complete_session_log.py:547` is already the instance of a caller that validated identity and forgot staleness, under the *current, stricter* contract. Narrowing `validate_qa_report()`'s contract further while keeping its name (critic P1-1, architect P1-1, independent-thinker P1-5) makes the same mistake cheaper to repeat. All three independently proposed folding staleness into the one call rather than trusting callers to pair two.
- **The referenced "acceptance criteria below" section does not exist in the document** (critic). Added below.
- **`QA_EVIDENCE_PREFIXES` has boundary problems the ADR does not examine**: it covers agent-instruction prose, not just data (security P1-1, memory-poisoning-adjacent risk on `.agents/sessions/handoffs/*.md` and the 2180-file episode store); `.agents/qa/` is inside its own allowlist so a report can rewrite its own verdict (security P1-2); `AI_AGENTS_ARTIFACT_ROOT` can desync the containment check from the hardcoded prefixes (security P1-3); a second, disagreeing definition of "bookkeeping path" already exists in `git_hook_policy.py`'s `GENERATED_PATHS`/`GENERATED_GLOBS` (independent-thinker P1-2). None of these are reachable in the measured history (independent-thinker: 0/50 commits), so they are named as an explicit, separate residual and follow-up rather than folded into this already-large change.
- **Benefit sizing predates the #5125/#5135 mandatory-gate retirement** (high-level-advisor, independent-thinker). Independent-thinker found only 1/50 recent commits has the exact shape this ADR fixes, while high-level-advisor found 12 QA reports were still authored in the 3 days after the retirements, arguing the opt-in path remains standard practice. Both points are kept: the fix is still worth shipping (traffic continues), but the headline pre-retirement counts should not be read as the current rate.
- **The `git log --all | grep -i rebind` evidence command returns 0 on a shallow clone** (high-level-advisor, independent-thinker independently). Not fabrication (the handoff's 23-occurrence count is independently confirmed by grep against a real file), but the command needs a ref/clone-depth annotation so a reader on a shallow checkout does not conclude the claim is false.

## Findings specific to one agent, folded in as noted

- Security: no subprocess `timeout=` on the two `post_qa_code_changes` git calls (add `timeout=10`, matching `_resolve_full_commit`'s existing pattern); shallow-clone ancestry failure needs naming in Negative consequences; ADR line originally overstating the equality check as "the real protection" against a dishonest actor is corrected (the gate is self-attested and catches carelessness, not adversarial reuse).
- Analyst: corrected the "tested indirectly via its one call site" claim; `post_qa_code_changes` has direct unit coverage at `tests/test_validate_session_json.py:399-505`.
- Architect: MUST-13 (`ci-scripts.md`) applies to the new gate this ADR adds at `complete_session_log.py`; the corpus-wide demonstration must be quoted in the implementing PR, not just described.
- High-level-advisor: recommends re-scoring the issue from P2 to P1 given ongoing traffic; recommends cutting the self-referential "highest-ROI" framing. Both are editorial/issue-tracker actions rather than design changes; the framing is cut below, and the priority recommendation is noted for the issue, not enforced by the ADR text itself.

## Resolution (Phase 3)

Given universal convergence on the same core defect (the `validation_head is None` fail-open) and largely overlapping secondary findings across all six reviewers, the ADR is being rewritten in place rather than iterating through a second full round. Applied changes:

1. `validate_qa_report()` is redesigned to require an explicit `head` for staleness (no longer an optional caller-supplied `validation_head` that can silently be `None`); both call sites are required to compute one, falling back to the session's own resolved `QaBinding.commit` when no stricter live-HEAD value is available. This closes the P0 finding structurally rather than by convention, and folds staleness detection into the identity-check call so no future caller can validate identity while forgetting staleness (closing the contract-narrowing footgun raised by critic, architect, and independent-thinker together).
2. Corrected the round-15 citation to `session_qa_binding()`, with that function's own equality explicitly named as out of scope and its residual stated.
3. Corrected the `complete_session_log.py` cost claims: no new git call, `ending_commit` is already in scope.
4. Named catch-up merges and rebase as accepted, unfixed residuals.
5. Added the missing Acceptance Criteria section.
6. Named the `QA_EVIDENCE_PREFIXES` boundary issues as an explicit, separate follow-up rather than in scope here.
7. Recalibrated the benefit framing to acknowledge post-retirement traffic continues without leaning on pre-retirement counts as the current rate; annotated the shallow-clone evidence command; cut the "highest-ROI" superlative.
8. Added `timeout=10` to the implementation requirements for both `post_qa_code_changes` git calls.

## Outcome

**Consensus reached at Phase 3 resolution.** The rewritten ADR (same change that adds this log) is considered implementation-ready. Reopen this log with a Round 2 entry if a reviewer finds the rewrite does not address their finding.

## Round 2 (post-implementation finding, AI spec validator on PR #5167)

The ADR's Decision and Acceptance Criteria sections (paragraphs after the "Post-round-1 correction" note in Decision) asserted that the code-change-aware staleness check runs on `scripts/validate_session_json.py`'s `--existing-log` path: "the `--existing-log` path where `validation_head` resolves to `None` today" gets `binding.commit` as a fallback `head`, and acceptance criteria claimed a QA report passes or fails "including `validate_session_json.py`'s `--existing-log` path."

That contradicts the ADR's own correction note two paragraphs earlier, which states accurately that `validate_session_log()` gates the entire QA-evidence block behind `not existing_log and not creation_mode` one level up, so `--existing-log` never reaches `validate_qa_report_evidence()` at all. The implementation matches the correction note, not the later Decision/Acceptance-Criteria prose: `tests/test_validate_session_json.py::test_existing_log_ignores_explicit_validation_head` passes an explicit `--validation-head` that would fail the check and asserts `post_qa_code_changes.assert_not_called()`, proving the call never happens on that path regardless of what `head` would resolve to.

No agent in round 1 caught this internal contradiction; the correction note was added during implementation, after the round-1 debate concluded, and nothing re-checked the Decision/Acceptance-Criteria prose against it. This is a documentation-only defect: no code changed, since the implementation was already correct. Fixed by rewording the Decision and Acceptance Criteria to state `--existing-log` is out of scope for this ADR (the check applies only to the fresh-validation path, `not existing_log and not creation_mode`), matching what the correction note and the tests already establish.

No further disagreement is open; this is a mechanical correction of a documentation defect the debate did not catch, not a reopened design question.

## Round 3 (post-implementation finding, AI spec validator on PR #5167)

The ADR's frontmatter `status` field remained `proposed` through two pushed PR heads, despite Round 1 reaching 6/6 ACCEPT-WITH-CHANGES with this debate log recorded and the ADR's own "## Status" prose already asserting "no code lands until this ADR is accepted." The `adr-review` skill's own verification checklist requires debate-log evidence to accompany an accepted-transition; that evidence existed (this file), but the frontmatter transition itself was never made. This is a status-tracking oversight, not a reopened design question: the consensus this log already recorded stands. Corrected by setting `status: accepted` in the ADR frontmatter and updating the "## Status" prose to match, in the same change as this entry.
