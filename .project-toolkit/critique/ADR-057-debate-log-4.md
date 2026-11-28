# ADR Debate Log 4: ADR-057 Amendment 2026-11-28, plugin eval migration

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-057-debate-log-3.md`
- **Outcome**: Consensus (4 Accept, 2 Disagree-and-Commit; ADR-057 architect vote Accept, ADR-087 architect vote Disagree-and-Commit)
- **Final Status**: accepted (unchanged; consensus covers the amendment only)
- **Panel**: full six-seat panel, covering the coupled amendments and pointer.
- **Claims ledger**: `.project-toolkit/critique/ADR-057-claims-ledger.md`, Amendment 2026-11-28 section.
- **Date**: 2026-11-28

## Round 1

| Seat | Vote |
|---|---|
| Architect | Block |
| Critic | Block |
| Independent-thinker | Block |
| Security | Block |
| Analyst | Disagree-and-Commit |
| High-level-advisor | Block |

The panel raised inconsistent score bases, insufficient scored runs, the security tier designation and minimum, comparison scope, frozen baseline, selection-budget accounting, budget namespaces, noise-floor statistics, partial pass accounting, stage ceilings, and missing evidence identities. The draft was revised to address these findings. Spec item 6 records the changed rules. The revised text is not yet a consensus verdict.

## Round 2

| Seat | Vote | Evidence and remaining concern |
|---|---|---|
| Architect | Accept for ADR-057; Disagree-and-Commit for ADR-087 | Membership budget and stage reservations resolved. Reconcile preflight and returned-result identity checks with consultation charging. |
| Critic | Block | Distinguish preflight from returned-result checks, reject reservations above remaining stage allocation, and classify baseline refusals. Aggregate identities and distinct scoring bases accepted. |
| Independent-thinker | Accept | Small-sample floor and consultation scope resolved. PR B must test insufficient pairs. |
| Security | Accept | Security tier and deterministic grader minimum resolved; attestation and same-user limits disclosed. Implementation verification remains required. |
| Analyst | Disagree-and-Commit | Freeze gated-case membership before scores are observed; enforce remaining stage allocation before launch. Scope, consumer enumeration and sel minimum resolved. |
| High-level-advisor | Block | Match scoring units for floor, gain and probe; require explicit Stage 0 affordability decision. |

## Round 3

Resolved all remaining blockers: preflight identity mismatches refuse before charging, returned-result mismatches refuse without refund, reservations check remaining stage and total balances, refusals fail both arms, expected grader definitions freeze the gated set, the floor and gain share a deterministic basis, matched probe subsets have their own floor, and Stage 0 requires an affordability decision before further spend.

| Seat | Final position |
|---|---|
| Architect | Round 2 Accept on ADR-057, Disagree-and-Commit on ADR-087; condition addressed in round 3 |
| Critic | Accept, reassessed all three blockers against revised text |
| Independent-thinker | Round 2 Accept, no remaining blocker |
| Security | Round 2 Accept, no remaining blocker |
| Analyst | Round 2 Disagree-and-Commit, both reservations addressed in round 3 |
| High-level-advisor | Accept, reassessed both blockers against revised text |

Consensus uses the round 2 non-blocking votes, carried forward, and the two round 3 rechecks. It is not a fresh six-seat round 3 review. ADR-087 remains proposed because the original Open Requirements are outside this review. ADR-127 keeps its frontmatter unchanged per owner D1; the pointer follows the accepted amendment and changes no executable enforcement.

Implementation owners: PR B owns accounting, scoring and trust conformance tests; PR C1 owns the gate, receipt verification, trace exclusions and consumer migration; PR C2 owns frozen manifest, reviewed spend allocation and baseline/hillclimb execution. The proposed ADR-087's isolation and ledger custody limits remain open. No paid eval pass ran in PR A.

## Post-consensus edit, 2026-11-28 (non-frontmatter, logged per AGENTS.md)

Editor: workstream owner, after the parent session's review of PR #7888. This is a wording change only; no gate, number, or rule changed, so the consensus above stands.

- Amendment 2026-11-28, opening paragraph: "the 8 most used skills" became "8 skills the owner selects in PR C2 ... selection is a PR C2 input and outside this amendment". Reason: the coordinator for the related threads ruled that this ADR change must not take on skill portfolio choices, and the selection input (organic usage against eval activity, capability form, JTBD ownership, shipping constraints) belongs to PR C2.
- Review threads on PR #7888 (Devin, 2026-11-28) found two gaps in item 6. (1) The prompt-surface hash covers only `SKILL.md` and `references/` (`scripts/validation/skill_rewrite_skills.py`, `SkillSide.surface`), but a plugin eval session runs the skill's scripts, so a script edit left the receipt fresh. Item 6 now adds `skill_tree_sha256` over every tracked file in the skill directory, and the floor and probe freshness key includes it. (2) Item 6 replaced ADR-127 decision 9 without carrying its first-run rule. Item 6 now states it: the first whole-corpus candidate pass sets the verdict, later passes are diagnostic, a skill edit starts a new first pass, three first passes then the owner decides. Both restore semantics the amendment already claimed to carry over; neither adds a gate.
