# SESSION-PROTOCOL Debate Log: Commit Count Guidance

## Summary

- **Rounds**: 3
- **Outcome**: Consensus
- **Final Status**: accepted
- **Trigger**: `.agents/SESSION-PROTOCOL.md` changed
- **Tracked dissent**: Issue #3997 covers CI and pre-push merge detection

## Ground Truth

`scripts/validation/pr_commit_count.py` defines the live classifier:

| Count | Status |
|-------|--------|
| 0-9 | OK |
| 10-14 | WARNING |
| 15 through active limit | ALERT |
| Above active limit | BLOCKED |

The default active limit is 20. Validation may grant 40 after its base-merge
check. Equality is allowed. Counts 20 and 40 remain ALERT.

## Round 1 Summary

### Key Issues Addressed

- Protocol bands contradicted the enforcing classifier.
- Protocol attributed the commit limit to ADR-008.
- Live guidance rewrote historical PR #908 evidence.
- CI and pre-push used different base-merge predicates.

### Major Changes Made

- Parameterized the table around the active limit.
- Made the blocking condition strictly above the active limit.
- Named `scripts/validation/pr_commit_count.py` as threshold authority.
- Restored the PR #908 incident wording.
- Filed issue #3997 for predicate alignment.

## Round 2 Summary

### Key Issues Addressed

- "Limit reached" still implied equality was blocked.
- Phase 2.7 still implied `pre_pr.py` checked commit count.
- The rationale repeated that false enforcement claim.
- A canonical pointer led to incomplete threshold guidance.

### Major Changes Made

- Changed the stop rule to exceeding the active limit.
- Pointed the checklist to Session Mid monitoring.
- Removed commit count from the `pre_pr.py` claims and rationale.
- Removed the incomplete canonical-policy pointer.
- Told agents to plan against 20 and treat 40 as validation-granted relief.

## Round 3 Summary

### Agent Positions

| Agent | Position | Dissent or Reservation |
|-------|----------|------------------------|
| architect | Accept | Preferred more definition around the 40-limit check. |
| critic | Accept | No remaining P0 or P1 finding. |
| independent-thinker | Disagree-and-Commit | Preferred synchronizing broader constraints prose. |
| security | Accept | No security or governance blocker. |
| analyst | Accept | Noted an ambiguous threshold shorthand in a module docstring. |
| high-level-advisor | Disagree-and-Commit | Preferred a follow-up for broader constraints prose. |

### Consensus

All six roles voted Accept or Disagree-and-Commit. No role voted Block.
The broader constraints text remains conservative at 20, which matches the
protocol's planning limit. Issue #3997 owns the verified enforcement predicate
difference. Neither reservation blocks this scoped correction.

## Strategic Review

- **Chesterton's Fence**: PASS. PR #908 history was restored, not rewritten.
- **Path Dependence**: PASS. This documentation change is reversible.
- **Core vs Context**: N/A. This corrects repository governance.
- **Second-System Effect**: PASS. The change reuses the enforcing classifier.
- **Overall Strategic Assessment**: APPROVED

## Verification

- 74 targeted commit-count tests passed.
- Session log validation passed.
- `git diff --check` passed.
