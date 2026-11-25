# ADR Debate Log 5: ADR-127 Amendment 2026-11-25, Decision 9 Check Lands

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-127-debate-log-4.md`
- **Outcome**: Consensus (2 Accept)
- **Final Status**: accepted. The record's status is unchanged. This debate covers one amendment.
- **Panel**: reduced, architect and critic. The edit records an owner ruling and refreshes stale text. It changes no executable enforcement. The check it describes was reviewed in `ADR-057-debate-log-2.md`.
- **Claims ledger**: `.project-toolkit/critique/ADR-127-claims-ledger.md`, rows 56 to 61 added, row 52 superseded.
- **Scope**: ADR-127 decisions 7 and 9, Consequences, Impact, Implementation Notes, Related Decisions, and a new Amendment section. One line of ADR-057 Amendment 2026-11-25 item 5.
- **Date**: 2026-11-25

## Exit gates before review

| Gate | Result |
|---|---|
| Claims ledger | VERIFIED. Rows 56 to 61 cover the script path, the CI job, the identity block, the floor recompute, the new-skill rule, and the owner ruling. |
| Documentation accuracy (`doc-accuracy` Phase 4) | NOT RUN. Each new claim has a ledger row backed by a direct file read. |
| Self-consistency | VERIFIED. The new-skill rule agrees with decisions 9, 12, and 13 and with the Neutral consequences. |
| Refuting seat (analyst, haiku) | Rows 56 and 57 CONFIRMED. Two FALSE findings were wrong: `TestFloors` exists at `tests/validation/test_skill_rewrite_evidence.py:278`, and line 1152 is the output key while 1134 is the call. Both rows now cite both lines. Row 61 UNAVAILABLE to the seat: the ruling is the owner's answer in the #7589 session. |

## Round 1 Summary

### Key Issues Addressed

- Architect P1: decision 9 still said the pilot may merge on reviewer enforcement. The check now lands first, so the check enforces the pilot.
- Architect P1: this log did not exist yet. Written now and staged with the ADR.
- Critic P1: a rename split into a delete PR and a later add PR skips the gate.
- Critic P1: any deletion in a PR gates every new skill in it.
- Critic P1: the check does not verify the `--renamed-from` predecessor.
- Critic P1: Consequences did not say a new driver ships with no eval floor.

### Major Changes Made

- Decision 7 names the deleted-skill rule, the over-gate, the unverified predecessor, and the split rename. The reviewer owns the last two.
- The "four triggers cover every rewrite" line now names the split-rename exception.
- Negative consequences gain "A brand-new driver ships with no eval floor."
- Decision 9 says the check landed before the pilot and enforces it.
- "Issue #7589 lands" now reads "the PR for issue #7589 lands".
- Ledger row 52 is marked SUPERSEDED by row 58.

### Rejected

- The critic's "90 days" rule for a copied surface. Nothing records deletion dates, so the number would be an unenforced invention. The text assigns the case to the reviewer instead.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept, with two P1 text fixes |
| critic | Disagree-and-Commit until the rename loopholes are written down |

## Round 2 Summary

### Key Issues Addressed

- Each round 1 fix checked against the revised diff.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. The text matches `_gate_or_skip`, and the gaps the check cannot detect are assigned to the reviewer. |
| critic | Accept. No P0 or P1 remains. No `shape: driver` skill and no pilot commit exist, so "landed before the pilot" holds. |

### Next Steps

- Richard ratifies the amendment at merge of the #7589 PR.
- ADR-057 Amendment 2026-11-25 item 5 now says the owner confirmed the reading. This log reviews that line, so it covers ADR-057 for the commit gate.

## Recommendations to the owner

- Merge the #7589 PR only after reading decision 7's new-skill paragraph. Your merge is the ratification.
