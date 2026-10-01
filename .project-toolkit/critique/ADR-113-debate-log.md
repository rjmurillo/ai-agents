# ADR Debate Log: ADR-113 Promotion Gate Evidence, Artifact Binding, and Governed Exceptions

## Summary

- **Status after review**: proposed, then accepted by owner decision D21 (see Owner decision below). Nothing implemented.
- **Rounds**: 3.
- **Outcome**: no P0 remains. All six seats Accept or Disagree-and-Commit. One P1 raised in round 3 (the finding fingerprint needs a structured items field) is fixed in text.
- **Method note**: the skill names six agents. Two reviewer agents were reused across the change under a two-concurrent-subagent limit, each filling three seats one after the other: architect, critic, and independent-thinker in one; security, analyst, and high-level-advisor in the other. The seats were reviewed separately and each voted separately. The reviewers are not independent of each other's context, so this is a weaker panel than six fresh agents.
- **Claims ledger**: `.project-toolkit/critique/ADR-113-claims-ledger.md`. 15 rows. Row 12 and row 15 are marked not checked in the tree.

## Round 1

| Seat | Key findings | Vote |
|---|---|---|
| architect | P1: no digest field on CheckOutcome, aggregate compares no revisions. P1: no named store for typed results. | Disagree-and-Commit |
| critic | P0: "runs from the base branch" is unimplementable for tag-triggered publish. P1: finding identity, remediated baseline, "artifact-level" undefined. | Block |
| independent-thinker | Approver-differs-from-owner is met by typing another name when CODEOWNERS has one owner. | Disagree-and-Commit |
| security | P1: tag push runs the candidate's workflow file. P1: trust root unnamed. P1: digest TOCTOU. P1: self-approval. | Block |
| analyst | Context omitted workflow_dispatch. D17 cited as fact though unmerged. | Disagree-and-Commit |
| high-level-advisor | Right scope for a proposed record. Plane and trust root are load-bearing. | Disagree-and-Commit |

### Author response

Decisions 2 to 9 rewritten: named result store, two-tier SHA and digest binding, build once and re-verify before publish, default-branch entry workflow with a tag ruleset, CODEOWNER PR review as approval evidence, single-owner interim rule, UTC expiry, workflow_dispatch coverage, D17 reworded as proposed and unmerged.

## Round 2

| Seat | Remaining findings | Vote |
|---|---|---|
| architect | P1: pin the check-run publisher by integration_id. P2: release asset needs a write path. | Disagree-and-Commit |
| critic | P1: "default-branch definitions" ambiguous. P1: entry SHA must descend from the default branch. P1: state-to-finding mapping undefined. | Block |
| independent-thinker | Bind artifacts to run id, event, head SHA read from the API. First promotion waits on a clean tree. | Disagree-and-Commit |
| security | P1: validators run from the PR head's workflow file. | Disagree-and-Commit |
| analyst | No wrong factual claim at P0 or P1. | Accept |
| high-level-advisor | Only the validator-plane gap remains. | Disagree-and-Commit |

### Author response

Decision 5 anchored on push and merge_group runs of a default-branch commit, verified through the workflow-run API, integration_id pinned, ancestry check on the entry SHA, review of workflow edits named as the trust limit. Decision 9 gained the state-to-finding table and the first-promotion note. Open Questions gained the release-asset store.

## Round 3

| Seat | Remaining findings | Vote |
|---|---|---|
| architect | None | Accept |
| critic | P1: the fingerprint has no per-item identity in CheckOutcome | Disagree-and-Commit |
| independent-thinker | None | Accept |
| security | None at P0 or P1. P2: single CODEOWNER makes workflow review thin. | Accept |
| analyst | None | Accept |
| high-level-advisor | None | Accept |

### Author response

Decision 6 and the Impact table now require a structured `items` field, and say per-item exceptions wait until it exists. The integration pin is described as weaker than the ADR-101 Phase 0 publishing App.

## Dissent recorded

- critic (Disagree-and-Commit): the fingerprint depends on new schema. Fixed in text, unproven until implementation.
- security P2: with one CODEOWNER and possible admin bypass, review of workflow edits is thin today. The ADR's advisory-until-prerequisites clause covers it.

## Strategic checks

- Chesterton's Fence: N/A. No existing structure is removed.
- Path dependence: the SHA and digest binding and the default-branch entry point are hard to reverse once release tooling depends on them. Signed attestations stay open as option C.
- Core versus context: release gating is context. The design reuses evidence.py rather than adding a vocabulary.
- Second-system: scope is bounded to the epic's five requirements, and decision 10 allows splitting.

**Overall strategic assessment**: APPROVED for status proposed. Acceptance waits on the Open Questions.

## Owner decision

- **Decision**: D21, rjmurillo, 2026-09-30. Verdict: ACCEPT ADR-113 with solo-maintainer defaults. This is an owner decision, not a fourth debate round. No reviewer seat re-voted. The six-seat position above stands (APPROVED for status proposed, acceptance waiting on the Open Questions).
- **Participants**: rjmurillo (decision-maker). The agents that voted in rounds 1 to 3 were not re-run.
- **Answers recorded in the ADR**: (1) no second approving identity, so decision 7 allows no exceptions, and a second identity re-opens it; (2) a read-only ruleset probe found a branch-target ruleset on this repository and the tag target is part of the same ruleset feature, so the owner creates the `v*` tag ruleset and this change does not; (3) a GitHub Release stores the previous manifest through a narrowly scoped `contents: write` release job.
- **Claims ledger**: row 12 is now checked in the tree. #6085 merged the D17 allowlist. Row 15 is unchanged.
